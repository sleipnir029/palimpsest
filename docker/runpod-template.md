# RunPod custom templates — parser pods

RunPod runs **pre-built images**; it does not build Dockerfiles. Each parser runs on its
own pod from a custom template (the four parsers ship as four isolated images — see
`README.md`). This file is the template registry: one entry per parser. We build
docling / mineru / chandra; **olmOCR uses Allen AI's upstream image as-is** (its dependency
pins are the tightest of the four, so Allen AI ships its own image — the "hybrid" leg).

| Parser  | Container Image                                  | GPU               | Source         |
|---------|--------------------------------------------------|-------------------|----------------|
| docling | `docker.io/<your-user>/palimpsest-docling:0.1.0` | RTX 4090 / 3090   | we build (T10) |
| mineru  | `docker.io/<your-user>/palimpsest-mineru:0.1.0`  | RTX 4090 / 3090   | we build (T11) |
| olmocr  | `alleninstituteforai/olmocr:latest-with-model`   | **Ada+ (FP8)**    | upstream (T12) |
| chandra | `docker.io/<your-user>/palimpsest-chandra:0.1.0` | RTX 4090 / 3090   | we build (T13) |

## Register a template (RunPod console)

1. Console → **Templates** → **New Template** → **Custom**.
2. **Container Image** = the value from the table.
3. **Container Start Command** = per parser (see below) — must keep the container alive so
   `gpu_provider` (T14) can exec/SSH in.
4. **Container Disk / Volume** = per parser (see below).
5. SSH: put your key in RunPod **Settings → SSH Public Keys *before* deploy** — a restart
   does not re-inject it (see `notes/runpod-bootstrap.md`). Deploy → SSH over TCP.
6. **Stop the pod within ~5 min of finishing** — cost discipline (€50 cap).

## docling — `palimpsest/docling:0.1.0`

- Container Image: `docker.io/<your-user>/palimpsest-docling:0.1.0`
- Container Start Command: _(leave blank — the image `CMD` is already `sleep infinity`)_
- Disk: ~25 GB (image + `granite-docling-258M` baked).
- Verify on the pod: `docling --version` → `Docling 2.95.0` (verified on a 3090 pod, T10).

## mineru — `palimpsest/mineru:0.1.0`

- Container Image: `docker.io/<your-user>/palimpsest-mineru:0.1.0`
- Container Start Command: _(leave blank — the image `CMD` is already `sleep infinity`)_
- Disk: ~25 GB (image + `MinerU2.5-2509-1.2B` baked).
- Verify on the pod:
  ```bash
  mineru --version
  python -c "import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B'))"
  ```
- Run with `mineru -b vlm` (VLM mode) — wired in T16's parser registry.

## olmocr — upstream `alleninstituteforai/olmocr:latest-with-model`

We do **not** build olmOCR. The `latest-with-model` image (~30 GB) bakes the default model,
which is the **FP8** variant `allenai/olmOCR-2-7B-1025-FP8` (README; the base `:latest`
bakes no weights — its root Dockerfile has no download step).

- Container Image: `alleninstituteforai/olmocr:latest-with-model`
- Container Start Command: `sleep infinity`
  > **Confirmed on a pod (2026-05-28):** RunPod **shell-wraps** this field (`sh -c "<field>"`),
  > so it does NOT append to the image's `/bin/bash` ENTRYPOINT the way `docker run` would.
  > `-c "sleep infinity"` was tried first and the container exited immediately
  > (`container … is not running` on connect) because `sh -c '-c "sleep infinity"'` runs a
  > command literally named `-c`. **Bare `sleep infinity` is correct.** Same liveness need as
  > our own images' baked `CMD ["sleep","infinity"]` (T10).
- GPU: **any Ada / Hopper / Blackwell** (FP8) — RTX 4090, **RTX 4000 Ada (20 GB, cheapest Ada)**,
  L4, L40S, H100. An RTX 3090 / A100 (Ampere) will **not** run the FP8 checkpoint.
  (docling/mineru are fine on a 3090; olmOCR is not.) On a 20 GB card watch for vLLM OOM →
  lower `--gpu-memory-utilization`.
- Disk: **≥ 50 GB** (~30 GB image + weights + work-dir headroom).
- CUDA: 12.8 (`FROM vllm/vllm-openai:v0.11.2`) = RunPod's host-driver ceiling. No bump needed.
- Run form: `olmocr /workspace/out --markdown --pdfs /workspace/sample.pdf`
  ≡ `python -m olmocr.pipeline …`.

### Verify on the pod (from the T12 card, verbatim)

Access: RunPod **Web Terminal**, or **Basic SSH** via the proxy
(`ssh <pod-id>@ssh.runpod.io -i <key>` — confirmed working 2026-05-28). The image has **no
sshd**, so "SSH over exposed TCP" (direct `root@ip`) will not work; the proxy / web terminal
`exec` into the running container instead (which is why the container must stay alive).

```bash
python -m olmocr.pipeline --help
python -c "from huggingface_hub import snapshot_download; import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--allenai--olmOCR-2-7B-1025'))"
```

First prints help. Second exits 0 **if** the weights are baked at that exact path — expected to
**fail** here (the real dir is likely `…-1025-FP8`; confirm with
`ls ~/.cache/huggingface/hub/ | grep -i olmocr`, then verify a real parse — see status below).

### Confirm on first pod spin-up — status

**Resolved this session (2026-05-28):**
- Container Start Command is **`sleep infinity`** (the `-c` form exited the container — see above).
- Pod access via RunPod proxy SSH / Web Terminal works for this custom image (no sshd needed).

**Still deferred — no GPU available 2026-05-28, model verification postponed:**
1. **`--help` + baked weights path.** Run the two commands above; the baked dir is expected to
   be `models--allenai--olmOCR-2-7B-1025-FP8`, **not** the card's `…-1025`, so that verbatim
   assert will likely fail. Confirm the real path (`ls … | grep -i olmocr`) and, per the card,
   verify a real parse run; do not assume the image is wrong.
2. **FP8 init.** Confirm the FP8 model loads on the chosen Ada GPU (e.g. RTX 4000 Ada, 20 GB).
3. **Exact tag.** `:latest-with-model` is not reproducible — pin to the dated v0.4.x tag
   (Oct 2025) once a pod confirms which tag ships the 1025 model.

## chandra — `palimpsest/chandra:0.1.0`

- Container Image: `docker.io/<your-user>/palimpsest-chandra:0.1.0`
- Container Start Command: _(leave blank — the image `CMD` is already `sleep infinity`)_
- Disk: ~35 GB (image + ~10 GB `chandra-ocr-2` weights baked).
- GPU: RTX 4090 / 3090 — Chandra OCR 2 is ~5B params in **BF16**, so an Ampere 3090 works
  (unlike olmOCR's FP8, which needs Ada+). ~10 GB weights fit comfortably on 24 GB.
- Verify on the pod (Chandra has **no `--version` flag** — confirmed from the project README / PyPI;
  use `--help` + `pip show`):
  ```bash
  chandra --help
  pip show chandra-ocr      # installed version (0.2.0)
  python -c "import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--datalab-to--chandra-ocr-2'))"
  ```
- Run with `chandra <pdf> <outdir> --method hf` (HuggingFace/transformers, in-process) — wired in
  T16's parser registry. (Base `chandra-ocr` is only the OpenAI-API client; the image bakes the
  `[hf]` backend so the model runs in-process — see DEVIATIONS.md, T13.)
