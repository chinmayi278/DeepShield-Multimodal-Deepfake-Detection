import reflex as rx

import asyncio
import base64
import hashlib
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from app.components.deepshield.contracts import (
    DetectionResponse,
    MediaRequest,
    TextRequest,
)
from app.components.deepshield.service import DetectionService
from app.components.deepshield.language import LanguageService
from app.models import (
    Analysis,
    UploadedFile,
    ModalityResult,
    Modality,
    ProcessingStatus,
    Verdict,
)


EXTENSIONS = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".mp4": "video",
    ".webm": "video",
    ".mov": "video",
    ".wav": "audio",
    ".mp3": "audio",
    ".flac": "audio",
    ".m4a": "audio",
}
LIMITS = {
    "image": 10 * 1024 * 1024,
    "video": 32 * 1024 * 1024,
    "audio": 20 * 1024 * 1024,
}


def inspect_file(data: bytes, name: str) -> dict[str, str]:
    modality = EXTENSIONS.get(Path(name).suffix.lower(), "")
    if not modality:
        raise ValueError(
            "Unsupported extension. Accepted formats: JPG/JPEG/PNG/WebP, MP4/WebM/MOV, WAV/MP3/FLAC/M4A."
        )
    if not data or len(data) > LIMITS[modality]:
        raise ValueError(f"Empty file or size exceeds the {modality} limit.")
    mime = ""
    preview = ""
    width = height = 0
    if modality == "image":
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if (
                image.format not in {"JPEG", "PNG", "WEBP"}
                or image.width * image.height > 16000000
                or min(image.size) < 32
            ):
                raise ValueError(
                    "Use a JPG, PNG or WebP image between 32 pixels and 16 megapixels."
                )
            image.load()
            width, height = image.size
            mime = Image.MIME[image.format]
            image.thumbnail((640, 640))
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=75)
            preview = f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}"
    else:
        suffix = Path(name).suffix.lower()
        valid = {
            ".wav": data[:4] == b"RIFF" and data[8:12] == b"WAVE",
            ".flac": data[:4] == b"fLaC",
            ".mp3": data[:3] == b"ID3"
            or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224),
            ".mp4": data[4:8] == b"ftyp",
            ".mov": data[4:8] in {b"ftyp", b"moov", b"mdat"},
            ".m4a": data[4:8] == b"ftyp",
            ".webm": data[:4] == b"\x1aE\xdf\xa3",
        }
        if not valid.get(suffix, False):
            raise ValueError("The file content does not match its extension.")
        mime = {
            ".wav": "audio/wav",
            ".flac": "audio/flac",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
        }[suffix]
        if len(data) <= 2 * 1024 * 1024:
            preview = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    return {
        "id": uuid4().hex,
        "name": Path(name).name[:255],
        "modality": modality,
        "mime": mime,
        "size": str(len(data)),
        "display_size": f"{len(data) / 1048576:.2f} MB",
        "hash": hashlib.sha256(data).hexdigest(),
        "preview": preview,
        "width": str(width),
        "height": str(height),
    }


class IntakeState(rx.State):
    light: bool = False
    owner: str = rx.Cookie("", name="deepshield_review", same_site="strict")
    mode: str = "image"
    language: str = "auto"
    text_draft: str = ""
    detected: str = "Automatic identification runs on submission."
    explain: bool = True
    consent: bool = False
    files: list[dict[str, str]] = []
    _payloads: dict[str, bytes] = {}
    busy: bool = False
    uploading: bool = False
    progress: int = 0
    stage: str = ""
    error: str = ""

    @rx.event
    def initialize(self):
        if not self.owner:
            self.owner = uuid4().hex

    @rx.event
    def toggle_theme(self):
        self.light = not self.light

    @rx.event
    def choose_mode(self, mode: str):
        if (
            self.busy
            or self.uploading
            or mode not in {"image", "video", "audio", "text", "multimodal"}
        ):
            return
        self.mode = mode
        self.files = []
        self._payloads = {}
        self.text_draft = ""
        self.error = ""
        self.progress = 0

    @rx.event
    def choose_language(self, language: str):
        if not self.busy and language in {
            "auto",
            "en",
            "hi",
            "kn",
            "ta",
            "te",
            "ml",
            "mr",
            "bn",
        }:
            self.language = language

    @rx.event
    def toggle_explain(self):
        if not self.busy:
            self.explain = not self.explain

    @rx.event
    def toggle_consent(self):
        if not self.busy:
            self.consent = not self.consent

    @rx.event
    def upload_progress(self, progress: dict[str, Any]):
        self.progress = max(
            0, min(100, round(float(progress.get("progress", 0)) * 100))
        )
        self.uploading = self.progress < 100

    @rx.event
    async def upload(self, files: list[rx.UploadFile]):
        if self.busy:
            return
        self.uploading = True
        self.error = ""
        try:
            if len(files) > (3 if self.mode == "multimodal" else 1):
                raise ValueError(
                    "Select one file per modality; multimodal accepts up to three media files."
                )
            for file in files:
                data = await file.read(32 * 1024 * 1024 + 1)
                metadata = await asyncio.to_thread(
                    inspect_file, data, file.name or "unnamed"
                )
                if (
                    self.mode != "multimodal"
                    and metadata["modality"] != self.mode
                ):
                    raise ValueError(
                        "This file does not match the selected analysis mode."
                    )
                if any(item["hash"] == metadata["hash"] for item in self.files):
                    raise ValueError(
                        "Duplicate file detected. This evidence is already attached."
                    )
                if any(
                    item["modality"] == metadata["modality"]
                    for item in self.files
                ):
                    raise ValueError(
                        "One file per modality is supported. Remove the existing file to replace it."
                    )
                self.files.append(metadata)
                self._payloads[metadata["id"]] = data
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "Unable to read this file. Try a different file."
        finally:
            self.uploading = False
            self.progress = 100
            for file in files:
                await file.close()

    @rx.event
    def remove_file(self, file_id: str):
        if not self.busy and not self.uploading:
            self.files = [item for item in self.files if item["id"] != file_id]
            self._payloads.pop(file_id, None)

    @rx.event
    def clear_intake(self):
        if self.busy or self.uploading:
            return
        self.files = []
        self._payloads = {}
        self.text_draft = ""
        self.error = ""
        self.progress = 0
        self.consent = False
        self.stage = ""

    @rx.event
    def submit(self, form_data: dict[str, Any]):
        if self.busy or self.uploading:
            return
        self.text_draft = str(form_data.get("evidence_text", "")).strip()
        self.error = ""
        if not self.consent:
            self.error = "Please acknowledge processing and metadata retention before continuing."
        elif len(self.text_draft) > 20000:
            self.error = "Text must be no longer than 20,000 characters."
        elif not self.files and not self.text_draft:
            self.error = "Add a media file or paste text before starting."
        elif (
            self.mode == "multimodal"
            and len(self.files) + bool(self.text_draft) < 2
        ):
            self.error = "Multimodal analysis needs at least two inputs from different modalities."
        if self.error:
            return
        if not self.owner:
            self.owner = uuid4().hex
        self.busy = True
        self.stage = "01 / Validating evidence and identifying language"
        return IntakeState.process

    @rx.event(background=True)
    async def process(self):
        async with self:
            files = [dict(item) for item in self.files]
            payloads = dict(self._payloads)
            text = self.text_draft
            language = self.language
            explain = self.explain
            owner = str(self.owner)
            mode = self.mode
        try:
            service = await asyncio.to_thread(DetectionService)
            identification = await asyncio.to_thread(
                LanguageService().detect, text, language
            )
            async with self:
                self.detected = f"Language: {identification.language} · {identification.method}"
                self.stage = "02 / Running independent detection pipelines"
            results = []
            for item in files:
                async with self:
                    self.stage = f"02 / Analyzing {item['modality']} evidence"
                request = MediaRequest(
                    data_base64=base64.b64encode(payloads[item["id"]]).decode(),
                    language=language,
                    explain=explain,
                )
                results.append(
                    await asyncio.to_thread(
                        service.detect, item["modality"], request
                    )
                )
            if text:
                results.append(
                    await asyncio.to_thread(
                        service.detect,
                        "text",
                        TextRequest(text=text, language=language),
                    )
                )
            async with self:
                self.stage = "03 / Applying reliability gates"
            fusion = (
                await asyncio.to_thread(service.fusion.detect, results)
                if mode == "multimodal"
                else None
            )
            response = DetectionResponse(
                request_id=uuid4().hex, results=results, fusion=fusion
            )
            records = service.record_bundle(response, owner)
            analysis = records[0]
            summary = fusion or results[0]
            analysis.title = f"{mode.title()} analysis"
            analysis.language_requested = language
            analysis.language_detected = (
                identification.language if text else None
            )
            analysis.language_confidence = (
                identification.confidence if text else None
            )
            analysis.configuration = {
                "explain": explain,
                "mode": mode,
                "raw_media_retained": False,
            }
            analysis.consent_record = {
                "metadata_retention_acknowledged": True,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "raw_media_retained": False,
            }
            statuses = [r.status for r in results]
            analysis.status = (
                ProcessingStatus.UNAVAILABLE
                if all(s == "unavailable" for s in statuses)
                else ProcessingStatus.FAILED
                if all(s == "invalid_input" for s in statuses)
                else ProcessingStatus.DEGRADED
                if any(s != "ok" for s in statuses) or summary.status != "ok"
                else ProcessingStatus.COMPLETED
            )
            analysis.verdict = Verdict(summary.verdict)
            analysis.fake_probability = (
                summary.score if summary.provenance.calibrated else None
            )
            analysis.calibration_version = (
                summary.provenance.calibration_id or None
            )
            analysis.summary = (
                f"Preliminary {summary.verdict.title()} model classification; not a calibrated probability."
                if summary.verdict in {"real", "fake"}
                else "Insufficient available detector evidence for a Real/Fake classification; factuality has not been assessed."
            )
            analysis.fusion_details = {
                "status": summary.status,
                "reason": summary.reason,
                "score": summary.score,
                "semantics": summary.score_semantics,
            }
            now = datetime.now(timezone.utc)
            for item in files:
                uploaded = UploadedFile(
                    id=uuid4(),
                    analysis_id=analysis.id,
                    modality=Modality(item["modality"]),
                    original_filename=item["name"],
                    media_type_detected=item["mime"],
                    byte_size=int(item["size"]),
                    sha256=item["hash"],
                    hash_verified_at=now,
                    upload_completed_at=now,
                    validation_status="validated",
                    validation_details={
                        "header_checked": True,
                        "decode_status": next(
                            r.status
                            for r in results
                            if r.modality == item["modality"]
                        ),
                    },
                    storage_key=None,
                    purged_at=now,
                    retention_policy=analysis.retention_policy,
                    expires_at=analysis.expires_at,
                    width=int(item["width"]) or None,
                    height=int(item["height"]) or None,
                )
                records.append(uploaded)
                for record in records:
                    if (
                        isinstance(record, ModalityResult)
                        and record.modality == uploaded.modality
                    ):
                        record.uploaded_file_id = uploaded.id
            if text:
                records.append(
                    UploadedFile(
                        analysis_id=analysis.id,
                        modality=Modality.TEXT,
                        original_filename="Pasted text",
                        media_type_detected="text/plain; charset=utf-8",
                        byte_size=len(text.encode()),
                        sha256=hashlib.sha256(text.encode()).hexdigest(),
                        hash_verified_at=now,
                        upload_completed_at=now,
                        validation_status="validated",
                        purged_at=now,
                        retention_policy=analysis.retention_policy,
                        expires_at=analysis.expires_at,
                        media_metadata={
                            "characters": len(text),
                            "language": identification.language,
                        },
                    )
                )
            async with self:
                self.stage = "04 / Saving evidence metadata"
            async with rx.asession() as session:
                session.add(analysis)
                await session.flush()
                session.add_all(
                    [r for r in records if isinstance(r, UploadedFile)]
                )
                await session.flush()
                session.add_all(
                    [r for r in records if isinstance(r, ModalityResult)]
                )
                await session.flush()
                session.add_all(
                    [
                        r
                        for r in records
                        if not isinstance(
                            r, (Analysis, UploadedFile, ModalityResult)
                        )
                    ]
                )
                await session.commit()
            destination = f"/results/{analysis.id}"
            async with self:
                self._payloads = {}
                self.files = []
                self.text_draft = ""
                self.busy = False
                self.stage = "Complete"
            yield rx.redirect(destination)
        except Exception as e:
            logging.exception(f"Error: {e}")
            async with self:
                self.busy = False
                self.error = "Analysis could not be saved. Your evidence has not been published. Please retry."
                self.stage = ""
