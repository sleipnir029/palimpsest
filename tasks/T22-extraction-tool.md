# T22 — Extraction tool: parser output → Sonnet → Pydantic

## Why
The core extraction step. Takes cached parser output, calls Sonnet 4.5 with cache_control, returns validated Pydantic instances.

## Input state
- T17 (cache), T19 (schema generation), T21 (skill loader) merged.

## Output state
- File `src/palimpsest/tools/extract.py` exports:
  - `def extract(paper_sha: str, parser_name: str = "mineru", skill_name: str = "oer-extraction") -> list[BaseModel]`:
    1. Load parser output from cache via `ParserCache.get_output(sha, parser_name)`.
    2. Load skill body via `SkillLoader.load(skill_name)`.
    3. Build a system prompt that includes: skill body, schema definitions (from `schema/generated/jsonschema.json`), instructions to return JSON matching specific Pydantic classes.
    4. Call AnthropicProvider with `cache_breakpoints=["system"]` so the skill + schema are cached (1-hour TTL preferred for batch extraction).
    5. Parse the returned JSON. For each item, instantiate the appropriate Pydantic class. Collect into list.
    6. Return list of validated instances.
  - Registered in TOOLS so agent can invoke from chat.
- File `tests/test_extract.py` covers:
  - Happy path with mocked Anthropic returning a known JSON. Asserts Pydantic validation succeeds and the right classes are instantiated.
  - Schema violation path: mocked Anthropic returns invalid JSON; the tool returns a partial list AND raises/logs the validation error so the agent can self-correct.

## Verification
```bash
pixi run pytest tests/test_extract.py -v
# Live (costs ~$0.30):
pixi run python -c "
from palimpsest.tools.extract import extract
import json
result = extract(paper_sha='SHA_FROM_T16', parser_name='mineru', skill_name='oer-extraction')
print(f'extracted {len(result)} instances')
for r in result: print(' ', type(r).__name__, r.model_dump_json()[:80])
"
```
Live invocation: returns ≥5 instances, mostly Overpotential and TafelSlope.

## Will touch
- `src/palimpsest/tools/extract.py` (new)
- `src/palimpsest/tools/__init__.py` (edit: import extract)
- `tests/test_extract.py` (new)

## Will NOT touch
- agent.py, cost.py, cache.py.

## Out of scope
- SHACL validation → T23.
- pyoxigraph insertion → T24.
- Exploratory schema mode (proposing new slots) → defer to T22.5 (add only if needed during week 5 experiments).

## Notes / references
- Design ref: §F8 schema-first extraction.
- The system prompt should be ~10–15K tokens (schema + skill body + instructions). Cache it; second call should show `cache_read > 0` in cost ledger.
- Sonnet 4.5 pricing with caching makes per-paper cost ~$0.30. 25 papers × $0.30 = $7.50 total. Well within budget.
- Use `pydantic.ValidationError` to catch invalid instances; return them as `(error, raw_dict)` tuples in a separate list so the agent can see failures and decide whether to re-prompt.
