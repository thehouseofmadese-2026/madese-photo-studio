"""
Thin wrapper around the Gemini image-editing model. Never reads or shows the
API key anywhere except pulling it from the environment (set via a local .env).
"""
import io
import os

from PIL import Image
from google import genai
from google.genai import errors as genai_errors

# gemini-2.5-flash-image is being shut down by Google on Oct 2, 2026, and cost
# more per image (and per input image) than these — see README for details.
DEFAULT_MODEL = "gemini-3.1-flash-lite-image"

# Selectable in the UI — label + rough per-image cost shown to the user before they generate.
MODEL_OPTIONS = [
    ("gemini-3.1-flash-lite-image", "⚡ Fast & Cheap — Lite", "~₹3/image"),
    ("gemini-3.1-flash-image", "⚖️ Balanced — Flash", "~₹5.7/image"),
    ("gemini-3-pro-image", "✨ Best Quality — Pro", "~₹11.5/image"),
]

_client = None  # cached for the process lifetime


class GeminiImageError(Exception):
    """Raised for any problem talking to Gemini — callers should catch this
    and show it in the UI rather than letting it crash the app."""


def get_client() -> "genai.Client":
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiImageError(
            "GEMINI_API_KEY is not set. Create a .env file in this folder with "
            "GEMINI_API_KEY=your_key_here, then restart the app."
        )
    _client = genai.Client(api_key=api_key)
    return _client


def generate_variant(
    image: Image.Image,
    instruction: str,
    reference_images: list | None = None,
    model: str | None = None,
    product_context: str | None = None,
) -> Image.Image:
    """Send one product photo + one instruction (optionally + style/composition
    reference images) to Gemini, return the edited image.

    `model` picks which image model to use for this call (see MODEL_OPTIONS);
    defaults to DEFAULT_MODEL if not given.

    `product_context` is free-text from the user describing what the product
    actually is and how it's used — passed ahead of the styling instruction so
    Gemini identifies the product correctly instead of guessing from pixels alone.

    Raises GeminiImageError on any failure (auth, network, safety block, no
    image returned, etc) — callers should catch this per-instruction so one
    bad call doesn't stop the rest of a batch.
    """
    if not instruction or not instruction.strip():
        raise GeminiImageError("Empty instruction.")

    client = get_client()
    model = model or DEFAULT_MODEL

    contents = []
    if product_context and product_context.strip():
        contents.append(
            "Context about the product in the photo below — use this to correctly "
            f"identify what it is before editing it: {product_context.strip()}"
        )
    contents.append(instruction.strip())

    if reference_images:
        contents += [
            "Primary product photo — this exact product must appear in the result:",
            image,
            "Reference image(s) below are for style, composition, lighting, or framing "
            "inspiration only — copy their look, not their product:",
            *reference_images,
        ]
    else:
        contents.append(image)

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
        )
    except genai_errors.APIError as e:
        raise GeminiImageError(f"Gemini API error: {e}") from e
    except Exception as e:  # network issues, timeouts, SDK bugs, etc.
        raise GeminiImageError(f"Could not reach Gemini: {e}") from e

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise GeminiImageError("Gemini returned no result (it may have been blocked by safety filters).")

    parts = getattr(candidates[0].content, "parts", None) or []
    for part in parts:
        inline_data = getattr(part, "inline_data", None)
        if inline_data is not None and inline_data.data:
            return Image.open(io.BytesIO(inline_data.data))

    # No image came back — surface whatever text Gemini gave us (often a refusal reason).
    text_bits = [p.text for p in parts if getattr(p, "text", None)]
    detail = " ".join(text_bits).strip() if text_bits else "Gemini did not return an image for this instruction."
    raise GeminiImageError(detail)
