"""dots.ocr → one JSON envelope, for the palimpsest parser registry (T17).

Usage: python dots_run.py <input.pdf> <output.json>

dots.ocr's own dots_ocr/parser.py needs a running vLLM server; we instead run the model in-process
via transformers (matching the chandra image's pattern) so the pod needs no separate server. Each
PDF page is rendered, prompted with dots.ocr's 'parse all' layout prompt, and the per-page JSON
(elements with bbox [x1,y1,x2,y2] + category + text; formulas=LaTeX, tables=HTML) is collected into
a single envelope:
    {"markdown": "<reading-order concatenation>", "pages": [[<elements>], ...]}
uniform with the other parsers' single-artifact outputs.

[VALIDATE ON POD] The attn_implementation, the exact per-page JSON shape, and process_vision_info
with PIL images are taken from the model card but not yet exercised on hardware — finalize after the
night pod run (e.g. switch to flash_attention_2 + flash-attn if sdpa is unsupported by the model).
"""

import json
import sys

import pypdfium2 as pdfium
import torch
from qwen_vl_utils import process_vision_info
from transformers import AutoModelForCausalLM, AutoProcessor

MODEL = "/opt/weights/DotsOCR"
PROMPT = (
    "Please output the layout information from the PDF image, including each layout element's "
    "bbox, its category, and the corresponding text content within the bbox.\n\n"
    "1. Bbox format: [x1, y1, x2, y2]\n\n"
    "2. Layout Categories: ['Caption','Footnote','Formula','List-item','Page-footer',"
    "'Page-header','Picture','Section-header','Table','Text','Title'].\n\n"
    "3. Formatting: Picture -> omit text; Formula -> LaTeX; Table -> HTML; others -> Markdown.\n\n"
    "4. Use the original text only (no translation), sorted in human reading order.\n\n"
    "5. The entire output must be a single JSON object."
)


def _render_pages(pdf: str, dpi: int = 150):
    doc = pdfium.PdfDocument(pdf)
    for i in range(len(doc)):
        yield doc[i].render(scale=dpi / 72).to_pil()


def main(pdf: str, out: str) -> None:
    model = AutoModelForCausalLM.from_pretrained(
        MODEL,
        attn_implementation="sdpa",  # no flash-attn dependency; see module docstring
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)

    pages: list = []
    md_parts: list[str] = []
    for img in _render_pages(pdf):
        messages = [{"role": "user", "content": [
            {"type": "image", "image": img}, {"type": "text", "text": PROMPT}]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(text=[text], images=image_inputs, videos=video_inputs,
                           padding=True, return_tensors="pt").to(model.device)
        gen = model.generate(**inputs, max_new_tokens=24000)
        trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen)]
        raw = processor.batch_decode(trimmed, skip_special_tokens=True)[0]
        try:
            elements = json.loads(raw)
        except json.JSONDecodeError:
            elements = [{"category": "Text", "text": raw}]  # keep raw text if not valid JSON
        pages.append(elements)
        for el in elements if isinstance(elements, list) else []:
            if isinstance(el, dict) and el.get("text"):
                md_parts.append(el["text"])

    with open(out, "w") as f:
        json.dump({"markdown": "\n\n".join(md_parts), "pages": pages}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
