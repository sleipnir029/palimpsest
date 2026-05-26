# T08 — end-to-end smoke: "title of this paper?"

## Why
First full vertical slice. Proves the agent can call a tool, read a paper, and produce a correct answer. If T08 works, the foundation is real.

## Input state
- T07 merged. `read_paper` tool registered.
- `tests/fixtures/sample.pdf` exists.

## Output state
- File `src/palimpsest/__main__.py` exists and:
  - Loads `.env` via `python-dotenv`.
  - Creates AnthropicProvider, CostMeter, Agent (with TOOLS).
  - Sets a system prompt that mentions the available tools and instructs the model to read the paper if asked about it.
  - Takes `sys.argv[1]` as the user message and prints `agent.run(...)`.
- Running `pixi run python -m palimpsest "what is the title of tests/fixtures/sample.pdf?"` produces output that includes the actual title from the PDF (verified by hand).
- File `tests/test_e2e.py` covers a programmatic version of the above with `pytest.mark.slow` so it can be skipped in normal runs.

## Verification
```bash
pixi run python -m palimpsest "what is the title of tests/fixtures/sample.pdf?"
pixi run python -c "
from palimpsest.cost import CostMeter
m = CostMeter('palimpsest.db')
assert m.total_eur() > 0, 'expected non-zero spend after E2E call'
print(f'spend: €{m.total_eur():.4f}')
"
```
First must print a string containing the paper title. Second must print a positive EUR amount, typically €0.001–€0.01.

## Will touch
- `src/palimpsest/__main__.py` (new)
- `tests/test_e2e.py` (new)

## Will NOT touch
- Any other src file. The agent loop should just work.

## Out of scope
- TUI → T26.
- Slash commands → T27.
- The full multi-turn extraction flow → week 3.

## Notes / references
- The system prompt at this stage can be short, e.g. "You are palimpsest, an agent that extracts data from research papers. You have one tool: read_paper(path). Use it when the user mentions a PDF path."
- The model needs to call `read_paper`, see the page count, then call `read_paper` is not enough to get the title — for this MVP step, we ALLOW the agent to make up the title from the filename if `read_paper` doesn't surface text. The proper title extraction happens after parsing in week 3. **What we are verifying here is that the agent calls the tool and produces a coherent answer, not that the answer is perfectly accurate.**
- If you find this test brittle (model hallucinates), add a second tool `read_first_page_text(path)` that uses `fitz.open(path)[0].get_text()` to return the first page's text. This is acceptable scope expansion — log in DEVIATIONS.md.
