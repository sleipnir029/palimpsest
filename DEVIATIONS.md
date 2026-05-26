# Deviations log

Every time Claude does something unexpected — good or bad — log it here. This becomes the reflection chapter of your thesis.

Template per entry:

```
## YYYY-MM-DD — T##
**What:** <what Claude did>
**Verdict:** <rejected/accepted/partially>
**Lesson:** <one sentence>
```

---

## 2026-05-26 — T01
**What:** `pymupdf4llm` has no conda-forge build, so the `pixi install` solver failed on osx-arm64. Moved it from `[dependencies]` to `[pypi-dependencies]` (per card note: prefer conda-forge, fall back to pypi if no arm64 build). `pymupdf` itself stayed on conda-forge.
**Verdict:** accepted
**Lesson:** Not every package the design lists for conda-forge actually ships there; verify at install time.

## 2026-05-26 — T01
**What:** Added `palimpsest = { path = ".", editable = true }` to `[pypi-dependencies]` — not literally in the card spec. The card's verification (`import palimpsest`) needs the src-layout package installed; this self-editable reference is pixi's standard mechanism for that.
**Verdict:** accepted
**Lesson:** src-layout + a verification that imports the package implies the project must self-install; the card omitted the line that makes it work.

## 2026-05-26 — T01
**What:** Added two things to `pyproject.toml` not in the card spec: a `[build-system]` table (`requires = ["setuptools"]`, setuptools build backend) and `requires-python = ">=3.11"`. The build-system table is load-bearing — PEP 517 editable install of the src-layout package (deviation above) needs it. `requires-python` agrees with the pixi `python = "3.11.*"` pin.
**Verdict:** accepted
**Lesson:** A pyproject that gets pip-installed editable needs a build-system table; the card's `[project]`-only spec was incomplete.

## 2026-05-26 — T08
**What:** Added a second tool `read_first_page_text(path)` (`fitz.open(path)[0].get_text()`) plus its registration and a mention in the `__main__` / e2e system prompts — beyond the card's two named files. With only `read_paper` (metadata: SHA-256/pages/size), the model correctly refused to invent a title; the literal "output contains the title" check couldn't pass. The card pre-authorizes exactly this tool as "acceptable scope expansion" and asks to log it here. User confirmed adding it over accepting the metadata-only answer. CLI now returns the real title ("Iridium single atoms incorporated in Co₃O₄ efficiently catalyze the oxygen evolution in acidic conditions", Nat. Commun. 2022).
**Verdict:** accepted
**Lesson:** A metadata-only tool can't satisfy a text question, and an honest model refuses rather than hallucinates — the card anticipated this and shipped the escape hatch with the task.

## 2026-05-26 — T09
**What:** The card's second verification snippet does `r.json().get("data", [])`, but `GET https://rest.runpod.io/v1/pods` returns a **bare JSON list**, not `{"data": [...]}`. The snippet crashes (`AttributeError: 'list' object has no attribute 'get'`) on the pod-count line — *after* the auth assert (`status_code == 200`) has already passed. Ran a shape-tolerant variant to confirm: status 200, 0 pods (test pod terminated). Pass condition (key accepted → 200) is met; only the cosmetic count line was buggy.
**Verdict:** accepted (card snippet had a latent bug; auth verification itself succeeds). **Fixed:** card snippet updated to `body if isinstance(body, list) else body.get('data', [])`; now exits 0 literally.
**Lesson:** The RunPod REST `/v1/pods` response shape is a top-level array; don't assume a `data` envelope. The card's count line was never load-bearing — 200 is the real gate.

## 2026-05-26 — T09
**What:** Used **RTX 3090** (Community Cloud) for the manual SSH connectivity test instead of the RTX 4090 named in the card, because the 4090 showed "Low" availability at deploy time. Card explicitly permits "any small GPU" for this test.
**Verdict:** accepted
**Lesson:** Availability on Community Cloud is variable; the connectivity path is GPU-agnostic, so substitute freely for a throwaway test. The 4090 is only load-bearing later (T10/T14) for the actual parsers.

## 2026-05-26 — T10
**What:** The card pins `FROM nvidia/cuda:12.1.0-devel-ubuntu22.04`. Current vLLM (0.19.1, released 2026-04-18) ships cu129 prebuilt wheels and dropped CUDA 12.1 support — torch/vLLM will not load on a 12.1 base. Bumped the Dockerfile base to **`nvidia/cuda:12.9.1-devel-ubuntu22.04`** and install torch + **`vllm==0.19.1`** from the cu129 PyTorch index (vLLM's documented default), so base runtime + torch wheel + vLLM all agree on CUDA 12.9 — enforced by a build-time `assert '+cu129' in torch.__version__`. Also dropped flash-attn (HF model card marks it optional; not named in the T10 card; saves a long nvcc build), and added a GitHub Actions workflow (`.github/workflows/build-gpu-image.yml`) as the build host since there is no local GPU/Docker — a 4th file beyond the card's three. User approved the base bump and the CI setup before code was written.
**Verdict:** accepted
**Lesson:** Pinned base-image / CUDA versions in a task card written months earlier go stale fast against a fast-moving dep like vLLM; check the dep's current CUDA support before honoring the literal pin.

## 2026-05-27 — T10
**What:** The first GitHub Actions build pushed fine to Docker Hub but RunPod refused to start the pod: `failed to pull image: layers from manifest don't match image configuration`. Cause: `docker/build-push-action@v6` (buildx ≥0.10) attaches a provenance attestation by default, publishing a multi-manifest OCI index (image manifest + in-toto attestation manifest). RunPod's image puller walks the index, hits the attestation entry whose config is not an image, and the diff_ids mismatch. Docker Hub renders the index fine, so the image *looked* healthy. Fixed by adding `provenance: false` + `sbom: false` to the build step so buildx pushes a plain single-image manifest; re-ran the workflow on the same tag.
**Verdict:** accepted (external-tooling default, not a Dockerfile bug)
**Lesson:** A "successfully pushed" image on Docker Hub is not proof it will run — buildx attestations make an OCI index that some container runtimes (RunPod) reject; for BYO-container targets, build with `provenance: false`.

## 2026-05-27 — T10
**What:** The card specifies `CMD ["bash"]` ("interactive — gpu_provider will SSH in"). On RunPod the container starts detached, so `bash` as PID 1 hits EOF and exits immediately — the pod reported `Container ... is not running` the instant SSH attached. Changed `CMD` to `["sleep", "infinity"]` so the container stays alive and RunPod's SSH proxy / web terminal can `exec` a shell into it. Immediate unblock used the RunPod template's *Container Start Command* override (`sleep infinity`) to avoid a second 30-min rebuild; the Dockerfile change bakes it in for future pods.
**Verdict:** accepted (card's CMD is platform-incompatible)
**Lesson:** A RunPod custom container needs a long-lived foreground PID 1 (`sleep infinity`); `CMD ["bash"]` only works when a TTY is attached, which a detached pod start does not provide.

## 2026-05-27 — T10
**What:** Corrected the CUDA base from **12.9.1 → 12.8.1** (and torch/vLLM cu129 → cu128). The 12.9 image failed at the nvidia container-init hook on RunPod: `unsatisfied condition: cuda>=12.9, please update your driver`. Measured RunPod's available host drivers via the deploy page's CUDA-version filter: **ceiling is 12.8** (2× RTX 3090 available). 12.8 is also vLLM 0.19.1's lowest supported CUDA and the version olmOCR's official Docker image ships, with Chandra needing only 12.1+ and MinerU on torch cu128 — so all four parsers (T11-T13) share the 12.8 base. The earlier 12.9 choice (preceding entry) maximized version-cleanliness but ignored the binding constraint: the host driver caps the runnable CUDA, and I had not measured it.
**Verdict:** accepted (corrects the 12.9 over-reach with host data)
**Lesson:** The GPU **host driver** — not vLLM's default, not the parsers — is the binding constraint on CUDA version; measure the target hosts' supported CUDA *before* pinning a base image. The build-time `+cuXXX` assert proves image-internal consistency, never host compatibility.
