# T30 — /paper/{sha}/data JSON endpoint

## Why
The right pane data. HTMX will pull this and render hoverable values.

## Input state
- T29 merged. Viewer renders PDF.
- T24 merged. Store has extraction triples with provenance.

## Output state
- `viewer/app.py` adds route `GET /paper/{sha}/data`:
  - Runs SPARQL against RDFStore: select all measurements with their values, units, and provenance (page, bbox, parser_name, source_text).
  - Returns JSON: `{"sha": ..., "triples": [{"id": ..., "slot_path": ..., "value": ..., "unit": ..., "page": ..., "bbox": [x0,y0,x1,y1], "parser_name": ..., "source_text": ...}, ...]}`.
- File `tests/test_viewer_data.py` covers: GET on a known sha returns valid JSON with ≥1 triple containing all required fields.

## Verification
```bash
pixi run viewer &
sleep 2
curl http://localhost:8765/paper/<sha>/data | python -m json.tool | head -30
pixi run pytest tests/test_viewer_data.py -v
kill %1
```

## Will touch
- `src/palimpsest/viewer/app.py` (edit: add /data route)
- `tests/test_viewer_data.py` (new)

## Will NOT touch
- store.py.

## Out of scope
- Rendering on the page → T31.

## Notes / references
- SPARQL CONSTRUCT or SELECT with multiple joins is fine. Cache the result per-request — don't worry about caching across requests in MVP.
- If bbox is stored as a string `"page,x0,y0,x1,y1"`, parse it back to a list of floats in the JSON response.
