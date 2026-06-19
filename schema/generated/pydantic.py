# GENERATED — DO NOT EDIT BY HAND. Run: pixi run schema
from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.11.0"
version = "0.1.0"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'palimpsest',
     'default_range': 'string',
     'description': 'LinkML schema for structured OER catalyst data extracted from '
                    'research PDFs. Aligned to EMMO Domain Electrochemistry (ECHO) '
                    'for concepts, QUDT for units, PROV-O for extraction '
                    'provenance, and schema.org for bibliographic metadata. '
                    'palimpsest-local IRIs are used (with skos:closeMatch to '
                    'nearest EMMO term) where EMMO has not yet minted a concept; '
                    'each such case carries a TODO_EMMO_UPSTREAM: comment naming '
                    'the term to request.',
     'id': 'https://w3id.org/palimpsest/v1',
     'imports': ['linkml:types'],
     'license': 'MIT',
     'name': 'palimpsest',
     'prefixes': {'emmo': {'prefix_prefix': 'emmo',
                           'prefix_reference': 'https://w3id.org/emmo/domain/electrochemistry#'},
                  'h2kg': {'prefix_prefix': 'h2kg',
                           'prefix_reference': 'https://w3id.org/h2kg/hydrogen-ontology#'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'palimpsest': {'prefix_prefix': 'palimpsest',
                                 'prefix_reference': 'https://w3id.org/palimpsest/'},
                  'prov': {'prefix_prefix': 'prov',
                           'prefix_reference': 'http://www.w3.org/ns/prov#'},
                  'qudt': {'prefix_prefix': 'qudt',
                           'prefix_reference': 'http://qudt.org/vocab/unit/'},
                  'schema': {'prefix_prefix': 'schema',
                             'prefix_reference': 'http://schema.org/'},
                  'skos': {'prefix_prefix': 'skos',
                           'prefix_reference': 'http://www.w3.org/2004/02/skos/core#'},
                  'xsd': {'prefix_prefix': 'xsd',
                          'prefix_reference': 'http://www.w3.org/2001/XMLSchema#'}},
     'source_file': 'schema/palimpsest.yaml',
     'title': 'palimpsest OER extraction schema'} )

class IRCorrectionEnum(str, Enum):
    applied = "applied"
    not_applied = "not_applied"
    unknown = "unknown"


class NormalizationBasisEnum(str, Enum):
    geometric = "geometric"
    ECSA = "ECSA"
    BET = "BET"
    mass = "mass"


class CellTypeFamilyEnum(str, Enum):
    RDE = "RDE"
    three_electrode_flow = "three_electrode_flow"
    single_cell_MEA = "single_cell_MEA"
    stack = "stack"


class ElectrolyteFamilyEnum(str, Enum):
    acid = "acid"
    alkaline = "alkaline"
    neutral = "neutral"


class ScanRateRegimeEnum(str, Enum):
    steady_state = "steady_state"
    slow_LSV = "slow_LSV"
    fast_LSV = "fast_LSV"
    fast_CV = "fast_CV"



class Paper(ConfiguredBaseModel):
    """
    A research article that palimpsest has parsed.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'schema:ScholarlyArticle',
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    doi: Optional[str] = Field(default=None, description="""DOI of the paper.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Paper'], 'slot_uri': 'schema:identifier'} })
    title: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Paper'], 'slot_uri': 'schema:name'} })
    authors: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Paper'], 'slot_uri': 'schema:author'} })
    sha256: str = Field(default=..., description="""SHA-256 of the raw PDF bytes (T07 contract); identity key for the Paper, completes the \"paper_hash\" half of the provenance non-negotiable on Evidence.paper.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Paper'], 'slot_uri': 'palimpsest:sha256'} })


class Measurement(ConfiguredBaseModel):
    """
    Abstract base for any numeric OER metric extracted from a paper.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'class_uri': 'palimpsest:Measurement',
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class Overpotential(Measurement):
    """
    Deviation of the electrode potential from its equilibrium value.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'emmo:electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6',
         'close_mappings': ['h2kg:Overpotential'],
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class TafelSlope(Measurement):
    """
    Slope of overpotential vs log(current density) in the Tafel region.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:TafelSlope',
         'close_mappings': ['emmo:electrochemistry_d48ea516_5cac_4f86_bc88_21b6276c0938',
                            'h2kg:TafelSlope'],
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class ExchangeCurrentDensity(Measurement):
    """
    Current density at zero overpotential; Butler-Volmer i0.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'emmo:electrochemistry_e9fd9ef9_adfe_46cb_b2f9_4558468a25e7',
         'close_mappings': ['h2kg:ExchangeCurrentDensity'],
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class ChargeTransferCoefficient(Measurement):
    """
    Butler-Volmer alpha; fraction of overpotential affecting forward reaction.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'emmo:electrochemistry_a4dfa5c1_55a9_4285_b71d_90cf6613ca31',
         'close_mappings': ['h2kg:ChargeTransferCoefficient'],
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class MassActivity(Measurement):
    """
    Catalytic current per unit mass of active material (A/g).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:MassActivity',
         'close_mappings': ['h2kg:MassActivity'],
         'from_schema': 'https://w3id.org/palimpsest/v1',
         'related_mappings': ['emmo:electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841']})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class TurnoverFrequency(Measurement):
    """
    Catalytic events per active site per second.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:TurnoverFrequency',
         'close_mappings': ['h2kg:TurnoverFrequency'],
         'from_schema': 'https://w3id.org/palimpsest/v1',
         'related_mappings': ['emmo:electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841']})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class ECSA(Measurement):
    """
    Electrochemically active surface area.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'emmo:electrochemistry_bad1b6f4_1b26_40e2_b552_6d53873e3973',
         'close_mappings': ['h2kg:ElectrochemicallyActiveSurfaceArea'],
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class SpecificActivity(Measurement):
    """
    OER current normalized to electrochemically active surface area (mA/cm2_ECSA).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:SpecificActivity',
         'from_schema': 'https://w3id.org/palimpsest/v1',
         'related_mappings': ['emmo:electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841']})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class Stability(Measurement):
    """
    Duration a catalyst sustains OER at a held current density (hours).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:Stability',
         'from_schema': 'https://w3id.org/palimpsest/v1',
         'related_mappings': ['emmo:electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841']})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class PEMWECellVoltage(Measurement):
    """
    Full-cell operating voltage at a stated cell current density (PEMWE single cell).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:PEMWECellVoltage',
         'close_mappings': ['h2kg:CellVoltage'],
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class DegradationRate(Measurement):
    """
    Rate of cell-voltage rise during a PEMWE durability hold (mV/h).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:DegradationRate',
         'close_mappings': ['h2kg:CellVoltageIncreaseRate'],
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    value: Optional[float] = Field(default=None, description="""Numeric value of the measurement, in the unit named by unit_label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:value'} })
    unit_label: Optional[str] = Field(default=None, description="""Human-readable unit (e.g. \"mV\", \"mA/cm2\"); QUDT IRI on the typed class.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:unitLabel'} })
    condition: Optional[Condition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'palimpsest:condition'} })
    evidence: Optional[Evidence] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Measurement'], 'slot_uri': 'prov:hadPrimarySource'} })


class Catalyst(ConfiguredBaseModel):
    """
    An electrocatalyst material under study.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'emmo:electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841',
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    name: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Catalyst'], 'slot_uri': 'schema:name'} })
    composition: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Catalyst'], 'slot_uri': 'palimpsest:composition'} })
    support: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Catalyst'], 'slot_uri': 'palimpsest:support'} })


class Electrolyte(ConfiguredBaseModel):
    """
    Electrolyte solution used in the electrochemical cell.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:Electrolyte',
         'from_schema': 'https://w3id.org/palimpsest/v1',
         'related_mappings': ['emmo:electrochemistry_6592d8cc_4ce4_42ca_b010_6bfc4a8444d2',
                              'emmo:electrochemistry_615cff2a_be95_4e65_9471_98db23f4c878']})

    formula: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Electrolyte'], 'slot_uri': 'palimpsest:formula'} })
    concentration: Optional[float] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Electrolyte'],
         'slot_uri': 'palimpsest:concentration',
         'unit': {'exact_mappings': ['qudt:MOL-PER-L'], 'ucum_code': 'mol/L'}} })
    electrolyte_ph: Optional[float] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Electrolyte'],
         'related_mappings': ['emmo:electrochemistry_6592d8cc_4ce4_42ca_b010_6bfc4a8444d2',
                              'emmo:electrochemistry_615cff2a_be95_4e65_9471_98db23f4c878'],
         'slot_uri': 'palimpsest:electrolytePH',
         'unit': {'ucum_code': '[pH]'}} })


class Condition(ConfiguredBaseModel):
    """
    Experimental conditions under which a measurement was taken.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'palimpsest:Condition',
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    current_density: Optional[float] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'],
         'slot_uri': 'palimpsest:currentDensity',
         'unit': {'exact_mappings': ['qudt:MilliA-PER-CentiM2'], 'ucum_code': 'mA/cm2'}} })
    electrode_potential_vs_rhe: Optional[float] = Field(default=None, json_schema_extra = { "linkml_meta": {'close_mappings': ['emmo:electrochemistry_f509645f_eb27_470e_9112_7ab828ed40d3'],
         'domain_of': ['Condition'],
         'slot_uri': 'palimpsest:potentialVsRHE',
         'unit': {'exact_mappings': ['qudt:V'], 'ucum_code': 'V'}} })
    temperature_C: Optional[float] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'],
         'slot_uri': 'palimpsest:temperatureC',
         'unit': {'exact_mappings': ['qudt:DEG_C'], 'ucum_code': 'Cel'}} })
    electrolyte: Optional[Electrolyte] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'], 'slot_uri': 'palimpsest:electrolyte'} })
    cell_type: Optional[str] = Field(default=None, description="""e.g. \"three-electrode half-cell\", \"MEA\", \"flow cell\".""", json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'], 'slot_uri': 'palimpsest:cellType'} })
    scan_rate: Optional[float] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'],
         'related_mappings': ['emmo:electrochemistry_29f2a35a_8c09_429d_b9e8_33f3e1fc3671'],
         'slot_uri': 'palimpsest:scanRate',
         'unit': {'exact_mappings': ['qudt:MilliV-PER-SEC'], 'ucum_code': 'mV/s'}} })
    catalyst_loading: Optional[float] = Field(default=None, description="""Catalyst (typically anode Ir) loading on the electrode.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'],
         'slot_uri': 'palimpsest:catalystLoading',
         'unit': {'ucum_code': 'mg/cm2'}} })
    iR_correction: Optional[IRCorrectionEnum] = Field(default=None, description="""Whether the reported value is iR-corrected.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'], 'slot_uri': 'palimpsest:iRCorrection'} })
    normalization_basis: Optional[NormalizationBasisEnum] = Field(default=None, description="""Surface-area/mass basis the value is normalized to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'], 'slot_uri': 'palimpsest:normalizationBasis'} })
    cell_type_family: Optional[CellTypeFamilyEnum] = Field(default=None, description="""Coarse cell-architecture family (machine-readable peer of cell_type).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'], 'slot_uri': 'palimpsest:cellTypeFamily'} })
    electrolyte_family: Optional[ElectrolyteFamilyEnum] = Field(default=None, description="""Coarse electrolyte pH family.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'], 'slot_uri': 'palimpsest:electrolyteFamily'} })
    scan_rate_regime: Optional[ScanRateRegimeEnum] = Field(default=None, description="""Coarse scan-rate regime.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Condition'], 'slot_uri': 'palimpsest:scanRateRegime'} })


class Evidence(ConfiguredBaseModel):
    """
    Provenance anchor for an extracted triple, per CLAUDE.md non-negotiable.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'prov:Entity', 'from_schema': 'https://w3id.org/palimpsest/v1'})

    paper: Paper = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'palimpsest:paper'} })
    page: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'palimpsest:page'} })
    bbox_x0: float = Field(default=..., description="""Page-relative left edge (x0) of the source region.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'palimpsest:bboxX0'} })
    bbox_y0: float = Field(default=..., description="""Page-relative top edge (y0) of the source region.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'palimpsest:bboxY0'} })
    bbox_x1: float = Field(default=..., description="""Page-relative right edge (x1) of the source region.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'palimpsest:bboxX1'} })
    bbox_y1: float = Field(default=..., description="""Page-relative bottom edge (y1) of the source region.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'palimpsest:bboxY1'} })
    source_text: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'palimpsest:sourceText'} })
    parser_name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence'], 'slot_uri': 'palimpsest:parserName'} })


class OxygenEvolutionReaction(ConfiguredBaseModel):
    """
    The anodic half-reaction producing O2 from water.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'broad_mappings': ['emmo:electrochemistry_2e3e14f9_4cb8_45b2_908e_47eec893dec8'],
         'class_uri': 'palimpsest:OxygenEvolutionReaction',
         'close_mappings': ['emmo:electrochemistry_a0580fa9_5073_44af_b33e_7adbc83892d0'],
         'from_schema': 'https://w3id.org/palimpsest/v1'})

    pass


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
Paper.model_rebuild()
Measurement.model_rebuild()
Overpotential.model_rebuild()
TafelSlope.model_rebuild()
ExchangeCurrentDensity.model_rebuild()
ChargeTransferCoefficient.model_rebuild()
MassActivity.model_rebuild()
TurnoverFrequency.model_rebuild()
ECSA.model_rebuild()
SpecificActivity.model_rebuild()
Stability.model_rebuild()
PEMWECellVoltage.model_rebuild()
DegradationRate.model_rebuild()
Catalyst.model_rebuild()
Electrolyte.model_rebuild()
Condition.model_rebuild()
Evidence.model_rebuild()
OxygenEvolutionReaction.model_rebuild()
