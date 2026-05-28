# T11 — Build the standalone MinerU 2.5 image

## Why
Second parser. MinerU 2.5 (1.2B decoupled VLM, opendatalab/MinerU2.5-2509-1.2B) for the comparison.

## Architecture note
The four parsers ship as **four isolated images**, not one stacked image — their
torch/vLLM/transformers pins conflict and a shared env risks silently degrading a parser.
We build docling / MinerU / Chandra; olmOCR uses Allen AI's upstream image (T12).
See the plan in `.claude/plans/` and DEVIATIONS.md (CUDA 12.8 host-driver ceiling).

## Input state
- T10 merged. docling is its own image (`docker/palimpsest-docling.Dockerfile` →
  `palimpsest/docling:0.1.0`); `build.sh` is parametrized by parser; CI builds a matrix.

## Output state
- `docker/palimpsest-mineru.Dockerfile` (new, standalone):
  - `FROM nvidia/cuda:12.8.1-devel-ubuntu22.04`, Python 3.11 venv (mirrors docling).
  - **Seed torch from the cu128 index first** (`pip install torch --index-url …/whl/cu128`), then
    `pip install "mineru[all]" huggingface_hub --extra-index-url …/whl/cu128` (no `-U`, fresh venv).
    MinerU 2.5 needs torch ≥ 2.8; cu128 serves 2.8–2.11, so the version is left to MinerU's resolver
    while the CUDA build is pinned to 12.8. On `[all]` resolver failure, fall back to `mineru[core]`
    and log it in DEVIATIONS.md. Assert `'+cu128' in torch.__version__` — guards both a CPU-only torch
    and a CUDA build above RunPod's 12.8 host ceiling.
  - Pre-download `opendatalab/MinerU2.5-2509-1.2B` (verified HF repo id) via
    `huggingface_hub.snapshot_download` into `HF_HOME=/root/.cache/huggingface`. MinerU's own offline
    tool is `mineru-models-download` but it is interactive (no confirmed non-interactive flags), so
    snapshot_download is the build-safe path; `MINERU_MODEL_SOURCE` stays at its `huggingface` default
    (huggingface_hub's cache is global, so MinerU's loader finds the baked weights). Worst case is a
    one-time runtime re-download, not a build break.
  - `CMD ["sleep","infinity"]` (RunPod detached-pod liveness, per T10).
- `docker/build.sh` builds it via `./build.sh mineru [push]` → `palimpsest/mineru:0.1.0`
  (Docker Hub: `<user>/palimpsest-mineru:0.1.0`).
- CI workflow matrix already includes `mineru`.

## Verification
```bash
docker run --rm --gpus all palimpsest/mineru:0.1.0 mineru --version
docker run --rm --gpus all palimpsest/mineru:0.1.0 python -c "from huggingface_hub import snapshot_download; import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B'))"
```
First prints a version. Second exits 0 confirming weights are present.
(Build runs via GitHub Actions → Docker Hub; verification runs on a RunPod pod, as in T10.)

## Will touch
- `docker/palimpsest-mineru.Dockerfile` (new)
- `docker/build.sh` (parametrized — done in the T11 turn)
- `.github/workflows/build-gpu-image.yml` (matrix — done in the T11 turn)

## Will NOT touch
- Anything outside docker/ and the CI workflow.
- The docling image content.

## Out of scope
- olmOCR → T12.
- Chandra → T13.

## Notes / references
- MinerU docs: https://github.com/opendatalab/mineru
- HF model: https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B
- Use `mineru -b vlm` (VLM mode) when running on GPU (wired in T16's parser registry).
