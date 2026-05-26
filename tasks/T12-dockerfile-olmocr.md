# T12 — Add olmOCR-2-7B-1025 layer to Dockerfile

## Why
Third parser. olmOCR 2 (7B VLM, RLVR-trained, allenai/olmOCR-2-7B-1025).

## Input state
- T11 merged.

## Output state
- `docker/palimpsest-gpu.Dockerfile` extended:
  - Clone or pip-install olmOCR per https://github.com/allenai/olmocr.
  - Pre-download `allenai/olmOCR-2-7B-1025` weights.
- `docker/build.sh` retags as `palimpsest/gpu:0.3.0-docling-mineru-olmocr`.

## Verification
```bash
docker run --rm --gpus all palimpsest/gpu:0.3.0-docling-mineru-olmocr python -m olmocr.pipeline --help
docker run --rm --gpus all palimpsest/gpu:0.3.0-docling-mineru-olmocr python -c "from huggingface_hub import snapshot_download; import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--allenai--olmOCR-2-7B-1025'))"
```

## Will touch
- `docker/palimpsest-gpu.Dockerfile` (edit)
- `docker/build.sh` (edit: new tag)

## Will NOT touch
- Anything outside docker/.

## Out of scope
- Chandra → T13.

## Notes / references
- olmOCR 2 paper: arXiv 2510.19817.
- HF model: https://huggingface.co/allenai/olmOCR-2-7B-1025
- olmOCR uses vLLM for serving — make sure vLLM (already installed for docling) supports the architecture.
