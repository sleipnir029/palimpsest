# T13 — Add Chandra layer + build final image + push to RunPod template

## Why
Fourth parser. Chandra 2 (4B, datalab-to/chandra, March 2026, current SOTA on olmOCR-Bench at 85.9%). Then push the final image to RunPod templates.

## Input state
- T12 merged.

## Output state
- `docker/palimpsest-gpu.Dockerfile` extended:
  - `pip install chandra-ocr` (or whatever the official install method is — verify from GitHub README).
  - Pre-download Chandra 2 weights.
- `docker/build.sh` final tag: `palimpsest/gpu:1.0.0-all`.
- The image is pushed to a public Docker registry (Docker Hub or GitHub Container Registry) OR registered as a RunPod custom template.
- File `docker/runpod-template.md` documents the template ID, image URL, recommended GPU (RTX 4090), recommended container disk (≥ 80 GB to hold all four model weights), recommended volume (none needed for parsing — outputs are SCP'd back).
- Test pod run: spin a pod with the new template, run all four parsers' `--version` commands sequentially. All four succeed. Pod stopped. Total cost < $0.30.

## Verification
```bash
# (Replace POD_IP and PORT with values from a running test pod)
ssh root@POD_IP -p PORT "docling --version && mineru --version && python -m olmocr.pipeline --help > /dev/null 2>&1 && echo olmocr-ok && chandra --version"
```
All four must produce expected output.

## Will touch
- `docker/palimpsest-gpu.Dockerfile` (edit)
- `docker/build.sh` (edit: final tag)
- `docker/runpod-template.md` (new)

## Will NOT touch
- src/.
- pixi.toml.

## Out of scope
- Automating pod lifecycle → T14.

## Notes / references
- Chandra GitHub: https://github.com/datalab-to/chandra
- Chandra 2 announcement (Mar 2026): scoring 85.9% on olmOCR-Bench, beats both Chandra v0.1.0 (83.1%) and olmOCR-2 (82.4%).
- If image > 30 GB, consider splitting weight downloads into a separate stage so layers cache properly.
- RunPod docs: https://docs.runpod.io/pods/templates/overview
