#!/usr/bin/env bash
# Build the palimpsest GPU image. Pass "push" to also push.
# Build needs an amd64 Docker host with ~40 GB free disk (no GPU required to
# build; GPU is only needed at runtime for vllm serve). See README.md.
#
# Pushing: set PUSH_TAG to a flat Docker Hub repo (Hub has no nested paths), e.g.
#   PUSH_TAG=docker.io/<your-user>/palimpsest-gpu:0.1.0-docling ./build.sh push
set -euo pipefail

TAG="palimpsest/gpu:0.1.0-docling"   # local build label (per task card)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --platform linux/amd64 is mandatory: RunPod RTX pods are amd64. Building on an
# Apple-silicon Mac without this produces an arm64 image that fails silently.
docker build --platform linux/amd64 \
    -f "${HERE}/palimpsest-gpu.Dockerfile" -t "${TAG}" "${HERE}"

if [[ "${1:-}" == "push" ]]; then
    : "${PUSH_TAG:?set PUSH_TAG=docker.io/<your-user>/palimpsest-gpu:0.1.0-docling}"
    docker tag "${TAG}" "${PUSH_TAG}"
    docker push "${PUSH_TAG}"
fi
