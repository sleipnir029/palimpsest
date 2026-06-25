"""Re-project an existing RDF store's Evidence boxes to tight PDF points — no LLM.

Reads each measurement's (page, value, source_text, paper) from a COPY of the
store and replaces its 4 bbox literals with the tight box `geometry.tighten_bbox`
finds in the born-digital PDF. This is the budget-safe way to upgrade a store the
extractor produced before the tightening pass existed (re-running extraction would
re-pay the LLM); future `extract()` runs already tighten in-process.

Usage:  pixi run python scripts/tighten_store.py [src=store] [dst=store.tight]
The source store is never modified; dst must not already exist.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root: `schema` ns pkg

import fitz
from pyoxigraph import Store

from palimpsest.tools.extract import _pdf_for_sha
from palimpsest.tools.geometry import tighten_bbox

_SELECT = """\
PREFIX palim: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?m ?paper ?page ?value ?src ?x0 ?y0 ?x1 ?y1 WHERE {
  ?m prov:hadPrimarySource ?ev .
  ?ev palim:paper ?paper ; palim:page ?page ;
      palim:bboxX0 ?x0 ; palim:bboxY0 ?y0 ; palim:bboxX1 ?x1 ; palim:bboxY1 ?y1 .
  OPTIONAL { ?ev palim:value ?value } OPTIONAL { ?m palim:value ?value }
  OPTIONAL { ?ev palim:sourceText ?src }
}"""

_UPDATE = """\
PREFIX palim: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
DELETE {{ ?ev palim:bboxX0 ?x0 ; palim:bboxY0 ?y0 ; palim:bboxX1 ?x1 ; palim:bboxY1 ?y1 }}
INSERT {{ ?ev palim:bboxX0 "{x0}"^^xsd:float ; palim:bboxY0 "{y0}"^^xsd:float ;
              palim:bboxX1 "{x1}"^^xsd:float ; palim:bboxY1 "{y1}"^^xsd:float }}
WHERE  {{ <{m}> prov:hadPrimarySource ?ev .
          ?ev palim:bboxX0 ?x0 ; palim:bboxY0 ?y0 ; palim:bboxX1 ?x1 ; palim:bboxY1 ?y1 }}"""


def main(src: str = "store", dst: str = "store.tight") -> None:
    if Path(dst).exists():
        sys.exit(f"refusing to overwrite existing {dst!r} — remove it or pick another dst")
    shutil.copytree(src, dst)
    store = Store(dst)

    docs: dict[str, fitz.Document | None] = {}
    total = refined = 0
    for r in store.query(_SELECT):
        total += 1
        sha = str(r["paper"].value).rsplit("/", 1)[-1]
        if sha not in docs:
            pdf = _pdf_for_sha(sha)
            docs[sha] = fitz.open(pdf) if pdf else None
        doc = docs[sha]
        if doc is None:
            continue
        page = int(r["page"].value)
        if not (1 <= page <= doc.page_count):
            continue
        fallback = tuple(float(r[k].value) for k in ("x0", "y0", "x1", "y1"))
        value = r["value"].value if r["value"] else None
        src_text = r["src"].value if r["src"] else ""
        (nx0, ny0, nx1, ny1), ok = tighten_bbox(doc[page - 1], value, src_text, fallback)
        if not ok:
            continue
        refined += 1
        store.update(_UPDATE.format(m=r["m"].value, x0=nx0, y0=ny0, x1=nx1, y1=ny1))

    for d in docs.values():
        if d is not None:
            d.close()
    print(f"{dst}: {refined}/{total} boxes tightened to PDF points (rest kept native).")


if __name__ == "__main__":
    main(*sys.argv[1:3])
