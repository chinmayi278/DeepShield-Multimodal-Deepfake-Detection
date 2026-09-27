# DeepShield persistent model contract

This phase defines only SQLAlchemy declarative mappings. All six tables share `Base.metadata` in `app.models`. They work with SQLAlchemy sessions, including Reflex's session helpers; they do not inherit from the deprecated `rx.Model`. Importing the module does not open a session, query tables, create a schema, or seed records.

## Relationships

- `Analysis` owns uploaded-file metadata, modality results, and report revisions.
- `UploadedFile` optionally references an earlier duplicate. The hash is indexed, not globally unique: multiple submissions of identical bytes remain independently auditable.
- `ModalityResult` references an analysis, an optional uploaded file, and an optional model version. Multiple stages, retries, models, and fusion results may coexist. Text-only and fusion results do not require an uploaded file.
- `EvidenceRecord` belongs to a modality result, through which its analysis and source file are retrieved.
- `ModelVersion` is a registry entry with a unique name/version pair, checkpoint hash, license, source revision, training/evaluation manifests, and runtime requirements.
- `ForensicReport` is unique by analysis, format, and revision. Its manifest can identify the exact result and evidence IDs used to build it.

Foreign keys use `RESTRICT` for forensic provenance. A duplicate pointer uses `SET NULL` so purging the original file record does not block independent duplicate records. Relationships use `lazy="raise"`: future retrieval code must explicitly choose eager loading rather than accidentally issue queries during serialization. No delete cascade is configured.

## Values and lifecycle

- UUIDs identify records. New columns are nullable or have a default.
- Nullable parent references support staged metadata and incomplete imports. Future ingestion must bind records before publication and validate that a result's file belongs to the same analysis. Database checks additionally require completed/degraded results to have an analysis and modality, and completed reports to have a parent and artifact metadata.
- Unknown verdicts, scores, languages, sizes, and hashes are NULL, not misleading zeroes. Confidence, fake probability, risk, reliability, and fusion weight use the interval `[0, 1]`. Risk levels are separate categorical fields. NULL verdict means not assessed; `uncertain` means an assessment abstained.
- Language fields store BCP-47-style tags; requested language may be `auto`. Tag validation belongs to a future input/service boundary.
- Temporal evidence positions use milliseconds and zero-based frame indexes. Region JSON should declare its coordinate space, source dimensions, and geometry. Structured factuality assessment is separate from synthetic-text indicators.
- Status values explicitly distinguish degraded, unavailable, failed, cancelled, and successful processing. Attempt counters and failure timestamps/details support diagnosis without pretending unavailable models produced a result.
- Report revision and model version are intended as append-only identities once published. Future writers must enforce publication immutability; these mappings do not introduce triggers or authorization policy.

## JSON and auditing

JSON columns use PostgreSQL JSONB with a portable JSON fallback, and fresh dictionary defaults. Values must be ordinary JSON-compatible primitives, lists, and objects; encode UUIDs/datetimes as strings and reject non-finite floats in future adapters. Top-level dictionary changes are tracked. For nested edits, replace the top-level dictionary rather than relying on recursive mutation tracking.

`created_at` and `updated_at` are timezone-aware. Database defaults initialize both; SQLAlchemy updates `updated_at` on ORM/Core updates. Raw SQL writers must explicitly maintain `updated_at`. Actor references are opaque application identifiers, not credentials. These timestamps are audit metadata, not a tamper-proof event log. Provenance snapshots and report manifests preserve reproducibility when registry metadata changes.

## Privacy and retention

Every record carries retention policy, expiration, soft-deletion actor/reason/time, purge time, and legal-hold fields. `unassigned` policy means a retention decision has not yet been made; NULL expiration must not be interpreted as consent to indefinite storage. Future writers must apply a concrete policy before accepting sensitive content.

Retention fields are metadata only: no scheduler, file deletion, automatic expiry, authorization, or legal-hold enforcement is implemented here. Purge dependents in foreign-key order and honor legal holds. Soft deletion does not automatically filter queries. Future history/report retrieval must filter deleted/expired records and apply ownership checks.

Storage keys are private relative object identifiers, not public URLs, absolute machine paths, signed links, or credentials. Do not store raw media bytes or submitted text in metadata JSON. Original filenames, transcripts, excerpts, model source locations, failure detail, and report manifests may themselves be sensitive and need minimization/redaction. Hash-based deduplication must be restricted to the recorded privacy scope; never reveal cross-owner matches. A duplicate pointer records provenance, not a shared-artifact deletion policy.

No migration files or schema initialization are included. No existing page behavior is changed.
