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

### docling — `palimpsest-docling:0.2.0`
- Disk ~25 GB (image + `granite-docling-258M` baked). Verify: `docling --version` → `Docling 2.95.0`
  (pod-verified, T10). Run `docling … --to json`.

### mineru — `palimpsest-mineru:0.2.0`
- Disk ~25 GB (image + `MinerU2.5-2509-1.2B` baked). Verify:
  `python -c "import os; assert os.path.exists(os.path.expanduser('~/.cache/huggingface/hub/models--opendatalab--MinerU2.5-2509-1.2B'))"`.
  Run `mineru -b vlm`.

### chandra — `palimpsest-chandra:0.2.0`
- Disk ~35 GB (image + ~10 GB `chandra-ocr-2`). BF16 → an Ampere 3090 works. Verify:
  `chandra --help` (no `--version` flag) + the `models--datalab-to--chandra-ocr-2` cache path.
  Run `chandra <pdf> <outdir> --method hf` (HF backend, in-process; pod-verified T13).

### dots — `palimpsest-dots:0.2.0` (T17, new)
- dots.ocr (`rednote-hilab/dots.ocr`, ~1.7B VLM, **MIT**), BF16 → 3090/4090. Disk ~25 GB.
- Weights baked to `/opt/weights/DotsOCR` (no-periods dir — the trust_remote_code module-name
  workaround). Run via the baked wrapper: `python /opt/dots_run.py <pdf> <out.json>` (transformers
  in-process, `sdpa` attention — no vLLM server, no flash-attn). Verify: `ls /opt/weights/DotsOCR`
  then a one-page parse.

### paddle — `palimpsest-paddle:0.2.0` (T17, new)
- PaddleOCR PP-StructureV3 (`paddleocr[doc-parser]`, **Apache-2.0**) — the only **non-torch** image
  (PaddlePaddle on **CUDA 12.6**; the cu128 Paddle index has no py3.11 wheel, and cu126 runs on
  RunPod's ≥12.8 hosts via backward-compat). Disk ~20 GB. Run via the baked wrapper:
  `python /opt/paddle_run.py <pdf> <out.json>`. Verify:
  `python -c "import paddle; print(paddle.is_compiled_with_cuda())"` then a one-page parse.

## SSH verification (all five — T17)
Direct TCP SSH now works because each image runs `sshd`:
`ssh root@<publicIp> -p <mapped-port> -i ~/.ssh/id_ed25519` (or just let `RunPodSession` do it).
Pre-T17 these custom images had no sshd and were reachable only via RunPod's proxy SSH / web
terminal; that limitation is gone.
