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
    PREFIX pmp: <https://palimpsest.local/schema/>
    SELECT ?value ?unit ?paper ?parser ?page WHERE {
      ?m a pmp:Overpotential ;
         pmp:value ?value ; pmp:unit_label ?unit ;
         pmp:evidence ?e .
      ?e pmp:paper ?paper ; pmp:parser_name ?parser ; pmp:page ?page .
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
