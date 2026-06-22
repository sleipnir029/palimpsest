# T78 — Change visibility: edit diffs, bash/extract surfacing, pipeline progress

## Why
The human supervises and verifies, but `edit_file` returned only `"edited path"`,
long `extract_paper` runs showed only `· working…` for minutes, and the
graph mutation (the real product) wasn't surfaced. Supervision via visibility,
NOT interactive approval gates (keeps the "autonomy bounded in code" thesis claim).

## Input state
- T63 live tool trace truncated every result to 200 chars.
- `run_paper` was one opaque compound call.

## Output state (delivered)
- `edit_file` returns a capped `difflib` unified diff; the TUI renders it with
  +/− coloring and shows `bash`/`extract_paper` results un-truncated (the
  supervision-relevant tools), so the command run and the graph mutation are visible.
- **Pipeline stage progress:** `progress.py` is a process-global sink the agent installs
  for the duration of a run; `pipeline.run_paper` emits at the real boundaries
  (parse → extract → validate → insert); the TUI renders them as live `stage` lines.
- **Graph-mutation preview:** the un-truncated `extract_paper` summary surfaces
  inserted/dropped counts inline.

## Verification
`pixi run pytest tests/test_tui.py tests/test_pipeline.py -q`
- `test_tool_error_result_renders_failure_marker`, edit-diff render path
- `progress.emit` is best-effort (a faulty sink never breaks a run)

## Will touch
- `src/palimpsest/tools/edit_file.py`, `src/palimpsest/progress.py` (new),
  `src/palimpsest/pipeline.py`, `src/palimpsest/tui/app.py`

## Will NOT touch
- The provenance-on-insert invariant; the pipeline's funnel counts.
