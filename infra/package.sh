#!/usr/bin/env bash
# Builds everything infra/template.yaml loads and uploads it to a code bucket:
#   s3://<bucket>/<prefix>app.zip      backend/ + ai/ + light Python deps (Linux x86_64, Python 3.11)
#   s3://<bucket>/<prefix>web/         frontend/dist built against the same-origin API (/api/v1/...)
#   s3://<bucket>/<prefix>artifacts/   the precomputed files the backend reads, at their repo paths
#
# Usage (from the repository root, after pasting this account's Learner Lab credentials):
#   AWS_PROFILE=mfp-a ./infra/package.sh mfp-code-123456789012            # prefix defaults to mfp/v1/
#   AWS_PROFILE=mfp-a ./infra/package.sh mfp-code-123456789012 mfp/v2/    # new prefix = redeploy new code
# Then create or update the stack with CodeBucket and CodePrefix set to the same values.
# The bucket is created if it does not exist. AWS_REGION defaults to us-east-1 (Learner Lab).

set -euo pipefail

BUCKET="${1:?usage: infra/package.sh <code-bucket> [prefix, default mfp/v1/]}"
PREFIX="${2:-mfp/v1/}"
[[ "$PREFIX" == */ ]] || PREFIX="$PREFIX/"
export AWS_REGION="${AWS_REGION:-us-east-1}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/infra/build"
cd "$ROOT"

for tool in aws npm python3 zip; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done

# Files the backend opens (found by calling every endpoint with an open() audit hook).
# .env is never packed: secrets go in as stack parameters.
REQUIRED=(
  models/results.csv
  models/favorita/results.csv
  models/experiments/ablation.csv
  models/experiments/learning_curves.csv
  models/experiments/seed_ensemble.csv
  models/experiments/seed_ensemble_k.csv
  models/experiments/seeds.csv
  models/forecasts/ensemble.json
  models/forecasts/long_backtest.parquet
  models/forecasts/long_forecast.parquet
  models/forecasts/long_range_metrics.json
  models/forecasts/sales_history.parquet
  models/forecasts/seasonal_backtest.parquet
  models/forecasts/seasonal_outlook.parquet
  models/forecasts/synthetic_sales.parquet
  models/forecasts/uci_demo.json
  data/synthetic/cash_flow_gaps.json
  data/synthetic/credit_signal.json
  data/synthetic/expenses.parquet
  data/synthetic/shortfall_calibration.json
  data/synthetic/shortfall_risk.json
)
# Read only when present: the model-experiments screen lists the cells that have a config.
OPTIONAL=(models/lstm/config.json models/gru/config.json models/tcn/config.json models/transformer/config.json)

missing=0
for f in "${REQUIRED[@]}"; do
  [[ -f "$f" ]] || { echo "Missing artifact: $f" >&2; missing=1; }
done
[[ $missing -eq 0 ]] || { echo "Regenerate the missing files first (see CLAUDE.md, Commands)." >&2; exit 1; }

echo "Account: $(aws sts get-caller-identity --query Account --output text)  Region: $AWS_REGION"
echo "Target:  s3://$BUCKET/$PREFIX"

rm -rf "$BUILD"
mkdir -p "$BUILD/app" "$BUILD/artifacts"

echo "== 1/4 Frontend"
# Shell variables win over the root .env in Vite. An empty base URL makes api.ts call /api/v1/... on
# the CloudFront domain, so one build works in every account.
(cd frontend && VITE_USE_MOCK=false VITE_API_BASE_URL= npm run build)
if grep -rq "localhost:8000" frontend/dist; then
  echo "frontend/dist still points at localhost:8000; check VITE_API_BASE_URL handling in api.ts" >&2
  exit 1
fi

echo "== 2/4 app.zip"
python3 -m pip install --quiet --target "$BUILD/app" \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.11 --only-binary=:all: \
  -r infra/lambda-requirements.txt
for pkg in backend ai; do
  (find "$pkg" -name "*.py" -not -path "*/__pycache__/*" -print0 | xargs -0 -I{} rsync -R {} "$BUILD/app/")
done
(cd "$BUILD/app" && zip -qr "$BUILD/app.zip" .)
echo "app.zip: $(du -h "$BUILD/app.zip" | cut -f1) zipped, $(du -sh "$BUILD/app" | cut -f1) unzipped (layer adds pandas; total must stay under 250 MB)"

echo "== 3/4 Artifacts"
for f in "${REQUIRED[@]}"; do rsync -R "$f" "$BUILD/artifacts/"; done
for f in "${OPTIONAL[@]}"; do [[ -f "$f" ]] && rsync -R "$f" "$BUILD/artifacts/"; done
echo "artifacts: $(find "$BUILD/artifacts" -type f | wc -l | tr -d ' ') files, $(du -sh "$BUILD/artifacts" | cut -f1)"

echo "== 4/4 Upload"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "Creating bucket $BUCKET"
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$BUCKET" >/dev/null
  else
    aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  fi
fi
aws s3 cp "$BUILD/app.zip" "s3://$BUCKET/${PREFIX}app.zip"
aws s3 sync frontend/dist "s3://$BUCKET/${PREFIX}web/" --delete
aws s3 sync "$BUILD/artifacts" "s3://$BUCKET/${PREFIX}artifacts/" --delete

cat <<EOF

Done. Stack parameters:
  CodeBucket = $BUCKET
  CodePrefix = $PREFIX
EOF
