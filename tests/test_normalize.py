"""Central normalization layer + per-skill overlay loader (T20.5).

Universal canonical units + enums apply to every electrochemistry domain.
Per-skill `normalization.yaml` overlays add domain-specific buckets
(operating points, mechanisms, active metals, …).

Conflict policy: if a domain overlay tries to redefine a UNIVERSAL_ENUMS
key, ``build_normalization_prompt`` raises ValueError loudly. Universal is
the source of truth.
"""
from pathlib import Path

import pytest

from palimpsest.normalize import (
    UNIVERSAL_ENUMS,
    UNIVERSAL_UNITS,
    build_normalization_prompt,
    canonical_unit,
    load_skill_normalization,
    units_match,
)

OER_DIR = Path(__file__).parent.parent / "skills" / "oer-extraction"


def test_universal_constants_well_formed():
    """Every UNIVERSAL_UNITS value is a non-empty str; every UNIVERSAL_ENUMS
    value is a non-empty list of non-empty strs."""
    assert UNIVERSAL_UNITS, "UNIVERSAL_UNITS must not be empty"
    for slot, unit in UNIVERSAL_UNITS.items():
        assert isinstance(slot, str) and slot, f"bad slot key: {slot!r}"
        assert isinstance(unit, str) and unit, f"bad unit for {slot}: {unit!r}"

    assert UNIVERSAL_ENUMS, "UNIVERSAL_ENUMS must not be empty"
    for name, values in UNIVERSAL_ENUMS.items():
        assert isinstance(name, str) and name, f"bad enum name: {name!r}"
        assert isinstance(values, list) and values, f"bad values for {name}: {values!r}"
        for v in values:
            assert isinstance(v, str) and v, f"bad enum value in {name}: {v!r}"


def test_load_skill_normalization_oer():
    """The OER overlay has the four domain-specific keys the card promises."""
    overlay = load_skill_normalization(OER_DIR)
    assert overlay["domain"] == "oer-extraction"
    for key in ("operating_points", "mechanisms", "active_metals", "electrolytes"):
        assert key in overlay, f"OER overlay missing {key!r}"


def test_load_skill_normalization_missing_file(tmp_path):
    """An empty dir returns {} (no normalization.yaml) — never raises."""
    assert load_skill_normalization(tmp_path) == {}


def test_build_normalization_prompt_contains_both_layers():
    """The merged prompt block contains a universal enum AND an OER bucket."""
    block = build_normalization_prompt([OER_DIR])
    assert "iR_correction" in block, "universal enum missing from merged prompt"
    assert "RDE_10mA" in block, "OER operating-point bucket missing from merged prompt"
    assert "LOM" in block, "OER mechanism enum missing from merged prompt"


@pytest.mark.parametrize(
    "colliding_yaml,collision_key",
    [
        # Enum collision (card-literal).
        ("domain: bad-skill\niR_correction: [yes, no]\n", "iR_correction"),
        # Unit collision (advisor-widened): a domain redefining temperature_C
        # would silently contradict the universal "Canonical units" section.
        ("domain: bad-skill\ntemperature_C: F\n", "temperature_C"),
    ],
)
def test_overlay_conflict_raises(tmp_path, colliding_yaml, collision_key):
    """A domain overlay that redefines a universal enum OR unit raises."""
    (tmp_path / "normalization.yaml").write_text(colliding_yaml)
    with pytest.raises(ValueError, match=collision_key):
        build_normalization_prompt([tmp_path])


# ----- T49: canonical_unit + units_match (C2) -------------------------------


def test_universal_enums_match_schema():
    """T50: the universal enums are advertised to the LLM by normalize.py AND
    modeled as schema enums on Condition. If the two drift, the LLM is told
    values the schema rejects (or vice-versa) — the exact bug T50 fixed. This
    pins them in sync against the generated Pydantic enums.
    """
    from schema.generated import pydantic as s

    mapping = {
        "iR_correction": s.IRCorrectionEnum,
        "normalization_basis": s.NormalizationBasisEnum,
        "cell_type_family": s.CellTypeFamilyEnum,
        "electrolyte_family": s.ElectrolyteFamilyEnum,
        "scan_rate_regime": s.ScanRateRegimeEnum,
    }
    for key, enum_cls in mapping.items():
        assert set(UNIVERSAL_ENUMS[key]) == {e.value for e in enum_cls}, key


def test_canonical_unit_lookup():
    assert canonical_unit("Overpotential") == "mV"
    assert canonical_unit("TurnoverFrequency") == "1/s"
    assert canonical_unit("NotAMeasurement") is None


def test_t71_canonical_units():
    """T71: the two PEMWE classes + the catalyst_loading condition slot are
    advertised with their canonical units, so the LLM converts before emitting
    and units_match validates them."""
    assert canonical_unit("PEMWECellVoltage") == "V"
    assert canonical_unit("DegradationRate") == "mV/h"
    assert UNIVERSAL_UNITS["catalyst_loading"] == "mg/cm2"
    # paper-faithful spellings match; a prefix error (V/h is 1000x mV/h) does not
    assert units_match("mV h⁻¹", "mV/h") is True
    assert units_match("mg cm⁻²", "mg/cm2") is True
    assert units_match("V/h", "mV/h") is False


def test_pemwe_overlay_does_not_shadow_universal_keys():
    """T71: catalyst_loading is now a universal Condition-slot unit. The PEMWE
    overlay must not redefine it (or any UNIVERSAL_* key) — build the merged
    prompt for BOTH real skills and assert it does not raise and renders both.
    """
    from pathlib import Path

    prompt = build_normalization_prompt(
        [Path("skills") / "oer-extraction", Path("skills") / "pemwe-anode"]
    )
    assert "oer-extraction" in prompt and "pemwe-anode" in prompt
    assert "catalyst_loading" in prompt  # advertised once, from the universal layer


@pytest.mark.parametrize(
    "emitted,canonical,expected",
    [
        # Correct unit, paper-faithful spelling — MUST pass (the live-run cases).
        ("s⁻¹", "1/s", True),
        ("A g⁻¹_Ir", "A/g", True),
        (r"A g^{-1}_{Ir}", "A/g", True),   # the LaTeX form mineru actually emits
        ("cm²", "cm2", True),
        ("mA cm⁻²", "mA/cm2", True),
        ("mV/dec", "mV/decade", True),     # dec/decade synonym
        ("mV", "mV", True),
        ("", "dimensionless", True),       # blank label == dimensionless
        # Genuine errors — MUST fail.
        ("V", "mV", False),                # 1000× magnitude error
        ("A", "mV/decade", False),
        (None, "mV", False),
    ],
)
def test_units_match(emitted, canonical, expected):
    assert units_match(emitted, canonical) is expected


# T74 — magnitude sanity check (C3). The dimensional check (units_match/C2) validates
# the unit LABEL but not that the value was actually converted to it: a model can emit
# a value in a prefixed unit (mV) under the canonical label (V) and pass C2 with a
# value ~1000× too large. magnitude_ok bounds |value| per slot to catch that. It checks
# only an UPPER ceiling on |value| — never a sign or lower bound — so real negatives
# (HER overpotential) pass; and DegradationRate is intentionally untracked (magnitude
# can't separate the µV/h blunder from a real high accelerated-stress rate).
import pytest as _pytest
from palimpsest.normalize import magnitude_ok


@_pytest.mark.parametrize(
    "type_name,value,expected",
    [
        ("PEMWECellVoltage", 1.83, True),
        ("PEMWECellVoltage", 1900.0, False),  # mV emitted under a V label ⇒ ~1000× too big
        ("PEMWECellVoltage", 5.0, True),      # ceiling is inclusive
        ("Overpotential", 236.0, True),
        ("Overpotential", -58.0, True),       # negative (HER sign convention) is REAL, not a blunder
        ("Overpotential", 2000.0, True),      # ceiling inclusive
        ("Overpotential", 236000.0, False),   # V emitted under an mV label
        ("Stability", 400.0, True),
        # DegradationRate intentionally NOT magnitude-guarded → always allowed here.
        ("DegradationRate", 22.0, True),
        ("UnknownType", 1e9, True),           # untracked slot → never reject
        ("Overpotential", None, True),        # null handled elsewhere; don't crash here
    ],
)
def test_magnitude_ok(type_name, value, expected):
    assert magnitude_ok(type_name, value) is expected


# T74 — unit re-derivation. Models emit the raw source number under the canonical
# label without converting ("22 µV/h" → value=22, label="mV/h", 1000× too big).
# rederive_milli_value rescales using the cited span's OWN metric prefix, for
# milli-prefixed linear units only (mV*, mA*). Tested against the real (messy,
# OCR/LaTeX) spans from the corpus, and against spans that must NOT change.
from palimpsest.normalize import rederive_milli_value


@_pytest.mark.parametrize(
    "value,source,canonical,expected",
    [
        # the bug, in every form the parsers actually produced:
        (22.0, "rate: 22 μV/h, Figs", "mV/h", 0.022),          # greek mu
        (22.0, "rate: 22 µV/h, Figs", "mV/h", 0.022),          # micro sign
        (22.0, "rate: 22 μ V/h, Figs", "mV/h", 0.022),         # space after prefix
        (52.0, "of 52 µV/h), achieving", "mV/h", 0.052),
        (2.8, r"2.8\mu\mathrm{V}\mathrm{h}^{-1}", "mV/h", 0.0028),  # LaTeX
        (2.3, "2.3–2.8 µV h -1 . To", "mV/h", 0.0023),          # range: unit after the OTHER number
        # must NOT change — canonical-unit spans (same milli prefix or no prefix):
        (236.0, "236 mV, which is", "mV", 236.0),
        (236.0, "236mVinanacid medium", "mV", 236.0),           # no space, trailing junk
        (52.6, "52.6 mV dec -1 ", "mV/decade", 52.6),
        # excluded slots (canonical not milli-V/A) → never touched:
        (30.0, "30 h, which is", "h", 30.0),                    # Stability
        (1.83, "1.83V i@ 2 A/cm2", "V", 1.83),                  # PEMWECellVoltage (no m-prefix canonical)
        (None, "whatever", "mV/h", None),
    ],
)
def test_rederive_milli_value(value, source, canonical, expected):
    got = rederive_milli_value(value, source, canonical)
    if expected is None:
        assert got is None
    else:
        assert got == _pytest.approx(expected, rel=1e-9)
