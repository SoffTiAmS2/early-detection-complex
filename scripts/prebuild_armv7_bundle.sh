#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGES_DIR="${ROOT_DIR}/sensor/dockerfiles"
BUNDLE_DIR="${ROOT_DIR}/artifacts"
DATE_TAG="$(date +%F-%H%M%S)"
BUNDLE_PATH="${BUNDLE_DIR}/edc-armv7-images-${DATE_TAG}.tar.gz"

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
build_module conpot --build-arg HONEYPOT_BASE_IMAGE=python:3.8-slim
build_module mailoney --build-arg MAILONEY_BASE_IMAGE=python:3.11-slim
build_module honeypy --build-arg HONEYPY_BASE_IMAGE=python:2.7-slim-buster
build_module glutton --build-arg GLUTTON_BUILDER_IMAGE=golang:1.23-bookworm --build-arg GLUTTON_RUNTIME_IMAGE=debian:bookworm-slim

images=(
  "edc/cowrie:local"
  "edc/conpot:local"
  "edc/mailoney:local"
  "edc/honeypy:local"
  "edc/glutton:local"
)

echo "==> save bundle ${BUNDLE_PATH}"
docker save "${images[@]}" | gzip -1 > "${BUNDLE_PATH}"
ls -lh "${BUNDLE_PATH}"
echo "bundle_ready=${BUNDLE_PATH}"
