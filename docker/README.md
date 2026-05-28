# palimpsest parser images

The cloud parser images. Run on a RunPod RTX 4090/3090 pod — never on the M1 dev
box (running docling locally is a project anti-pattern).

The four parsers ship as **four isolated images**, not one stacked image — their
torch/vLLM/transformers pins conflict, and a shared environment risks silently
degrading a parser (which would corrupt the parser comparison). We build three;
olmOCR uses Allen AI's upstream image as-is:

| Parser  | Dockerfile                          | Tag                      | Source         |
|---------|-------------------------------------|--------------------------|----------------|
| docling | `palimpsest-docling.Dockerfile`     | `palimpsest/docling:0.1.0` | we build (T10) |
| mineru  | `palimpsest-mineru.Dockerfile`      | `palimpsest/mineru:0.1.0`  | we build (T11) |
| olmocr  | — (upstream)                        | `alleninstituteforai/olmocr:<tag>` | upstream (T12) |
| chandra | `palimpsest-chandra.Dockerfile`     | `palimpsest/chandra:0.1.0` | we build (T13) |

Each image is ~10–15 GB. Pulled to the pod once, then cached on RunPod's side.

## Contents (example: the docling image)

- `nvidia/cuda:12.8.1-devel-ubuntu22.04` base (nvcc + CUDA 12.8 runtime).
- Python 3.11 in `/opt/venv` (on `PATH`).
- `vllm==0.19.1` (cu128 wheels) + `docling` + `docling-ibm-models`.
- `ibm-granite/granite-docling-258M` weights baked into `/root/.cache/huggingface`
  (default + `untied` revisions), so the first pod run does not download.
- `CMD ["sleep", "infinity"]` — keeps the container alive so RunPod can exec/SSH
  in (a bare `bash` exits immediately on a detached pod start). `gpu_provider`
  (T14) execs the parser's command in the running container.

The mineru / chandra images follow the same skeleton but install their own parser
and weights, and do **not** pin vLLM (each image owns its own torch/vLLM).

> **CUDA note (deviation from task card):** the card pins CUDA 12.1.0, but vLLM
> 0.19.x dropped 12.1. The base is 12.8.1 — the ceiling RunPod's host drivers
> support, used by every image we build (the upstream olmOCR image is also 12.8).
> For docling, base/torch/vLLM agreement is asserted at build. See `DEVIATIONS.md`.

## Build

Build needs an **amd64 Docker host with ~40 GB free disk**. No GPU is needed to
*build* — the GPU is only used at runtime. Docker Hub repos are flat (`user/repo`),
so the push target is `<your-user>/palimpsest-<parser>:0.1.0`.

**Canonical path (no local Docker): GitHub Actions → Docker Hub.** The workflow
`.github/workflows/build-gpu-image.yml` builds each image we own (matrix over
`docling`, `mineru`; `chandra` added in T13) natively on an amd64 runner and pushes.
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
   `docker.io/<your-user>/palimpsest-<parser>:0.1.0` (or the upstream image for olmOCR).
2. Deploy a pod on that template (RTX 4090 / 3090). Ensure your SSH key is in
   RunPod Settings *before* deploy (see `notes/runpod-bootstrap.md`).
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
