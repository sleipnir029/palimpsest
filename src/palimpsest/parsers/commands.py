"""Parser registry — one entry per parser image (T16).

Single literal dict that absorbs per-parser heterogeneity (CLI flags, baked wrappers,
output paths). Each entry binds a parser name to its RunPod template (via env var
name) and two callables: `run_cmd(inp, outdir)` returns the shell command to execute
on the pod (paths RELATIVE to /workspace), and `pod_output(inp, outdir)` returns the
ABSOLUTE on-pod path the parser will write to — different per parser, documented in
`docker/runpod-template.md` (T17 pod-verify pass).

The runner.py scps `pod_output` to `cache_dir / <sha> / <parser>.<ext>` where ext is
taken from `pod_output`'s suffix (`.json` for 4 parsers, `.md` for chandra).
"""

from __future__ import annotations

from pathlib import PurePosixPath


PARSERS: dict[str, dict] = {
    "docling": {
        "template_id_env": "RUNPOD_TEMPLATE_DOCLING",
        # docling writes <outdir>/<stem>.json (--to json controls format only).
        "run_cmd": (lambda inp, outdir:
            f"docling /workspace/{inp} --output /workspace/{outdir} --to json"),
        "pod_output": (lambda inp, outdir:
            f"/workspace/{outdir}/{PurePosixPath(inp).stem}.json"),
        "version": "docling-2.95.0",
    },
    "mineru": {
        "template_id_env": "RUNPOD_TEMPLATE_MINERU",
        # mineru 2.5 split `-b vlm` into vlm-auto-engine (in-process, baked weights)
        # and vlm-http-client. T17 verify: vlm-auto-engine + baked MinerU2.5-1.2B.
        "run_cmd": (lambda inp, outdir:
            f"mineru -p /workspace/{inp} -o /workspace/{outdir} -b vlm-auto-engine"),
        # mineru writes <outdir>/<stem>/vlm/<stem>_content_list_v2.json
        "pod_output": (lambda inp, outdir: (
            f"/workspace/{outdir}/{PurePosixPath(inp).stem}/vlm/"
            f"{PurePosixPath(inp).stem}_content_list_v2.json"
        )),
        "version": "mineru-2.5",
    },
    "chandra": {
        "template_id_env": "RUNPOD_TEMPLATE_CHANDRA",
        "run_cmd": (lambda inp, outdir:
            f"chandra /workspace/{inp} /workspace/{outdir} --method hf"),
        # chandra writes <outdir>/<stem>/<stem>.md (content) + .._metadata.json (stub).
        # The .md is what T16 captures — verified pass-2 + pass-3, 84.5 KB on the sample.
        "pod_output": (lambda inp, outdir:
            f"/workspace/{outdir}/{PurePosixPath(inp).stem}/"
            f"{PurePosixPath(inp).stem}.md"),
        "version": "chandra-ocr-2",
    },
    "dots": {
        "template_id_env": "RUNPOD_TEMPLATE_DOTS",
        # The baked /opt/dots_run.py takes (pdf, output_json_path); we control the path.
        # Per-PDF filename ({stem}.json) keeps a batch's outputs unique within /workspace/out.
        "run_cmd": (lambda inp, outdir:
            f"python /opt/dots_run.py /workspace/{inp} "
            f"/workspace/{outdir}/{PurePosixPath(inp).stem}.json"),
        "pod_output": (lambda inp, outdir:
            f"/workspace/{outdir}/{PurePosixPath(inp).stem}.json"),
        "version": "dots.ocr-1.7B",
    },
    "paddle": {
        "template_id_env": "RUNPOD_TEMPLATE_PADDLE",
        "run_cmd": (lambda inp, outdir:
            f"python /opt/paddle_run.py /workspace/{inp} "
            f"/workspace/{outdir}/{PurePosixPath(inp).stem}.json"),
        "pod_output": (lambda inp, outdir:
            f"/workspace/{outdir}/{PurePosixPath(inp).stem}.json"),
        "version": "paddle-pp-structurev3",
    },
}
