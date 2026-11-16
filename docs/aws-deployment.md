# Deploying to AWS

`./deploy/aws.sh` puts the whole stack on one EC2 instance. It is the same Docker Compose stack, started by the same `start.sh`, that runs on a laptop. LibreChat and JupyterLab get public HTTPS addresses. A run takes one command, and every run ends by printing **SUCCESS** or **FAILURE**.

```bash
./deploy/aws.sh up
...
LibreChat:  https://3-15-20-7.sslip.io
JupyterLab: https://jupyter.3-15-20-7.sslip.io/lab   (token: JUPYTER_TOKEN in .env)
SUCCESS
```

## What gets created

```
Internet --443--> EC2 instance (Ubuntu 24.04, t3.large, 40 GB encrypted disk, fixed public IP)
                    Caddy (HTTPS, free Let's Encrypt certificates)
                      https://<ip>.sslip.io          -> LibreChat
                      https://jupyter.<ip>.sslip.io  -> JupyterLab (IP allow-list, then its token)
                    docker compose: postgres, jupyter, librechat, mongodb (as on a laptop)
```

All of it is one CloudFormation stack (`deploy/aws/template.yaml`), named `glassbox-fda` by default:
- a small VPC of its own;
- a security group;
- the instance and its role;
- a fixed IP address (Elastic IP);
- a private S3 bucket that holds the deployed code.

Secrets are kept in SSM Parameter Store under `/glassbox/<stack>/`.

**Web addresses.** No domain is needed. [sslip.io](https://sslip.io) is a free public DNS service: any name that contains an IP address resolves to that address. So `3-15-20-7.sslip.io` points at `3.15.20.7`, and Let's Encrypt issues real certificates for it. The IP is fixed, so the addresses survive `stop`/`start` and redeploys. They change only after `destroy` followed by `up`.

**What is public:**

| Port | Open to | What |
|---|---|---|
| 443 | `DEPLOY_ALLOWED_CIDR` (default: everyone) | LibreChat, which needs its admin login, and JupyterLab, which needs an allowed IP and its token |
| 80 | Everyone | Let's Encrypt certificate checks. Everything else redirects to HTTPS. |

**What is private:** Postgres, MongoDB and the containers' own ports are bound to `127.0.0.1` on the instance. There is no SSH: administration goes through AWS Systems Manager (`./deploy/aws.sh shell`).

## Before the first deploy

1. **AWS CLI** v2 with credentials for the target account (`aws configure` or `aws sso login`). Check them with `aws sts get-caller-identity`.
   - The identity needs permission to manage CloudFormation, EC2, VPC, IAM roles, S3, SSM, and Route 53 if you use a real domain. An administrator role in a sandbox account is simplest.
2. **`.env`** filled in as for a local run, plus the deployment settings (see `.env.example`). Because the sites are public, the script refuses weak values:
   - `ADMIN_PASSWORD`: 12+ characters, not the default `glassbox`.
   - `JUPYTER_TOKEN`: 32+ random characters, for example from `openssl rand -hex 24`. Anyone with the token can run code in the `jupyter` container.
   - `POSTGRES_PASSWORD` and `AGENT_RO_PASSWORD`: not the example values.
   - `OPENAI_API_KEY`: set.
3. **Strongly recommended:** limit JupyterLab to your own networks with `DEPLOY_JUPYTER_ALLOWED_CIDRS`, for example your office or VPN range. To find your current IP, run `curl https://checkip.amazonaws.com`, then add `/32` to it.
4. **Optional:** the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html), needed only for `./deploy/aws.sh shell`.

Deployment settings in `.env`:

| Setting | Default | Meaning |
|---|---|---|
| `DEPLOY_STACK_NAME` | `glassbox-fda` | Name of the stack; also the Parameter Store path |
| `DEPLOY_REGION` | the AWS CLI's region | Where to deploy |
| `DEPLOY_INSTANCE_TYPE` | `t3.large` | x86_64 only (the LibreChat image is amd64) |
| `DEPLOY_ALLOWED_CIDR` | `0.0.0.0/0` | Who may open the sites |
| `DEPLOY_JUPYTER_ALLOWED_CIDRS` | same as above | Comma-separated networks allowed to reach JupyterLab |
| `DEPLOY_DOMAIN_NAME` | `<ip-with-dashes>.sslip.io` | A real domain instead (see below) |
| `DEPLOY_HOSTED_ZONE_ID` | none | A public Route 53 zone for that domain, so the DNS records are created for you |

## Commands

```bash
./deploy/aws.sh up          # create or update everything, then deploy the current commit
./deploy/aws.sh status      # instance state, and checks that both sites answer
./deploy/aws.sh logs        # last 200 lines of the stack's logs (or: logs librechat)
./deploy/aws.sh test        # fast test suite (pytest -m "not agent") on the instance
./deploy/aws.sh shell       # a root shell on the instance (needs the Session Manager plugin)
./deploy/aws.sh stop        # stop the instance to save money (data and addresses are kept)
./deploy/aws.sh start       # start it again
./deploy/aws.sh destroy     # delete everything, including chats and users
```

Each run ends with the addresses and `SUCCESS` (exit code 0), or with `FAILURE: <the step that failed>` (non-zero exit code).
- For `up`, SUCCESS means both sites actually answered over HTTPS with a valid certificate, not just that the commands ran.
- The JupyterLab address is printed only on success.
- The token is never printed: it is `JUPYTER_TOKEN` in your `.env`.

### First deploy

`./deploy/aws.sh up` takes about 15–20 minutes the first time:
1. Creating the AWS resources: about 5 minutes.
2. Installing Docker and Caddy, downloading the container images (the LibreChat image is large), and loading the FDA data.
3. Issuing the certificates: up to a few minutes.

The script prints progress every minute while the instance works.

### Updating

Commit your changes, then run `./deploy/aws.sh up` again. It deploys the **committed** code: `git archive HEAD`, so uncommitted changes are left out, with a warning. Users, chats and the database are kept. LibreChat restarts if its configuration or skills changed. Redeploys take a few minutes.

To change a secret (for example the OpenAI key or the Jupyter token), edit `.env` and rerun `up`.

If a commit changes the FDA workbooks in `data/raw/`, the deploy converts them again, but the database keeps its old data. Reload it from `./deploy/aws.sh shell`: in `/opt/glassbox`, run `./stop.sh --reset`, then rerun `up`. This also deletes chats and users.

**The LibreChat admin is created only once.** Changing `ADMIN_PASSWORD` afterwards doesn't change the existing account. Either change the password in LibreChat, or use `./deploy/aws.sh shell` and, in `/opt/glassbox`, run `./stop.sh --reset`, then rerun `up`. The reset also deletes all chats.

## How a deploy works

1. **Checks:** `.env` and the AWS credentials, before anything is created.
2. **Secrets:** the app settings from `.env` go to Parameter Store as encrypted values. Only these are copied; the `DEPLOY_*` settings stay local. LibreChat's own encryption and session secrets are generated there once and never changed.
3. **Infrastructure:** CloudFormation creates or updates the stack. The Ubuntu image is chosen on the first create only, because changing it would replace the instance and lose its data.
4. **Code:** the current commit is archived and uploaded to the stack's bucket.
5. **The instance:** through SSM Run Command, the instance downloads the release and runs `deploy/aws/bootstrap.sh`, which:
   - installs Docker, the Compose plugin and Caddy;
   - copies the code into `/opt/glassbox`, keeping the generated CSVs and LibreChat configuration;
   - writes `.env` from Parameter Store;
   - writes the Caddy configuration;
   - runs `./start.sh`.

   The output is shown at the end of the step. The full log is `/var/log/glassbox-deploy.log` on the instance.
6. **Health checks:** the script checks both addresses over HTTPS.

## Cost

Approximate, in `us-east-2`:
- **Running:** about $65–70 a month. That is the t3.large (about $61), the disk (about $3) and the public IP (about $4).
- **Stopped:** about $7 a month, for the disk and the IP.
- `destroy` brings it to zero.

OpenAI usage is billed separately. The site is public, so the admin login is what protects that spend.

## Using a real domain later

Set `DEPLOY_DOMAIN_NAME` (for example `glassbox.example.com`) and rerun `up`.
- **With a public Route 53 hosted zone for it:** also set `DEPLOY_HOSTED_ZONE_ID`. The stack then creates the `A` records for the name and for `jupyter.<name>`.
- **With DNS elsewhere:** create those two `A` records yourself, pointing at the IP from `./deploy/aws.sh status`, then rerun `up`.

## Troubleshooting

- **`FAILURE: waiting for HTTPS ...`:** the stack is running, but a site didn't answer within the time limit.
  - Run `./deploy/aws.sh status` a minute later. Certificates can take a little while.
  - Check `./deploy/aws.sh logs librechat`.
  - On the instance (`shell`), `journalctl -u caddy` shows certificate errors.
  - sslip.io must be reachable. If it is down, the names don't resolve, though the server keeps running.
- **`FAILURE: waiting for the instance in SSM`:** the instance didn't register with Systems Manager within 10 minutes. Check that it is running in the EC2 console, then rerun `up`.
- **`stack ... is in ROLLBACK_COMPLETE`:** the first create failed. The CloudFormation console's *Events* tab says why. Run `destroy`, then `up`.
- **JupyterLab answers 403:** your IP is not in `DEPLOY_JUPYTER_ALLOWED_CIDRS`. Update it in `.env` and rerun `up`.

## Security notes

- **JupyterLab is the sensitive part.** Its terminal and notebooks run code inside the `jupyter` container, which holds the OpenAI and Gemini keys and the read-only database login. It has no Docker access, and the database admin password is not in it. Keep the token long, keep the allow-list narrow, and change the token (in `.env`, then rerun `up`) if it may have leaked.
- **LibreChat's protections:** registration is off, and the only account is the admin. The same prompt-injection caveats as on a laptop apply (AGENTS.md §3).
- **The instance:**
  - IMDSv2 is required, with a hop limit of 1, so containers can't fetch its AWS credentials.
  - Its role can only read its own releases and its own parameters.
  - Its disk is encrypted.
- Public data only. No customer data, ever.
