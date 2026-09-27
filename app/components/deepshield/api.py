import reflex as rx

import asyncio
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.components.deepshield.contracts import (
    DetectionResponse,
    MediaRequest,
    MultimodalRequest,
    TextRequest,
)
from app.components.deepshield.service import DetectionService


class BodyLimit:
    def __init__(self, app, maximum: int):
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        size = 0
        chunks = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.maximum:
                response = JSONResponse(
                    {"status": "invalid_input", "reason": "request_too_large"},
                    status_code=413,
                )
                return await response(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if chunks:
                return chunks.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        return await self.app(scope, replay, send)


def create_api(service: DetectionService | None = None) -> FastAPI:
    engine = service or DetectionService()
    api = FastAPI(
        title="DeepShield detection",
        version="0.2.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    api.add_middleware(BodyLimit, maximum=engine.settings.max_body_bytes)
    admission = asyncio.Semaphore(2)

    @api.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {
                "status": "invalid_input",
                "reason": "request_schema_validation_failed",
            },
            status_code=422,
        )

    async def single(modality: str, payload: MediaRequest | TextRequest):
        if admission.locked():
            return JSONResponse(
                {"status": "unavailable", "reason": "capacity_exceeded"},
                status_code=503,
            )
        async with admission:
            result = await asyncio.to_thread(engine.detect, modality, payload)
        return DetectionResponse(request_id=str(uuid4()), results=[result])

    @api.get("/health")
    async def health():
        return {
            "status": "ok",
            "scope": "service_liveness_not_model_readiness",
            "version": "0.2.0",
            "models": engine.registry.health(),
            "warnings": [
                "Model loading is lazy. No measured accuracy is claimed."
            ],
        }

    @api.post("/detect/image", response_model=DetectionResponse)
    async def image(payload: MediaRequest):
        return await single("image", payload)

    @api.post("/detect/video", response_model=DetectionResponse)
    async def video(payload: MediaRequest):
        return await single("video", payload)

    @api.post("/detect/audio", response_model=DetectionResponse)
    async def audio(payload: MediaRequest):
        return await single("audio", payload)

    @api.post("/detect/text", response_model=DetectionResponse)
    async def text(payload: TextRequest):
        return await single("text", payload)

    @api.post("/detect/multimodal", response_model=DetectionResponse)
    async def multimodal(payload: MultimodalRequest):
        if admission.locked():
            return JSONResponse(
                {"status": "unavailable", "reason": "capacity_exceeded"},
                status_code=503,
            )
        async with admission:
            return await asyncio.to_thread(engine.multimodal, payload)

    return api


def attach_api(app):
    app.mount("/api", create_api())
    return app
