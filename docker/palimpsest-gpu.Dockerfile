# palimpsest GPU image — base + docling (T10)
#
# Runs on a RunPod RTX 4090/3090 pod. docling never runs on the M1 dev box.
# Layer order: CUDA base -> Python 3.11 -> vLLM -> docling -> baked weights.
# T11-T13 add MinerU / olmOCR / Chandra on top of this image.
#
# NOTE (deviation from task card, see DEVIATIONS.md): the card pins
# nvidia/cuda:12.1.0-devel. vLLM 0.19.x ships cu129 wheels and no longer runs on
# CUDA 12.1, so the base is bumped to 12.9.1 and torch/vLLM are installed from the
# cu129 PyTorch index — matching vLLM's documented default. Base runtime, torch
# wheel, and vLLM then agree on CUDA 12.9 (asserted at build time below).
FROM nvidia/cuda:12.9.1-devel-ubuntu22.04

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

# Install torch from the cu129 index FIRST so vLLM resolves against it. With
# --extra-index-url alone, pip can pick PyPI's default-CUDA torch on a version
# tie, silently disagreeing with the 12.9 base. The assert fails the build in CI
# (free, ~20 min) if the CUDA build is wrong, before any paid GPU pod.
RUN pip install --no-cache-dir torch \
        --index-url https://download.pytorch.org/whl/cu129
RUN pip install --no-cache-dir vllm==0.19.1 \
        --extra-index-url https://download.pytorch.org/whl/cu129
RUN python -c "import torch; assert '+cu129' in torch.__version__, torch.__version__"

# docling + the granite VLM models package. huggingface_hub is pinned explicitly
# (not left to a transitive dep) because the next RUN depends on it.
RUN pip install --no-cache-dir docling docling-ibm-models huggingface_hub

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
