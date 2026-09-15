"""OCR.space: hosted OCR on a free tier, no card and no model download.

`ocr.py` reads an image with a vision model, which handles handwriting and can
be told to ignore a struck-out line - but it needs a paid API key. This is the
other end of the trade: OCR.space gives 25,000 pages a month for nothing, and
in exchange it is a **printed-text** engine. Its own documentation says it does
not do handwriting.

So the honest expectation is that this reads typed invoices, printed bills and
screenshots well, and handwritten slips poorly or not at all. It is wired up
anyway because "poorly" is worth measuring rather than assuming, and because
the human confirm screen catches whatever it gets wrong - nothing here writes
to the books.

Two free-tier limits shape the code:

* **1 MB per upload.** Phone photos are bigger than that, so `prepare()`
  re-encodes before sending.
* **No handwriting model**, which no amount of preprocessing fixes. Grayscale
  and contrast still help on printed text, so `prepare()` does them.
"""

from __future__ import annotations

import io
import logging

import httpx

from ..core.config import settings

log = logging.getLogger("smartsme.ai.ocrspace")

API = "https://api.ocr.space/parse/image"

#: The free tier rejects anything larger, with a message rather than a status.
MAX_UPLOAD = 1024 * 1024

#: Beyond this the engine gains nothing and the upload gets slower.
MAX_EDGE = 2200


class OcrUnavailable(RuntimeError):
    """No key, or the service refused the request."""


def enabled() -> bool:
    return bool(settings.ocr_space_api_key)


def prepare(data: bytes, max_bytes: int = MAX_UPLOAD) -> bytes:
    """Re-encode an image so the free tier will accept it.

    Grayscale, because colour carries nothing for text and costs a third of the
    bytes; JPEG, because these are photographs and PNG is the wrong container
    for a photograph; then quality and finally size come down until it fits.
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as image:
        # EXIF orientation first: a photo taken sideways otherwise reaches the
        # engine sideways, and no OCR recovers from that.
        prepared = ImageOps.exif_transpose(image)
        prepared = ImageOps.grayscale(prepared)
        prepared = ImageOps.autocontrast(prepared, cutoff=1)

        if max(prepared.size) > MAX_EDGE:
            scale = MAX_EDGE / max(prepared.size)
            new_size = (max(1, int(prepared.width * scale)), max(1, int(prepared.height * scale)))
            prepared = prepared.resize(new_size, Image.LANCZOS)

        for quality in (85, 70, 55, 40):
            buffer = io.BytesIO()
            prepared.save(buffer, format="JPEG", quality=quality, optimize=True)
            if buffer.tell() <= max_bytes:
                return buffer.getvalue()

        # Still too big: halve the longest edge and try once more. Text this
        # small is not going to be read anyway, but failing loudly beats
        # sending something the server will reject.
        half = (max(1, prepared.width // 2), max(1, prepared.height // 2))
        buffer = io.BytesIO()
        prepared.resize(half, Image.LANCZOS).save(buffer, format="JPEG", quality=70, optimize=True)
        return buffer.getvalue()


def read_text(data: bytes, filename: str = "order.jpg") -> str:
    """The text OCR.space finds in one image.

    Raises `OcrUnavailable` when there is no key or the service refuses, and
    returns "" when it simply found nothing - those are different situations and
    callers treat them differently.
    """
    if not enabled():
        raise OcrUnavailable(
            "No OCR_SPACE_API_KEY is set. Get a free key at https://ocr.space/ocrapi "
            "and put it in backend/.env."
        )

    payload = prepare(data)
    try:
        response = httpx.post(
            API,
            data={
                "apikey": settings.ocr_space_api_key,
                # Engine 2 is the newer model and noticeably better on the
                # short, unstructured lines an order slip is made of.
                "OCREngine": str(settings.ocr_space_engine),
                "language": "eng",
                "scale": "true",
                "detectOrientation": "true",
                "isTable": "true",
            },
            files={"file": (filename, payload, "image/jpeg")},
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as err:
        raise OcrUnavailable(f"Could not reach OCR.space: {err}") from err
    except ValueError as err:
        raise OcrUnavailable("OCR.space returned something that was not JSON.") from err

    if body.get("IsErroredOnProcessing"):
        message = body.get("ErrorMessage") or body.get("ErrorDetails") or "unknown error"
        if isinstance(message, list):
            message = "; ".join(str(m) for m in message)
        raise OcrUnavailable(f"OCR.space refused the image: {message}")

    results = body.get("ParsedResults") or []
    if not results:
        return ""
    return (results[0].get("ParsedText") or "").strip()


__all__ = ["MAX_UPLOAD", "OcrUnavailable", "enabled", "prepare", "read_text"]
