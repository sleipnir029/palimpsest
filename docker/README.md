# palimpsest parser images

The cloud parser images. Run on a RunPod RTX 4090/3090 pod — never on the M1 dev
box (running docling locally is a project anti-pattern).

The five parsers ship as **five isolated images**, not one stacked image — their
torch/vLLM/transformers (and Paddle) pins conflict, and a shared environment risks
silently degrading a parser (which would corrupt the parser comparison). We build all five:

| Parser  | Dockerfile                          | Tag                        | Source         |
|---------|-------------------------------------|----------------------------|----------------|
| docling | `palimpsest-docling.Dockerfile`     | `palimpsest/docling:0.2.0` | we build (T10) |
| mineru  | `palimpsest-mineru.Dockerfile`      | `palimpsest/mineru:0.2.0`  | we build (T11) |
| chandra | `palimpsest-chandra.Dockerfile`     | `palimpsest/chandra:0.2.0` | we build (T13) |
| dots    | `palimpsest-dots.Dockerfile`        | `palimpsest/dots:0.2.0`    | we build (T17) |
| paddle  | `palimpsest-paddle.Dockerfile`      | `palimpsest/paddle:0.2.0`  | we build (T17) |

Each image is ~10–15 GB. Pulled to the pod once, then cached on RunPod's side.

## Contents (example: the docling image)

- `nvidia/cuda:12.8.1-devel-ubuntu22.04` base (nvcc + CUDA 12.8 runtime).
- Python 3.11 in `/opt/venv` (on `PATH`).
- `vllm==0.19.1` (cu128 wheels) + `docling` + `docling-ibm-models`.
- `ibm-granite/granite-docling-258M` weights baked into `/root/.cache/huggingface`
  (default + `untied` revisions), so the first pod run does not download.
- `CMD ["/opt/start.sh"]` (T17) — starts `sshd` (every image runs an SSH daemon so
  `gpu_provider` (T14) reaches it over direct TCP SSH + scp), injects the pod's
  `$PUBLIC_KEY` into authorized_keys, then idles (`sleep infinity`) to keep the
  container alive. `gpu_provider` execs the parser's command in the running container.

The mineru / chandra images follow the same skeleton but install their own parser
and weights, and do **not** pin vLLM (each image owns its own torch/vLLM).

> **CUDA note:** the torch images (docling/mineru/chandra/dots) use base 12.8.1 — the
> ceiling RunPod's host drivers support; base/torch agreement is asserted at build. The
> **paddle** image is the exception: CUDA **12.6** (PaddlePaddle publishes no py3.11 cu128
> wheel), which still runs on ≥12.8 hosts via CUDA backward-compat. See `DEVIATIONS.md`.

## Build

Build needs an **amd64 Docker host with ~40 GB free disk**. No GPU is needed to
*build* — the GPU is only used at runtime. Docker Hub repos are flat (`user/repo`),
so the push target is `<your-user>/palimpsest-<parser>:0.2.0`.

**Canonical path (no local Docker): GitHub Actions → Docker Hub.** The workflow
`.github/workflows/build-gpu-image.yml` builds each image (matrix over
`docling`, `mineru`, `chandra`, `paddle`, `dots`) natively on an amd64 runner and pushes.
Set repo secrets `DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN`, then run the workflow
manually (Actions tab → "Build parser images" → Run workflow).

**On an amd64 Docker host you control** (cloud VM, or Docker Desktop with
`--platform linux/amd64` — slow QEMU on Apple silicon), build one parser at a time:

```bash
DOCKERHUB_USERNAME=<your-user> ./docker/build.sh mineru push
```

## Run on RunPod

RunPod runs **pre-built images** — it does not build Dockerfiles. After pushing,
register one custom template per parser (see `runpod-template.md`, created in T12, extended in T13):

1. Console → Templates → **New Template** → Custom → Container Image =
   `docker.io/<your-user>/palimpsest-<parser>:0.2.0`, and set env `PUBLIC_KEY` to the
   contents of your `~/.ssh/id_ed25519.pub` (T17: the images run sshd; this key authenticates SSH).
2. Deploy a pod on that template (RTX 4090 / 3090). See `runpod-template.md` for per-parser detail.
3. SSH in and verify the parser, e.g.:

   ```bash
   docling --version    # or: mineru --version
   ```

4. **Stop the pod within ~5 min** — cost discipline.

Serving the docling model later (T14) uses the `untied` weights:

```bash
vllm serve ibm-granite/granite-docling-258M --revision untied \
    --gpu-memory-utilization 0.9
```
