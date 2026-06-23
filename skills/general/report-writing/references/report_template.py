"""HTML report skeleton over the palimpsest RDF graph.

Adapt: change STORE_PATH, the SPARQL queries, and the prose. Emits a single
self-contained HTML file. plotly.graph_objects only (no pandas, no kaleido).
"""

import plotly.graph_objects as go

from palimpsest.store import RDFStore

STORE_PATH = "store"
OUT = "workspace/reports/report.html"

QUERY = """
PREFIX palim: <https://w3id.org/palimpsest/>
PREFIX emmo: <https://w3id.org/emmo/domain/electrochemistry#>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?value ?paper ?parser ?page WHERE {
  ?m a emmo:electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6 ;  # Overpotential
     palim:value ?value ;
     prov:hadPrimarySource ?e .
  ?e palim:paper ?paper ; palim:parserName ?parser ; palim:page ?page .
}
"""


def build() -> str:
    rows = list(RDFStore(STORE_PATH).sparql(QUERY))
    values = [float(r["value"]) for r in rows]
    fig = go.Figure(data=[go.Histogram(x=values)])
    table = go.Figure(
        data=[go.Table(
            header=dict(values=["paper", "parser", "page"]),
            cells=dict(values=[
                [r["paper"] for r in rows],
                [r["parser"] for r in rows],
                [r["page"] for r in rows],
            ]),
        )]
    )
    parts = [
        "<h1>OER extraction report</h1>",
        fig.to_html(full_html=False, include_plotlyjs="cdn"),
        "<h2>Provenance</h2>",
        table.to_html(full_html=False, include_plotlyjs=False),
    ]
    return "<html><body>" + "\n".join(parts) + "</body></html>"


if __name__ == "__main__":
    from pathlib import Path

    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    Path(OUT).write_text(build(), encoding="utf-8")
