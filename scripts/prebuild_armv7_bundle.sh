#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGES_DIR="${ROOT_DIR}/sensor/images"
BUNDLE_DIR="${ROOT_DIR}/artifacts"
DATE_TAG="$(date +%F-%H%M%S)"
BUNDLE_PATH="${BUNDLE_DIR}/edc-armv7-images-${DATE_TAG}.tar.gz"

# По умолчанию dionaea отключён: upstream image часто не имеет linux/arm/v7 manifest.
BUILD_DIONAEA="${BUILD_DIONAEA:-0}"
DIONAEA_BASE_IMAGE="${DIONAEA_BASE_IMAGE:-}"

mkdir -p "${BUNDLE_DIR}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing command: $1" >&2
    exit 1
  }
}

require_cmd docker

docker buildx version >/dev/null 2>&1 || {
  echo "docker buildx is required" >&2
  exit 1
}

if ! docker buildx inspect edc-armv7 >/dev/null 2>&1; then
  docker buildx create --name edc-armv7 --use >/dev/null
else
  docker buildx use edc-armv7 >/dev/null
fi

docker buildx inspect --bootstrap >/dev/null

build_module() {
  local module="$1"
  local dockerfile="${IMAGES_DIR}/${module}/Dockerfile"
  local tag="edc/${module}:local"
  shift
  echo "==> build ${tag}"
  docker buildx build \
    --platform linux/arm/v7 \
    --load \
    -t "${tag}" \
    -f "${dockerfile}" \
    "$@" \
    "${IMAGES_DIR}/${module}"
}

build_module cowrie --build-arg COWRIE_BASE_IMAGE=arm32v7/debian:bookworm-slim --build-arg COWRIE_REF=v2.6.1
build_module opencanary --build-arg HONEYPOT_BASE_IMAGE=python:3.11-slim
build_module heralding --build-arg HONEYPOT_BASE_IMAGE=python:3.9-slim
build_module conpot --build-arg HONEYPOT_BASE_IMAGE=python:3.11-slim

if [[ "${BUILD_DIONAEA}" == "1" ]]; then
  if [[ -n "${DIONAEA_BASE_IMAGE}" ]]; then
    build_module dionaea --build-arg HONEYPOT_BASE_IMAGE="${DIONAEA_BASE_IMAGE}"
  else
    echo "BUILD_DIONAEA=1 set but DIONAEA_BASE_IMAGE is empty" >&2
    exit 1
  fi
else
  echo "==> skip dionaea (set BUILD_DIONAEA=1 and DIONAEA_BASE_IMAGE=<image> to enable)"
fi

images=(
  "edc/cowrie:local"
  "edc/opencanary:local"
  "edc/heralding:local"
  "edc/conpot:local"
)

if [[ "${BUILD_DIONAEA}" == "1" ]]; then
  images+=("edc/dionaea:local")
fi

echo "==> save bundle ${BUNDLE_PATH}"
docker save "${images[@]}" | gzip -1 > "${BUNDLE_PATH}"
ls -lh "${BUNDLE_PATH}"
echo "bundle_ready=${BUNDLE_PATH}"
