# palimpsest GPU image

The cloud parser image. Runs on a RunPod RTX 4090/3090 pod — never on the M1 dev
box (running docling locally is a project anti-pattern). T10 ships the docling
layer; T11–T13 (MinerU / olmOCR / Chandra) extend this same image.

## Contents

- `nvidia/cuda:12.9.1-devel-ubuntu22.04` base (nvcc + CUDA 12.9 runtime).
- Python 3.11 in `/opt/venv` (on `PATH`).
- `vllm==0.19.1` (cu129 wheels) + `docling` + `docling-ibm-models`.
- `ibm-granite/granite-docling-258M` weights baked into `/root/.cache/huggingface`
  (default + `untied` revisions), so the first pod run does not download.
- `CMD ["bash"]` — interactive; the `gpu_provider` (T14) SSHes in.

Image is ~10–15 GB. Pulled to the pod once, then cached on RunPod's side.

> **CUDA note (deviation from task card):** the card pins CUDA 12.1.0, but vLLM
> 0.19.x dropped 12.1 and ships cu129 wheels. Base bumped to 12.9.1 + cu129 wheels
> so base runtime, torch, and vLLM agree (asserted at build time). See `DEVIATIONS.md`.

## Build

Build needs an **amd64 Docker host with ~40 GB free disk**. No GPU is needed to
*build* — the GPU is only used at runtime by `vllm serve`. Docker Hub repos are
flat (`user/repo`), so the push target is `<your-user>/palimpsest-gpu:0.1.0-docling`.

**Canonical path (no local Docker): GitHub Actions → Docker Hub.** The workflow
`.github/workflows/build-gpu-image.yml` builds natively on an amd64 runner and
pushes. Set repo secrets `DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN`, then run the
workflow manually (Actions tab → "Build GPU image" → Run workflow).

**On an amd64 Docker host you control** (cloud VM, or Docker Desktop with
`--platform linux/amd64` — slow QEMU on Apple silicon):

```bash
PUSH_TAG=docker.io/<your-user>/palimpsest-gpu:0.1.0-docling ./docker/build.sh push
```

## Run on RunPod

RunPod runs **pre-built images** — it does not build Dockerfiles. After pushing:

1. Console → Templates → **New Template** → Custom → Container Image =
   `docker.io/<your-user>/palimpsest-gpu:0.1.0-docling`.
2. Deploy a pod on that template (RTX 4090 / 3090). Ensure your SSH key is in
   RunPod Settings *before* deploy (see `notes/runpod-bootstrap.md`).
3. SSH in and verify:

   ```bash
   docling --version
   ```

   A version string is T10's required deliverable.

4. **Stop the pod within ~5 min** — cost discipline.

Serving the model later (T14) uses the `untied` weights:

```bash
vllm serve ibm-granite/granite-docling-258M --revision untied \
    --gpu-memory-utilization 0.9
```
