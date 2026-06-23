"""marimo notebook skeleton — analysis of the palimpsest RDF graph.

Adapt: change STORE_PATH and the SPARQL query. Spawn via open_notebook; never
run headless. Charts use plotly.graph_objects (no pandas).
"""

import marimo

app = marimo.App()


@app.cell
def _():
    import plotly.graph_objects as go

    from palimpsest.store import RDFStore

    STORE_PATH = "store"
    QUERY = """
    PREFIX palim: <https://w3id.org/palimpsest/>
    PREFIX emmo: <https://w3id.org/emmo/domain/electrochemistry#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    SELECT ?value ?unit ?paper ?parser ?page WHERE {
      ?m a emmo:electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6 ;  # Overpotential
         palim:value ?value ; palim:unitLabel ?unit ;
         prov:hadPrimarySource ?e .
      ?e palim:paper ?paper ; palim:parserName ?parser ; palim:page ?page .
    }
    """
    rows = list(RDFStore(STORE_PATH).sparql(QUERY))
    return go, rows


@app.cell
def _(go, rows):
    values = [float(r["value"]) for r in rows]
    fig = go.Figure(data=[go.Histogram(x=values)])
    fig.update_layout(title="Overpotential distribution", xaxis_title="value")
    fig
    return


if __name__ == "__main__":
    app.run()
