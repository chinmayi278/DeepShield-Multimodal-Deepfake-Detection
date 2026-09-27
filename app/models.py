import reflex as rx

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    JSON,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


type JSONValue = (
    str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
)


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Modality(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    FUSION = "fusion"


class Verdict(StrEnum):
    REAL = "real"
    FAKE = "fake"
    UNCERTAIN = "uncertain"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ReportFormat(StrEnum):
    PDF = "pdf"
    JSON = "json"
    HTML = "html"


class ModelAvailability(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    RETIRED = "retired"


def enum_column(enum_class: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [item.value for item in members],
    )


def structured_json():
    return MutableDict.as_mutable(JSON().with_variant(JSONB(), "postgresql"))


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class AuditRetentionMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retention_policy: Mapped[str] = mapped_column(
        String(128), default="unassigned"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    legal_hold: Mapped[bool] = mapped_column(default=False)


class ProcessingMixin:
    status: Mapped[ProcessingStatus] = mapped_column(
        enum_column(ProcessingStatus, "processing_status"),
        default=ProcessingStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_context: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)


class AssessmentMixin:
    verdict: Mapped[Verdict | None] = mapped_column(
        enum_column(Verdict, "verdict"), nullable=True
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        enum_column(RiskLevel, "risk_level"), default=RiskLevel.UNKNOWN
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    fake_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_method: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    calibration_version: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    language_detected: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    language_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )


class Analysis(AuditRetentionMixin, ProcessingMixin, AssessmentMixin, Base):
    __tablename__ = "deepshield_analysis"
    __table_args__ = (
        UniqueConstraint(
            "owner_scope", "request_key", name="uq_analysis_owner_request"
        ),
        Index("ix_analysis_owner_history", "owner_scope", "created_at"),
        Index("ix_analysis_status_created", "status", "created_at"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint(
            "fake_probability BETWEEN 0 AND 1", name="probability_range"
        ),
        CheckConstraint("risk_score BETWEEN 0 AND 1", name="risk_range"),
        CheckConstraint(
            "language_confidence BETWEEN 0 AND 1",
            name="language_confidence_range",
        ),
        CheckConstraint("attempt_number >= 1", name="positive_attempt"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="processing_order",
        ),
    )

    owner_scope: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="Untitled analysis")
    language_requested: Mapped[str] = mapped_column(String(64), default="auto")
    pipeline_version: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    configuration: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    fusion_details: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    consent_record: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )

    uploaded_files: Mapped[list["UploadedFile"]] = relationship(
        back_populates="analysis", lazy="raise", passive_deletes="all"
    )
    modality_results: Mapped[list["ModalityResult"]] = relationship(
        back_populates="analysis", lazy="raise", passive_deletes="all"
    )
    reports: Mapped[list["ForensicReport"]] = relationship(
        back_populates="analysis", lazy="raise", passive_deletes="all"
    )


class UploadedFile(AuditRetentionMixin, Base):
    __tablename__ = "deepshield_uploaded_file"
    __table_args__ = (
        UniqueConstraint("analysis_id", "id", name="uq_file_analysis_id"),
        Index(
            "ix_file_duplicate_lookup",
            "deduplication_scope",
            "sha256",
            "byte_size",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0", name="nonnegative_size"
        ),
        CheckConstraint(
            "sha256 IS NULL OR length(sha256) = 64", name="sha256_length"
        ),
        CheckConstraint(
            "duplicate_of_id IS NULL OR duplicate_of_id <> id",
            name="not_self_duplicate",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="nonnegative_duration",
        ),
        CheckConstraint("width IS NULL OR width > 0", name="positive_width"),
        CheckConstraint("height IS NULL OR height > 0", name="positive_height"),
    )

    analysis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deepshield_analysis.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    modality: Mapped[Modality | None] = mapped_column(
        enum_column(Modality, "file_modality"), nullable=True
    )
    original_filename: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type_declared: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    media_type_detected: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    byte_size: Mapped[int | None] = mapped_column(nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deduplication_scope: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    duplicate_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deepshield_uploaded_file.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    duplicate_detected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    upload_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    validation_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )
    validation_details: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    media_metadata: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)

    analysis: Mapped[Analysis | None] = relationship(
        back_populates="uploaded_files", lazy="raise"
    )
    duplicate_of: Mapped["UploadedFile | None"] = relationship(
        remote_side="UploadedFile.id", lazy="raise"
    )
    modality_results: Mapped[list["ModalityResult"]] = relationship(
        back_populates="uploaded_file", lazy="raise", passive_deletes="all"
    )


class ModelVersion(AuditRetentionMixin, Base):
    __tablename__ = "deepshield_model_version"
    __table_args__ = (
        UniqueConstraint(
            "registry_name", "version", name="uq_model_registry_version"
        ),
        CheckConstraint(
            "checkpoint_sha256 IS NULL OR length(checkpoint_sha256) = 64",
            name="checkpoint_hash_length",
        ),
    )

    registry_name: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    modality: Mapped[Modality | None] = mapped_column(
        enum_column(Modality, "model_modality"), nullable=True
    )
    availability: Mapped[ModelAvailability] = mapped_column(
        enum_column(ModelAvailability, "model_availability"),
        default=ModelAvailability.UNAVAILABLE,
    )
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(256), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_revision: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    checkpoint_storage_key: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    checkpoint_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    license_identifier: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    adapter_version: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provenance: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    training_manifest: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    evaluation_metrics: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    supported_languages: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    runtime_requirements: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )

    modality_results: Mapped[list["ModalityResult"]] = relationship(
        back_populates="model_version", lazy="raise", passive_deletes="all"
    )


class ModalityResult(
    AuditRetentionMixin, ProcessingMixin, AssessmentMixin, Base
):
    __tablename__ = "deepshield_modality_result"
    __table_args__ = (
        Index("ix_result_analysis_modality", "analysis_id", "modality"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint(
            "fake_probability BETWEEN 0 AND 1", name="probability_range"
        ),
        CheckConstraint("risk_score BETWEEN 0 AND 1", name="risk_range"),
        CheckConstraint(
            "language_confidence BETWEEN 0 AND 1",
            name="language_confidence_range",
        ),
        CheckConstraint(
            "reliability BETWEEN 0 AND 1", name="reliability_range"
        ),
        CheckConstraint("fusion_weight BETWEEN 0 AND 1", name="weight_range"),
        CheckConstraint("attempt_number >= 1", name="positive_attempt"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="processing_order",
        ),
        CheckConstraint(
            "status NOT IN ('completed', 'degraded') OR (analysis_id IS NOT NULL AND modality IS NOT NULL)",
            name="finished_result_has_parent",
        ),
    )

    analysis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deepshield_analysis.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deepshield_uploaded_file.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    model_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deepshield_model_version.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    modality: Mapped[Modality | None] = mapped_column(
        enum_column(Modality, "result_modality"), nullable=True
    )
    stage_name: Mapped[str] = mapped_column(String(128), default="detection")
    reliability: Mapped[float | None] = mapped_column(Float, nullable=True)
    fusion_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    included_in_fusion: Mapped[bool] = mapped_column(default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_manifest: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    manipulation_labels: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    quality_metrics: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    indicators: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    factuality_assessment: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    inference_configuration: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    model_provenance_snapshot: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )

    analysis: Mapped[Analysis | None] = relationship(
        back_populates="modality_results", lazy="raise"
    )
    uploaded_file: Mapped[UploadedFile | None] = relationship(
        back_populates="modality_results", lazy="raise"
    )
    model_version: Mapped[ModelVersion | None] = relationship(
        back_populates="modality_results", lazy="raise"
    )
    evidence_records: Mapped[list["EvidenceRecord"]] = relationship(
        back_populates="modality_result", lazy="raise", passive_deletes="all"
    )


class EvidenceRecord(AuditRetentionMixin, Base):
    __tablename__ = "deepshield_evidence"
    __table_args__ = (
        Index(
            "ix_evidence_result_order", "modality_result_id", "sequence_number"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint("sequence_number >= 0", name="nonnegative_sequence"),
        CheckConstraint(
            "start_ms IS NULL OR start_ms >= 0", name="nonnegative_start"
        ),
        CheckConstraint(
            "end_ms IS NULL OR (end_ms >= 0 AND (start_ms IS NULL OR end_ms >= start_ms))",
            name="segment_order",
        ),
        CheckConstraint(
            "frame_index IS NULL OR frame_index >= 0", name="nonnegative_frame"
        ),
        CheckConstraint(
            "artifact_sha256 IS NULL OR length(artifact_sha256) = 64",
            name="artifact_hash_length",
        ),
    )

    modality_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deepshield_modality_result.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(64), default="observation")
    sequence_number: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_ms: Mapped[int | None] = mapped_column(nullable=True)
    end_ms: Mapped[int | None] = mapped_column(nullable=True)
    frame_index: Mapped[int | None] = mapped_column(nullable=True)
    region: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    measurements: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    explanation: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    artifact_storage_key: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    artifact_media_type: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    artifact_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    generator_version: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    modality_result: Mapped[ModalityResult | None] = relationship(
        back_populates="evidence_records", lazy="raise"
    )


class ForensicReport(AuditRetentionMixin, ProcessingMixin, Base):
    __tablename__ = "deepshield_forensic_report"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id",
            "format",
            "revision",
            name="uq_report_analysis_format_revision",
        ),
        CheckConstraint("revision >= 1", name="positive_revision"),
        CheckConstraint("attempt_number >= 1", name="positive_attempt"),
        CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0", name="nonnegative_size"
        ),
        CheckConstraint(
            "sha256 IS NULL OR length(sha256) = 64", name="sha256_length"
        ),
        CheckConstraint(
            "status <> 'completed' OR (analysis_id IS NOT NULL AND format IS NOT NULL AND storage_key IS NOT NULL AND sha256 IS NOT NULL AND generated_at IS NOT NULL)",
            name="completed_artifact_present",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="processing_order",
        ),
    )

    analysis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deepshield_analysis.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    format: Mapped[ReportFormat | None] = mapped_column(
        enum_column(ReportFormat, "report_format"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(64), default="en")
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generator_version: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    template_version: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    schema_version: Mapped[str] = mapped_column(String(64), default="1")
    analysis_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_manifest: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    redaction_manifest: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )
    integrity_metadata: Mapped[dict[str, JSONValue]] = mapped_column(
        structured_json(), default=dict
    )

    analysis: Mapped[Analysis | None] = relationship(
        back_populates="reports", lazy="raise"
    )
