"""Central normalization layer + per-skill overlay merger (T20.5).

UNIVERSAL_* hold canonical units and categorical enums that apply to every
electrochemistry extraction domain (OER, HER, CO2RR, NRR, …). Per-skill
``normalization.yaml`` files in each ``skills/<domain>/`` folder add the
domain-specific buckets (operating points, mechanisms, active metals, …).

``build_normalization_prompt`` merges both layers into one markdown block
that the agent (T22) injects into the LLM system prompt at extraction time.

Conflict policy: a domain overlay MAY NOT redefine a UNIVERSAL_ENUMS or
UNIVERSAL_UNITS key. ``build_normalization_prompt`` raises ``ValueError``
if it tries to. Universal is the source of truth; domains extend, never
override (advisor-widened from card-literal enum-only to also cover units).
"""
from __future__ import annotations

from pathlib import Path

import yaml

# Canonical units per schema entity in schema/palimpsest.yaml. Keys are either:
#   * a Measurement subclass name (CamelCase, lines 54-101 of the schema) — the
#     LLM emits an instance and sets unit_label to the canonical unit below.
#   * a Condition slot name (snake_case, lines 365-385) — populated on the
#     embedded Condition block of a Measurement.
# Disjoint namespaces by capitalization; mixing in one dict keeps lookup simple.
# Variables not yet modeled (Stability hours, PEMWE Vcell, Pressure, specific
# ECSA in m2/g) are tracked in tasks/T18a-schema-cleanups.md Finding F3 and
# deliberately omitted here until the schema declares them.
UNIVERSAL_UNITS: dict[str, str] = {
    # Measurement subclasses:
    "Overpotential": "mV",
    "TafelSlope": "mV/decade",
    "ExchangeCurrentDensity": "mA/cm2",
    "ChargeTransferCoefficient": "dimensionless",
    "MassActivity": "A/g",
    "TurnoverFrequency": "1/s",
    "ECSA": "cm2",  # geometric ECSA; specific ECSA (m2/g) is T18a F3
    # Condition slots:
    "current_density": "mA/cm2",
    "temperature_C": "Cel",
    "scan_rate": "mV/s",
    "electrolyte_ph": "[pH]",
    "electrode_potential_vs_rhe": "V",
}

UNIVERSAL_ENUMS: dict[str, list[str]] = {
    "iR_correction": ["applied", "not_applied", "unknown"],
    "normalization_basis": ["geometric", "ECSA", "BET", "mass"],
    "cell_type_family": ["RDE", "three_electrode_flow", "single_cell_MEA", "stack"],
    "electrolyte_family": ["acid", "alkaline", "neutral"],
    "scan_rate_regime": ["steady_state", "slow_LSV", "fast_LSV", "fast_CV"],
}


def load_skill_normalization(skill_dir: Path) -> dict:
    """Return the parsed ``normalization.yaml`` from ``skill_dir``, or ``{}``.

    A missing file is a graceful no-overlay (returns ``{}``). A malformed file
    is a programmer error and lets ``yaml.YAMLError`` bubble up.
    """
    path = Path(skill_dir) / "normalization.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def build_normalization_prompt(active_skill_dirs: list[Path]) -> str:
    """Merge UNIVERSAL_* with each active skill's overlay into one markdown block.

    Output is intended for injection into the LLM system prompt. Returns a
    single string; never writes to disk.

    Raises:
        ValueError: a domain overlay tries to redefine a UNIVERSAL_ENUMS or
        UNIVERSAL_UNITS key.
    """
    universal_keys = set(UNIVERSAL_ENUMS) | set(UNIVERSAL_UNITS)
    overlays: list[tuple[str, dict]] = []
    for skill_dir in active_skill_dirs:
        overlay = load_skill_normalization(skill_dir)
        if not overlay:
            continue
        collisions = set(overlay) & universal_keys
        if collisions:
            raise ValueError(
                f"{Path(skill_dir).name}/normalization.yaml redefines universal "
                f"key(s) {sorted(collisions)}; universal enums/units are the source "
                "of truth — domain overlays may extend but not override."
            )
        domain = overlay.get("domain", Path(skill_dir).name)
        overlays.append((domain, overlay))

    lines: list[str] = ["## Normalization rules", ""]
    lines.append(
        "Emit every Measurement in the canonical unit below. Convert before emission."
    )
    lines.append(
        "For categorical fields, use only the listed enum values; never invent values."
    )
    lines.append("")
    lines.append("### Canonical units")
    for slot, unit in UNIVERSAL_UNITS.items():
        lines.append(f"- `{slot}`: {unit}")
    lines.append("")
    lines.append("### Universal categorical enums")
    for name, values in UNIVERSAL_ENUMS.items():
        lines.append(f"- `{name}`: {' | '.join(values)}")
    if overlays:
        lines.append("")
        lines.append("### Domain overlays")
        for domain, overlay in overlays:
            lines.append(f"#### {domain}")
            # yaml-dump the domain payload (operating_points, mechanisms, …) verbatim
            # so new keys added later auto-render without code change.
            dumped = yaml.safe_dump(
                {k: v for k, v in overlay.items() if k != "domain"},
                sort_keys=False,
                default_flow_style=False,
            )
            lines.append(dumped.rstrip())
    return "\n".join(lines) + "\n"
