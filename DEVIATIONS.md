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
