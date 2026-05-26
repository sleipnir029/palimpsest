# T09 — RunPod account + API key + manual test pod

## Why
All four parsers run on RunPod RTX 4090. Need an account, an API key, and confirmation that we can start and stop a pod manually before automating it in T14.

## Input state
- T08 merged. Agent works end-to-end with one tool.

## Output state
- RunPod account exists. Credit added (at least $5).
- API key generated and saved to `.env` as `RUNPOD_API_KEY=...`.
- One pod started manually via RunPod web UI (any small GPU, e.g. RTX 4090 community cloud). Confirmed SSH access works (`ssh root@<pod-ip> -p <port>` connects). Pod stopped within 5 minutes (cost < $0.05).
- Notes on the pod ID, IP, SSH command saved to `notes/runpod-bootstrap.md` (create the `notes/` dir if needed; it's not in the original layout but adding it is fine, just add to .gitignore if it should be private).

## Verification
```bash
pixi run python -c "
import os, dotenv
dotenv.load_dotenv()
assert os.environ.get('RUNPOD_API_KEY'), 'RUNPOD_API_KEY not set'
print('runpod key ok')
"
pixi run python -c "
import os, httpx, dotenv
dotenv.load_dotenv()
r = httpx.get('https://rest.runpod.io/v1/pods', headers={'Authorization': f'Bearer {os.environ[\"RUNPOD_API_KEY\"]}'})
assert r.status_code == 200, f'runpod API rejected key: {r.status_code} {r.text}'
body = r.json()
pods = body if isinstance(body, list) else body.get('data', [])
print(f'runpod API ok; {len(pods)} pods listed')
"
```
Both must succeed.

## Will touch
- `.env` (edit, add RUNPOD_API_KEY) — NOT committed.
- `notes/runpod-bootstrap.md` (new) — personal notes; can be gitignored.

## Will NOT touch
- Any src file.
- `pixi.toml` (httpx is already a dependency).

## Out of scope
- Automating pod start/stop → T14.
- Building the GPU Docker image → T10.

## Notes / references
- RunPod REST API docs: https://rest.runpod.io/v1/docs
- Community cloud RTX 4090 ≈ $0.34/hr (April 2026 verified). Secure cloud ≈ $0.69/hr.
- This is a manual task. ~30 min. No code commit beyond .env and notes.
- DO NOT leave the test pod running. Verify it's `STOPPED` in the RunPod dashboard before you finish the task.
