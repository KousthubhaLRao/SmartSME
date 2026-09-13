"""Smart Input endpoints: parse text, parse an image, publish the draft."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select

from ..ai.client import ai_status, has_vision
from ..core.deps import CurrentUser, Db, require
from ..core.roles import P
from ..models import Party, Product
from ..schemas import ParseTextInput
from ..smart_input import draft_from_image, draft_from_text, publish_draft
from ..worker import drain_queue

router = APIRouter(prefix="/api/input", tags=["smart-input"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024


@router.get("/status", dependencies=[Depends(require(P.DATA_READ))])
def status(ctx: CurrentUser, db: Db) -> dict:
    parties = list(
        db.scalars(select(Party).where(Party.business_id == ctx.business.id).order_by(Party.name))
    )
    products = list(
        db.scalars(
            select(Product).where(Product.business_id == ctx.business.id).order_by(Product.name)
        )
    )
    ai = ai_status()
    return {
        "hasAI": ai is not None,
        "aiLabel": (ai or {}).get("label"),
        "hasVision": has_vision(),
        "parties": [{"id": str(p.id), "name": p.name, "type": p.type} for p in parties],
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "unit": p.unit,
                "sellingPrice": p.selling_price,
                "purchasePrice": p.purchase_price,
            }
            for p in products
        ],
        "taxRate": ctx.business.tax_rate,
        "currency": ctx.business.currency,
    }


@router.post("/parse-text", dependencies=[Depends(require(P.DATA_READ))])
def parse_text(body: ParseTextInput, ctx: CurrentUser, db: Db) -> dict:
    try:
        return {"draft": draft_from_text(db, ctx.business.id, body.text)}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.post("/parse-image", dependencies=[Depends(require(P.DATA_READ))])
async def parse_image(ctx: CurrentUser, db: Db, file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="That image is too large. Try a smaller photo.")
    media_type = (file.content_type or "").lower()
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    try:
        encoded = base64.b64encode(raw).decode()
        return {"draft": draft_from_image(db, ctx.business.id, encoded, media_type)}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(status_code=502, detail=str(err)) from err


@router.post("/publish", dependencies=[Depends(require(P.TXN_WRITE))])
def publish(payload: dict[str, Any], ctx: CurrentUser, db: Db) -> dict:
    try:
        result = publish_draft(db, ctx.business.id, payload)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    drain_queue()
    return result
