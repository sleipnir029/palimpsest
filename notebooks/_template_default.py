"""Default palimpsest analysis notebook (T33 template) — copied by the
open_notebook tool. Reads the RDF graph (populated by `python -m palimpsest
demo <pdf>`) and plots overpotentials. Open with `marimo edit`, never auto-run."""

import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def _():
    import marimo as mo
    import plotly.graph_objects as go

    from palimpsest.store import RDFStore

    return RDFStore, go, mo


@app.cell
def _(RDFStore):
    # Overpotentials are the measurements reported in "mV"; we filter on the unit
    # label rather than the rdf:type IRI (Overpotential's type is an opaque EMMO
    # hash whose resolution would fetch a 4.6 MB ontology at notebook-open).
    QUERY = """
    PREFIX palimpsest: <https://w3id.org/palimpsest/>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    PREFIX schema: <http://schema.org/>

    SELECT ?value ?title ?cd WHERE {
        ?m palimpsest:value ?value ;
           palimpsest:unitLabel ?unit ;
           prov:hadPrimarySource ?ev .
        ?ev palimpsest:paper ?paper .
        OPTIONAL { ?paper schema:name ?title }
        OPTIONAL { ?m palimpsest:condition ?c . ?c palimpsest:currentDensity ?cd }
        FILTER(?unit = "mV")
    }
    ORDER BY ?value
    """

    # "store" is the on-disk graph the viewer/demo populate. Guarded so the template
    # opens cleanly when the store is empty, absent, or held open by the viewer.
    try:
        rows = RDFStore("store").sparql(QUERY)
        store_error = None
    except Exception as exc:  # noqa: BLE001 - keep the template openable on any error
        rows, store_error = [], str(exc)
    return rows, store_error


@app.cell
def _(go, mo, rows, store_error):
    if store_error is not None:
        out = mo.md(f"⚠️ could not open the store: `{store_error}`")
    elif not rows:
        out = mo.md(
            "No overpotentials in the store yet — run "
            "`python -m palimpsest demo <pdf>` (with the viewer stopped) to populate it."
        )
    else:
        xpos = list(range(len(rows)))
        ticks = [f"{float(r['cd']):g}" if r.get("cd") else f"#{i + 1}"
                 for i, r in enumerate(rows)]
        fig = go.Figure(go.Bar(
            x=xpos,
            y=[float(r["value"]) for r in rows],
            text=[f"{float(r['value']):g}" for r in rows],
            hovertext=[r.get("title") or "" for r in rows],
        ))
        fig.update_layout(
            title="Overpotentials by paper",
            yaxis_title="overpotential (mV)",
            xaxis=dict(title="current density (mA/cm²)", tickmode="array",
                       tickvals=xpos, ticktext=ticks),
        )
        out = fig
    out
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## How to modify
        - **Other metrics:** `FILTER(?unit = "mV")` is an exact match on the unit
          label — change it to `"mV/dec"` (Tafel slope) or `"A/g"` (mass activity),
          or remove it to see every measurement.
        - **Another graph:** edit `RDFStore("store")` to point at a different store path.
        - **Group by paper:** the query returns `?title`; colour the bars by it.
        """
    )
    return


if __name__ == "__main__":
    app.run()
