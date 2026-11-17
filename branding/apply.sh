#!/bin/sh
# Applies the agency branding to LibreChat's built client, then starts LibreChat.
# docker-compose.yml runs this as the librechat service's command, with ./branding mounted
# read-only at /opt/glassbox/branding. The official image stays unmodified: the copies land in
# the container's own writable layer and are redone on every start. See developer.md.
set -eu

src=/opt/glassbox/branding
dist=/app/client/dist

# The logo LibreChat shows on its login page, in place of its own, and the agent's chat icon
# (the Glass Box FDA spec's iconURL, set in agent/librechat_config.py).
cp "$src/logo.svg" "$dist/assets/logo.svg"
cp "$src/icon.svg" "$dist/assets/glassbox-icon.svg"

# The color theme, linked after LibreChat's own stylesheet so its values win. The ?v= hash
# changes whenever theme.css does, so browsers don't keep a cached copy.
cp "$src/theme.css" "$dist/assets/glassbox-theme.css"
version="$(md5sum "$src/theme.css" | cut -c1-8)"

# LibreChat reads index.html once, at startup. Always edit a pristine copy, so restarts and
# theme changes never stack up links.
[ -f "$dist/index.html.orig" ] || cp "$dist/index.html" "$dist/index.html.orig"
sed "s#</head>#<link rel=\"stylesheet\" href=\"assets/glassbox-theme.css?v=${version}\" /></head>#" \
  "$dist/index.html.orig" >"$dist/index.html"

exec npm run backend
