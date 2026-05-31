# palimpsest Chandra image (T13) — one of four isolated per-parser GPU images.
#
# Runs on a RunPod RTX 4090/3090 pod. Chandra never runs on the M1 dev box.
# Layer order: CUDA base -> Python 3.11 -> torch (cu128) -> Chandra -> baked weights.
# Chandra OCR 2 is a ~5B-param VLM OCR model (datalab-to/chandra-ocr-2, BF16); run with
# `chandra <pdf> <outdir> --method hf` (the HuggingFace/transformers in-process backend).
#
# Same CUDA 12.8 base as the docling/mineru images, for the same reason: it is the ceiling
# RunPod's host drivers support (see DEVIATIONS.md, T10). We do NOT pin torch/transformers —
# this image is isolated, so chandra-ocr[hf]'s own deps pick the versions they were tested
# against. We DO seed torch from the cu128 index (pinning the CUDA build to 12.8, not the
# version) and assert +cu128, so nothing resolves above the host driver ceiling.
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 from deadsnakes (ubuntu 22.04 ships 3.10). build-essential + the
# -devel base give nvcc/headers for any source builds chandra-ocr's deps pull in.
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

# Isolated venv so the `chandra` console script is deterministically on PATH.
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir --upgrade pip

# Seed torch + torchvision from the cu128 index FIRST (index-url, not extra) so the resolver
# can't pick a non-12.8 wheel (e.g. cu130) on a version tie — the lesson the docling image
# paid for (DEVIATIONS.md, T10). The `[hf]` extra below pulls torch>=2.8 AND torchvision>=0.23;
# seeding BOTH here (already installed → satisfies the lower bounds → no off-index reinstall)
# pins the CUDA minor to 12.8 first. torchvision matters specifically: left to `--extra-index-url`
# it can resolve to a CPU wheel, splitting the torch/torchvision CUDA ABI — a failure that only
# surfaces on the paid pod, which the assert below now also guards (DEVIATIONS.md, T13).
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu128

# Install the HuggingFace backend. Base `chandra-ocr` is only the OpenAI-API client and bakes
# NO runtime — the first CI build proved it (`import vllm` -> ModuleNotFoundError; the install
# pulled openai/httpx/pypdfium2 but no vllm, no torch; see DEVIATIONS.md, T13). The `[hf]` extra
# pulls torch + transformers so chandra runs the model in-process via `--method hf`. NOT `[all]`
# — that adds streamlit we don't need. cu128 stays an EXTRA index so any torch (re)resolution
# keeps cu128 wheels. huggingface_hub is explicit (not relied on as a transitive dep) because
# the weight-prefetch RUN below imports it.
RUN pip install --no-cache-dir "chandra-ocr[hf]" huggingface_hub \
        --extra-index-url https://download.pytorch.org/whl/cu128

# Fail the build (free, in CI) before any paid GPU pod. Assert `+cu128` (not just `+cu`) on BOTH
# torch AND torchvision: it guards a CPU-only / above-ceiling wheel, and torchvision is the `[hf]`
# dep most likely to resolve off the cu128 index → a torch/torchvision ABI split that otherwise
# only blows up on the pod (DEVIATIONS.md, T10/T13). We also import transformers — chandra runs
# `--method hf`, so a missing transformers is THIS parser's runtime failure mode. All three
# import GPU-free, so the assert is safe in the no-GPU CI builder (the lesson of T13's first build).
RUN python -c "import torch, torchvision, transformers; print(torch.__version__, torchvision.__version__, transformers.__version__); \
assert '+cu128' in torch.__version__, torch.__version__; \
assert '+cu128' in torchvision.__version__, torchvision.__version__"

# Bake the Chandra OCR 2 weights so the first pod run does not download. datalab-to/chandra-ocr-2
# is chandra-ocr's default MODEL_CHECKPOINT, so this is exactly what the CLI loads at runtime.
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download('datalab-to/chandra-ocr-2')"

# T17: start sshd (so RunPodSession can ssh/scp in), then idle to keep the container alive.
# gpu_provider (T14) execs `chandra ... --method hf` in the running container.
COPY start.sh /opt/start.sh
RUN chmod +x /opt/start.sh
CMD ["/opt/start.sh"]
