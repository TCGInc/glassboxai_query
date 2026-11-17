#!/usr/bin/env bash
# Deploy the Glass Box stack to AWS: one EC2 instance running the same Docker Compose stack as a
# laptop, with LibreChat and JupyterLab on public HTTPS URLs. See docs/aws-deployment.md.
#
# Usage: ./deploy/aws.sh <command>
#   up        create or update the AWS resources, then deploy the current commit
#   status    show the instance and check both sites
#   logs [s]  last 200 log lines of the stack, or of one service (librechat, jupyter, ...)
#   test      run the fast test suite (pytest -m "not agent") on the instance
#   shell     open a shell on the instance (needs the Session Manager plugin)
#   stop      stop the instance to save money (data, IP address and URLs are kept)
#   start     start it again
#   destroy   delete everything, including chats and users
#             (asks for the stack name; or pass it: destroy --confirm <stack-name>)
#
# Settings come from .env (DEPLOY_* and the app's own keys); see .env.example.
# Every run ends with SUCCESS or FAILURE (and the exit code to match).
set -euo pipefail
cd "$(dirname "$0")/.."

TEMPLATE=deploy/aws/template.yaml
UBUNTU_AMI_PARAM=/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id
# The .env keys the instance gets (everything else in .env stays on this machine)
SECRET_KEYS=(OPENAI_API_KEY GEMINI_API_KEY LLM_MODEL_ID LLM_REASONING_EFFORT
  POSTGRES_PASSWORD POSTGRES_DB POSTGRES_USER AGENT_RO_USER AGENT_RO_PASSWORD
  JUPYTER_TOKEN ADMIN_EMAIL ADMIN_PASSWORD)
HEALTH_TIMEOUT=300 # seconds to wait for HTTPS (Let's Encrypt issues the certificates)

# --- Result reporting: every run ends with the URLs and SUCCESS or FAILURE -----------------

current_step="starting"
command_name="${1:-}"
librechat_url="" jupyter_url="" healthy=0

step() {
  current_step="$1"
  echo "==> $1"
}

finish() {
  local rc=$?
  echo
  if [[ "$command_name" != "destroy" && -n "$librechat_url" ]]; then
    echo "LibreChat:  ${librechat_url}"
    if ((rc == 0 && healthy)); then
      echo "JupyterLab: ${jupyter_url}/lab   (token: JUPYTER_TOKEN in .env)"
    fi
  fi
  if ((rc == 0)); then
    echo "SUCCESS"
  else
    echo "FAILURE: ${current_step}"
  fi
}
trap finish EXIT

die() {
  echo "Error: $*" >&2
  exit 1
}

# --- Settings ------------------------------------------------------------------------------

# Read KEY from .env without executing it; the last assignment wins, quotes are stripped.
env_get() {
  local line value
  line="$(grep -E "^[[:space:]]*$1=" .env 2>/dev/null | tail -n 1 || true)"
  value="${line#*=}"
  value="${value%$'\r'}"
  [[ "$value" =~ ^\"(.*)\"$ || "$value" =~ ^\'(.*)\'$ ]] && value="${BASH_REMATCH[1]}"
  printf '%s' "$value"
}

load_settings() {
  step "reading settings from .env"
  [[ -f .env ]] || die "missing .env; run 'cp .env.example .env' and fill it in"
  command -v aws >/dev/null || die "the AWS CLI is not installed"
  command -v curl >/dev/null || die "curl is not installed"

  STACK="$(env_get DEPLOY_STACK_NAME)"
  STACK="${STACK:-glassbox-fda}"
  [[ "$STACK" =~ ^[A-Za-z][A-Za-z0-9-]{0,62}$ ]] || die "DEPLOY_STACK_NAME must be letters, digits and dashes"
  REGION="$(env_get DEPLOY_REGION)"
  REGION="${REGION:-$(aws configure get region || true)}"
  [[ -n "$REGION" ]] || die "set DEPLOY_REGION in .env (or a default region in the AWS CLI)"
  export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""
  SSM_PATH="/glassbox/${STACK}"
  DOMAIN_SETTING="$(env_get DEPLOY_DOMAIN_NAME)"
  HOSTED_ZONE_ID="$(env_get DEPLOY_HOSTED_ZONE_ID)"
  INSTANCE_TYPE="$(env_get DEPLOY_INSTANCE_TYPE)"
  INSTANCE_TYPE="${INSTANCE_TYPE:-t3.large}"
  ALLOWED_CIDR="$(env_get DEPLOY_ALLOWED_CIDR)"
  ALLOWED_CIDR="${ALLOWED_CIDR:-0.0.0.0/0}"
  JUPYTER_CIDRS="$(env_get DEPLOY_JUPYTER_ALLOWED_CIDRS)"
  JUPYTER_CIDRS="${JUPYTER_CIDRS:-$ALLOWED_CIDR}"
  JUPYTER_CIDRS="${JUPYTER_CIDRS// /}"
  local cidr='[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}'
  [[ "$ALLOWED_CIDR" =~ ^${cidr}$ ]] || die "DEPLOY_ALLOWED_CIDR must look like 203.0.113.0/24"
  [[ "$JUPYTER_CIDRS" =~ ^${cidr}(,${cidr})*$ ]] || die "DEPLOY_JUPYTER_ALLOWED_CIDRS must be comma-separated CIDRs"
  [[ -z "$DOMAIN_SETTING" || "$DOMAIN_SETTING" =~ ^[a-z0-9.-]+$ ]] || die "DEPLOY_DOMAIN_NAME must be a lowercase host name"

  step "checking AWS credentials"
  aws sts get-caller-identity --query Account --output text >/dev/null ||
    die "the AWS CLI has no working credentials (try 'aws configure' or 'aws sso login')"
  set_urls # best effort: known when the stack exists or a domain is set
}

# --- Stack helpers -------------------------------------------------------------------------

stack_status() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE
}

stack_output() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

# The URLs: a real domain if configured, otherwise <ip-with-dashes>.sslip.io
set_urls() {
  local domain="$DOMAIN_SETTING" ip
  if [[ -z "$domain" ]]; then
    ip="$(stack_output PublicIp 2>/dev/null || true)"
    [[ "$ip" =~ ^[0-9.]+$ ]] || return 0
    domain="${ip//./-}.sslip.io"
  fi
  DOMAIN="$domain"
  JUPYTER_DOMAIN="jupyter.${domain}"
  librechat_url="https://${DOMAIN}"
  jupyter_url="https://${JUPYTER_DOMAIN}"
}

require_stack() {
  step "finding stack ${STACK} in ${REGION}"
  [[ "$(stack_status)" != NONE ]] || die "stack ${STACK} does not exist in ${REGION}; run './deploy/aws.sh up'"
  INSTANCE_ID="$(stack_output InstanceId)"
  set_urls
}

# --- Remote commands (SSM Run Command) -----------------------------------------------------

# A JSON string literal: backslashes and double quotes escaped (the lines have no newlines)
json_str() {
  printf '"%s"' "$(printf '%s' "$1" | sed 's/[\\"]/\\&/g')"
}

wait_for_ssm() {
  step "waiting for the instance in SSM"
  local deadline=$((SECONDS + 600)) ping
  while ((SECONDS < deadline)); do
    ping="$(aws ssm describe-instance-information \
      --filters "Key=InstanceIds,Values=${INSTANCE_ID}" \
      --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || true)"
    [[ "$ping" == Online ]] && return 0
    sleep 10
  done
  die "instance ${INSTANCE_ID} did not register with SSM within 10 minutes"
}

# remote_run <timeout-seconds> <shell line>...  Runs the lines on the instance as root and
# prints their output. Fails unless the command finishes with status Success.
remote_run() {
  local timeout="$1" params cmd_id status="Pending" lines="" line started=$SECONDS reported=$SECONDS
  shift
  for line in "$@"; do lines+="${lines:+,}$(json_str "$line")"; done
  params="{\"commands\":[${lines}],\"executionTimeout\":[\"${timeout}\"]}"
  cmd_id="$(aws ssm send-command --instance-ids "$INSTANCE_ID" \
    --document-name AWS-RunShellScript --comment "glassbox ${command_name}" \
    --timeout-seconds 600 --parameters "$params" --query Command.CommandId --output text)"
  while [[ "$status" =~ ^(Pending|InProgress|Delayed)$ ]]; do
    sleep 10
    status="$(aws ssm get-command-invocation --command-id "$cmd_id" --instance-id "$INSTANCE_ID" \
      --query Status --output text 2>/dev/null || echo Pending)"
    if ((SECONDS - reported >= 60)); then
      reported=$SECONDS
      echo "    ... still running ($(((SECONDS - started) / 60)) min)"
    fi
  done
  aws ssm get-command-invocation --command-id "$cmd_id" --instance-id "$INSTANCE_ID" \
    --query '[StandardOutputContent,StandardErrorContent]' --output text | sed 's/^/    /'
  [[ "$status" == Success ]] || die "remote command ended with status ${status} (full log on the instance: /var/log/glassbox-deploy.log)"
}

# --- Health checks -------------------------------------------------------------------------

check_sites() {
  step "waiting for HTTPS at ${librechat_url} and ${jupyter_url}"
  local deadline=$((SECONDS + ${1:-$HEALTH_TIMEOUT})) body code
  while :; do
    body="$(curl -fsS --max-time 10 "${librechat_url}/health" 2>/dev/null || true)"
    code="$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "${jupyter_url}/api" 2>/dev/null || true)"
    if [[ "$body" == OK && ("$code" == 200 || "$code" == 403) ]]; then
      # 403 is Caddy's allow-list: the site and its certificate work, but not for this machine
      [[ "$code" == 403 ]] && echo "    note: JupyterLab answered 403; this machine's IP is not in DEPLOY_JUPYTER_ALLOWED_CIDRS"
      healthy=1
      return 0
    fi
    ((SECONDS < deadline)) || break
    sleep 10
  done
  die "the sites did not answer over HTTPS (LibreChat: '${body:-no answer}', JupyterLab HTTP ${code:-none})"
}

# --- Commands ------------------------------------------------------------------------------

preflight_app_settings() {
  step "checking the app settings in .env"
  local value
  [[ -n "$(env_get OPENAI_API_KEY)" ]] || die "OPENAI_API_KEY is empty in .env"
  value="$(env_get ADMIN_PASSWORD)"
  [[ -n "$value" && "$value" != glassbox && ${#value} -ge 12 ]] ||
    die "set ADMIN_PASSWORD in .env to 12+ characters (not the default): the site is public"
  for key in POSTGRES_PASSWORD AGENT_RO_PASSWORD; do
    value="$(env_get "$key")"
    [[ -n "$value" && ! "$value" =~ ^change-me ]] || die "set a real ${key} in .env"
  done
  value="$(env_get JUPYTER_TOKEN)"
  [[ ${#value} -ge 32 && ! "$value" =~ ^change-me ]] ||
    die "JUPYTER_TOKEN must be 32+ random characters, it guards a public JupyterLab (try: openssl rand -hex 24)"
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "    warning: uncommitted changes are not deployed; deploying commit $(git rev-parse --short HEAD)"
  fi
}

put_secrets() {
  step "storing secrets in SSM Parameter Store (${SSM_PATH})"
  local key value
  for key in "${SECRET_KEYS[@]}"; do
    value="$(env_get "$key")"
    if [[ -n "$value" ]]; then
      # Read from stdin, so the value never appears in a process list
      printf '%s' "$value" | aws ssm put-parameter --name "${SSM_PATH}/${key}" \
        --type SecureString --overwrite --value file:///dev/stdin >/dev/null
    else
      aws ssm delete-parameter --name "${SSM_PATH}/${key}" >/dev/null 2>&1 || true
    fi
  done
  # LibreChat's encryption and session secrets: created once, never changed (changing them
  # logs everyone out and breaks stored encrypted values).
  for spec in CREDS_KEY:32 CREDS_IV:16 JWT_SECRET:32 JWT_REFRESH_SECRET:32; do
    key="LIBRECHAT_${spec%%:*}"
    if ! aws ssm get-parameter --name "${SSM_PATH}/${key}" >/dev/null 2>&1; then
      head -c "${spec##*:}" /dev/urandom | od -An -vtx1 | tr -d ' \n' |
        aws ssm put-parameter --name "${SSM_PATH}/${key}" --type SecureString \
          --value file:///dev/stdin >/dev/null
    fi
  done
}

deploy_stack() {
  local status overrides
  status="$(stack_status)"
  case "$status" in
    NONE) ;;
    ROLLBACK_COMPLETE | ROLLBACK_FAILED | DELETE_FAILED)
      die "stack ${STACK} is in ${status} (a failed first create); run './deploy/aws.sh destroy', then 'up'" ;;
    *_IN_PROGRESS) die "stack ${STACK} is busy (${status}); wait for it to finish and rerun" ;;
  esac
  overrides=(InstanceType="$INSTANCE_TYPE" AllowedCidr="$ALLOWED_CIDR"
    DomainName="$DOMAIN_SETTING" HostedZoneId="$HOSTED_ZONE_ID")
  if [[ "$status" == NONE ]]; then
    # The image is chosen once. Re-resolving it on updates would replace the instance (and its data).
    step "finding the current Ubuntu 24.04 image"
    overrides+=(ImageId="$(aws ssm get-parameter --name "$UBUNTU_AMI_PARAM" --query Parameter.Value --output text)")
  fi
  step "creating or updating the AWS resources (stack ${STACK} in ${REGION}; first time takes ~5 min)"
  aws cloudformation deploy --stack-name "$STACK" --template-file "$TEMPLATE" \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --tags Project=glassbox-fda --parameter-overrides "${overrides[@]}"
}

cmd_up() {
  load_settings
  preflight_app_settings
  put_secrets
  deploy_stack
  require_stack
  [[ -n "$librechat_url" ]] || die "the stack has no public IP output"

  local sha bucket archive
  sha="$(git rev-parse --short=12 HEAD)"
  bucket="$(stack_output BucketName)"
  step "uploading release ${sha}"
  archive="$(mktemp)"
  git archive --format=tar.gz -o "$archive" HEAD
  aws s3 cp --only-show-errors "$archive" "s3://${bucket}/releases/${sha}.tar.gz"
  rm -f "$archive"

  wait_for_ssm
  step "installing and starting the stack on the instance (first time takes 10-15 min)"
  local rel="/opt/glassbox-releases/${sha}"
  remote_run 5400 \
    "set -eu" \
    "export PATH=\"\$PATH:/snap/bin\"" \
    "command -v aws >/dev/null || snap install aws-cli --classic >/dev/null" \
    "rm -rf ${rel} && mkdir -p ${rel}" \
    "aws s3 cp --only-show-errors --region ${REGION} s3://${bucket}/releases/${sha}.tar.gz - | tar -xz -C ${rel}" \
    "bash ${rel}/deploy/aws/bootstrap.sh ${rel} ${DOMAIN} ${JUPYTER_DOMAIN} ${JUPYTER_CIDRS} ${SSM_PATH} ${REGION}" \
    "ls -1dt /opt/glassbox-releases/* | tail -n +4 | xargs -r rm -rf"
  check_sites
}

cmd_status() {
  load_settings
  require_stack
  step "reading the instance state"
  aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].{Instance:InstanceId,State:State.Name,Type:InstanceType,PublicIp:PublicIpAddress}' \
    --output table
  check_sites 30
}

cmd_logs() {
  current_step="checking the arguments"
  [[ "${1:-}" =~ ^[a-z0-9_-]*$ ]] || die "unknown service: $1"
  load_settings
  require_stack
  wait_for_ssm
  step "reading the logs"
  remote_run 120 "cd /opt/glassbox && docker compose logs --no-color --tail 200 ${1:-}"
}

cmd_test() {
  load_settings
  require_stack
  wait_for_ssm
  step "running the fast tests on the instance"
  remote_run 1200 "cd /opt/glassbox && docker compose exec -T jupyter pytest -m 'not agent' -q"
}

cmd_shell() {
  load_settings
  require_stack
  command -v session-manager-plugin >/dev/null ||
    die "install the AWS Session Manager plugin first (see docs/aws-deployment.md)"
  step "opening a shell on ${INSTANCE_ID} (type exit to leave)"
  aws ssm start-session --target "$INSTANCE_ID"
}

cmd_stop() {
  load_settings
  require_stack
  step "stopping the instance"
  aws ec2 stop-instances --instance-ids "$INSTANCE_ID" >/dev/null
  aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"
  echo "    stopped: the instance costs nothing now; its disk and IP address cost about \$7/month"
}

cmd_start() {
  load_settings
  require_stack
  step "starting the instance"
  aws ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null
  aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
  # The containers restart on their own (restart: unless-stopped), and Caddy is a service
  check_sites 600
}

cmd_destroy() {
  local confirmed="" status bucket answer names
  if [[ "${1:-}" == --confirm ]]; then
    confirmed="${2:-}"
  elif [[ -n "${1:-}" ]]; then
    current_step="checking the arguments"
    die "usage: destroy [--confirm <stack-name>]"
  fi
  load_settings
  status="$(stack_status)"
  step "confirming"
  echo "This deletes stack ${STACK} in ${REGION}: the instance and its disk (all chats and users),"
  echo "the release bucket and the secrets under ${SSM_PATH}. The FDA data itself is in git."
  if [[ -n "$confirmed" ]]; then
    answer="$confirmed"
  elif { : </dev/tty; } 2>/dev/null; then
    read -r -p "Type the stack name to confirm: " answer </dev/tty
  else
    die "no terminal to confirm in; rerun as: ./deploy/aws.sh destroy --confirm ${STACK}"
  fi
  [[ "$answer" == "$STACK" ]] || die "not confirmed: '${answer}' is not the stack name ${STACK}"
  if [[ "$status" != NONE ]]; then
    bucket="$(stack_output BucketName 2>/dev/null || true)"
    if [[ -n "$bucket" && "$bucket" != None ]]; then
      step "emptying bucket ${bucket}"
      aws s3 rm --only-show-errors --recursive "s3://${bucket}" || true
    fi
    step "deleting stack ${STACK} (takes a few minutes)"
    aws cloudformation delete-stack --stack-name "$STACK"
    aws cloudformation wait stack-delete-complete --stack-name "$STACK"
  fi
  step "deleting the secrets under ${SSM_PATH}"
  names="$(aws ssm get-parameters-by-path --path "$SSM_PATH" --recursive \
    --query 'Parameters[].Name' --output text)"
  [[ "$names" != None ]] || names=""
  # delete-parameters takes at most 10 names at a time
  # shellcheck disable=SC2086 # word splitting is intended: the names have no spaces
  [[ -z "$names" ]] || printf '%s\n' $names | xargs -n 10 aws ssm delete-parameters --names >/dev/null
}

usage() {
  sed -n '5,15p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

case "$command_name" in
  up | status | test | shell | stop | start) "cmd_${command_name}" ;;
  destroy) cmd_destroy "${@:2}" ;;
  logs) cmd_logs "${2:-}" ;;
  *) current_step="usage"; usage ;;
esac
