# palimpsest MinerU image (T11) — one of four isolated per-parser GPU images.
#
# Runs on a RunPod RTX 4090/3090 pod. MinerU never runs on the M1 dev box.
# Layer order: CUDA base -> Python 3.11 -> torch (cu128) -> MinerU -> baked weights.
# MinerU 2.5 is a 1.2B decoupled VLM (opendatalab/MinerU2.5-2509-1.2B); run with `mineru -b vlm`.
#
# Same CUDA 12.8 base as the docling image, for the same reason: it is the ceiling
# RunPod's host drivers support (see DEVIATIONS.md, T10). Unlike docling we do NOT pin a
# vLLM version — this image is isolated, so MinerU's own extras pick the versions they were
# tested against. We DO seed torch from the cu128 index (pinning the CUDA build to 12.8, not
# the version) and assert +cu128, so nothing resolves above the host driver ceiling.
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 from deadsnakes (ubuntu 22.04 ships 3.10). build-essential + the
# -devel base give nvcc/headers for any source builds MinerU's deps pull in.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
        git curl build-essential openssh-server \
        libxcb1 libxext6 libgl1 libsm6 libglib2.0-0 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# sshd (T17): RunPodSession drives this pod over direct TCP SSH, so the image runs an SSH daemon.
# Key-only root login; RunPod injects the public key via $PUBLIC_KEY, consumed by start.sh.
RUN mkdir -p /var/run/sshd \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config

# Isolated venv so the `mineru` console script is deterministically on PATH.
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir --upgrade pip

# Seed torch from the cu128 index FIRST (index-url, not extra) so the resolver can't
# pick a non-12.8 wheel (e.g. cu130) on a version tie — the lesson the docling image
# paid for (DEVIATIONS.md, T10). MinerU 2.5 needs torch >= 2.8; the cu128 index serves
# 2.8–2.11+cu128 for cp311, so this satisfies MinerU while pinning the CUDA minor to 12.8.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu128

# Install MinerU with the full extras, keeping cu128 as an EXTRA index so any torch/vLLM
# (re)resolution stays on cu128 wheels. `mineru[all]` is the documented default; if the
# resolver fails on `[all]` in CI, fall back to `mineru[core]` (T11 card authorizes this)
# and log the swap in DEVIATIONS.md. No `-U`: this is a fresh venv (already latest), and
# `-U` could eagerly replace the seeded cu128 torch. huggingface_hub is explicit (not a
# MinerU transitive dep) because the weight-prefetch RUN below imports it.
RUN pip install --no-cache-dir "mineru[all]" huggingface_hub \
        --extra-index-url https://download.pytorch.org/whl/cu128

# vllm is NOT pulled by `mineru[all]` (T17 verify, 2026-05-31): `-b vlm-auto-engine` errors
# with "Please install vllm to use the vllm-async-engine backend." Pin matches docling's pin
# so the two VLM images share the same vllm. cu128 stays an EXTRA index.
RUN pip install --no-cache-dir 'vllm==0.19.1' \
        --extra-index-url https://download.pytorch.org/whl/cu128

# Fail the build (free, in CI) before any paid GPU pod if torch is not a cu128 wheel.
# Now that torch is seeded from cu128, asserting `+cu128` (not just `+cu`) guards BOTH a
# CPU-only torch AND a CUDA build above RunPod's 12.8 host ceiling (DEVIATIONS.md, T10).
RUN python -c "import torch; print(torch.__version__); assert '+cu128' in torch.__version__, torch.__version__"

# Bake the MinerU 2.5 VLM weights so the first pod run does not download. Pulled via
# huggingface_hub directly (robust, version-independent) rather than a MinerU CLI.
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download('opendatalab/MinerU2.5-2509-1.2B')"

# T17: start sshd (so RunPodSession can ssh/scp in), then idle to keep the container alive.
# gpu_provider (T14) execs `mineru -b vlm ...` in the running container.
COPY start.sh /opt/start.sh
RUN chmod +x /opt/start.sh
CMD ["/opt/start.sh"]
