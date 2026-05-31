# RunPod custom templates — parser pods

RunPod runs **pre-built images**; it does not build Dockerfiles. Each parser runs on its own pod
from a custom template (the five parsers ship as five isolated images — see `README.md`). This
file is the template registry: one entry per parser. We build **all five** ourselves.

| Parser  | Container Image                                  | GPU             | Source         |
|---------|--------------------------------------------------|-----------------|----------------|
| docling | `docker.io/<your-user>/palimpsest-docling:0.2.0` | RTX 4090 / 3090 | we build (T10) |
| mineru  | `docker.io/<your-user>/palimpsest-mineru:0.2.0`  | RTX 4090 / 3090 | we build (T11) |
| chandra | `docker.io/<your-user>/palimpsest-chandra:0.2.0` | RTX 4090 / 3090 | we build (T13) |
| dots    | `docker.io/<your-user>/palimpsest-dots:0.2.0`    | RTX 4090 / 3090 | we build (T17) |
| paddle  | `docker.io/<your-user>/palimpsest-paddle:0.2.0`  | RTX 4090 / 3090 | we build (T17) |

> **`0.2.0` = the sshd era (T17).** Every image now runs an SSH daemon so `gpu_provider`'s (T14)
> `RunPodSession` reaches it over **direct TCP SSH** (publicIp + mapped port 22) — required for
> `scp_up`/`scp_down`. olmOCR was dropped in T17 (FP8/Ada-only vendor image, no sshd; see
> DEVIATIONS.md). The `0.1.0` images had no sshd; re-pull `0.2.0`.

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

> **Common pod-verify gotchas (T17, 2026-05-31).** All five images share these. T16's `commands.py`
> must handle them until baked into 0.2.1: (a) sshd login shell does NOT inherit Dockerfile `ENV
> PATH` — prepend `export PATH=/opt/venv/bin:$PATH && ` to every parser invocation; (b) every image
> needs `libxcb1 libxext6 libgl1 libsm6 libglib2.0-0 libxrender1` apt-installed once at pod boot
> (cv2 dlopens these at parse time); (c) `_await_running` needs ≥ 900s on SECURE first-pull;
> (d) RunPod multi-id `gpuTypeIds` is rejected with 500 — iterate one id at a time (fixed in
> `gpu_provider.py` per `fb44ef1`); (e) fabric `Connection.run` default `timeout=600s` and the
> watchdog's `idle_hard=300s` are both too short for multi-minute parses — pass `timeout=1800` and
> set `idle_hard=1800` in `RunPodSession`.

### docling — `palimpsest-docling:0.2.0`
- Disk ~25 GB (image + `granite-docling-258M` baked). Verify: `docling --version` → `Docling 2.95.0`
  (pod-verified, T10). Run `docling … --to json`.
- **Pod-verified end-to-end (T17, 2026-05-31, SECURE 3090, €0.0065, 100s):**
  `docling /workspace/in/<pdf> --output /workspace/out --to json` → writes `<stem>.json` (19 MB on
  the 12-page sample paper, 645 text items + tables + pictures).

### mineru — `palimpsest-mineru:0.2.0`
- Disk ~25 GB (image + `MinerU2.5-2509-1.2B` baked). Verify:
  `python -c "import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B'))"`.
- **Pod-verified end-to-end (T17, 2026-05-31, SECURE 3090, €0.0295, 428s):**
  `mineru -p /workspace/in/<pdf> -o /workspace/out -b vlm-auto-engine` → writes
  `<stem>/vlm/<stem>_content_list_v2.json` (315 KB on the 12-page sample; list of 12 pages with
  equation_inline + bbox; the real paper title was extracted).
- **Runtime install needed**: `pip install --no-cache-dir vllm==0.19.1` — `mineru[all]` does NOT
  pull vllm; `vlm-auto-engine` errors with "Please install vllm" otherwise. Bake into 0.2.1.
- **CLI changed**: T11's `-b vlm` is gone in mineru 2.5; use `vlm-auto-engine` (in-process) or
  `vlm-http-client`.

### chandra — `palimpsest-chandra:0.2.0`
- Disk ~35 GB (image + ~10 GB `chandra-ocr-2`). BF16 → an Ampere 3090 works. Verify:
  `chandra --help` (no `--version` flag) + the `models--datalab-to--chandra-ocr-2` cache path.
- **Pod-verified parse (T17, 2026-05-31, SECURE 3090, €0.20, 31 min):**
  `chandra /workspace/in/<pdf> /workspace/out --method hf` → writes `<stem>/<stem>.md` (content,
  **scp THIS**) and `<stem>/<stem>_metadata.json` (12 pages × 33,809 tokens × 168 chunks × 4
  images per the metadata; the model did the work; content NOT yet retrieved end-to-end because
  the verify script's "newest .json" picker grabbed the metadata stub).
- Slow on 3090 HF backend (~140s/page on a 12-page paper). Pass `idle_hard=1800` and `timeout=1800`.

### dots — `palimpsest-dots:0.2.0` (T17, new)
- dots.ocr (`rednote-hilab/dots.ocr`, ~1.7B VLM, **MIT**), BF16 → 3090/4090. Disk ~25 GB.
- Weights baked to `/opt/weights/DotsOCR` (no-periods dir — the trust_remote_code module-name
  workaround). Run via the baked wrapper: `python /opt/dots_run.py <pdf> <out.json>` (transformers
  in-process, `sdpa` attention — no vLLM server, no flash-attn). Verify: `ls /opt/weights/DotsOCR`
  then a one-page parse.
- **⏳ Pod-verify deferred (T17, 2026-05-31):** `Qwen2_5_VLProcessor.check_argument_for_proper_class`
  refuses `video_processor=None`. Wrapper fix `docker/dots_run.py` (skip `videos=` kwarg when None)
  + Dockerfile pin `transformers==4.51.3` (dots README floor) staged for 0.2.1; verify after rebuild.

### paddle — `palimpsest-paddle:0.2.0` (T17, new)
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
