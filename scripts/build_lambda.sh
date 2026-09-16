#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
OUTPUT="${DIST_DIR}/soundscope-lambda.zip"
BUILD_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${BUILD_DIR}"
}
trap cleanup EXIT
trap 'echo "Lambda build failed at line ${LINENO}." >&2' ERR

command -v python >/dev/null || { echo "python is required." >&2; exit 1; }
command -v zip >/dev/null || { echo "zip is required." >&2; exit 1; }

mkdir -p "${DIST_DIR}" "${BUILD_DIR}/package"
rm -f "${OUTPUT}"

python -m pip install \
  --requirement "${ROOT_DIR}/requirements.txt" \
  --target "${BUILD_DIR}/package" \
  --quiet
cp -R "${ROOT_DIR}/src" "${BUILD_DIR}/package/src"
find "${BUILD_DIR}/package" -type d -name __pycache__ -prune -exec rm -rf {} +
find "${BUILD_DIR}/package" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

(
  cd "${BUILD_DIR}/package"
  zip -q -r "${OUTPUT}" .
)

echo "Created ${OUTPUT}"
