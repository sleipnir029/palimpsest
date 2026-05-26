# T20 — oer-extraction SKILL.md

## Why
Domain knowledge for the agent. Progressive disclosure: frontmatter in system prompt, body loaded on demand.

## Input state
- T18 merged. The schema defines what slots exist.

## Output state
- File `skills/oer-extraction/SKILL.md` exists with:
  - YAML frontmatter:
    ```yaml
    ---
    name: oer-extraction
    description: Extract OER catalyst performance variables (overpotential, Tafel slope, mass activity, TOF, ECSA, exchange current density, stability, PEMWE cell voltage) from PEM electrolyzer / acidic water-splitting papers. Use when paper topic is OER, PEMWE, IrO2, RuO2, or oxygen evolution.
    when_to_use: paper_topic in {OER, PEMWE, acidic_water_splitting, iridium_oxide, ruthenium_oxide}
    version: 1.0.0
    ---
    ```
  - Body (markdown) covers:
    - Required slots and their conditions (overpotential REQUIRES current density; mass activity REQUIRES potential vs RHE; TOF REQUIRES potential).
    - Heuristics: η@10 mA cm⁻² is RDE default; η@1 A cm⁻² or 2 A cm⁻² is PEMWE default.
    - Tafel slope conventions: report mV/decade, note the current density range used for the fit.
    - Mass activity: A g⁻¹Ir; specify the potential.
    - Stability: in hours; report at what current density and what cell type.
    - Mechanism annotations: LOM (lattice oxygen mechanism), AEM (adsorbate evolution mechanism), water nucleophilic attack.
    - Common traps: iR-correction (specify if values are uncorrected); scan-rate sensitivity; difference between geometric and ECSA-normalized current density.
- File `skills/oer-extraction/references/tafel-conventions.md` covers Tafel sign conventions and intercept handling.
- File `skills/oer-extraction/references/pemwe-protocols.md` describes typical PEMWE test protocols (75–80°C, deionized water, Nafion-bonded electrodes).

## Verification
```bash
pixi run python -c "
import yaml
from pathlib import Path
md = Path('skills/oer-extraction/SKILL.md').read_text()
_, fm, body = md.split('---', 2)
meta = yaml.safe_load(fm)
assert meta['name'] == 'oer-extraction'
assert meta['version'] == '1.0.0'
assert len(body) > 1000
print('SKILL.md valid')
"
```

## Will touch
- `skills/oer-extraction/SKILL.md` (new)
- `skills/oer-extraction/references/tafel-conventions.md` (new)
- `skills/oer-extraction/references/pemwe-protocols.md` (new)

## Will NOT touch
- Any src file.

## Out of scope
- Skill loader (read_skill tool) → T21.
- Extraction logic that uses the skill → T22.
- HER, CO2RR, NRR skills → future work, NOT in MVP.

## Notes / references
- Design ref: §F3 Agent Skills, Appendix A CLAUDE.md skill rules.
- Anthropic Skills spec: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Open standard reference: https://agentskills.io/home
- Keep the body under ~3000 tokens. The agent loads it on demand; long skills are wasteful.
