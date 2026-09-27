import reflex as rx

import base64
import hashlib
import io
import json
import logging
import math
from pathlib import Path
from xml.sax.saxutils import escape
from app.models import JSONValue

WARNING = "AI detection is probabilistic and may produce false positives or false negatives."


def clean(value: JSONValue) -> JSONValue:
    if isinstance(value, dict):
        return {
            k: clean(v)
            for k, v in value.items()
            if not any(
                token in k.lower()
                for token in (
                    "storage",
                    "path",
                    "secret",
                    "token",
                    "credential",
                    "owner",
                    "base64",
                    "uri",
                    "url",
                )
            )
            and k
            not in {"text", "original_text", "excerpt", "spatial_evidence"}
        }
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def pretty(value: JSONValue) -> str:
    if value is None or value == {} or value == []:
        return "Not recorded"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def number(value: JSONValue) -> str:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    ):
        return f"{value:.3f}"
    return "Unavailable / not recorded"


def retained_data(key: str, mime: str, digest: str) -> str:
    try:
        allowed = {
            "image/jpeg",
            "image/png",
            "image/webp",
            "audio/wav",
            "audio/mpeg",
            "audio/flac",
            "audio/mp4",
            "video/mp4",
            "video/webm",
            "video/quicktime",
            "text/plain",
        }
        mime = mime.split(";", 1)[0].strip()
        if mime not in allowed:
            return ""
        root = rx.get_upload_dir().resolve()
        path = (root / key).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or path.stat().st_size > 32 * 1024 * 1024
        ):
            return ""
        payload = path.read_bytes()
        if digest and hashlib.sha256(payload).hexdigest() != digest:
            return ""
        return f"data:{mime};base64,{base64.b64encode(payload).decode()}"
    except Exception as e:
        logging.exception(f"Error: {e}")
        return ""


def pdf_value(value: JSONValue) -> str:
    if isinstance(value, dict):
        return "\n".join(f"{k}: {pdf_value(v)}" for k, v in value.items())
    if isinstance(value, list) and len(value) > 80:
        return f"{len(value)} measurements retained; complete numeric values available in JSON export."
    if isinstance(value, list) and value and isinstance(value[0], list):
        return f"{len(value)} × {len(value[0])} measurement matrix; complete cells available in JSON export."
    return pretty(value)


def make_pdf(bundle: dict[str, JSONValue]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        KeepTogether,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    buffer = io.BytesIO()
    font = "Helvetica"
    candidate = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if candidate.is_file():
        pdfmetrics.registerFont(TTFont("ReviewUnicode", candidate))
        font = "ReviewUnicode"
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "EvidenceBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#142334"),
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    heading = ParagraphStyle(
        "EvidenceHeading",
        parent=body,
        fontSize=15,
        leading=20,
        spaceBefore=18,
        spaceAfter=9,
        textColor=colors.HexColor("#087c94"),
    )
    story = [
        Paragraph("DEEPSHIELD / FORENSIC REVIEW", heading),
        Paragraph(escape(WARNING), body),
        Spacer(1, 10),
        Paragraph(
            "Explanations describe model behavior, not proof of manipulation. AI-origin detection is not factuality assessment, authorship attribution or identity verification.",
            body,
        ),
    ]
    for title, data in [
        ("Case & retention", bundle["case"]),
        ("Generation timestamp", bundle["generated_at"]),
        ("File integrity", bundle["files"]),
        ("Modality assessments & model provenance", bundle["results"]),
        (
            "Persisted evidence / regions / timestamps / segments",
            bundle["evidence"],
        ),
        ("Scope & redactions", bundle["limits"]),
    ]:
        story.append(Paragraph(escape(title), heading))
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            text = pdf_value(entry)
            for line in text.splitlines():
                story.append(Paragraph(escape(line) or " ", body))
            story.append(Spacer(1, 9))
    story.append(
        Paragraph(
            "Integrity notice: SHA-256 establishes byte consistency, not source authenticity. Raw sources, original text and private storage locations are excluded. Large numeric arrays are summarized here and included in the JSON export. Factuality remains Not assessed unless a dedicated result is explicitly recorded.",
            body,
        )
    )

    def page_mark(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#536376"))
        canvas.drawString(
            42, 25, "DEEPSHIELD · Research signals / human-led decisions"
        )
        canvas.drawRightString(doc.pagesize[0] - 42, 25, f"{doc.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        buffer,
        title="DeepShield forensic review",
        author="DeepShield",
        leftMargin=42,
        rightMargin=42,
        topMargin=42,
        bottomMargin=45,
    )
    document.build(story, onFirstPage=page_mark, onLaterPages=page_mark)
    return buffer.getvalue()
