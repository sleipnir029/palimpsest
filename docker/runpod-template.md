# RunPod custom templates — parser pods

RunPod runs **pre-built images**; it does not build Dockerfiles. Each parser runs on its own pod
from a custom template (the five parsers ship as five isolated images — see `README.md`). This
file is the template registry: one entry per parser. We build **all five** ourselves.

| Parser  | Container Image                                  | GPU             | Source         |
|---------|--------------------------------------------------|-----------------|----------------|
| docling | `docker.io/<your-user>/palimpsest-docling:0.2.2` | RTX 4090 / 3090 | we build (T10) |
| mineru  | `docker.io/<your-user>/palimpsest-mineru:0.2.2`  | RTX 4090 / 3090 | we build (T11) |
| chandra | `docker.io/<your-user>/palimpsest-chandra:0.2.2` | RTX 4090 / 3090 | we build (T13) |
| dots    | `docker.io/<your-user>/palimpsest-dots:0.2.2`    | RTX 4090 / 3090 | we build (T17) |
| paddle  | `docker.io/<your-user>/palimpsest-paddle:0.2.2`  | RTX 4090 / 3090 | we build (T17) |

> **Image tag = the contract between Docker Hub and the RunPod template.** The template's
> `imageName` points to a specific `:<tag>`; RunPod pulls that tag on each pod-create. Bumping the
> tag (in `docker/build.sh`, `.github/workflows/build-gpu-image.yml`, this table, and the per-parser
> headers below) is what forces RunPod to pull a fresh image. Updating the 5 templates' `imageName`
> via `PATCH /v1/templates/<id>` keeps the template IDs stable (so `.env`'s `RUNPOD_TEMPLATE_*`
> don't rotate) but swaps in the new tag.
>
> **Version history (the sshd-era line, T17, late 2026-05-29 → 2026-05-31):**
> - `0.1.0` — pre-sshd. Reachable only via RunPod's proxy SSH / web terminal. Do not use.
> - `0.2.0` — **sshd in all five images** via shared `docker/start.sh` (consumes `$PUBLIC_KEY`,
>   runs `sshd`, idles). `gpu_provider`'s (T14) `RunPodSession` now reaches pods over **direct TCP
>   SSH** (publicIp + mapped port 22). olmOCR was dropped (FP8/Ada-only vendor image, no sshd we
>   control — DEVIATIONS.md, T12 superseded).
> - `0.2.1` — bakes T17 verify findings: `start.sh` writes `/etc/environment` so sshd sessions
>   inherit `/opt/venv/bin` on PATH; all 5 Dockerfiles gain `libxcb1 libxext6 libgl1 libsm6
>   libglib2.0-0 libxrender1` (cv2 dlopens these at parse time); `palimpsest-mineru.Dockerfile`
>   pins `vllm==0.19.1` explicitly (`mineru[all]` does NOT pull it). 4/5 verified end-to-end.
> - `0.2.2` — bakes the dots fix (`docker/dots_run.py` monkey-patches
>   `ProcessorMixin.check_argument_for_proper_class` to allow `video_processor=None` for image-only
>   models; transformers 4.56.1 from dots.ocr's `requirements.txt` is unchanged). 5/5 verified.

## Register a template (RunPod console or `POST /v1/templates`)

1. **Container Image** = the value from the table.
2. **Container Start Command** = _leave blank_ — every image's `CMD` is `/opt/start.sh`, which
   starts `sshd` and then idles (`sleep infinity`) to keep the container alive.
3. **Env `PUBLIC_KEY`** = the contents of your `~/.ssh/id_ed25519.pub`. `start.sh` appends it to
   `authorized_keys`; this is what makes direct TCP SSH authenticate. **RunPod does NOT auto-inject
   account keys into custom images**, so set `PUBLIC_KEY` per template (the T14/T17 lesson — a base
   image only worked because the key was set explicitly in its template env).
4. **Port 22** is requested by `RunPodSession` at pod-create (`ports:["22/tcp"]`), so no template
   port field is needed.
5. **Container Disk** = per parser (see below).
6. **Idle teardown** — `RunPodSession`'s watchdog stops the pod (≤5 min idle); cost discipline (€50 cap).

## Per-parser

> **Common contract — what's baked vs what T16's `commands.py` still owns (0.2.2).**
> Image-side (baked, T16 should NOT re-do these):
> - `/opt/start.sh` writes `/etc/environment` → sshd sessions inherit `/opt/venv/bin` on PATH. No
>   `export PATH=` prefix needed.
> - Every image has `libxcb1 libxext6 libgl1 libsm6 libglib2.0-0 libxrender1` (cv2 dlopen). No
>   runtime apt-get.
> - mineru bakes `vllm==0.19.1`. No runtime `pip install vllm`.
> - dots bakes the `ProcessorMixin.check_argument_for_proper_class` monkey-patch. No
>   runtime patching.
> - All five run sshd; `RunPodSession` reaches them via direct TCP SSH on port 22.
>
> Caller-side (T16's `commands.py` MUST handle):
> - `_await_running` ≥ 900s on SECURE first-pull (default in `gpu_provider.py` per `c753cac`).
> - Multi-id `gpuTypeIds` is NOT "any of" — iterate one id at a time (fixed in `gpu_provider.py`
>   per `fb44ef1`).
> - fabric `Connection.run` default `timeout=600s` and `idle_hard=300s` are too short for
>   multi-minute parses — pass `timeout=1800` and set `idle_hard=1800` on long parsers (chandra,
>   dots, mineru).
> - The output file path is parser-specific (see each section below). Don't rely on "newest .json".

### docling — `palimpsest-docling:0.2.2`
- Disk ~25 GB (image + `granite-docling-258M` baked). Verify: `docling --version` → `Docling 2.95.0`
  (pod-verified, T10). Run `docling … --to json`.
- **Pod-verified end-to-end (T17, 2026-05-31, SECURE 3090, €0.0065, 100s):**
  `docling /workspace/in/<pdf> --output /workspace/out --to json` → writes `<stem>.json` (19 MB on
  the 12-page sample paper, 645 text items + tables + pictures).

### mineru — `palimpsest-mineru:0.2.2`
- Disk ~25 GB (image + `MinerU2.5-2509-1.2B` baked). Verify:
  `python -c "import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B'))"`.
- **Pod-verified end-to-end (T17, 2026-05-31, SECURE 3090, €0.0295, 428s):**
  `mineru -p /workspace/in/<pdf> -o /workspace/out -b vlm-auto-engine` → writes
  `<stem>/vlm/<stem>_content_list_v2.json` (315 KB on the 12-page sample; list of 12 pages with
  equation_inline + bbox; the real paper title was extracted).
- **vllm baked** since 0.2.1: `mineru[all]` does NOT pull vllm and `vlm-auto-engine` errors with
  "Please install vllm" otherwise. The Dockerfile pins `vllm==0.19.1` explicitly post-`mineru[all]`.
- **CLI changed**: T11's `-b vlm` is gone in mineru 2.5; use `vlm-auto-engine` (in-process) or
  `vlm-http-client`.

### chandra — `palimpsest-chandra:0.2.2`
- Disk ~35 GB (image + ~10 GB `chandra-ocr-2`). BF16 → an Ampere 3090 works. Verify:
  `chandra --help` (no `--version` flag) + the `models--datalab-to--chandra-ocr-2` cache path.
- **Pod-verified end-to-end (T17 pass 2, 2026-05-31, SECURE 3090, €0.18, 1664s on 0.2.1):**
  `chandra /workspace/in/<pdf> /workspace/out --method hf` → writes `<stem>/<stem>.md` (content,
  **scp THIS** — 84.5 KB on the 12-page sample, real paper title + authors + abstract) and
  `<stem>/<stem>_metadata.json` (page counts, tokens, chunks). T16 must scp the `.md` explicitly;
  do NOT rely on "newest .json" — that grabs the metadata stub.
- Slow on 3090 HF backend (~140s/page on a 12-page paper). Pass `idle_hard=1800` and `timeout=1800`.

### dots — `palimpsest-dots:0.2.2` (T17)
- dots.ocr (`rednote-hilab/dots.ocr`, ~1.7B VLM, **MIT**), BF16 → 3090/4090/L4 all work. Disk ~25 GB.
- Weights baked to `/opt/weights/DotsOCR` (no-periods dir — the trust_remote_code module-name
  workaround). Run via the baked wrapper: `python /opt/dots_run.py <pdf> <out.json>` (transformers
  in-process, `sdpa` attention — no vLLM server, no flash-attn).
- **Pod-verified end-to-end (T17 pass 3, 2026-05-31, SECURE L4, €0.08, 1040s on 0.2.2):**
  `python /opt/dots_run.py /workspace/in/<pdf> /workspace/out/dots.json` → writes `dots.json`
  (165 KB on the 12-page sample, `{markdown, pages}` envelope, 72,207 chars markdown, real paper
  title + authors + DOI).
- **The dots fix** (baked into 0.2.2): dots.ocr's `requirements.txt` exact-pins
  `transformers==4.56.1`, which gained `ProcessorMixin.check_argument_for_proper_class` that
  Qwen2_5_VLProcessor calls on `video_processor` and rejects None for image-only models. Neither a
  transformers downgrade (pip resolver wins) nor `use_fast=True` (silently falls back to slow)
  works. `dots_run.py` monkey-patches `check_argument_for_proper_class` to no-op when
  `arg is None AND attribute_name == "video_processor"` — surgical, attribute-scoped.

### paddle — `palimpsest-paddle:0.2.2` (T17, new)
- PaddleOCR PP-StructureV3 (`paddleocr[doc-parser]`, **Apache-2.0**) — the only **non-torch** image
  (PaddlePaddle on **CUDA 12.6**; the cu128 Paddle index has no py3.11 wheel, and cu126 runs on
  RunPod's ≥12.8 hosts via backward-compat). Disk ~20 GB.
- **Pod-verified end-to-end (T17, 2026-05-31, SECURE 3090, €0.0174, 283s):**
  `python /opt/paddle_run.py /workspace/in/<pdf> /workspace/out/paddle.json` → writes
  `paddle.json` (869 KB on the 12-page sample, `{markdown, pages}` envelope).

## SSH verification (all five — T17)
Direct TCP SSH now works because each image runs `sshd`:
`ssh root@<publicIp> -p <mapped-port> -i ~/.ssh/id_ed25519` (or just let `RunPodSession` do it).
Pre-T17 these custom images had no sshd and were reachable only via RunPod's proxy SSH / web
terminal; that limitation is gone.
