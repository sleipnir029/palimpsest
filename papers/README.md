# Example papers

Four open-access acidic OER / PEM electrolyzer papers, bundled so you can try palimpsest
without parsing anything yourself. Their parser outputs (docling, MinerU, dots.ocr,
PaddleOCR; chandra for the first) are in `cache/<sha256>/`, so the agent can extract
from them with only an LLM key. The docling outputs were saved without their embedded
page images to keep the repository small; the text, layout and bounding boxes are intact.

All four are published under the Creative Commons Attribution 4.0 licence
([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)) and are redistributed here
unmodified. Copyright stays with the authors.

| File | Article |
|---|---|
| `s41467-022-35426-8.pdf` | Zhu et al., "Iridium single atoms incorporated in Co3O4 efficiently catalyze the oxygen evolution in acidic conditions", *Nature Communications* 13 (2022). [doi:10.1038/s41467-022-35426-8](https://doi.org/10.1038/s41467-022-35426-8) |
| `s41467-023-40912-8.pdf` | Wang et al., "Nano-metal diborides-supported anode catalyst with strongly coupled TaOx/IrO2 catalytic layer for low-iridium-loading proton exchange membrane electrolyzer", *Nature Communications* 14 (2023). [doi:10.1038/s41467-023-40912-8](https://doi.org/10.1038/s41467-023-40912-8) |
| `s41467-025-63541-9.pdf` | Zhang et al., "Support-tuned iridium reconstruction with crystalline phase dominating acidic oxygen evolution", *Nature Communications* 16 (2025). [doi:10.1038/s41467-025-63541-9](https://doi.org/10.1038/s41467-025-63541-9) |
| `s41929-024-01168-7.pdf` | Liang et al., "Unravelling the effects of active site density and energetics on the water oxidation activity of iridium oxides", *Nature Catalysis* 7 (2024). [doi:10.1038/s41929-024-01168-7](https://doi.org/10.1038/s41929-024-01168-7) |

Add your own PDFs to this folder. Parsing a new PDF runs on a cloud GPU (see the main
README, "Parsing your own PDFs").
