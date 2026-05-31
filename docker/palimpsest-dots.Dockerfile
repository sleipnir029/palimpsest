# palimpsest dots.ocr image (T17) — the multilingual layout-VLM of the 5-parser set.
#
# rednote-hilab/dots.ocr: a single ~1.7B vision-language model that does layout detection + OCR +
# bbox grounding + formula/table parsing by switching the prompt. MIT-licensed, distinct vendor
# (rednote / Xiaohongshu) from docling/mineru/chandra. Emits per-element bbox [x1,y1,x2,y2] +
# category + text (formulas->LaTeX, tables->HTML) → all six comparison metrics apply.
#
# Same cu128 base/pattern as the chandra image (torch VLM, run in-process via transformers). dots.ocr
# ships as a git repo (`pip install -e .`), not a PyPI package, and its own parser.py needs a vLLM
# server — so we run it in-process and drive per-page inference from /opt/dots_run.py.
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 + openssh-server (T17: every parser image runs sshd for RunPodSession) + OpenCV libs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
        git curl build-essential openssh-server \
        libxcb1 libxext6 libgl1 libsm6 libglib2.0-0 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# sshd: key-only root login (RunPod injects the key via $PUBLIC_KEY, consumed by start.sh).
RUN mkdir -p /var/run/sshd \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config

# Isolated venv so python + the dots_ocr package are deterministically on PATH (matches chandra).
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir --upgrade pip

# Seed torch + torchvision from the cu128 index FIRST (pin the CUDA build to 12.8, not above the
# RunPod host-driver ceiling). dots.ocr's card suggests torch 2.7.0 cu128 — pin it for reproducibility.
RUN pip install --no-cache-dir torch==2.7.0 torchvision==0.22.0 \
        --index-url https://download.pytorch.org/whl/cu128

# Transformers: pinning before dots.ocr does NOT work — its requirements.txt exact-pins
# transformers==4.56.1 and pip's resolver promotes it during `pip install -e`. Confirmed live on
# 0.2.1 (T17 pass 2). The real fix for the video_processor=None TypeError is the monkey-patch in
# dots_run.py (0.2.2) — see that file. Letting dots.ocr's own install resolve transformers is fine.

# Clone + install dots.ocr (it's `pip install -e .`, not on PyPI); it pulls transformers. Add
# qwen-vl-utils (process_vision_info), pypdfium2 (PDF->image, used by dots_run.py), huggingface_hub
# (weight bake). cu128 stays an EXTRA index so any torch reresolution keeps cu128 wheels.
# NO flash-attn: it's slow/fragile to build and dots_run.py uses sdpa attention.
# [VALIDATE ON POD: if dots.ocr's custom modeling requires flash_attention_2, add `flash-attn`.]
RUN git clone --depth 1 https://github.com/rednote-hilab/dots.ocr.git /opt/dots_ocr_src \
    && pip install --no-cache-dir -e /opt/dots_ocr_src qwen-vl-utils pypdfium2 huggingface_hub \
        --extra-index-url https://download.pytorch.org/whl/cu128

# Build-time guard (free, in CI): cu128 torch + the deps import GPU-free.
RUN python -c "import torch, transformers, qwen_vl_utils, pypdfium2; \
print('torch', torch.__version__, 'transformers', transformers.__version__); \
assert '+cu128' in torch.__version__, torch.__version__"

# Bake the weights into a NO-PERIODS dir: dots.ocr loads the model via trust_remote_code, so the
# directory name becomes the Python module name — `dots.ocr` would ModuleNotFoundError (documented
# workaround). dots_run.py loads from /opt/weights/DotsOCR.
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download('rednote-hilab/dots.ocr', local_dir='/opt/weights/DotsOCR')"

COPY dots_run.py /opt/dots_run.py
COPY start.sh /opt/start.sh
RUN chmod +x /opt/start.sh

# Start sshd then idle; RunPodSession execs `python /opt/dots_run.py <pdf> <out>` in the pod.
CMD ["/opt/start.sh"]
