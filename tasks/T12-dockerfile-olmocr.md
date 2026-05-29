# T12 — Register olmOCR-2-7B from Allen AI's upstream image

> **⏭ SUPERSEDED by T17 (2026-05-29).** olmOCR was dropped from the comparison — its only
> distribution is Allen AI's FP8/Ada-only prebuilt image (no Dockerfile we control, no sshd),
> which proved too painful to fit the self-built + SSH-able 5-parser design. Replaced by
> **dots.ocr** and **PaddleOCR PP-StructureV3** (both self-built, BF16/cheap-GPU, emit bbox +
> tables). This card is kept for history; see DEVIATIONS.md (T17) and the plan file.

## Why
Third parser. olmOCR 2 (7B VLM, RLVR-trained, allenai/olmOCR-2-7B-1025).

## Architecture note
olmOCR has the tightest dependency pins of the four — Allen AI ships its **own Docker
image** precisely because of this. So we do NOT build an olmOCR image; we use the upstream
one as-is and register it as a RunPod custom template. This is the "hybrid" leg of the
four-isolated-images decision (see the plan in `.claude/plans/`).

## Input state
- T11 merged. docling + mineru images build via CI; build.sh is parametrized.

## Output state
- **No `docker/` Dockerfile for olmOCR.** Instead:
  - Verify the current upstream olmOCR image name + tag (e.g. `alleninstituteforai/olmocr:<tag>`
    — confirm the exact registry/repo/tag on a pod before locking it in).
  - Confirm the entrypoint: `python -m olmocr.pipeline` works and the
    `allenai/olmOCR-2-7B-1025` weights are present or fetched on first run (document which).
  - Register the image as a RunPod custom template. **Create** `docker/runpod-template.md`
    (it does not exist yet) with the olmOCR entry plus the already-built docling + mineru
    templates; T13 extends it with the chandra entry.

## Verification
```bash
# On a RunPod pod started from the olmOCR template (image = upstream olmOCR):
python -m olmocr.pipeline --help
python -c "from huggingface_hub import snapshot_download; import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--allenai--olmOCR-2-7B-1025'))"
```
First prints help. Second exits 0 (if the upstream image bakes the weights; if it fetches
on first run instead, document that and verify a real parse run instead).

## Will touch
- `docker/runpod-template.md` (new — created here with docling/mineru/olmocr entries; T13 adds chandra)
- (No Dockerfile, no build.sh change, no CI matrix entry for olmOCR.)

## Will NOT touch
- src/.
- The docling / mineru / chandra images.

## Out of scope
- Chandra → T13.

## Notes / references
- olmOCR 2 paper: arXiv 2510.19817.
- HF model: https://huggingface.co/allenai/olmOCR-2-7B-1025
- olmOCR GitHub (for the canonical Docker image name + run command): https://github.com/allenai/olmocr
- If the upstream image's CUDA exceeds RunPod's host-driver ceiling (12.8, per DEVIATIONS.md),
  flag it — we may need an older olmOCR image tag.
