#!/usr/bin/env bash
# Build one palimpsest parser image. Usage: ./build.sh <parser> [push]
#   ./build.sh docling          # build palimpsest/docling:0.1.0 locally
#   ./build.sh mineru push      # build palimpsest/mineru:0.1.0 and push
# <parser> is one we build ourselves: docling | mineru | chandra.
# (olmOCR uses Allen AI's upstream image — there is no Dockerfile for it here.)
#
# Build needs an amd64 Docker host with ~40 GB free disk (no GPU required to
# build; GPU is only needed at runtime). See README.md.
#
# Pushing: set PUSH_TAG to a flat Docker Hub repo (Hub has no nested paths); it
# defaults to docker.io/<your-user>/palimpsest-<parser>:0.1.0 via DOCKERHUB_USERNAME.
#   DOCKERHUB_USERNAME=<you> ./build.sh mineru push
set -euo pipefail

PARSER="${1:?usage: ./build.sh <docling|mineru|chandra> [push]}"
TAG="palimpsest/${PARSER}:0.1.0"     # local build label
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="${HERE}/palimpsest-${PARSER}.Dockerfile"

[[ -f "${DOCKERFILE}" ]] || { echo "no Dockerfile for '${PARSER}': ${DOCKERFILE}" >&2; exit 1; }

# --platform linux/amd64 is mandatory: RunPod RTX pods are amd64. Building on an
# Apple-silicon Mac without this produces an arm64 image that fails silently.
docker build --platform linux/amd64 -f "${DOCKERFILE}" -t "${TAG}" "${HERE}"

if [[ "${2:-}" == "push" ]]; then
    PUSH_TAG="${PUSH_TAG:-docker.io/${DOCKERHUB_USERNAME:?set DOCKERHUB_USERNAME or PUSH_TAG}/palimpsest-${PARSER}:0.1.0}"
    docker tag "${TAG}" "${PUSH_TAG}"
    docker push "${PUSH_TAG}"
fi
