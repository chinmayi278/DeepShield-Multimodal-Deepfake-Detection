import reflex as rx

import asyncio
import base64
import hashlib
import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import reflex_xy
import xy
from sqlalchemy import select, or_, func
from app.models import (
    Analysis,
    ModalityResult,
    UploadedFile,
    EvidenceRecord,
    ModelVersion,
    ForensicReport,
    ProcessingStatus,
    ReportFormat,
    JSONValue,
)
from app.states.intake_state import IntakeState
from app.components.review_support import (
    clean,
    pretty,
    number,
    retained_data,
    make_pdf,
    WARNING,
)


def active(model):
    return (
        model.deleted_at.is_(None),
        model.purged_at.is_(None),
        or_(
            model.expires_at.is_(None),
            model.expires_at > datetime.now(timezone.utc),
        ),
    )


class ReviewState(rx.State):
    loading: bool = False
    error: str = ""
    exporting: bool = False
    export_note: str = ""
    history_rows: list[dict[str, str]] = []
    filters: dict[str, str] = {
        "search": "",
        "from": "",
        "to": "",
        "modality": "",
        "verdict": "",
        "risk": "",
        "language": "",
        "model": "",
    }
    case: dict[str, str] = {
        "id": "",
        "title": "",
        "verdict": "Uncertain",
        "status": "",
        "risk": "Unknown",
        "confidence": "Unavailable",
        "probability": "Unavailable",
        "reason": "",
        "created": "",
        "expires": "",
        "language": "",
        "retention": "",
        "pipeline": "",
        "limitations": "",
        "updated": "",
    }
    modalities: list[dict[str, str]] = []
    files: list[dict[str, str]] = []
    evidence: list[dict[str, str]] = []
    selected: str = ""
    selected_info: dict[str, str] = {
        "modality": "",
        "factuality": "Not assessed",
        "provenance": "",
        "indicators": "",
        "quality": "",
        "limitations": "",
        "language": "",
    }
    media: str = ""
    original_text: str = ""
    media_note: str = "Source media was not retained. Metadata and redacted measurements only."
    chart_title: str = ""
    chart_description: str = (
        "No persisted measurements available for this view."
    )
    chart_kind: str = "none"
    chart_x: list[float] = []
    chart_y: list[float] = []
    chart_matrix: list[list[float]] = []
    chart_x_label: str = "Time (seconds)"
    chart_y_label: str = "Detector score (not calibrated confidence)"
    _bundle: dict[str, JSONValue] = {}
    _media: dict[str, str] = {}
    _artifacts: dict[str, str] = {}
    artifact: str = ""
    page_number: int = 0
    has_more: bool = False

    @reflex_xy.figure
    def evidence_chart(self) -> xy.Chart:
        if self.chart_kind == "matrix" and self.chart_matrix:
            return xy.chart(
                xy.heatmap(self.chart_matrix, colormap="viridis"),
                xy.colorbar(title=self.chart_y_label),
                xy.x_axis(label=self.chart_x_label),
                xy.y_axis(label="Row / band index"),
                xy.modebar(False),
                xy.interaction_config(navigation=False),
            )
        return xy.chart(
            xy.line(self.chart_x, self.chart_y, color="#06b6d4", width=2),
            xy.scatter(self.chart_x, self.chart_y, color="#06b6d4", size=4),
            xy.x_axis(label=self.chart_x_label),
            xy.y_axis(label=self.chart_y_label),
            xy.modebar(False),
            xy.interaction_config(navigation=False),
        )

    @rx.event
    async def load_history(self):
        self.loading = True
        self.error = ""
        self.history_rows = []
        yield
        try:
            intake = await self.get_state(IntakeState)
            owner = str(intake.owner)
            if not owner:
                self.has_more = False
                return
            conditions = [Analysis.owner_scope == owner, *active(Analysis)]
            f = self.filters
            if f["search"]:
                conditions.append(Analysis.title.ilike(f"%{f['search']}%"))
            if f["from"]:
                conditions.append(
                    Analysis.created_at
                    >= datetime.fromisoformat(f["from"]).replace(
                        tzinfo=timezone.utc
                    )
                )
            if f["to"]:
                conditions.append(
                    Analysis.created_at
                    < datetime.fromisoformat(f["to"]).replace(
                        tzinfo=timezone.utc
                    )
                    + timedelta(days=1)
                )
            for key, col in [
                ("verdict", Analysis.verdict),
                ("risk", Analysis.risk_level),
                ("language", Analysis.language_detected),
            ]:
                if f[key]:
                    conditions.append(col == f[key])
            if f["modality"] or f["model"]:
                related = select(ModalityResult.id).where(
                    ModalityResult.analysis_id == Analysis.id,
                    *active(ModalityResult),
                )
                if f["modality"]:
                    related = related.where(
                        ModalityResult.modality == f["modality"]
                    )
                if f["model"]:
                    related = related.where(
                        or_(
                            ModalityResult.model_provenance_snapshot["revision"]
                            .as_string()
                            .ilike(f"%{f['model']}%"),
                            ModalityResult.model_version_id.in_(
                                select(ModelVersion.id).where(
                                    ModelVersion.version.ilike(
                                        f"%{f['model']}%"
                                    ),
                                    *active(ModelVersion),
                                )
                            ),
                        )
                    )
                conditions.append(related.exists())
            async with rx.asession() as session:
                rows = (
                    await session.execute(
                        select(
                            Analysis.id,
                            Analysis.title,
                            Analysis.created_at,
                            Analysis.status,
                            Analysis.verdict,
                            Analysis.risk_level,
                            Analysis.language_detected,
                        )
                        .where(*conditions)
                        .order_by(Analysis.created_at.desc(), Analysis.id)
                        .offset(self.page_number * 30)
                        .limit(31)
                    )
                ).all()
            self.has_more = len(rows) > 30
            self.history_rows = [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "created": r.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                    "status": str(r.status),
                    "verdict": str(r.verdict or "uncertain").title(),
                    "risk": str(r.risk_level),
                    "language": r.language_detected or "und",
                }
                for r in rows[:30]
            ]
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "History could not be loaded. Check your date filters and retry."
        finally:
            self.loading = False

    @rx.event
    def filter_history(self, form: dict[str, Any]):
        self.filters = {
            key: str(form.get(key, "")).strip() for key in self.filters
        }
        self.page_number = 0
        return ReviewState.load_history

    @rx.event
    def turn_page(self, direction: int):
        self.page_number = max(0, self.page_number + direction)
        return ReviewState.load_history

    async def _fetch(
        self, session, identifier: str, owner: str, lock: bool = False
    ):
        if not owner or not isinstance(identifier, str):
            return None
        if (
            re.fullmatch(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                identifier,
            )
            is None
        ):
            return None
        analysis_uuid = UUID(identifier)
        query = (
            select(Analysis)
            .where(
                Analysis.id == analysis_uuid,
                Analysis.owner_scope == owner,
                *active(Analysis),
            )
            .limit(1)
        )
        if lock:
            query = query.with_for_update()
        analysis = (await session.scalars(query)).first()
        if analysis is None:
            return None
        if (
            lock
            and analysis.expires_at
            and analysis.expires_at <= datetime.now(timezone.utc)
        ):
            return None
        results = (
            await session.scalars(
                select(ModalityResult)
                .where(
                    ModalityResult.analysis_id == analysis.id,
                    *active(ModalityResult),
                )
                .order_by(ModalityResult.created_at, ModalityResult.id)
                .limit(50)
            )
        ).all()
        # Purged source bytes do not erase retained file metadata.
        files = (
            await session.scalars(
                select(UploadedFile)
                .where(
                    UploadedFile.analysis_id == analysis.id,
                    UploadedFile.deleted_at.is_(None),
                    or_(
                        UploadedFile.expires_at.is_(None),
                        UploadedFile.expires_at > datetime.now(timezone.utc),
                    ),
                )
                .order_by(UploadedFile.created_at)
                .limit(50)
            )
        ).all()
        evidence = (
            await session.scalars(
                select(EvidenceRecord)
                .where(
                    EvidenceRecord.modality_result_id.in_(
                        [r.id for r in results]
                    ),
                    *active(EvidenceRecord),
                )
                .order_by(EvidenceRecord.sequence_number, EvidenceRecord.id)
                .limit(2000)
            )
        ).all()
        models = (
            await session.scalars(
                select(ModelVersion)
                .where(
                    ModelVersion.id.in_(
                        [
                            r.model_version_id
                            for r in results
                            if r.model_version_id
                        ]
                    ),
                    *active(ModelVersion),
                )
                .limit(50)
            )
        ).all()
        model_map = {m.id: m for m in models}
        result_data = []
        for r in results:
            provenance = clean(r.model_provenance_snapshot or {})
            model = model_map.get(r.model_version_id)
            if model:
                provenance = {
                    **provenance,
                    "model_id": model.registry_name,
                    "revision": model.source_revision,
                    "version": model.version,
                    "artifact_sha256": model.checkpoint_sha256,
                    "license": model.license_identifier,
                    "preprocessing": model.adapter_version,
                }
            result_data.append(
                {
                    "id": str(r.id),
                    "modality": str(r.modality),
                    "status": str(r.status),
                    "score": r.indicators.get("score"),
                    "semantics": r.indicators.get("semantics", "not_assessed"),
                    "reliability": r.reliability
                    if r.reliability is not None
                    else r.quality_metrics.get("reliability"),
                    "weight": r.fusion_weight,
                    "included_in_fusion": r.included_in_fusion,
                    "exclusion_reason": r.exclusion_reason,
                    "reason": r.failure_code,
                    "language": r.language_detected or "und",
                    "provenance": provenance,
                    "limitations": clean(r.limitations),
                    "quality": clean(r.quality_metrics),
                    "indicators": clean(r.indicators),
                    "labels": clean(r.manipulation_labels),
                    "factuality": clean(r.factuality_assessment),
                }
            )
        summary = next(
            (r for r in results if str(r.modality) == "fusion"),
            results[0] if len(results) == 1 else None,
        )
        calibrated = bool(
            analysis.calibration_version
            or (
                summary
                and summary.model_provenance_snapshot.get("calibrated")
                and summary.model_provenance_snapshot.get("calibration_id")
            )
        )
        case = {
            "id": str(analysis.id),
            "title": analysis.title,
            "verdict": str(analysis.verdict or "uncertain").title(),
            "status": str(analysis.status),
            "risk": str(analysis.risk_level).title(),
            "confidence": number(analysis.confidence)
            if calibrated
            else "Unavailable — no calibration",
            "probability": number(analysis.fake_probability)
            if calibrated
            else "Unavailable — no calibration",
            "reason": str(
                analysis.fusion_details.get("reason")
                or analysis.summary
                or "Insufficient evidence for a definitive conclusion."
            ),
            "created": analysis.created_at.isoformat(),
            "updated": analysis.updated_at.isoformat(),
            "expires": analysis.expires_at.isoformat()
            if analysis.expires_at
            else "No expiry recorded",
            "language": analysis.language_detected or "und",
            "retention": analysis.retention_policy,
            "pipeline": analysis.pipeline_version or "Not recorded",
            "limitations": pretty(clean(analysis.limitations)),
        }
        bundle = {
            "case": case,
            "warning": WARNING,
            "interpretation": "Explanations describe model behavior, not proof of manipulation. AI-origin detection is separate from factuality.",
            "results": result_data,
            "files": [
                {
                    "id": str(f.id),
                    "name": f.original_filename or "Unnamed",
                    "modality": str(f.modality),
                    "mime": f.media_type_detected
                    or f.media_type_declared
                    or "Unknown",
                    "bytes": str(f.byte_size)
                    if f.byte_size is not None
                    else "Unknown",
                    "sha256": f.sha256 or "Not recorded",
                    "verified": f.hash_verified_at.isoformat()
                    if f.hash_verified_at
                    else "Not recorded",
                    "dimensions": f"{f.width or '?'} × {f.height or '?'}",
                    "duration_ms": str(f.duration_ms)
                    if f.duration_ms is not None
                    else "Not recorded",
                    "retention": "Not retained"
                    if f.purged_at or not f.storage_key
                    else "Retained; authorized preview only",
                    "policy": f.retention_policy,
                }
                for f in files
            ],
            "evidence": [
                {
                    "id": str(e.id),
                    "result_id": str(e.modality_result_id),
                    "kind": e.kind,
                    "label": e.label or "",
                    "description": e.description or "",
                    "start_ms": e.start_ms,
                    "end_ms": e.end_ms,
                    "frame_index": e.frame_index,
                    "region": clean(e.region),
                    "measurements": clean(e.measurements),
                    "explanation": clean(e.explanation),
                    "artifact_sha256": e.artifact_sha256,
                    "generator": e.generator_version,
                }
                for e in evidence
            ],
            "limits": "Review/export safety caps: 50 results, 50 files, 2000 evidence records. Raw media, text, storage locations and owner identifiers excluded from exports.",
        }
        return analysis, bundle, files, evidence

    @rx.event
    async def load_case(self):
        self.loading = True
        self.error = ""
        self.export_note = ""
        self._bundle = {}
        self._media = {}
        self._artifacts = {}
        self.media = self.original_text = self.artifact = ""
        self.modalities = self.files = self.evidence = []
        self.chart_kind = "none"
        yield
        try:
            intake = await self.get_state(IntakeState)
            async with rx.asession() as session:
                fetched = await self._fetch(
                    session,
                    str(self.router.page.params.get("analysis_id", "")),
                    str(intake.owner),
                )
                if fetched is None:
                    self.error = "This analysis is unavailable, expired, deleted, or belongs to another browser scope."
                    self._bundle = {}
                    return
                analysis, bundle, files, evidence = fetched
            self._bundle = bundle
            self.case = bundle["case"]
            self.files = bundle["files"]
            self.modalities = [
                {
                    "id": r["id"],
                    "modality": r["modality"],
                    "status": r["status"],
                    "score": number(r["score"])
                    if r["status"] in {"completed", "degraded"}
                    else "Unavailable",
                    "semantics": r["semantics"],
                    "reliability": number(r["reliability"]),
                    "weight": number(r["weight"]),
                    "labels": pretty(r["labels"]) if r["labels"] else "",
                    "reason": r["reason"] or r["exclusion_reason"] or "",
                    "language": r["language"],
                }
                for r in bundle["results"]
            ]
            for f in files:
                if not f.purged_at and f.storage_key:
                    self._media[str(f.modality)] = await asyncio.to_thread(
                        retained_data,
                        f.storage_key,
                        f.media_type_detected or "",
                        f.sha256 or "",
                    )
            for e in evidence:
                if e.artifact_storage_key:
                    self._artifacts[str(e.id)] = await asyncio.to_thread(
                        retained_data,
                        e.artifact_storage_key,
                        e.artifact_media_type or "",
                        e.artifact_sha256 or "",
                    )
            if self.modalities:
                self._select(self.modalities[0]["id"])
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "This analysis is unavailable, expired, deleted, or belongs to another browser scope."
            self._bundle = {}
        finally:
            self.loading = False

    def _select(self, result_id: str):
        self.selected = result_id
        result = next(
            (
                r
                for r in self._bundle.get("results", [])
                if r["id"] == result_id
            ),
            None,
        )
        if not result:
            return
        self.selected_info = {
            key: pretty(result.get(key))
            for key in [
                "modality",
                "provenance",
                "indicators",
                "quality",
                "limitations",
                "language",
            ]
        }
        factuality = result.get("factuality") or {}
        self.selected_info["factuality"] = (
            pretty(factuality)
            if factuality.get("status") not in {None, "not_assessed"}
            else "Not assessed"
        )
        self.media = self._media.get(result["modality"], "")
        self.original_text = ""
        if result["modality"] == "text" and self.media.startswith(
            "data:text/plain;base64,"
        ):
            self.original_text = base64.b64decode(
                self.media.split(",", 1)[1]
            ).decode("utf-8", errors="replace")
            self.media = ""
        self.artifact = ""
        entries = [
            e
            for e in self._bundle.get("evidence", [])
            if e["result_id"] == result_id
        ]
        self.evidence = [
            {
                "id": e["id"],
                "kind": e["kind"],
                "label": e["label"],
                "description": e["description"],
                "interval": f"{e['start_ms'] if e['start_ms'] is not None else '—'} → {e['end_ms'] if e['end_ms'] is not None else '—'} ms",
                "score": number(e["explanation"].get("score")),
                "details": pretty(
                    {
                        "region": e["region"],
                        "measurements": e["measurements"],
                        "explanation": e["explanation"],
                    }
                ),
            }
            for e in entries
        ]
        self.chart_x = []
        self.chart_y = []
        self.chart_matrix = []
        self.chart_kind = "none"
        self.chart_x_label = "Time (seconds)"
        self.chart_y_label = "Detector score (not calibrated confidence)"
        for e in entries:
            score = e["explanation"].get("score")
            if isinstance(score, (int, float)) and math.isfinite(score):
                x = e["start_ms"]
                if x is None:
                    x = e["measurements"].get("start_char")
                    self.chart_x_label = "Original character offset"
                elif self.chart_x_label == "Time (seconds)":
                    x /= 1000
                if isinstance(x, (int, float)):
                    self.chart_x.append(float(x))
                    self.chart_y.append(float(score))
        if self.chart_x:
            ordered = sorted(zip(self.chart_x, self.chart_y))
            self.chart_x, self.chart_y = map(list, zip(*ordered))
            self.chart_kind = "line"
            self.chart_title = (
                f"{result['modality'].title()} · persisted score timeline"
            )
            self.chart_description = f"{len(self.chart_y)} scored observations; range {min(self.chart_y):.3f}–{max(self.chart_y):.3f}. Missing scores are omitted, not zero. Lines connect samples, not continuous detection."
        else:
            self.chart_description = "No scored timeline retained. Select a measurement below to inspect available waveform, matrix or artifact evidence."
            for e in entries:
                if e["kind"] in {"waveform", "log_mel", "occlusion"}:
                    self._show_evidence(e["id"])
                    break

    @rx.event
    def select_modality(self, result_id: str):
        self._select(result_id)

    def _show_evidence(self, identifier: str):
        e = next(
            (
                e
                for e in self._bundle.get("evidence", [])
                if e["id"] == identifier and e["result_id"] == self.selected
            ),
            None,
        )
        if not e:
            return
        self.artifact = self._artifacts.get(identifier, "")
        d = e["measurements"]
        self.chart_kind = "none"
        self.chart_title = e["kind"].replace("_", " ").title()
        self.chart_description = "No plottable measurements for this record. See the exact evidence below."
        values = d.get("values")
        matrix = d.get("db")
        if e["kind"] == "occlusion":
            grid, deltas = d.get("grid", []), d.get("score_deltas", [])
            if (
                len(grid) == 2
                and all(isinstance(n, int) and 0 < n <= 128 for n in grid)
                and len(deltas) == grid[0] * grid[1]
            ):
                matrix = [
                    deltas[i : i + grid[1]]
                    for i in range(0, len(deltas), grid[1])
                ]
        if (
            isinstance(matrix, list)
            and matrix
            and all(
                isinstance(row, list)
                and len(row) == len(matrix[0])
                and all(
                    isinstance(v, (int, float)) and math.isfinite(v)
                    for v in row
                )
                for row in matrix
            )
        ):
            self.chart_matrix = matrix
            self.chart_kind = "matrix"
            self.chart_x_label = (
                "Time bin index"
                if e["kind"] == "log_mel"
                else "Image column index"
            )
            self.chart_y_label = (
                "dB relative to peak"
                if e["kind"] == "log_mel"
                else "Score delta after masking"
            )
            flat = [v for row in matrix for v in row]
            self.chart_description = f"{len(matrix)} × {len(matrix[0])} persisted cells; range {min(flat):.3f}–{max(flat):.3f}. Coordinates and sampling parameters are in the evidence record. Describes signal/model behavior, not proof."
        elif (
            e["kind"] == "waveform"
            and isinstance(values, list)
            and values
            and all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in values
            )
            and d.get("sample_rate", 0) > 0
        ):
            self.chart_y = values
            self.chart_x = [
                i * d.get("stride_samples", 1) / d["sample_rate"]
                for i in range(len(values))
            ]
            self.chart_kind = "line"
            self.chart_x_label = "Time (seconds)"
            self.chart_y_label = "Sample amplitude"
            self.chart_description = f"{len(values)} retained waveform samples. Strided visualization, not a full reconstruction or attribution map."

    @rx.event
    def show_evidence(self, identifier: str):
        self._show_evidence(identifier)

    @rx.event
    async def download_report(self, format_name: str):
        if self.exporting or format_name not in {"pdf", "json"}:
            return
        self.exporting = True
        self.export_note = ""
        yield
        try:
            intake = await self.get_state(IntakeState)
            owner = str(intake.owner)
            identifier = str(self.router.page.params.get("analysis_id", ""))
            async with rx.asession() as session:
                fetched = await self._fetch(
                    session, identifier, owner, lock=True
                )
                if fetched is None:
                    self.export_note = "Export unavailable. The analysis may have expired or could not be rendered. Please retry."
                    return
                analysis, bundle, _, _ = fetched
                now = datetime.now(timezone.utc)
                bundle["generated_at"] = now.isoformat()
                canonical = json.dumps(
                    bundle, ensure_ascii=False, sort_keys=True, allow_nan=False
                ).encode()
                payload = (
                    await asyncio.to_thread(make_pdf, bundle)
                    if format_name == "pdf"
                    else canonical
                )
                digest = hashlib.sha256(payload).hexdigest()
                filename = f"DeepShield-{analysis.id}.{format_name}"
                revision = (
                    await session.scalar(
                        select(func.max(ForensicReport.revision)).where(
                            ForensicReport.analysis_id == analysis.id,
                            ForensicReport.format == ReportFormat(format_name),
                        )
                    )
                ) or 0
                report = ForensicReport(
                    id=uuid4(),
                    analysis_id=analysis.id,
                    format=ReportFormat(format_name),
                    revision=revision + 1,
                    status=ProcessingStatus.COMPLETED,
                    storage_key="private-database-payload",
                    filename=filename,
                    media_type="application/pdf"
                    if format_name == "pdf"
                    else "application/json",
                    byte_size=len(payload),
                    sha256=digest,
                    generated_at=now,
                    generated_by=owner,
                    started_at=now,
                    finished_at=now,
                    generator_version="review-1",
                    template_version="forensic-1",
                    analysis_updated_at=analysis.updated_at,
                    retention_policy=analysis.retention_policy,
                    expires_at=analysis.expires_at,
                    payload=payload,
                    content_manifest={
                        "sections": list(bundle.keys()),
                        "evidence_count": len(bundle["evidence"]),
                        "snapshot_sha256": hashlib.sha256(
                            canonical
                        ).hexdigest(),
                    },
                    redaction_manifest={
                        "raw_media": "excluded",
                        "original_text": "excluded",
                        "storage_locations": "excluded",
                        "owner_scope": "excluded",
                    },
                    integrity_metadata={
                        "algorithm": "SHA-256",
                        "artifact_sha256": digest,
                        "meaning": "Byte integrity only; not authenticity or proof of manipulation",
                    },
                )
                # Recheck time-bound authorization after rendering and before delivery.
                if analysis.expires_at and analysis.expires_at <= datetime.now(
                    timezone.utc
                ):
                    self.export_note = "Export unavailable. The analysis may have expired or could not be rendered. Please retry."
                    return
                session.add(report)
                await session.commit()
            self.export_note = f"Generated {now.isoformat()} · {len(payload):,} bytes · SHA-256 {digest}"
            yield rx.download(data=payload, filename=filename)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.export_note = "Export unavailable. The analysis may have expired or could not be rendered. Please retry."
        finally:
            self.exporting = False
