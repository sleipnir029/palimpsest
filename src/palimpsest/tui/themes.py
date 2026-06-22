"""Selectable themes for the TUI — switch live with ``/theme``, persisted in the
``ui_theme`` setting. All share the per-message Scriptorium *structure* (the layout
in app.py); they differ only in palette, so each is a distinct visual identity that
stays on-par with the others. Colours reach styles.tcss as theme variables
($background/$foreground/$primary/$secondary/$accent).

- scriptorium — warm ink & parchment, oxidized copper. The namesake (default).
- vellum      — aged-paper LIGHT mode: cream ground, sepia ink, burnt-umber accent.
- oxide       — cool graphite instrument: redox cyan + oxidation amber (electrochem).
- catalogue   — slate-navy knowledge catalogue: IRI indigo + archival gold.
"""

from __future__ import annotations

from textual.theme import Theme

SCRIPTORIUM = Theme(
    name="scriptorium",
    primary="#b5651d",     # oxidized copper
    secondary="#8a7a5c",   # faded sepia (tool traces)
    accent="#d8b65a",      # vellum gold
    foreground="#e9dcc2",  # parchment
    background="#15110c",  # ink
    surface="#1c1712",
    panel="#241d16",
    success="#7a8c5a",
    warning="#c9a24b",
    error="#c0552d",
    dark=True,
)

VELLUM = Theme(
    name="vellum",
    primary="#9c5a1e",     # burnt umber
    secondary="#7a6a4c",   # dim sepia ink
    accent="#8a6d1f",      # antique gold
    foreground="#2b2218",  # iron-gall ink
    background="#ece3d0",  # aged paper
    surface="#e2d8c2",
    panel="#d8ccb2",
    success="#5a6a32",
    warning="#9a7a1f",
    error="#9c3a1e",
    dark=False,
)

OXIDE = Theme(
    name="oxide",
    primary="#34c2d6",     # reduction cyan (data/ok)
    secondary="#5a6470",   # slate (traces)
    accent="#e0a030",      # oxidation amber (cost/warn)
    foreground="#d7dde2",  # platinum
    background="#11151a",  # graphite
    surface="#171c22",
    panel="#1d242c",
    success="#34c2a0",
    warning="#e0a030",
    error="#d65a4a",
    dark=True,
)

CATALOGUE = Theme(
    name="catalogue",
    primary="#7c89f0",     # IRI indigo
    secondary="#5b6172",   # citation slate
    accent="#c9a24b",      # archival gold
    foreground="#e6e8ee",  # parchment white
    background="#14171f",  # slate navy
    surface="#1a1e28",
    panel="#222736",
    success="#6fa07a",
    warning="#c9a24b",
    error="#c05a6a",
    dark=True,
)

THEMES: dict[str, Theme] = {t.name: t for t in (SCRIPTORIUM, VELLUM, OXIDE, CATALOGUE)}
DEFAULT_THEME = "scriptorium"
