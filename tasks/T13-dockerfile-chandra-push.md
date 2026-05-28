# T13 — Build the standalone Chandra image + register all four RunPod templates

## Why
Fourth parser. Chandra 2 (4B, datalab-to/chandra, March 2026, current SOTA on olmOCR-Bench at
85.9%). Then register every parser image as a RunPod template so T14/T16 can start them.

## Architecture note
Four isolated images — Chandra builds the same way as docling/mineru. There is **no combined
`1.0.0-all` image** anymore; each parser is verified independently on its own pod.

## Input state
- T12 merged (olmOCR upstream image identified). docling + mineru build via the CI matrix.

## Output state
- `docker/palimpsest-chandra.Dockerfile` (new, standalone):
  - `FROM nvidia/cuda:12.8.1-devel-ubuntu22.04`, Python 3.11 venv (mirrors docling/mineru).
  - `pip install chandra-ocr` (or the official install method — verify from the GitHub README).
    Chandra brings its own torch/vLLM (not pinned). Assert torch is a CUDA build.
  - Pre-download Chandra 2 weights via `huggingface_hub.snapshot_download` into HF_HOME.
  - `CMD ["sleep","infinity"]`.
- `docker/build.sh` builds it via `./build.sh chandra [push]` → `palimpsest/chandra:0.1.0`.
- Add `chandra` to the CI workflow matrix (`strategy.matrix.parser: [docling, mineru, chandra]`).
- `docker/runpod-template.md` (extend — T12 created it) ends up documenting **all four**
  RunPod templates; T13 adds the chandra entry:
  - docling (`palimpsest/docling:0.1.0`), mineru (`palimpsest/mineru:0.1.0`),
    chandra (`palimpsest/chandra:0.1.0`), olmocr (upstream image from T12).
  - For each: template ID, image URL, recommended GPU (RTX 4090), container disk
    (sized per that image's weights — no single 80 GB image now), volume (none — outputs SCP'd back).

## Verification
```bash
# Each image is verified independently on its own pod (no combined check):
docker run --rm --gpus all palimpsest/chandra:0.1.0 chandra --version
```
Plus a cheap pod check per template that its parser's --version / --help runs. Total cost < $0.30.

## Will touch
- `docker/palimpsest-chandra.Dockerfile` (new)
- `docker/build.sh` (no change expected — already parser-parametrized; confirm `chandra` works)
- `.github/workflows/build-gpu-image.yml` (add `chandra` to the matrix)
- `docker/runpod-template.md` (extend — add the chandra template to the file T12 created)

## Will NOT touch
- src/.
- pixi.toml.
- The docling / mineru images.

## Out of scope
- Automating pod lifecycle → T14.

## Notes / references
- Chandra GitHub: https://github.com/datalab-to/chandra
- Chandra 2 announcement (Mar 2026): 85.9% on olmOCR-Bench, beats Chandra v0.1.0 (83.1%) and olmOCR-2 (82.4%).
- RunPod templates: https://docs.runpod.io/pods/templates/overview
