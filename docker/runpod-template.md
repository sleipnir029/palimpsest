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
| olmocr  | `alleninstituteforai/olmocr:latest-with-model`   | **RTX 4090 only** | upstream (T12) |
| chandra | _added in T13_                                   | —                 | we build (T13) |

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
- Container Start Command: `-c "sleep infinity"`
  > The upstream image's `ENTRYPOINT` is `/bin/bash` (its own run example is
  > `docker run … olmocr:latest-with-model -c "olmocr …"`). A bare `sleep infinity` would be
  > parsed as `/bin/bash sleep infinity` and fail; `-c "sleep infinity"` runs
  > `/bin/bash -c "sleep infinity"`. Same liveness need as our images' `CMD ["sleep","infinity"]`
  > (T10), different syntax because of the bash entrypoint. **Confirm on the first pod.**
- GPU: **RTX 4090 (Ada)** — the FP8 model needs Ada/Hopper FP8 support; an RTX 3090
  (Ampere) will not run it. (docling/mineru are fine on a 3090; olmOCR is not.)
- Disk: **≥ 50 GB** (~30 GB image + weights + work-dir headroom).
- CUDA: 12.8 (`FROM vllm/vllm-openai:v0.11.2`) = RunPod's host-driver ceiling. No bump needed.
- Run form: `olmocr /workspace/out --markdown --pdfs /workspace/sample.pdf`
  ≡ `python -m olmocr.pipeline …`.

### Verify on the pod (from the T12 card, verbatim)

```bash
python -m olmocr.pipeline --help
python -c "from huggingface_hub import snapshot_download; import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--allenai--olmOCR-2-7B-1025'))"
```

First prints help. Second exits 0 **if** the weights are baked at that exact path.

### Confirm on first pod spin-up (open empirical items)

The card deliberately defers these to a live pod — do not lock them in from docs:

1. **Exact tag.** `:latest-with-model` is not reproducible. Once a pod confirms the image,
   pin to the dated/version tag that ships the 1025 model (the v0.4.x release, Oct 2025).
2. **FP8 path mismatch.** The baked model is the FP8 variant, so the weights likely live at
   `models--allenai--olmOCR-2-7B-1025-FP8`, **not** the card's `…-1025`. If the verbatim
   assert above fails on that path, confirm the real path and — per the card — verify a
   **real parse run** instead; do not assume the image is wrong.
3. **Entrypoint form.** Confirm `python -m olmocr.pipeline` works as well as the `olmocr`
   console script, and that `-c "sleep infinity"` keeps the pod alive.
4. **GPU.** Confirm FP8 inference actually initializes on the chosen 4090 pod.
