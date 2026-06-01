# Tafel conventions for acidic OER

## Equation

The Tafel relation links overpotential to current density in the
kinetically-controlled regime:

```
η = a + b · log10(j / j0)
```

- `η` is overpotential in mV (always positive for OER).
- `j` is current density in mA cm⁻² (or A cm⁻², be explicit).
- `j0` is exchange current density (extrapolation of the Tafel line to η=0).
- `b` is the Tafel slope in **mV decade⁻¹**. Reported as a positive
  magnitude for OER.
- `a` is the intercept; rarely reported standalone — `j0` is the useful
  invariant.

## Sign and intercept handling

- Magnitude only. A paper writing `b = -42 mV/dec` for OER is using a
  cathodic-positive convention; convert to positive 42 mV/dec.
- If a paper reports `a` (in mV) and `b` (in mV/dec) but not `j0`, derive
  `j0 = 10^(-a/b)` and record both `tafel_slope` and `exchange_current_density`.
- If a paper reports `j0` but no `b`, do **not** invent a slope — `j0`
  alone is ambiguous (you need the slope to interpret extrapolation).

## Fit range — the field most often omitted

The Tafel slope depends on the current-density range used for the fit. A
clean acidic OER catalyst will show:

- A low-η Tafel region (typically 40–60 mV/dec for Ir-based, 30–40 mV/dec
  for some Ru-based) over roughly 0.1–10 mA cm⁻²_geom.
- A higher-η region (often 70–120 mV/dec) above 10–100 mA cm⁻², where
  mass-transport limitations or rate-determining-step transitions appear.

Fitting across both regions blends two physical regimes. Always record:

- `tafel_fit_j_min` (mA cm⁻²)
- `tafel_fit_j_max` (mA cm⁻²)
- `iR_correction` (true / false / unknown)

If the paper shows the Tafel plot but does not report numeric fit bounds,
estimate them from the plot and flag them as `extracted_from_figure`.
