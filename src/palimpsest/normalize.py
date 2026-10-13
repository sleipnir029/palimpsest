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

import math
import re
from pathlib import Path
from typing import Any

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


# T74 — per-slot UPPER magnitude ceilings (in the canonical unit above), for the C3
# sanity check. C2 (units_match) validates the unit LABEL's dimension but NOT that the
# value was converted to it — a model can emit a value in a prefixed unit under the
# canonical label (e.g. "1900 mV" labelled "V") and pass C2 with a value ~1000× too
# large. C3 rejects values whose MAGNITUDE exceeds a generous physical ceiling, catching
# that over-magnitude class. Only the ceiling matters (the blunder inflates), and the
# check is on |value| so a real sign convention (negative HER overpotential, a falling-
# voltage rate) is never what triggers a reject — palimpsest is general, not OER-only.
# Ceilings are DELIBERATELY GENEROUS — reject blunders, never a physically unusual but
# real value. Slots without a clear ceiling are omitted (magnitude_ok → True).
# Static ceilings, a backstop behind check_milli_value below; widen one if a real value
# is ever wrongly rejected.
PLAUSIBLE_MAX: dict[str, float] = {
    "Overpotential": 2000.0,        # mV
    "TafelSlope": 1000.0,           # mV/decade
    "MassActivity": 1e6,            # A/g
    "TurnoverFrequency": 1e5,       # 1/s
    "SpecificActivity": 1e6,        # mA/cm2
    "Stability": 1e5,               # h
    "PEMWECellVoltage": 5.0,        # V (a mV-under-V blunder ⇒ ~1900 ≫ 5)
    "ChargeTransferCoefficient": 2.0,
    "ECSA": 5000.0,                 # cm2 (geometric); catches absurd values like 3.5e16
    "ExchangeCurrentDensity": 1000.0,  # mA/cm2
    "DegradationRate": 100.0,       # mV/h; catches unconverted values (e.g. 460 from audit)
}


def magnitude_ok(measurement_class_name: str, value: float | None) -> bool:
    """Is ``|value|`` within the slot's plausible ceiling (C3)? True if untracked.

    Complements ``units_match`` (C2): C2 checks the unit label is dimensionally the
    canonical one; this checks the magnitude is sane, catching a value emitted in a
    prefixed unit (e.g. mV under a V label) without conversion. Tests ``abs`` so a real
    negative value (HER sign convention, a falling-voltage rate) is never rejected.
    ``None`` passes (null-value handling lives in the caller, not here).
    """
    if value is None:
        return True
    cap = PLAUSIBLE_MAX.get(measurement_class_name)
    if cap is None:
        return True
    return abs(value) <= cap


# Unit-aware citation check (T74, revised 2026-10-13 after the thesis review). Models
# emit the number printed in the cited span either converted to the canonical unit
# ("22 µV/h" → 0.022 mV/h) or raw under the canonical label ("22 µV/h" → 22 "mV/h",
# 1000× too big). The 24 June 2026 run handled this with a digit-substring guard
# followed by a re-derivation step, which refused every correct conversion (0.022's
# digits are not in "22 µV/h") and let two raw values through (an OCR-dropped µ,
# "460 V/h", and a range low end, "2.3–2.8 µV h-1"). check_milli_value replaces both
# for the milli-prefixed LINEAR canonicals (mV·, mA·): Overpotential, TafelSlope,
# ExchangeCurrentDensity, SpecificActivity, DegradationRate. Area units (cm2) and
# everything without an m-prefixed V/A canonical keep the plain digit guard, via the
# `^m[VA]` gate below.
_MILLI_CANON = re.compile(r"^m([VA])\b")
# Accepted source prefixes a value could plausibly be PRINTED in for a milli slot:
# micro (two encodings + ascii), nano, milli. NOT centi/kilo/mega — those are coarse,
# don't occur for these quantities, and would only fire via a false match. 'µ'/'u' both
# map to micro; the span is unicode-normalised to 'µ' first. A bare base ("460 V") is
# factor 1.
_PREFIX_FACTOR = {"µ": 1e-6, "u": 1e-6, "n": 1e-9, "m": 1e-3, "": 1.0}
# A whole number (not the tail of a decimal or of a longer number), and the unit glued
# to it: optional prefix + base, the base not followed by a letter other than those
# that continue a unit (h, s, c(m), d(ec), R(HE)), so "2 Variation" is not read as volts.
_NUM = re.compile(r"(?<![\d.])\d+(?:\.\d+)?")
_RANGE_SEP = re.compile(r"\s*(?:[-–—−~]|to)\s*")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _clean_units(text: str) -> str:
    """De-noise LaTeX/unicode so a metric prefix reads as a bare char: \\mu→µ, μ→µ,
    drop \\mathrm{}, braces, thin-spaces, stray backslashes."""
    text = text.replace("\\mu", "µ").replace("\\mathrm", "").replace("\\,", "").replace("\\;", "")
    text = text.replace("{", "").replace("}", "").replace("\\", "")
    return text.replace("μ", "µ")  # GREEK SMALL LETTER MU → MICRO SIGN


def _span_numbers(text: str, base: str) -> list[tuple[float, str, str | None, bool]]:
    """Every whole number in ``text`` as ``(number, printed, prefix, carried)``.

    ``prefix`` is the metric prefix of a ``base`` unit glued to the number ("" for a
    bare base, ``None`` for no such unit). A range low end with no unit of its own
    ("2.3–2.8 µV") takes the high end's unit with ``carried=True``.
    """
    txt = _THOUSANDS.sub("", _clean_units(text))
    unit_re = re.compile(r"\s*([µunm]?)\s*" + base + r"(?![abe-gi-rt-zA-QS-Z])")
    out: list[list] = []
    for m in _NUM.finditer(txt):
        um = unit_re.match(txt, m.end())
        out.append([float(m.group()), m.group(), um.group(1) if um else None, False,
                    m.start(), m.end()])
    for lo, hi in zip(out, out[1:]):
        if lo[2] is None and hi[2] is not None:
            sep = _RANGE_SEP.match(txt, lo[5])
            if sep and sep.end() == hi[4]:
                lo[2], lo[3] = hi[2], True
    return [(n, s, p, c) for n, s, p, c, _a, _b in out]


def check_milli_value(
    value: Any, source_text: str, canonical: str | None,
) -> tuple[str, Any] | None:
    """Check an emitted value against the cited span, prefix-aware, for a milli slot.

    Returns ``None`` when the check does not apply (canonical not milli on a V/A base,
    or a non-numeric value) and the caller keeps the plain digit guard. Otherwise:

      ``("ok", v)``          a number in the span, read in its own unit, converts to v
                             (a correct conversion; also the canonical unit itself);
      ``("ok", v)``          v is printed with no unit glued to it (table cell, list);
      ``("ok", v')``         v is printed raw with a µ/n prefix, every occurrence the
                             same, none a range low end → re-derived to canonical;
      ``("miscite", None)``  v is not printed in the span in any form;
      ``("unit", printed)``  v is printed in another unit and was not converted, or
                             the conversion is ambiguous (e.g. "460 V/h" labelled
                             mV/h, a raw range low end) → the caller refuses.

    A wrong rescale corrupts silently while a refusal is recorded with its reason, so
    every ambiguous case refuses rather than converts.

    Deliberately strict and limited (recorded in tests/test_normalize.py):
      - the match is numeric to 1e-6, so a rounded value (52.6 for "52.63"), a decimal
        comma ("1,234" reads as 1234), a space thousands separator ("1 500") or powers
        of ten ("1.2 × 10^1") do not match and refuse as miscite;
      - a conversion is accepted from whatever number carries a unit, so the check
        cannot tell an electrode potential of 1.53 V from an overpotential of 1530 mV;
      - signs are not read: "−22 µV/h" accepts +0.022 (as the digit guard did).
    """
    mc = _MILLI_CANON.match(canonical or "")
    if not mc or value is None or not source_text:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    nums = _span_numbers(source_text, mc.group(1))
    a = abs(v)
    if any(p is not None and math.isclose(n * _PREFIX_FACTOR[p] / 1e-3, a, rel_tol=1e-6)
           for n, _s, p, _c in nums):
        return ("ok", v)
    same = [(s, p, c) for n, s, p, c in nums if math.isclose(n, a, rel_tol=1e-6)]
    if not same:
        return ("miscite", None)
    if all(p is None for _s, p, _c in same):
        return ("ok", v)
    prefixes = {p for _s, p, _c in same}
    if len(prefixes) == 1 and prefixes <= {"µ", "u", "n"} and not any(c for *_x, c in same):
        return ("ok", v * (_PREFIX_FACTOR[prefixes.pop()] / 1e-3))
    s, p, c = next(x for x in same if x[1] is not None)
    return ("unit", f"{s} {p}{mc.group(1)}" + (" (range end)" if c else ""))


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
    s = re.sub(r"[{}$]", "", s)          # LaTeX braces + dollar signs: ^{-1} -> ^-1
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
