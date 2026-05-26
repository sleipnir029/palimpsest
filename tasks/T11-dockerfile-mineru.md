# T11 — Add MinerU 2.5 layer to Dockerfile

## Why
Second parser. MinerU 2.5 (1.2B decoupled VLM, opendatalab/MinerU2.5-2509-1.2B) for the comparison.

## Input state
- T10 merged. Dockerfile has CUDA + Python + docling + granite weights.

## Output state
- `docker/palimpsest-gpu.Dockerfile` has additional layers (appended at the bottom):
  - `pip install -U "mineru[core]"`
  - Pre-download `opendatalab/MinerU2.5-2509-1.2B` weights via `mineru-models-download` or huggingface_hub.
- `docker/build.sh` re-tags as `palimpsest/gpu:0.2.0-docling-mineru`.

## Verification
```bash
docker run --rm --gpus all palimpsest/gpu:0.2.0-docling-mineru mineru --version
docker run --rm --gpus all palimpsest/gpu:0.2.0-docling-mineru python -c "from huggingface_hub import snapshot_download; import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B'))"
```
First prints a version. Second exits 0 confirming weights are present.

## Will touch
- `docker/palimpsest-gpu.Dockerfile` (edit)
- `docker/build.sh` (edit: new tag)

## Will NOT touch
- Anything outside docker/.

## Out of scope
- olmOCR → T12.
- Chandra → T13.

## Notes / references
- MinerU docs: https://github.com/opendatalab/mineru
- HF model: https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B
- Use `mineru -b vlm` (VLM mode) when running on GPU.
- If `pip install mineru[all]` fails, fall back to `mineru[core]` and document in DEVIATIONS.md.
