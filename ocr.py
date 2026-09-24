import base64
import json
import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

EXTRACTION_PROMPT = """You are looking at a photo of an auto parts invoice or receipt.

Extract two things and respond with ONLY a single JSON object, no other text, no markdown fences:

1. "header" - invoice-level info (appears once):
   - supplier: the company that issued the invoice (usually in the header/logo)
   - invoice_number: the invoice/order number if present (else empty string)
   - invoice_date: the date on the invoice if present, in YYYY-MM-DD format if you can tell (else empty string)
   - due_date: payment due date if printed, in YYYY-MM-DD format (else empty string)

2. "items" - every distinct part/line item on the invoice. For each one:
   - part_name: the part's description/name as printed
   - part_number: the part or SKU number if printed (else empty string)
   - cost: the price for that line item, as a plain number (no $ or commas). Leave null if you can't determine it.
   - fits: leave this as an empty string always. Do not guess at vehicle fitment - the user will fill this in themselves.

Example response:
{"header": {"supplier": "AutoZone Commercial", "invoice_number": "INV-88213", "invoice_date": "2026-08-14", "due_date": "2026-09-14"}, "items": [{"part_name": "Front brake pads", "part_number": "BP-4521", "cost": 42.99, "fits": ""}]}

If the image is not a legible invoice, respond with: {"header": {}, "items": []}
"""


def extract_invoice(image_bytes, media_type="image/jpeg"):
    b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_image,
                        },
                    },
                    {"type": "text", "text": EXTRACTION_PROMPT},
                ],
            }
        ],
    )

    text = "".join(block.text for block in response.content if block.type == "text").strip()

    # Strip stray markdown fences if the model adds them anyway
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
        header = parsed.get("header", {}) if isinstance(parsed, dict) else {}
        items = parsed.get("items", []) if isinstance(parsed, dict) else []
        if not isinstance(items, list):
            items = []
    except json.JSONDecodeError:
        header, items = {}, []

    return header, items
