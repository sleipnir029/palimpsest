"""PP-StructureV3 → one JSON envelope, for the palimpsest parser registry (T17).

Usage: python paddle_run.py <input.pdf> <output.json>

The CLI (`paddleocr pp_structurev3 --save_path …`) writes a *directory* (markdown + per-page JSON
+ cropped images). The batch runner (T16) expects ONE artifact per (paper, parser) to scp_down, so
this wrapper drives the Python API and writes a single JSON envelope:
    {"markdown": "<concatenated reading-order md>",
     "pages": [<per-page structured JSON: layout boxes, table cells, formulas>]}
uniform with dots_run.py and the other parsers' JSON outputs.

[VALIDATE ON FIRST POD RUN] The exact result accessors of PaddleOCR 3.x (`res.json`, `res.markdown`)
and multipage-PDF iteration are confirmed against the docs but not yet exercised on hardware; the
getattr() hedges keep this from hard-failing if an attribute shape differs, but finalize after the
night pod run.
"""

import json
import sys

from paddleocr import PPStructureV3


def main(pdf: str, out: str) -> None:
    pipeline = PPStructureV3()  # baked models in ~/.paddlex; GPU auto-selected on the pod
    md_parts: list[str] = []
    pages: list = []
    for res in pipeline.predict(input=pdf):  # one result per page
        pages.append(getattr(res, "json", None))  # structured: layout boxes + table cells
        md = getattr(res, "markdown", None)
        if isinstance(md, str):
            md_parts.append(md)
        elif isinstance(md, dict):  # 3.x may return {"markdown_texts": ...}
            md_parts.append(md.get("markdown_texts") or json.dumps(md))
    with open(out, "w") as f:
        json.dump({"markdown": "\n\n".join(md_parts), "pages": pages}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
