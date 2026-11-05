#!/usr/bin/env bash
# Prepares one step of the MFP stack for OpenTofu, the way the course labs do it in AWS CloudShell:
# installs OpenTofu if needed, writes terraform.tfvars (account, LabRole), builds what the step needs,
# and copies steps 1..N into infra/live/. You then run tofu plan / apply yourself.
#
#   ./infra/setup.sh 1 you@example.com   # S3 data bucket + artifacts, DynamoDB, SNS (email given once)
#   ./infra/setup.sh 2                   # + Lambda API and API Gateway   (builds infra/build/app.zip)
#   ./infra/setup.sh 3                   # + S3 web bucket and CloudFront (builds frontend/dist)
#   ./infra/setup.sh 4                   # + upload worker and daily alerts (S3 trigger, EventBridge)
#   ./infra/setup.sh graph               # architecture diagram: infra/live/arch.svg
#
# Region us-east-1 (Learner Lab). Remove everything with: cd infra/live && tofu destroy

set -euo pipefail

STEP="${1:?usage: infra/setup.sh <1|2|3|4|graph> [alert-email]}"
EMAIL="${2:-}"
TOFU_VERSION=1.12.11       # the version the course labs install
NODE_VERSION=22.12.0       # Vite needs Node ^20.19 or >=22.12
export AWS_REGION="${AWS_REGION:-us-east-1}"
export PATH="$HOME/.local/bin:$PATH"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INFRA="$ROOT/infra"
LIVE="$INFRA/live"
BUILD="$INFRA/build"
mkdir -p "$LIVE" "$BUILD" "$HOME/.local/bin"

say() { printf '\n== %s\n' "$*"; }

install_tofu() {
  command -v tofu >/dev/null && return
  [[ "$(uname -s)" == Linux ]] || { echo "Install OpenTofu first (macOS: brew install opentofu)" >&2; exit 1; }
  say "Installing OpenTofu $TOFU_VERSION to ~/.local/bin"
  local tmp; tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/tofu.zip" \
    "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_amd64.zip"
  unzip -q -o "$tmp/tofu.zip" tofu -d "$HOME/.local/bin"
  rm -rf "$tmp"
}

node_ok() {
  command -v node >/dev/null || return 1
  local v; v="$(node -p 'process.versions.node')"
  local major="${v%%.*}" minor; minor="$(echo "$v" | cut -d. -f2)"
  (( major > 22 || (major == 22 && minor >= 12) || (major == 20 && minor >= 19) ))
}

install_node() {
  node_ok && return
  [[ "$(uname -s)" == Linux ]] || { echo "Install Node $NODE_VERSION or newer first" >&2; exit 1; }
  say "Installing Node $NODE_VERSION to ~/.local (CloudShell's Node is too old for Vite)"
  local dir="$HOME/.local/node-v$NODE_VERSION"
  if [[ ! -x "$dir/bin/node" ]]; then
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
      | tar -xJ -C "$HOME/.local" && mv "$HOME/.local/node-v${NODE_VERSION}-linux-x64" "$dir"
  fi
  ln -sf "$dir/bin/node" "$dir/bin/npm" "$dir/bin/npx" "$HOME/.local/bin/"
}

write_tfvars() {
  local tfvars="$LIVE/terraform.tfvars" account
  account="$(aws sts get-caller-identity --query Account --output text)"
  if [[ -z "$EMAIL" && -f "$tfvars" ]]; then
    EMAIL="$(sed -n 's/^alert_email *= *"\(.*\)"/\1/p' "$tfvars")"
  fi
  [[ -n "$EMAIL" ]] || { echo "First run needs the alert email: infra/setup.sh $STEP you@example.com" >&2; exit 1; }
  local role="arn:aws:iam::${account}:role/LabRole"
  if aws iam get-role --role-name LabRole >/dev/null 2>&1; then echo "Verified IAM role : $role"
  else echo "Could not read LabRole (fine outside Learner Lab only if you edit lab_role_arn)"; fi
  cat > "$tfvars" <<EOF
account_id   = "$account"
aws_region   = "$AWS_REGION"
lab_role_arn = "$role"
alert_email  = "$EMAIL"
repo_root    = "$ROOT"
EOF
  echo "Account           : $account ($AWS_REGION)"
  echo "Alert email       : $EMAIL"
}

check_artifacts() {
  local missing=0 f
  while read -r f; do
    [[ -z "$f" || "$f" == \#* ]] && continue
    [[ -f "$ROOT/$f" ]] || { echo "Missing artifact: $f" >&2; missing=1; }
  done < "$INFRA/steps/artifacts.txt"
  (( missing == 0 )) || { echo "Regenerate the missing files first (CLAUDE.md, Commands)." >&2; exit 1; }
}

build_app_zip() {
  say "Building infra/build/app.zip (backend/ + ai/ + light deps; pandas comes from the Lambda layer)"
  rm -rf "$BUILD/app" "$BUILD/app.zip"
  mkdir -p "$BUILD/app"
  python3 -m pip install --quiet --target "$BUILD/app" \
    --platform manylinux2014_x86_64 --implementation cp --python-version 3.11 --only-binary=:all: \
    -r "$INFRA/lambda-requirements.txt"
  (cd "$ROOT" && find backend ai -name "*.py" -not -path "*/__pycache__/*" | while read -r f; do
    mkdir -p "$BUILD/app/$(dirname "$f")" && cp "$f" "$BUILD/app/$f"; done)
  (cd "$BUILD/app" && zip -qr "$BUILD/app.zip" .)
  echo "app.zip: $(du -h "$BUILD/app.zip" | cut -f1)"
}

build_web() {
  install_node
  say "Building frontend/dist for the same-origin API (/api/v1/... on the CloudFront domain)"
  (cd "$ROOT/frontend" && { [[ -d node_modules ]] || npm ci --no-audit --no-fund; } \
    && VITE_USE_MOCK=false VITE_API_BASE_URL= npm run build)
  if grep -rq "localhost:8000" "$ROOT/frontend/dist"; then
    echo "frontend/dist still points at localhost:8000" >&2; exit 1
  fi
}

copy_steps() {
  rm -f "$LIVE"/*.tf
  cp "$INFRA/steps/artifacts.txt" "$LIVE/"
  local n
  for n in $(seq 1 "$1"); do cp "$INFRA/steps/$n-"*.tf "$LIVE/"; done
  echo "infra/live/ now holds: $(cd "$LIVE" && ls *.tf | tr '\n' ' ')"
}

if [[ "$STEP" == graph ]]; then
  install_tofu
  command -v dot >/dev/null || { say "Installing Graphviz"; sudo dnf install -y -q graphviz; }
  (cd "$LIVE" && tofu graph | dot -Tsvg > arch.svg)
  echo "Saved $LIVE/arch.svg (CloudShell: Actions -> Download file)"
  exit 0
fi

[[ "$STEP" =~ ^[1-4]$ ]] || { echo "Step must be 1-4 or graph" >&2; exit 1; }

say "Step $STEP"
install_tofu
write_tfvars
check_artifacts
(( STEP >= 2 )) && build_app_zip
(( STEP >= 3 )) && build_web
copy_steps "$STEP"

cat <<EOF

Step $STEP ready. Run:
  export PATH=\$HOME/.local/bin:\$PATH
  cd $LIVE && tofu init
  tofu plan
  tofu apply -auto-approve
EOF
