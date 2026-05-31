# palimpsest PaddleOCR image (T17) — the classic-CV-pipeline parser of the 5-parser set.
#
# PP-StructureV3 (Baidu), Apache-2.0. The ONLY non-torch image: it runs on PaddlePaddle, not
# PyTorch, which is exactly why it's in the set — a genuinely different parser architecture from
# docling/mineru/chandra/dots (all torch VLMs/pipelines). Emits layout boxes + structured table
# cells, so all six comparison metrics apply to it.
#
# CUDA 12.6 — NOT the 12.8 the other four share. PaddlePaddle publishes py3.11 GPU wheels on its
# cu126 index but NOT on cu128 (verified: the cu128 index lists no cp311 wheel). cu126 binaries
# run on RunPod's >=12.8 host drivers via CUDA backward-compat. This is the one image that breaks
# the shared cu128 base, on purpose.
#
# Run via the baked /opt/paddle_run.py wrapper: `python /opt/paddle_run.py <pdf> <out.json>`.
FROM nvidia/cuda:12.6.3-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 (ubuntu 22.04 ships 3.10) + openssh-server (T17: every parser image runs sshd so
# RunPodSession can drive it over direct TCP SSH) + the system libs OpenCV/PaddleOCR load at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
        git curl build-essential openssh-server \
        libxcb1 libxext6 libgl1 libsm6 libglib2.0-0 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# sshd: key-only root login. RunPod injects the key via $PUBLIC_KEY, consumed by start.sh.
RUN mkdir -p /var/run/sshd \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config

# Isolated venv so paddle/paddleocr + python are deterministically on PATH (matches the other images).
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir --upgrade pip

# PaddlePaddle GPU from the cu126 index (cu128 has no py3.11 wheel — verified). Pins the CUDA build
# to 12.6; runs on RunPod's >=12.8 host driver via backward-compat.
RUN pip install --no-cache-dir paddlepaddle-gpu==3.2.0 \
        -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

# PaddleOCR + the `doc-parser` dependency group → the PP-StructureV3 pipeline (layout + table +
# formula + reading order). [VALIDATE IN CI: pin paddleocr version once the build is green.]
RUN pip install --no-cache-dir "paddleocr[doc-parser]"

# Build-time guard (free, in CI). We CANNOT `import paddle` here: paddlepaddle-gpu hard-links
# libcuda.so.1 (the NVIDIA driver lib), which is absent on the no-GPU CI builder (unlike torch,
# which lazy-loads CUDA). So confirm the GPU wheel (not CPU `paddlepaddle`) is installed via
# package metadata; the real `import paddle` + is_compiled_with_cuda() check runs on the pod
# (night verify), where the driver lib exists.
RUN python -c "from importlib.metadata import version; print('paddlepaddle-gpu', version('paddlepaddle-gpu'))"

COPY paddle_run.py /opt/paddle_run.py

# NOTE: PP-StructureV3 weights are NOT baked into the image. The bake would need to run a predict,
# which imports paddle → requires libcuda.so.1, absent on the no-GPU CI builder (see the guard
# above). So the model set (~hundreds of MB: layout/det/rec/table/formula) downloads to
# /root/.paddlex on the FIRST pod run. Unlike the torch images (whose weights bake via a pure
# huggingface_hub download), Paddle's models can't be pre-pulled without a GPU at build time.

COPY start.sh /opt/start.sh
RUN chmod +x /opt/start.sh

# Start sshd then idle; RunPodSession execs `python /opt/paddle_run.py <pdf> <out>` in the pod.
CMD ["/opt/start.sh"]
