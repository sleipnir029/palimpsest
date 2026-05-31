#!/usr/bin/env bash
# Build one palimpsest parser image. Usage: ./build.sh <parser> [push]
#   ./build.sh docling          # build palimpsest/docling:0.2.1 locally
#   ./build.sh mineru push      # build palimpsest/mineru:0.2.1 and push
# <parser> is one of the five we build: docling | mineru | chandra | dots | paddle.
#
# Build needs an amd64 Docker host with ~40 GB free disk (no GPU required to
# build; GPU is only needed at runtime). See README.md.
#
# Pushing: set PUSH_TAG to a flat Docker Hub repo (Hub has no nested paths); it
# defaults to docker.io/<your-user>/palimpsest-<parser>:0.2.1 via DOCKERHUB_USERNAME.
#   DOCKERHUB_USERNAME=<you> ./build.sh mineru push
set -euo pipefail

PARSER="${1:?usage: ./build.sh <docling|mineru|chandra|dots|paddle> [push]}"
TAG="palimpsest/${PARSER}:0.2.1"     # local build label
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="${HERE}/palimpsest-${PARSER}.Dockerfile"

[[ -f "${DOCKERFILE}" ]] || { echo "no Dockerfile for '${PARSER}': ${DOCKERFILE}" >&2; exit 1; }

# --platform linux/amd64 is mandatory: RunPod RTX pods are amd64. Building on an
# Apple-silicon Mac without this produces an arm64 image that fails silently.
docker build --platform linux/amd64 -f "${DOCKERFILE}" -t "${TAG}" "${HERE}"

if [[ "${2:-}" == "push" ]]; then
    PUSH_TAG="${PUSH_TAG:-docker.io/${DOCKERHUB_USERNAME:?set DOCKERHUB_USERNAME or PUSH_TAG}/palimpsest-${PARSER}:0.2.1}"
    docker tag "${TAG}" "${PUSH_TAG}"
    docker push "${PUSH_TAG}"
fi
