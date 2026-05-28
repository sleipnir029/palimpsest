# palimpsest Chandra image (T13) — one of four isolated per-parser GPU images.
#
# Runs on a RunPod RTX 4090/3090 pod. Chandra never runs on the M1 dev box.
# Layer order: CUDA base -> Python 3.11 -> torch (cu128) -> Chandra -> baked weights.
# Chandra OCR 2 is a ~5B-param VLM OCR model (datalab-to/chandra-ocr-2, BF16); run with
# `chandra <pdf> <outdir> --method vllm` (the vLLM backend, same serving path as the others).
#
# Same CUDA 12.8 base as the docling/mineru images, for the same reason: it is the ceiling
# RunPod's host drivers support (see DEVIATIONS.md, T10). Unlike docling we do NOT pin a
# vLLM version — this image is isolated, so chandra-ocr's own deps pick the versions they were
# tested against. We DO seed torch from the cu128 index (pinning the CUDA build to 12.8, not
# the version) and assert +cu128, so nothing resolves above the host driver ceiling.
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 from deadsnakes (ubuntu 22.04 ships 3.10). build-essential + the
# -devel base give nvcc/headers for any source builds chandra-ocr's deps pull in.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
        git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Isolated venv so the `chandra` console script is deterministically on PATH.
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir --upgrade pip

# Seed torch from the cu128 index FIRST (index-url, not extra) so the resolver can't
# pick a non-12.8 wheel (e.g. cu130) on a version tie — the lesson the docling image
# paid for (DEVIATIONS.md, T10). chandra-ocr's vLLM backend brings torch; seeding it
# here pins the CUDA minor to 12.8 before that resolution happens.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu128

# Base `chandra-ocr` install = the vLLM backend (the lightweight, GPU-serving path that
# matches the other three parsers). NOT `[all]` — that pulls streamlit + an HF-backend
# torch we don't use. cu128 stays an EXTRA index so any torch/vLLM (re)resolution keeps
# cu128 wheels. huggingface_hub is explicit (not relied on as a transitive dep) because
# the weight-prefetch RUN below imports it.
RUN pip install --no-cache-dir chandra-ocr huggingface_hub \
        --extra-index-url https://download.pytorch.org/whl/cu128

# Fail the build (free, in CI) before any paid GPU pod. Asserting `+cu128` (not just `+cu`)
# guards BOTH a CPU-only torch AND a CUDA build above RunPod's 12.8 host ceiling
# (DEVIATIONS.md, T10). We also import vllm: chandra runs with `--method vllm`, so a
# missing/broken vLLM is THIS parser's runtime failure mode — catch it in CI, not on a pod.
RUN python -c "import torch, vllm; print(torch.__version__, vllm.__version__); \
assert '+cu128' in torch.__version__, torch.__version__"

# Bake the Chandra OCR 2 weights so the first pod run does not download. datalab-to/chandra-ocr-2
# is chandra-ocr's default MODEL_CHECKPOINT, so this is exactly what the CLI loads at runtime.
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download('datalab-to/chandra-ocr-2')"

# Keep the container alive so RunPod can exec/SSH into it (a bare `bash` as PID 1
# exits immediately when the pod starts detached, stopping the container).
# gpu_provider (T14) execs `chandra ... --method vllm` in the running container.
CMD ["sleep", "infinity"]
