# palimpsest docling image (T10) — one of four isolated per-parser GPU images.
#
# Runs on a RunPod RTX 4090/3090 pod. docling never runs on the M1 dev box.
# Layer order: CUDA base -> Python 3.11 -> vLLM -> docling -> baked weights.
# Each parser (docling / MinerU / olmOCR / Chandra) ships as its own image so their
# conflicting torch/vLLM pins never collide; this Dockerfile builds docling only.
#
# NOTE (deviation from task card, see DEVIATIONS.md): the card pins
# nvidia/cuda:12.1.0-devel. vLLM 0.19.x dropped CUDA 12.1, so the base is on a
# newer CUDA. 12.8 (not vLLM's 12.9 default) is chosen because it is the ceiling
# RunPod's available host drivers support, and it is also vLLM's lowest supported
# CUDA. Base runtime, torch wheel, and vLLM all agree on CUDA 12.8 (asserted below).
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 from deadsnakes (ubuntu 22.04 ships 3.10). build-essential + the
# -devel base give nvcc/headers for any source builds vLLM pulls in.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
        git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Isolated venv so the docling / vllm console scripts are deterministically on PATH.
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir --upgrade pip

# Install torch from the cu128 index FIRST so vLLM resolves against it. With
# --extra-index-url alone, pip can pick PyPI's default-CUDA torch on a version
# tie, silently disagreeing with the 12.8 base. The assert fails the build in CI
# (free, ~20 min) if the CUDA build is wrong, before any paid GPU pod.
RUN pip install --no-cache-dir torch \
        --index-url https://download.pytorch.org/whl/cu128
RUN pip install --no-cache-dir vllm==0.19.1 \
        --extra-index-url https://download.pytorch.org/whl/cu128
RUN python -c "import torch; assert '+cu128' in torch.__version__, torch.__version__"

# docling + the granite VLM models package. Versions pinned to what the first
# verified build resolved (docling --version on a RunPod pod), so the
# 0.1.0-docling tag means fixed content. huggingface_hub is explicit (not a
# transitive dep) because the next RUN depends on it.
RUN pip install --no-cache-dir \
        docling==2.95.0 docling-ibm-models==3.13.2 huggingface_hub

# Bake granite-docling-258M into the image so the first pod run does not download.
# Two revisions: default branch for the docling CLI VLM pipeline, and `untied`
# for vLLM serve (vLLM cannot load the tied embedding weights on the default branch).
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download('ibm-granite/granite-docling-258M'); \
snapshot_download('ibm-granite/granite-docling-258M', revision='untied')"

# Keep the container alive so RunPod can exec/SSH into it (a bare `bash` as PID 1
# exits immediately when the pod starts detached, stopping the container).
# gpu_provider (T14) execs `docling` / `vllm serve` in the running container.
CMD ["sleep", "infinity"]
