import reflex as rx
import reflex_xy
from app.components.forensics_ui import shell, warning, BUTTON
from app.states.review_state import ReviewState

RULE = "border border-slate-500/25 p-5 sm:p-6"
LINK = "text-sm text-cyan-500 hover:underline focus-visible:outline-2 focus-visible:outline-cyan-400"


def metadata(label: str, value: rx.Var[str]) -> rx.Component:
    return rx.el.div(
        rx.el.dt(
            label, class_name="text-[10px] uppercase tracking-widest opacity-55"
        ),
        rx.el.dd(value, class_name="mt-2 break-words text-sm leading-6"),
        class_name="border-b border-slate-500/20 py-4",
    )


def page_header(title: str, subtitle: str) -> rx.Component:
    return rx.el.div(
        rx.el.p(
            "DEEPSHIELD / EVIDENCE REVIEW",
            class_name="text-[10px] tracking-[0.2em] text-cyan-500",
        ),
        rx.el.h1(
            title,
            class_name="mt-3 font-['Roboto_Condensed'] text-4xl font-semibold",
        ),
        rx.el.p(subtitle, class_name="mt-3 text-sm leading-6 opacity-65"),
        class_name="py-10",
    )


def filter_input(name: str, label: str, kind: str = "text") -> rx.Component:
    return rx.el.label(
        rx.el.span(label, class_name="text-xs opacity-65"),
        rx.el.input(
            name=name,
            type=kind,
            default_value=ReviewState.filters[name],
            key=ReviewState.filters[name],
            class_name="mt-2 w-full rounded-sm border border-slate-500/30 bg-transparent p-2.5 text-sm focus:outline-2 focus:outline-cyan-400",
        ),
        class_name="min-w-0",
    )


def filter_select(name: str, label: str, options: list[str]) -> rx.Component:
    return rx.el.label(
        rx.el.span(label, class_name="text-xs opacity-65"),
        rx.el.div(
            rx.el.select(
                rx.el.option("All", value=""),
                rx.foreach(
                    options, lambda item: rx.el.option(item, value=item)
                ),
                name=name,
                default_value=ReviewState.filters[name],
                key=ReviewState.filters[name],
                class_name="w-full appearance-none rounded-sm border border-slate-500/30 bg-transparent p-2.5 pr-8 text-sm [&_option]:bg-slate-100 [&_option]:text-slate-900",
            ),
            rx.icon(
                "chevron-down",
                class_name="pointer-events-none absolute right-2 top-3 h-4 w-4",
            ),
            class_name="relative mt-2",
        ),
    )


def history_actions(row: dict[str, str]) -> rx.Component:
    return rx.el.div(
        rx.el.a("Results", href=f"/results/{row['id']}", class_name=LINK),
        rx.el.a("Report", href=f"/report/{row['id']}", class_name=LINK),
        class_name="flex gap-4",
    )


def history_row(row: dict[str, str]) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            rx.el.p(row["title"], class_name="font-medium"),
            rx.el.p(
                row["id"], class_name="mt-1 font-mono text-[10px] opacity-50"
            ),
            class_name="p-4",
        ),
        rx.el.td(row["created"], class_name="p-4 text-xs"),
        rx.el.td(
            row["verdict"],
            rx.el.p(row["status"], class_name="mt-1 text-xs opacity-55"),
            class_name="p-4",
        ),
        rx.el.td(row["risk"], class_name="p-4 text-amber-500"),
        rx.el.td(row["language"], class_name="p-4"),
        rx.el.td(history_actions(row), class_name="p-4"),
        class_name="border-t border-slate-500/20 even:bg-slate-500/5 hover:bg-cyan-500/5",
        key=row["id"],
    )


def history_mobile(row: dict[str, str]) -> rx.Component:
    return rx.el.article(
        rx.el.h2(row["title"], class_name="font-medium"),
        rx.el.p(row["created"], class_name="my-2 text-xs opacity-60"),
        rx.el.p(
            f"{row['verdict']} · Risk {row['risk']} · {row['status']} · {row['language']}",
            class_name="mb-4 text-sm",
        ),
        history_actions(row),
        class_name=RULE,
        key=row["id"],
    )


def history_page() -> rx.Component:
    return shell(
        rx.el.main(
            page_header(
                "Analysis history",
                "Only this browser scope’s retained analyses. Expired and deleted cases are excluded; no demo records.",
            ),
            rx.el.form(
                rx.el.div(
                    filter_input("search", "Search case title"),
                    filter_input("from", "From date (UTC)", "date"),
                    filter_input("to", "Through date (UTC)", "date"),
                    filter_select(
                        "modality",
                        "Modality",
                        ["image", "video", "audio", "text", "fusion"],
                    ),
                    filter_select(
                        "verdict", "Verdict", ["real", "fake", "uncertain"]
                    ),
                    filter_select(
                        "risk", "Risk", ["low", "medium", "high", "unknown"]
                    ),
                    filter_input("language", "Language code, e.g. en"),
                    filter_input("model", "Model version / revision"),
                    class_name="grid gap-4 sm:grid-cols-2 lg:grid-cols-4",
                ),
                rx.el.button(
                    rx.icon("filter", class_name="h-4 w-4"),
                    "Apply filters",
                    type="submit",
                    disabled=ReviewState.loading,
                    class_name=BUTTON,
                ),
                on_submit=ReviewState.filter_history,
                class_name="space-y-5 border-y border-slate-500/25 py-6",
            ),
            rx.cond(
                ReviewState.loading,
                loading_panel(),
                rx.cond(
                    ReviewState.error != "",
                    error_panel(),
                    rx.cond(
                        ReviewState.history_rows.length() == 0,
                        rx.el.div(
                            rx.icon(
                                "folder-search",
                                class_name="mb-4 h-7 w-7 text-cyan-500",
                            ),
                            rx.el.h2(
                                "No matching analyses",
                                class_name="font-['Roboto_Condensed'] text-2xl",
                            ),
                            rx.el.p(
                                "Adjust filters or start an analysis. History is limited to the current browser scope and retention window.",
                                class_name="my-4 text-sm opacity-65",
                            ),
                            rx.el.a(
                                "Analyze evidence →",
                                href="/analyze",
                                class_name=LINK,
                            ),
                            class_name="my-8 border border-dashed border-slate-500/30 p-8",
                        ),
                        rx.el.div(
                            rx.el.div(
                                rx.el.table(
                                    rx.el.thead(
                                        rx.el.tr(
                                            rx.foreach(
                                                [
                                                    ("folder", "Case"),
                                                    (
                                                        "calendar",
                                                        "Created / UTC",
                                                    ),
                                                    (
                                                        "scan-line",
                                                        "Verdict / status",
                                                    ),
                                                    ("triangle-alert", "Risk"),
                                                    ("languages", "Language"),
                                                    ("arrow-up-right", "Open"),
                                                ],
                                                lambda col: rx.el.th(
                                                    rx.el.div(
                                                        rx.icon(
                                                            col[0],
                                                            class_name="h-3 w-3",
                                                        ),
                                                        col[1],
                                                        class_name="flex items-center gap-2",
                                                    ),
                                                    class_name="p-4 text-left text-xs font-medium opacity-60",
                                                ),
                                            )
                                        )
                                    ),
                                    rx.el.tbody(
                                        rx.foreach(
                                            ReviewState.history_rows,
                                            history_row,
                                        )
                                    ),
                                    class_name="w-full table-auto text-sm",
                                ),
                                class_name="hidden overflow-x-auto md:block",
                            ),
                            rx.el.div(
                                rx.foreach(
                                    ReviewState.history_rows, history_mobile
                                ),
                                class_name="space-y-3 md:hidden",
                            ),
                            class_name="mt-8 overflow-hidden border border-slate-500/20",
                        ),
                    ),
                ),
            ),
            rx.el.div(
                rx.el.button(
                    "← Previous",
                    disabled=(ReviewState.page_number == 0)
                    | ReviewState.loading,
                    on_click=ReviewState.turn_page(-1),
                    class_name="p-3 text-sm text-cyan-500 disabled:opacity-30",
                ),
                rx.el.p(
                    f"Page {ReviewState.page_number + 1} · 30 cases per page",
                    class_name="text-xs opacity-60",
                ),
                rx.el.button(
                    "Next →",
                    disabled=~ReviewState.has_more | ReviewState.loading,
                    on_click=ReviewState.turn_page(1),
                    class_name="p-3 text-sm text-cyan-500 disabled:opacity-30",
                ),
                class_name="my-6 flex items-center justify-between",
            ),
            warning(),
            id="main",
            class_name="mx-auto w-full max-w-7xl px-5 sm:px-8",
        )
    )


def loading_panel() -> rx.Component:
    return rx.el.div(
        "Loading authorized evidence…",
        role="status",
        aria_live="polite",
        class_name="my-8 h-40 border border-cyan-500/25 bg-slate-500/10 p-6 motion-safe:animate-pulse",
    )


def error_panel() -> rx.Component:
    return rx.el.div(
        rx.icon("shield-alert", class_name="h-6 w-6 text-amber-500"),
        rx.el.p(
            ReviewState.error,
            role="alert",
            class_name="my-4 text-sm text-amber-500",
        ),
        rx.el.a("Return to history →", href="/history", class_name=LINK),
        class_name="my-8 border border-amber-500/30 p-6",
    )


def modality_card(row: dict[str, str]) -> rx.Component:
    return rx.el.button(
        rx.el.div(
            rx.el.span(
                row["modality"],
                class_name="font-['Roboto_Condensed'] text-lg uppercase",
            ),
            rx.el.span(
                row["status"],
                class_name="text-[10px] uppercase tracking-widest opacity-65",
            ),
            class_name="flex items-center justify-between gap-4",
        ),
        rx.el.p(row["score"], class_name="mt-4 text-2xl text-cyan-500"),
        rx.el.p(
            row["semantics"],
            class_name="mt-1 break-words text-[10px] opacity-60",
        ),
        rx.el.p(
            f"Reliability {row['reliability']} / Weight {row['weight']}",
            class_name="mt-4 text-xs leading-5",
        ),
        rx.cond(
            row["labels"] != "",
            rx.el.p(
                f"Produced labels: {row['labels']}", class_name="mt-2 text-xs"
            ),
        ),
        rx.el.p(row["reason"], class_name="mt-2 text-xs opacity-60"),
        on_click=ReviewState.select_modality(row["id"]),
        aria_pressed=ReviewState.selected == row["id"],
        class_name=rx.cond(
            ReviewState.selected == row["id"],
            "min-w-[220px] flex-1 border border-cyan-500/60 bg-cyan-500/5 p-5 text-left",
            "min-w-[220px] flex-1 border border-slate-500/25 p-5 text-left hover:border-cyan-500/50",
        ),
        key=row["id"],
    )


def record_details(title: str, content: rx.Var[str]) -> rx.Component:
    return rx.el.details(
        rx.el.summary(
            title,
            class_name="cursor-pointer py-3 text-sm font-medium text-cyan-500",
        ),
        rx.el.pre(
            content,
            class_name="max-h-96 overflow-auto whitespace-pre-wrap break-words pb-4 font-mono text-xs leading-6 opacity-75",
        ),
        class_name="border-b border-slate-500/25",
    )


def evidence_record(row: dict[str, str]) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.el.div(
                rx.el.h3(
                    row["kind"], class_name="font-['Roboto_Condensed'] text-lg"
                ),
                rx.el.p(
                    f"{row['interval']} · Score {row['score']}",
                    class_name="mt-1 text-xs opacity-65",
                ),
            ),
            rx.el.button(
                "Inspect measurement",
                on_click=ReviewState.show_evidence(row["id"]),
                class_name=LINK,
            ),
            class_name="flex flex-wrap items-center justify-between gap-3",
        ),
        rx.el.p(row["label"], class_name="mt-2 text-sm"),
        rx.el.p(row["description"], class_name="text-sm opacity-65"),
        record_details(
            "Exact measurements / regions / explanation", row["details"]
        ),
        class_name="border-t border-slate-500/25 py-5",
        key=row["id"],
    )


def forensic_panel() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.h2(
                f"{ReviewState.selected_info['modality']} / forensic evidence",
                class_name="font-['Roboto_Condensed'] text-2xl uppercase",
            ),
            rx.el.p(
                "Explanations describe model behavior, not proof of manipulation. Highest-scoring timestamps and segments are relative rankings, not validated suspicious-event thresholds.",
                class_name="mt-3 text-xs leading-6 opacity-65",
            ),
            class_name="mb-6",
        ),
        rx.cond(
            ReviewState.media != "",
            rx.match(
                ReviewState.selected_info["modality"],
                (
                    "video",
                    rx.el.video(
                        src=ReviewState.media,
                        controls=True,
                        preload="metadata",
                        class_name="mb-6 max-h-96 w-full",
                    ),
                ),
                (
                    "audio",
                    rx.el.audio(
                        src=ReviewState.media,
                        controls=True,
                        preload="metadata",
                        class_name="mb-6 w-full",
                    ),
                ),
                rx.el.img(
                    src=ReviewState.media,
                    alt="Authorized retained source",
                    class_name="mb-6 max-h-96 object-contain",
                ),
            ),
            rx.el.div(
                rx.icon(
                    "file-lock-2", class_name="h-5 w-5 shrink-0 text-amber-500"
                ),
                rx.el.p(
                    "Source preview / original text unavailable or not retained. Crops cannot be reconstructed from coordinates. No substitute media is shown.",
                    class_name="text-xs leading-6 opacity-65",
                ),
                class_name="mb-6 flex gap-3 border border-dashed border-slate-500/30 p-4",
            ),
        ),
        rx.cond(
            ReviewState.original_text != "",
            rx.el.pre(
                ReviewState.original_text,
                class_name="mb-6 max-h-96 overflow-auto whitespace-pre-wrap text-sm leading-7",
            ),
        ),
        rx.cond(
            ReviewState.artifact != "",
            rx.el.img(
                src=ReviewState.artifact,
                alt="Retained model explanation artifact",
                class_name="my-5 max-h-96 object-contain",
            ),
        ),
        rx.cond(
            ReviewState.chart_kind != "none",
            rx.el.div(
                rx.el.h3(
                    ReviewState.chart_title,
                    class_name="mb-3 text-sm font-medium",
                ),
                reflex_xy.chart(
                    ReviewState.evidence_chart,
                    height="340px",
                    class_name="w-full min-w-[280px]",
                ),
                class_name="min-h-[390px] w-full shrink-0 overflow-x-auto border border-slate-500/25 bg-white p-3 text-slate-900",
            ),
        ),
        rx.el.p(
            ReviewState.chart_description,
            class_name="my-4 text-xs leading-6 opacity-65",
            role="status",
        ),
        rx.el.button(
            "Restore modality timeline",
            on_click=ReviewState.select_modality(ReviewState.selected),
            class_name=LINK,
        ),
        rx.cond(
            ReviewState.selected_info["modality"] == "text",
            rx.el.div(
                rx.el.h3(
                    "Factuality assessment",
                    class_name="font-['Roboto_Condensed'] text-xl",
                ),
                rx.el.p(
                    ReviewState.selected_info["factuality"],
                    class_name="mt-3 whitespace-pre-wrap text-amber-500",
                ),
                rx.el.p(
                    "AI-origin scores, chunks and suspicious spans do not establish whether a claim is true or false.",
                    class_name="mt-3 text-xs leading-6 opacity-65",
                ),
                class_name="my-6 border border-amber-500/25 p-5",
            ),
        ),
        record_details(
            "Language / quality diagnostics",
            ReviewState.selected_info["quality"],
        ),
        record_details(
            "Model provenance / calibration",
            ReviewState.selected_info["provenance"],
        ),
        record_details(
            "AI-origin / linguistic indicators",
            ReviewState.selected_info["indicators"],
        ),
        record_details(
            "Warnings and limitations", ReviewState.selected_info["limitations"]
        ),
        rx.cond(
            ReviewState.evidence.length() > 0,
            rx.el.div(
                rx.el.h3(
                    "Evidence ledger",
                    class_name="mt-8 mb-4 font-['Roboto_Condensed'] text-xl",
                ),
                rx.foreach(ReviewState.evidence, evidence_record),
            ),
            rx.el.p(
                "No persisted evidence records available for this modality.",
                class_name="my-8 text-sm opacity-60",
            ),
        ),
        class_name="min-w-0",
    )


def file_record(row: dict[str, str]) -> rx.Component:
    return rx.el.details(
        rx.el.summary(
            row["name"],
            class_name="cursor-pointer break-words py-4 text-sm font-medium",
        ),
        rx.el.dl(
            metadata("Modality / MIME", f"{row['modality']} / {row['mime']}"),
            metadata(
                "Bytes / dimensions / duration ms",
                f"{row['bytes']} / {row['dimensions']} / {row['duration_ms']}",
            ),
            metadata("SHA-256", row["sha256"]),
            metadata("Hash verified at", row["verified"]),
            metadata("Source retention", row["retention"]),
        ),
        class_name="border-b border-slate-500/25",
        key=row["id"],
    )


def dossier() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.p(
                    "OVERALL ASSESSMENT",
                    class_name="text-[10px] tracking-widest opacity-60",
                ),
                rx.el.h2(
                    ReviewState.case["verdict"],
                    class_name=rx.match(
                        ReviewState.case["verdict"],
                        (
                            "Fake",
                            "mt-2 font-['Roboto_Condensed'] text-5xl text-red-500",
                        ),
                        (
                            "Real",
                            "mt-2 font-['Roboto_Condensed'] text-5xl text-cyan-400",
                        ),
                        "mt-2 font-['Roboto_Condensed'] text-5xl text-amber-500",
                    ),
                ),
                rx.el.p(
                    f"Risk: {ReviewState.case['risk']} · Status: {ReviewState.case['status']}",
                    class_name="mt-4 text-sm",
                ),
                rx.cond(
                    ReviewState.case["verdict"] == "Uncertain",
                    rx.el.p(
                        "INSUFFICIENT EVIDENCE FOR A REAL / FAKE CONCLUSION",
                        class_name="mt-5 text-xs tracking-wider text-amber-500",
                    ),
                    rx.el.p(
                        "PRELIMINARY MODEL CLASSIFICATION · NOT A CALIBRATED PROBABILITY",
                        class_name="mt-5 text-xs tracking-wider text-cyan-400",
                    ),
                ),
                rx.el.p(
                    ReviewState.case["reason"],
                    class_name="mt-3 text-sm leading-6 opacity-65",
                ),
                class_name="flex-1",
            ),
            rx.el.dl(
                metadata(
                    "Calibrated confidence (0–1)",
                    ReviewState.case["confidence"],
                ),
                metadata(
                    "Calibrated fake probability (0–1)",
                    ReviewState.case["probability"],
                ),
                metadata("Detected language", ReviewState.case["language"]),
                class_name="w-full md:w-80",
            ),
            class_name="flex flex-col gap-8 border-y border-slate-500/25 py-7 md:flex-row",
        ),
        rx.el.div(
            rx.foreach(ReviewState.modalities, modality_card),
            class_name="my-8 flex flex-wrap gap-3",
        ),
        rx.el.p(
            "Unavailable is not a negative result. Reliability is a quality gate, not calibrated confidence. Fusion weights appear only when recorded; unknown risk is not low risk.",
            class_name="mb-8 text-xs leading-6 opacity-60",
        ),
        rx.el.div(
            forensic_panel(),
            rx.el.aside(
                rx.el.h2(
                    "CASE / PROVENANCE",
                    class_name="font-['Roboto_Condensed'] text-lg tracking-wider",
                ),
                rx.el.dl(
                    metadata("Case ID", ReviewState.case["id"]),
                    metadata("Created", ReviewState.case["created"]),
                    metadata("Last updated", ReviewState.case["updated"]),
                    metadata("Pipeline version", ReviewState.case["pipeline"]),
                    metadata("Retention policy", ReviewState.case["retention"]),
                    metadata("Accessible until", ReviewState.case["expires"]),
                ),
                rx.el.p(
                    "Expiry restricts access. It is not a promise of immediate database erasure. Hashes establish byte integrity, not source authenticity.",
                    class_name="my-5 text-xs leading-6 opacity-60",
                ),
                rx.el.h3(
                    "Files & integrity",
                    class_name="mt-8 font-['Roboto_Condensed'] text-xl",
                ),
                rx.foreach(ReviewState.files, file_record),
                record_details(
                    "Overall limitations", ReviewState.case["limitations"]
                ),
                class_name="min-w-0 border-t border-slate-500/25 pt-6 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0",
            ),
            class_name="grid gap-8 lg:grid-cols-[minmax(0,2.3fr)_minmax(250px,1fr)]",
        ),
    )


def review_page(report: bool = False) -> rx.Component:
    return shell(
        rx.el.main(
            page_header(
                rx.cond(report, "Forensic report", "Forensic workspace"),
                "Persisted evidence. Explicit uncertainty. A traceable, human-led review.",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.a("← History", href="/history", class_name=LINK),
                    rx.el.a(
                        rx.cond(report, "Open results", "Open report"),
                        href=rx.cond(
                            report,
                            f"/results/{ReviewState.case['id']}",
                            f"/report/{ReviewState.case['id']}",
                        ),
                        class_name=LINK,
                    ),
                    class_name="flex gap-5",
                ),
                rx.el.div(
                    rx.el.button(
                        rx.icon("download", class_name="h-4 w-4"),
                        rx.cond(
                            ReviewState.exporting, "Generating…", "Download PDF"
                        ),
                        on_click=ReviewState.download_report("pdf"),
                        disabled=ReviewState.loading
                        | ReviewState.exporting
                        | (ReviewState.error != "")
                        | (ReviewState.case["id"] == ""),
                        class_name=BUTTON,
                    ),
                    rx.el.button(
                        "Export JSON",
                        on_click=ReviewState.download_report("json"),
                        disabled=ReviewState.loading
                        | ReviewState.exporting
                        | (ReviewState.error != "")
                        | (ReviewState.case["id"] == ""),
                        class_name="px-3 py-3 text-sm text-cyan-500 disabled:opacity-40",
                    ),
                    class_name="flex flex-wrap gap-3",
                ),
                class_name="mb-6 flex flex-wrap items-center justify-between gap-5",
            ),
            rx.el.p(
                ReviewState.export_note,
                role="status",
                class_name="mb-5 break-all text-xs leading-6 text-cyan-500",
            ),
            warning(),
            rx.cond(
                ReviewState.loading,
                loading_panel(),
                rx.cond(ReviewState.error != "", error_panel(), dossier()),
            ),
            rx.el.p(
                "PDF and JSON are generated from a fresh authorized database snapshot. Raw sources and private storage locations are excluded. Complete numerical arrays are available in JSON; large arrays are summarized in PDF.",
                class_name="mt-8 border-t border-slate-500/25 pt-5 text-xs leading-6 opacity-60",
            ),
            id="main",
            class_name="mx-auto w-full max-w-7xl px-5 sm:px-8",
        )
    )


def forensic_workspace() -> rx.Component:
    return review_page()


def report_page() -> rx.Component:
    return review_page(True)
