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

OER_DIR = Path(__file__).parent.parent / "skills" / "domain" / "oer-extraction"


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
        [Path("skills") / "domain" / "oer-extraction",
         Path("skills") / "domain" / "pemwe-anode"]
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
        ("mA cm$^{-2}$", "mA/cm2", True),  # LaTeX dollar signs from LLM echo
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
# (HER overpotential) pass.
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
        # ECSA (cm2, geometric)
        ("ECSA", 150.0, True),
        ("ECSA", 5000.0, True),               # ceiling inclusive
        ("ECSA", 3.5e16, False),              # absurd value caught
        # ExchangeCurrentDensity (mA/cm2)
        ("ExchangeCurrentDensity", 0.01, True),
        ("ExchangeCurrentDensity", 1000.0, True),  # ceiling inclusive
        ("ExchangeCurrentDensity", 5000.0, False),
        # DegradationRate (mV/h)
        ("DegradationRate", 22.0, True),
        ("DegradationRate", 100.0, True),     # ceiling inclusive
        ("DegradationRate", 460.0, False),    # unconverted value from audit
        ("UnknownType", 1e9, True),           # untracked slot → never reject
        ("Overpotential", None, True),        # null handled elsewhere; don't crash here
    ],
)
def test_magnitude_ok(type_name, value, expected):
    assert magnitude_ok(type_name, value) is expected


# T74 — unit-aware citation check (revised 2026-10-13). Models emit the number printed
# in the cited span either converted ("22 µV/h" → 0.022 mV/h) or raw under the canonical
# label (22 "mV/h", 1000× too big). check_milli_value accepts the conversion, re-derives
# the raw value from the span's OWN metric prefix, and refuses ("unit") a value printed
# in another unit that it cannot safely re-derive — milli-prefixed linear units only
# (mV*, mA*). Tested against the real (messy, OCR/LaTeX) spans from the corpus.
from palimpsest.normalize import check_milli_value

OK, MISCITE, UNIT = "ok", "miscite", "unit"


@_pytest.mark.parametrize(
    "value,source,canonical,verdict,expected",
    [
        # raw prefixed value → re-derived, in every form the parsers actually produced:
        (22.0, "rate: 22 μV/h, Figs", "mV/h", OK, 0.022),          # greek mu
        (22.0, "rate: 22 µV/h, Figs", "mV/h", OK, 0.022),          # micro sign
        (22.0, "rate: 22 μ V/h, Figs", "mV/h", OK, 0.022),         # space after prefix
        (52.0, "of 52 µV/h), achieving", "mV/h", OK, 0.052),
        (2.8, r"2.8\mu\mathrm{V}\mathrm{h}^{-1}", "mV/h", OK, 0.0028),  # LaTeX
        (2.8, "2.3–2.8 µV h -1 . To", "mV/h", OK, 0.0028),          # range HIGH end converts
        # canonical-unit spans (same milli prefix, or no unit glued on) → unchanged:
        (236.0, "236 mV, which is", "mV", OK, 236.0),
        (236.0, "236mVinanacid medium", "mV", OK, 236.0),           # no space, trailing junk
        (52.6, "52.6 mV dec -1 ", "mV/decade", OK, 52.6),
        (5.0, "5 cV applied", "mV", OK, 5.0),                       # centi not a prefix → no unit
        (22.0, "22 kV/h test", "mV/h", OK, 22.0),                   # kilo not a prefix → no unit
        (5.0, "load 5}{kV elsewhere", "mV", OK, 5.0),               # brace-merge must not mint a prefix
        (2.0, "tested 2 times at 0.022 mV/h", "mV/h", OK, 2.0),     # value has no unit glued on
        (5.0, "5 µV noise floor; signal was 5 mV/h", "mV/h", OK, 5.0),  # one reading agrees
        # excluded slots (canonical not milli-V/A) and non-values → check does not apply:
        (30.0, "30 h, which is", "h", None, None),                  # Stability
        (1.83, "1.83V i@ 2 A/cm2", "V", None, None),                # PEMWECellVoltage
        (None, "whatever", "mV/h", None, None),
        # not printed at all → miscite:
        (22.0, "value 1225 µV/h reported", "mV/h", MISCITE, None),  # 22 is not a token of 1225
        # printed in another unit and not safely re-derivable → refuse:
        (2.3, "2.3–2.8 µV h -1 . To", "mV/h", UNIT, None),          # raw range LOW end
        (2.0, "2 electrodes, 2 µV/h", "mV/h", UNIT, None),          # ambiguous: two readings
        (3.0, "Fig 3-5 µV/h shown", "mV/h", UNIT, None),            # hyphen never bridges a µ in
        (2.0, "samples 2-8 µV/h plot", "mV/h", UNIT, None),
        (100.0, "100-5 µV/h", "mV/h", UNIT, None),
        # OCR glues the next word to the unit (re-review 2026-10-13):
        (22.0, "rate 22µVat 2 A", "mV/h", OK, 0.022),              # prefixed: still µV
        (0.022, "rate 22µVat 2 A", "mV/h", OK, 0.022),
        (0.236, "η = 0.236Vin acid", "mV", UNIT, None),            # bare V glued to a word
        (236.0, "η = 0.236Vin acid", "mV", MISCITE, None),         # not read as volts either
        (1.53, "E = 1.53VvsRHE", "mV", UNIT, None),
        (2.0, "Fig 2 Variation of", "mV", OK, 2.0),                # a word after a space: no unit
        (0.236, "η = 0.236 Vin acid", "mV", OK, 0.236),            # recorded limit: space, then word
        (1.53, "E = 1.53 Vvs. RHE", "mV", UNIT, None),             # "vs" continues a volt
        (1530.0, "E = 1.53 Vvs. RHE", "mV", OK, 1530.0),
        (0.2, "η = 0.2–0.236Vin", "mV", UNIT, None),               # "?" carries to the low end
        (5.0, "5 nAnoparticle", "mA cm-2", OK, 5.0),               # n before a word: not rescaled
    ],
)
def test_check_milli_value(value, source, canonical, verdict, expected):
    got = check_milli_value(value, source, canonical)
    if verdict is None:
        assert got is None
    elif verdict == OK:
        assert got[0] == OK and got[1] == _pytest.approx(expected, rel=1e-9)
    else:
        assert got[0] == verdict


# The examples the thesis review asked to be re-tested (2026-10-13), on the cited span
# texts the 24 June 2026 run actually stored. Comments give the 24 June outcome.
_Z = ("(degradation rate: 22 μV/h,Figs.7e) and 2 A/cm (degradation rate: 52 μV/h), "
      "achieving an 89%reduction in degradation rate compared to unsupported Ir NPs (460 μV/h).")
_ZP = _Z.replace("(460 μV/h)", "(460 V/h)")  # paddle: OCR dropped the µ
_QP = r"the 1,5o0-h test oa  s $2.3–2.8\mu\mathrm{V}\mathrm{h}^{-1}$  eee e e ee"
_QR = "voltage degradation ranging from 32 mV to 126 mV over 1,000 h"


@_pytest.mark.parametrize(
    "value,source,canonical,verdict,expected",
    [
        (0.022, _Z, "mV/h", OK, 0.022),      # was refused (mis-citation): correct conversion
        (0.052, _Z, "mV/h", OK, 0.052),      # was refused
        (0.46, _Z, "mV/h", OK, 0.46),        # was refused
        (22.0, _Z, "mV/h", OK, 0.022),       # was re-derived to 0.022
        (22.0, _Z + " " + _Z, "mV/h", OK, 0.022),  # docling duplicate paragraph: was stored as 22
        (460.0, _ZP, "mV/h", UNIT, None),    # was INSERTED as 460 mV/h (1000× too large)
        (0.46, _ZP, "mV/h", MISCITE, None),  # was refused; the span no longer shows the µ
        (2.3, _QP, "mV/h", UNIT, None),      # was INSERTED as 2.3 mV/h (1000× too large)
        (2.8, _QP, "mV/h", OK, 0.0028),      # was re-derived to 0.0028
        (0.0023, _QP, "mV/h", OK, 0.0023),   # was refused: correct conversion
        (0.0028, _QP, "mV/h", OK, 0.0028),   # was refused: correct conversion
        (0.00255, _QP, "mV/h", MISCITE, None),  # model-computed midpoint: still refused
        (0.126, _QR, "mV/h", MISCITE, None),    # model-computed rate: still refused
        (0.079, _QR, "mV/h", MISCITE, None),    # model-computed rate: still refused
        (126.0, _QR, "mV/h", OK, 126.0),     # passes here; gate 6 (100 mV/h) refuses it
        (236.0, "the overpotential was 236 mV at 10 mA cm-2", "mV", OK, 236.0),
        (999.0, "the overpotential was 236 mV at 10 mA cm-2", "mV", MISCITE, None),
        (236.0, "η of 0.236 V vs RHE", "mV", OK, 236.0),     # V → mV conversion
        (0.236, "η of 0.236 V vs RHE", "mV", UNIT, None),    # raw volts under mV
        (250.0, "236 and 250 mV for A and B", "mV", OK, 250.0),
        (1200.0, "η of 1,200 mV", "mV", OK, 1200.0),         # thousands comma
        (-236.0, "η = −236 mV for HER", "mV", OK, -236.0),   # sign kept
        (1466.0, "E = 1.466 VRHE at 10 mA", "mV", OK, 1466.0),  # V glued to RHE still volts
        # recorded strictness (see the check_milli_value docstring): these refuse
        (52.6, "52.63 mV dec-1", "mV/decade", MISCITE, None),  # rounded by the model
        (1.234, "1,234 mV", "mV", MISCITE, None),             # decimal comma reads as 1234
        (1500.0, "1 500 mV", "mV", MISCITE, None),            # space thousands separator
        # recorded limitation: a converted reading of another quantity is accepted
        (1530.0, "1.53 V vs RHE", "mV", OK, 1530.0),
    ],
)
def test_check_milli_value_review_examples(value, source, canonical, verdict, expected):
    test_check_milli_value(value, source, canonical, verdict, expected)
