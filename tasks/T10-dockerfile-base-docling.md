# T10 — Dockerfile: base + docling layer

## Why
First parser (docling, via granite-docling-258M VLM) runs on RunPod. Build the base image with CUDA + Python 3.11 + vLLM, then add docling and bake the model weights.

## Input state
- T09 merged. RunPod API access verified.
- `docker/` directory exists but empty.
- Docker installed locally (or use RunPod's template builder via web UI).

## Output state
- File `docker/palimpsest-gpu.Dockerfile` exists:
  - `FROM nvidia/cuda:12.1.0-devel-ubuntu22.04`
  - Installs Python 3.11, pip, build tools.
  - Installs vllm, docling, docling-ibm-models.
  - Pre-downloads `ibm-granite/granite-docling-258M` to `/root/.cache/huggingface/` so first run is fast.
  - Exposes the docling CLI in PATH.
  - `CMD ["bash"]` (interactive — the gpu_provider will SSH in and run commands).
- File `docker/build.sh` builds and tags as `palimpsest/gpu:0.1.0-docling`. Optional: pushes to Docker Hub or RunPod template registry.
- File `docker/README.md` documents how to build, push, and register as a RunPod template.

## Verification
EITHER (if local Docker with NVIDIA):
```bash
docker build -f docker/palimpsest-gpu.Dockerfile -t palimpsest/gpu:0.1.0-docling docker/
docker run --rm --gpus all palimpsest/gpu:0.1.0-docling docling --version
```
OR (no local GPU): use RunPod's "Custom Template" feature to build from the Dockerfile, spin a pod with the template, SSH in and run `docling --version`. Stop the pod within 5 minutes.

Verbatim output of `docling --version` showing a version string is required.

## Will touch
- `docker/palimpsest-gpu.Dockerfile` (new)
- `docker/build.sh` (new)
- `docker/README.md` (new)

## Will NOT touch
- Any src file. The Docker image is independent.
- `pixi.toml`. Docling does NOT go in pixi.toml — it only runs in the container.

## Out of scope
- MinerU layer → T11.
- olmOCR layer → T12.
- Chandra layer → T13.
- gpu_provider context manager → T14.

## Notes / references
- Docling on RTX docs: https://docling-project.github.io/docling/getting_started/rtx/
- granite-docling-258M HF: https://huggingface.co/ibm-granite/granite-docling-258M
- The image will end up ~10–15 GB. That's fine; it's pulled to the pod once and cached on RunPod's side.
- Use `--gpu-memory-utilization 0.9` when serving via vLLM.
- Do NOT use Docker Compose. Single image.
