# palimpsest MinerU image (T11) — one of four isolated per-parser GPU images.
#
# Runs on a RunPod RTX 4090/3090 pod. MinerU never runs on the M1 dev box.
# Layer order: CUDA base -> Python 3.11 -> MinerU (pulls its own torch/vLLM) -> baked weights.
# MinerU 2.5 is a 1.2B decoupled VLM (opendatalab/MinerU2.5-2509-1.2B); run with `mineru -b vlm`.
#
# Same CUDA 12.8 base as the docling image, for the same reason: it is the ceiling
# RunPod's host drivers support (see DEVIATIONS.md, T10). Unlike docling we do NOT
# pin vLLM here — this image is isolated, so MinerU's own extras pick the torch/vLLM
# they were tested against. We only assert torch ended up a CUDA build.
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 from deadsnakes (ubuntu 22.04 ships 3.10). build-essential + the
# -devel base give nvcc/headers for any source builds MinerU's deps pull in.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
        git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Isolated venv so the `mineru` console script is deterministically on PATH.
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir --upgrade pip

# Install MinerU with the full extras. Upstream docs show `mineru[all]` as the
# documented default; it pulls MinerU's own torch/vLLM/transformers pins. If the
# resolver fails on `[all]` in CI, fall back to `mineru[core]` (T11 card authorizes
# this) and log the swap in DEVIATIONS.md. huggingface_hub is installed explicitly
# (not relied on as a MinerU transitive dep) because the weight-prefetch RUN below
# imports it — the `[core]` fallback may not pull it in.
RUN pip install --no-cache-dir -U "mineru[all]" huggingface_hub

# MinerU may resolve a CPU-only torch on linux. Fail the build (free, in CI) if it
# is not a CUDA wheel, before any paid GPU pod. If this assert trips, add an explicit
# `pip install torch --index-url https://download.pytorch.org/whl/cu128` above and
# log the deviation. NOTE: this checks for *a* CUDA wheel, not the CUDA minor — a wheel
# built for CUDA > 12.8 would pass here but fail at runtime against RunPod's 12.8 host
# ceiling (DEVIATIONS.md, T10). The version printed here is verified ≤ 12.8 on first pod run.
RUN python -c "import torch; print(torch.__version__); assert '+cu' in torch.__version__, torch.__version__"

# Bake the MinerU 2.5 VLM weights so the first pod run does not download. Pulled via
# huggingface_hub directly (robust, version-independent) rather than a MinerU CLI.
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download('opendatalab/MinerU2.5-2509-1.2B')"

# Keep the container alive so RunPod can exec/SSH into it (a bare `bash` as PID 1
# exits immediately when the pod starts detached, stopping the container).
# gpu_provider (T14) execs `mineru -b vlm ...` in the running container.
CMD ["sleep", "infinity"]
