import reflex as rx

import app.models  # Register declarative metadata without accessing the database.
from app.components.deepshield.api import attach_api
from app.components.forensics_ui import landing, workspace
from app.components.review_ui import (
    forensic_workspace,
    history_page,
    report_page,
)
from app.states.intake_state import IntakeState
from app.states.review_state import ReviewState


def index() -> rx.Component:
    return landing()


app = rx.App(
    api_transformer=attach_api,
    theme=rx.theme(appearance="light"),
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(
            rel="preconnect",
            href="https://fonts.gstatic.com",
            cross_origin="",
        ),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Roboto+Condensed:wght@500;600;700&display=swap",
            rel="stylesheet",
        ),
    ],
)
app.add_page(
    index,
    route="/",
    title="DeepShield | Evidence before conclusions",
    on_load=IntakeState.initialize,
)
app.add_page(
    workspace,
    route="/analyze",
    title="DeepShield | Analyze evidence",
    on_load=IntakeState.initialize,
)
app.add_page(
    forensic_workspace,
    route="/results/[analysis_id]",
    title="DeepShield | Forensic workspace",
    on_load=ReviewState.load_case,
)
app.add_page(
    report_page,
    route="/report/[analysis_id]",
    title="DeepShield | Forensic report",
    on_load=ReviewState.load_case,
)
app.add_page(
    history_page,
    route="/history",
    title="DeepShield | Analysis history",
    on_load=ReviewState.load_history,
)
