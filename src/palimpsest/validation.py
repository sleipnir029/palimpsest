"""T23 — SHACL validation: Pydantic instance → JSON-LD → rdflib → pyshacl.

Belt-and-suspenders gate between T22 (Pydantic-validated extraction) and T24
(graph insert). Pydantic already enforces the required slots after T19's audit
(``Evidence.{paper, page, bbox, parser_name}``, ``Paper.sha256``); SHACL adds
``sh:closed`` and cross-class ``sh:class`` constraints that only fire once the
instance is rendered as RDF with explicit ``rdf:type`` on each node.

The conversion path injects ``@type`` at the root and at every nested
``BaseModel`` field, then leans on ``schema/generated/context.jsonld`` for slot
→ IRI mapping so the predicate URIs stay in sync with whatever T19's pipeline
emits (no hand-duplicated slot URIs here).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pyshacl
from pydantic import BaseModel
from rdflib import Graph

_SHAPES_PATH = Path("schema/generated/shacl.ttl")
_CONTEXT_PATH = Path("schema/generated/context.jsonld")


@lru_cache(maxsize=1)
def _shapes() -> Graph:
    """Parse ``shacl.ttl`` once per process."""
    return Graph().parse(_SHAPES_PATH, format="turtle")


@lru_cache(maxsize=1)
def _context() -> str:
    """The full @context block as a JSON string (rdflib accepts it inline)."""
    return json.dumps(json.loads(_CONTEXT_PATH.read_text())["@context"])


def _walk_attach_types(data: dict, instance: BaseModel) -> None:
    """Inject ``@type`` recursively, walking parallel instance + dumped dict.

    Each Pydantic sub-instance becomes an RDF node; SHACL's ``sh:targetClass``
    only fires when those nodes carry ``rdf:type``. The walker matches sub-dicts
    in ``data`` against the corresponding ``BaseModel`` field on ``instance``;
    lists of BaseModel are not in the current schema, so we don't handle them.
    """
    data["@type"] = instance.__class__.__name__
    for field_name in instance.__class__.model_fields:
        sub_inst = getattr(instance, field_name, None)
        sub_data = data.get(field_name)
        if isinstance(sub_inst, BaseModel) and isinstance(sub_data, dict):
            _walk_attach_types(sub_data, sub_inst)


def _to_jsonld(instance: BaseModel) -> dict:
    """Pydantic instance → JSON-LD dict ready for rdflib's json-ld parser."""
    data = instance.model_dump(mode="json", exclude_none=True)
    _walk_attach_types(data, instance)
    return {"@context": json.loads(_context()), **data}


def _validate_jsonld(data: dict) -> tuple[bool, str]:
    """Run pyshacl against a JSON-LD dict. Shared by ``validate_instance`` and
    the negative test (which hand-crafts a dict to exercise a SHACL-only catch
    that Pydantic would otherwise refuse to construct in the first place).
    """
    data_graph = Graph().parse(data=json.dumps(data), format="json-ld")
    conforms, _, report = pyshacl.validate(
        data_graph, shacl_graph=_shapes(), inference="none"
    )
    return conforms, report


def validate_instance(instance: BaseModel) -> tuple[bool, str]:
    """Convert one Pydantic instance to JSON-LD and validate against the
    generated SHACL shapes. Returns ``(conforms, pyshacl_report_text)``.
    """
    return _validate_jsonld(_to_jsonld(instance))


def validate_batch(
    instances: list[BaseModel],
) -> list[tuple[BaseModel, bool, str]]:
    """Per-instance validation; same order as input."""
    return [(inst, *validate_instance(inst)) for inst in instances]
