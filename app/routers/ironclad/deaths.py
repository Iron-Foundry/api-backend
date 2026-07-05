from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile
from loguru import logger
from pydantic import ValidationError

from ._helpers import DinkDeathNotification, forward_to_webhook, ironclad_wom_cache

router = APIRouter()

_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg"}


@router.post("/deaths", status_code=204)
async def receive_death(request: Request) -> Response:
    """Receive, validate, and forward a Dink death notification for Ironclad."""
    content_type = request.headers.get("content-type", "")
    image_data: bytes | None = None
    image_content_type: str | None = None
    payload_dict: Any = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        raw = form.get("payload_json")
        if not isinstance(raw, str):
            logger.warning("ironclad: multipart request missing payload_json field")
            raise HTTPException(status_code=422, detail="Missing payload_json field")
        try:
            payload_dict = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("ironclad: invalid JSON in payload_json: {}", exc)
            raise HTTPException(422, f"Invalid JSON in payload_json: {exc}") from exc
        file_field = form.get("file")
        if file_field is not None and isinstance(file_field, UploadFile):
            ct = file_field.content_type or ""
            if ct not in _ALLOWED_IMAGE_TYPES:
                logger.warning("ironclad: rejected unsupported image type {!r}", ct)
                raise HTTPException(422, f"Unsupported image type: {ct!r}")
            image_data = await file_field.read()
            if len(image_data) > _MAX_IMAGE_BYTES:
                logger.warning("ironclad: rejected image exceeding 8 MB limit")
                raise HTTPException(422, "Image exceeds 8 MB limit")
            image_content_type = ct
    else:
        try:
            payload_dict = await request.json()
        except Exception as exc:
            logger.warning("ironclad: invalid JSON body: {}", exc)
            raise HTTPException(422, "Invalid JSON body") from exc

    try:
        notification = DinkDeathNotification.model_validate(payload_dict)
    except ValidationError as exc:
        logger.warning("ironclad: payload validation failed: {}", exc.errors())
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    members = await ironclad_wom_cache.get_members()
    if notification.playerName.lower() not in members:
        logger.info(
            "ironclad: rejected death for {} - not in WOM group",
            notification.playerName,
        )
        raise HTTPException(
            status_code=422, detail="playerName not found in Ironclad WOM group"
        )

    await forward_to_webhook(notification, image_data, image_content_type)
    logger.info("ironclad: forwarded death for {}", notification.playerName)
    return Response(status_code=204)
