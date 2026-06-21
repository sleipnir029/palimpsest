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

import re
from pathlib import Path

import yaml

# Canonical units per schema entity in schema/palimpsest.yaml. Keys are either:
#   * a Measurement subclass name (CamelCase, lines 54-101 of the schema) — the
#     LLM emits an instance and sets unit_label to the canonical unit below.
#   * a Condition slot name (snake_case, lines 365-385) — populated on the
#     embedded Condition block of a Measurement.
# Disjoint namespaces by capitalization; mixing in one dict keeps lookup simple.
# T52 added SpecificActivity + Stability (T18a F3, ground-truth-driven). Still NOT
# modeled (no available paper reports them): PEMWE Vcell, Pressure, specific ECSA
# (m2/g) — tracked in tasks/T18a-schema-cleanups.md F3, omitted until a paper needs them.
UNIVERSAL_UNITS: dict[str, str] = {
    # Measurement subclasses:
    "Overpotential": "mV",
    "TafelSlope": "mV/decade",
    "ExchangeCurrentDensity": "mA/cm2",
    "ChargeTransferCoefficient": "dimensionless",
    "MassActivity": "A/g",
    "TurnoverFrequency": "1/s",
    "ECSA": "cm2",  # geometric ECSA; specific ECSA (m2/g) is T18a F3
    "SpecificActivity": "mA/cm2",  # T52: ECSA-normalized current
    "Stability": "h",  # T52: hours sustained at a held current density
    "PEMWECellVoltage": "V",  # T71: full-cell operating voltage
    "DegradationRate": "mV/h",  # T71: cell-voltage rise rate (convert uV/h, mV/1000h)
    # Condition slots:
    "current_density": "mA/cm2",
    "temperature_C": "Cel",
    "scan_rate": "mV/s",
    "electrolyte_ph": "[pH]",
    "electrode_potential_vs_rhe": "V",
    "catalyst_loading": "mg/cm2",  # T71: anode Ir loading (PEMWE MEA context)
}

UNIVERSAL_ENUMS: dict[str, list[str]] = {
    "iR_correction": ["applied", "not_applied", "unknown"],
    "normalization_basis": ["geometric", "ECSA", "BET", "mass"],
    "cell_type_family": ["RDE", "three_electrode_flow", "single_cell_MEA", "stack"],
    "electrolyte_family": ["acid", "alkaline", "neutral"],
    "scan_rate_regime": ["steady_state", "slow_LSV", "fast_LSV", "fast_CV"],
}


def canonical_unit(measurement_class_name: str) -> str | None:
    """Canonical ``unit_label`` for a Measurement subclass, or ``None`` if not tracked.

    The single source of truth is ``UNIVERSAL_UNITS`` (also the units advertised to
    the LLM in the normalization prompt). T49 uses this to reject an emitted
    ``unit_label`` that disagrees with the canonical unit (C2).
    """
    return UNIVERSAL_UNITS.get(measurement_class_name)


# T74 — per-slot plausibility bounds (in the canonical unit above), for the C3
# magnitude sanity check. C2 (units_match) validates the unit LABEL's dimension but
# NOT that the value was converted to it — a model can emit a µV/h reading under an
# "mV/h" label and pass C2 with a value 1000× too large (every DegradationRate
# candidate in the T74 gold audit). These bounds catch gross prefix errors. They are
# DELIBERATELY GENEROUS — meant to reject magnitude blunders, never to police a
# physically unusual but real value. Slots without clear physical bounds are omitted
# (magnitude_ok returns True for them → never rejected).
# ponytail: a static range, not unit re-derivation from the cited span; widen a bound
# here if a real value is ever wrongly rejected.
PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    "Overpotential": (0.0, 2000.0),        # mV
    "TafelSlope": (0.0, 1000.0),           # mV/decade
    "MassActivity": (0.0, 1e6),            # A/g
    "TurnoverFrequency": (0.0, 1e5),       # 1/s
    "SpecificActivity": (0.0, 1e6),        # mA/cm2
    "Stability": (0.0, 1e5),               # h
    "PEMWECellVoltage": (0.5, 5.0),        # V (full-cell operating voltage)
    "DegradationRate": (0.0, 10.0),        # mV/h (good PEMWE << 1; 22 mV/h ⇒ a µV/h blunder)
    "ChargeTransferCoefficient": (0.0, 2.0),
}


def magnitude_ok(measurement_class_name: str, value: float | None) -> bool:
    """Is ``value`` within the slot's plausible range (C3)? True if no range tracked.

    Complements ``units_match`` (C2): C2 checks the unit label is dimensionally the
    canonical one; this checks the magnitude is sane, catching values emitted in a
    prefixed unit (µV/h) under the canonical label (mV/h) without conversion. ``None``
    passes (null-value handling lives in the caller, not here).
    """
    if value is None:
        return True
    rng = PLAUSIBLE_RANGE.get(measurement_class_name)
    if rng is None:
        return True
    return rng[0] <= value <= rng[1]


# Map unicode superscript characters to ASCII so `s⁻¹` reads as `s-1`.
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
# Token-level synonyms folded to one spelling before comparison.
_UNIT_SYNONYMS = {"dec": "decade", "decades": "decade", "unitless": "dimensionless"}


def _unit_signature(unit: str | None) -> frozenset[tuple[str, int]]:
    """Reduce a unit string to a set of ``(base, signed_exponent)`` factors.

    This makes equivalent spellings compare equal while genuinely different units
    stay distinct: ``"s⁻¹" == "1/s"``, ``"A g⁻¹_Ir" == "A/g"``, ``"cm²" == "cm2"``,
    but ``"V" != "mV"``. The point of C2 is to catch a wrong unit (e.g. a 1000×
    magnitude error), not to reject a correct unit that the LLM spelled in
    paper-faithful notation.

    Handles: unicode/LaTeX superscripts (``⁻¹``, ``^{-1}``, ``^2``), ``/`` as a
    denominator, space/``·`` as multiplication, and subscript basis qualifiers
    (``_Ir``) which are dropped (they annotate the normalization basis, not the
    unit). A blank/dimensionless label collapses to ``{("dimensionless", 1)}``.
    """
    s = (unit or "").translate(_SUPERSCRIPTS).lower()
    s = re.sub(r"\\,|\\", " ", s)        # LaTeX thin-space / stray backslashes
    s = re.sub(r"[{}]", "", s)           # LaTeX braces: ^{-1} -> ^-1
    s = re.sub(r"_[a-z0-9]+", "", s)     # subscript qualifiers: A g-1_ir -> A g-1
    s = s.replace("^", "")               # s^-1 -> s-1, cm^2 -> cm2
    if not s.strip():
        return frozenset({("dimensionless", 1)})

    powers: dict[str, int] = {}
    num, _, den = s.partition("/")  # units here are simple; split on first '/'

    def _add(text: str, sign: int) -> None:
        for tok in re.split(r"[ ·*]+", text.strip()):
            if not tok or tok == "1":
                continue
            m = re.match(r"^([a-zμ%°]+)(-?\d+)?$", tok)
            if m:
                base = _UNIT_SYNONYMS.get(m.group(1), m.group(1))
                exp = int(m.group(2)) if m.group(2) else 1
            else:
                base, exp = tok, 1  # unparseable: compare the raw token verbatim
            powers[base] = powers.get(base, 0) + sign * exp

    _add(num, 1)
    _add(den, -1)
    return frozenset((b, e) for b, e in powers.items() if e != 0)


def units_match(emitted: str | None, canonical: str | None) -> bool:
    """True if ``emitted`` is the same unit as ``canonical`` modulo spelling (C2)."""
    return _unit_signature(emitted) == _unit_signature(canonical)


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
    lines.append(
        "Write `unit_label` in ASCII exactly as shown above — e.g. `1/s` not `s⁻¹`, "
        "`A/g` not `A g⁻¹`, `cm2` not `cm²` — and omit basis qualifiers like `_Ir`."
    )
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
