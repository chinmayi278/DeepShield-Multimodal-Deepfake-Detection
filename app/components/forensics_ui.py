import reflex as rx

from app.states.intake_state import IntakeState

LANGUAGES = [
    ("auto", "Auto-detect"),
    ("en", "English"),
    ("hi", "हिन्दी · Hindi"),
    ("kn", "ಕನ್ನಡ · Kannada"),
    ("ta", "தமிழ் · Tamil"),
    ("te", "తెలుగు · Telugu"),
    ("ml", "മലയാളം · Malayalam"),
    ("mr", "मराठी · Marathi"),
    ("bn", "বাংলা · Bengali"),
]
MODES = [
    ("image", "Image", "scan-face"),
    ("video", "Video", "film"),
    ("audio", "Audio", "audio-lines"),
    ("text", "Text", "text-cursor-input"),
    ("multimodal", "Multimodal", "layers"),
]
BUTTON = "inline-flex items-center justify-center gap-2 rounded-sm bg-cyan-400 px-5 py-3 text-sm font-semibold text-slate-950 hover:bg-cyan-300 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
PANEL = "rounded-sm border border-slate-700/40 bg-slate-900/40 p-6"


def navigation() -> rx.Component:
    return rx.el.header(
        rx.el.a(
            "Skip to content",
            href="#main",
            class_name="sr-only focus:not-sr-only focus:bg-cyan-400 focus:p-3 focus:text-slate-950",
        ),
        rx.el.div(
            rx.el.a(
                rx.icon("shield-check", class_name="h-7 w-7 text-cyan-400"),
                rx.el.span(
                    "DEEPSHIELD",
                    class_name="font-['Roboto_Condensed'] text-xl font-semibold tracking-[0.15em]",
                ),
                href="/",
                class_name="flex items-center gap-3",
            ),
            rx.el.nav(
                rx.el.a(
                    "How it works",
                    href="/#pipelines",
                    class_name="hidden text-sm opacity-70 hover:opacity-100 sm:block",
                ),
                rx.el.a(
                    "Analyze evidence",
                    href="/analyze",
                    class_name="text-sm hover:text-cyan-400",
                ),
                rx.el.a(
                    "History",
                    href="/history",
                    class_name="text-sm hover:text-cyan-400",
                ),
                rx.el.button(
                    rx.cond(
                        IntakeState.light,
                        rx.icon("moon", class_name="h-4 w-4"),
                        rx.icon("sun", class_name="h-4 w-4"),
                    ),
                    on_click=IntakeState.toggle_theme,
                    aria_label="Toggle light or dark presentation",
                    class_name="rounded-sm border border-slate-500/40 p-2 hover:text-cyan-500 focus-visible:outline-2 focus-visible:outline-cyan-400",
                ),
                class_name="flex items-center gap-4 sm:gap-8",
                aria_label="Main navigation",
            ),
            class_name="mx-auto flex min-h-20 max-w-7xl items-center justify-between gap-4 px-5 sm:px-8",
        ),
        class_name="border-b border-slate-500/25",
    )


def warning() -> rx.Component:
    return rx.el.div(
        rx.icon(
            "triangle-alert",
            class_name="mt-0.5 h-4 w-4 shrink-0 text-amber-500",
        ),
        rx.el.div(
            rx.el.p(
                "AI detection is probabilistic and may produce false positives or false negatives.",
                class_name="font-medium",
            ),
            rx.el.p(
                "Not proof of manipulation, authorship, identity, or factuality. Never use as sole evidence for high-stakes decisions.",
                class_name="mt-1 opacity-70",
            ),
        ),
        class_name="flex gap-3 border border-amber-500/25 bg-amber-500/5 p-4 text-xs leading-5",
    )


def footer() -> rx.Component:
    return rx.el.footer(
        rx.el.div(
            rx.el.span(
                "DEEPSHIELD / EVIDENCE BEFORE CONCLUSIONS",
                class_name="text-[10px] tracking-[0.15em]",
            ),
            rx.el.span(
                "Research-grade signals. Human-led decisions.",
                class_name="text-xs opacity-60",
            ),
            class_name="mx-auto flex max-w-7xl flex-wrap justify-between gap-3 px-5 py-7 sm:px-8",
        ),
        class_name="mt-16 border-t border-slate-500/25",
    )


def shell(content: rx.Component) -> rx.Component:
    return rx.el.div(
        navigation(),
        content,
        footer(),
        class_name=rx.cond(
            IntakeState.light,
            "min-h-dvh bg-slate-100 font-['Inter'] text-slate-900 [&_h1]:text-slate-900 [&_h2]:text-slate-900 [&_h3]:text-slate-900",
            "min-h-dvh bg-[#080f1b] font-['Inter'] text-slate-100",
        ),
    )


def signal_lane(label: str, icon: str) -> rx.Component:
    return rx.el.div(
        rx.icon(icon, class_name="h-4 w-4 text-cyan-400"),
        rx.el.span(
            label, class_name="w-14 text-[10px] tracking-widest text-slate-400"
        ),
        rx.el.div(
            rx.foreach(
                [
                    2,
                    5,
                    3,
                    8,
                    4,
                    9,
                    6,
                    3,
                    7,
                    10,
                    4,
                    6,
                    8,
                    3,
                    5,
                    2,
                    9,
                    5,
                    7,
                    3,
                    6,
                    4,
                    8,
                    2,
                ],
                lambda n: rx.el.div(
                    class_name=rx.match(
                        n,
                        (2, "h-2 w-1 bg-cyan-400/30"),
                        (3, "h-3 w-1 bg-cyan-400/40"),
                        (4, "h-4 w-1 bg-cyan-400/50"),
                        (5, "h-5 w-1 bg-cyan-400/60"),
                        (6, "h-6 w-1 bg-cyan-400/70"),
                        (7, "h-7 w-1 bg-cyan-400/80"),
                        "h-8 w-1 bg-cyan-400",
                    )
                ),
            ),
            class_name="flex h-12 flex-1 items-center justify-between gap-1 motion-safe:animate-pulse",
        ),
        class_name="flex items-center gap-4 border-b border-slate-800 py-3",
    )


def signal_field() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.span(
                "MULTIMODAL SIGNAL FIELD",
                class_name="text-[10px] tracking-[0.18em] text-slate-400",
            ),
            rx.el.span(
                "● ILLUSTRATIVE",
                class_name="text-[9px] tracking-widest text-cyan-400",
            ),
            class_name="flex justify-between gap-3 border-b border-slate-700 pb-4",
        ),
        signal_lane("IMAGE", "scan-face"),
        signal_lane("VIDEO", "film"),
        signal_lane("AUDIO", "audio-lines"),
        signal_lane("TEXT", "text-cursor-input"),
        rx.el.div(
            rx.icon("git-merge", class_name="h-8 w-8 text-cyan-400"),
            rx.el.div(
                rx.el.p(
                    "INDEPENDENT SIGNALS. ONE EVIDENCE LAYER.",
                    class_name="font-['Roboto_Condensed'] text-sm tracking-wider text-slate-100",
                ),
                rx.el.p(
                    "Quality → calibration → reliability-aware fusion",
                    class_name="mt-2 text-[11px] text-slate-500",
                ),
            ),
            class_name="mt-6 flex items-center gap-4",
        ),
        class_name="relative w-full rounded-sm border border-cyan-400/25 bg-[#0b1523] p-6 sm:p-8",
        aria_label="Illustrative animated signal field showing four independent input pipelines, not live inference",
    )


def pipeline_card(
    number: str, name: str, icon: str, description: str
) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.icon(icon, class_name="h-6 w-6 text-cyan-500"),
            rx.el.span(number, class_name="font-mono text-xs opacity-40"),
            class_name="flex items-center justify-between",
        ),
        rx.el.h3(
            name,
            class_name="mt-7 font-['Roboto_Condensed'] text-xl font-semibold",
        ),
        rx.el.p(description, class_name="mt-3 text-sm leading-6 opacity-65"),
        class_name="border border-slate-500/25 p-6",
    )


def pipelines() -> rx.Component:
    return rx.el.section(
        rx.el.p(
            "01 / INDEPENDENT BY DESIGN",
            class_name="text-xs tracking-[0.18em] text-cyan-500",
        ),
        rx.el.h2(
            "Every medium leaves a different signal.",
            class_name="mt-3 font-['Roboto_Condensed'] text-3xl font-semibold",
        ),
        rx.el.div(
            pipeline_card(
                "01",
                "Image forensics",
                "scan-face",
                "Inspect visual synthesis signals, face regions and model-influential patches. Compression and image quality affect reliability.",
            ),
            pipeline_card(
                "02",
                "Video forensics",
                "film",
                "Sample frames and surface time-localized evidence. Frame signals are not full temporal understanding; audio is assessed separately.",
            ),
            pipeline_card(
                "03",
                "Audio forensics",
                "audio-lines",
                "Evaluate synthetic-speech indicators and window-level quality. Noise, codecs and language can limit anti-spoofing evidence.",
            ),
            pipeline_card(
                "04",
                "Text origin analysis",
                "text-cursor-input",
                "Analyze the original language for AI-origin signals. This is not fact checking, plagiarism detection or authorship attribution.",
            ),
            class_name="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4",
        ),
        rx.el.div(
            rx.icon("git-merge", class_name="h-5 w-5 shrink-0 text-cyan-500"),
            rx.el.p(
                "Fusion is earned, not averaged. Reliability gates preserve missing modalities and require compatible calibration. Conflicting, weak or unavailable evidence leads to uncertainty—not an invented probability.",
                class_name="text-sm leading-6 opacity-75",
            ),
            class_name="mt-4 flex gap-4 border-y border-slate-500/25 py-5",
        ),
        id="pipelines",
        class_name="scroll-mt-8",
    )


def language_guidance() -> rx.Component:
    return rx.el.div(
        rx.el.p(
            "ORIGINAL LANGUAGE. ORIGINAL CONTEXT.",
            class_name="text-xs tracking-widest text-cyan-500",
        ),
        rx.el.h2(
            "Eight languages. No translation detour.",
            class_name="mt-3 font-['Roboto_Condensed'] text-2xl font-semibold",
        ),
        rx.el.p(
            "English · Hindi · Kannada · Tamil · Telugu · Malayalam · Marathi · Bengali",
            class_name="mt-4 text-sm leading-7",
        ),
        rx.el.p(
            "Auto-identification or manual selection. Interface support does not imply equal model coverage: detector availability and language limitations are disclosed with every analysis. Mixed-language and short text may remain undetermined.",
            class_name="mt-3 text-sm leading-6 opacity-65",
        ),
    )


def landing() -> rx.Component:
    return shell(
        rx.el.main(
            rx.el.section(
                rx.el.div(
                    rx.el.p(
                        "MULTIMODAL DIGITAL FORENSICS / 0.3",
                        class_name="mb-6 text-[11px] tracking-[0.2em] text-cyan-500",
                    ),
                    rx.el.h1(
                        "Question the content.",
                        rx.el.br(),
                        rx.el.span(
                            "Examine the evidence.", class_name="text-cyan-500"
                        ),
                        class_name="font-['Roboto_Condensed'] text-5xl font-semibold leading-[1.08] tracking-tight sm:text-6xl lg:text-7xl",
                    ),
                    rx.el.p(
                        "A clearer view of synthetic media. Trace image, video, audio and text signals through independent forensic pipelines—without turning uncertainty into certainty.",
                        class_name="mt-6 max-w-xl text-base leading-7 opacity-65",
                    ),
                    rx.el.div(
                        rx.el.a(
                            "Start an analysis",
                            rx.icon("arrow-up-right", class_name="h-4 w-4"),
                            href="/analyze",
                            class_name=BUTTON,
                        ),
                        rx.el.a(
                            "Explore the pipelines",
                            rx.icon("arrow-down", class_name="h-4 w-4"),
                            href="#pipelines",
                            class_name="flex items-center gap-2 py-3 text-sm opacity-70 hover:opacity-100",
                        ),
                        class_name="mt-8 flex flex-wrap items-center gap-6",
                    ),
                    rx.el.div(
                        rx.icon("lock-keyhole", class_name="h-3 w-3"),
                        "No raw-media retention by default",
                        class_name="mt-5 flex items-center gap-2 text-[11px] opacity-50",
                    ),
                ),
                signal_field(),
                class_name="grid items-center gap-12 py-16 lg:grid-cols-2 lg:py-24",
            ),
            rx.el.div(warning(), class_name="mb-16"),
            pipelines(),
            rx.el.section(
                language_guidance(),
                rx.el.div(
                    rx.icon("fingerprint", class_name="h-7 w-7 text-cyan-500"),
                    rx.el.h2(
                        "Keep the evidence trail. Not the source.",
                        class_name="mt-4 font-['Roboto_Condensed'] text-2xl font-semibold",
                    ),
                    rx.el.p(
                        "Files are processed transiently; raw media and pasted text are not saved to the results database. We retain hashes, file metadata and redacted detector evidence. Results are available in this browser for 24 hours; metadata expiry is recorded, not a promise of immediate database erasure.",
                        class_name="mt-4 text-sm leading-6 opacity-65",
                    ),
                    rx.el.a(
                        "Open the evidence workspace →",
                        href="/analyze",
                        class_name="mt-5 inline-block text-sm text-cyan-500",
                    ),
                    id="privacy",
                ),
                class_name="mt-16 grid gap-12 border-t border-slate-500/25 pt-12 md:grid-cols-2",
            ),
            id="main",
            class_name="mx-auto w-full max-w-7xl px-5 sm:px-8",
        )
    )


def modality_selector() -> rx.Component:
    return rx.el.div(
        rx.foreach(
            MODES,
            lambda mode: rx.el.button(
                rx.icon(mode[2], class_name="h-4 w-4"),
                mode[1],
                type="button",
                on_click=IntakeState.choose_mode(mode[0]),
                disabled=IntakeState.busy | IntakeState.uploading,
                aria_pressed=IntakeState.mode == mode[0],
                class_name=rx.cond(
                    IntakeState.mode == mode[0],
                    "flex flex-1 items-center justify-center gap-2 border-b-2 border-cyan-400 bg-cyan-400/10 px-4 py-4 text-sm text-cyan-500",
                    "flex flex-1 items-center justify-center gap-2 border-b-2 border-transparent px-4 py-4 text-sm opacity-60 hover:opacity-100 focus-visible:outline-2 focus-visible:outline-cyan-400",
                ),
            ),
        ),
        class_name="flex flex-wrap border-b border-slate-500/25",
        role="group",
        aria_label="Analysis mode",
    )


def language_selector() -> rx.Component:
    return rx.el.div(
        rx.el.label(
            "Analysis language",
            html_for="language",
            class_name="text-sm font-medium",
        ),
        rx.el.div(
            rx.el.select(
                rx.foreach(
                    LANGUAGES,
                    lambda item: rx.el.option(
                        item[1],
                        value=item[0],
                        class_name="bg-slate-100 text-slate-900",
                    ),
                ),
                id="language",
                value=IntakeState.language,
                on_change=IntakeState.choose_language,
                disabled=IntakeState.busy,
                class_name="mt-2 w-full appearance-none rounded-sm border border-slate-500/40 bg-transparent p-3 pr-10 text-sm focus:outline-2 focus:outline-cyan-400",
            ),
            rx.icon(
                "chevron-down",
                class_name="pointer-events-none absolute right-3 top-5 h-4 w-4 opacity-60",
            ),
            class_name="relative",
        ),
        rx.el.p(
            "Original-language analysis. Model coverage varies; manual selections are not verified.",
            class_name="mt-2 text-xs leading-5 opacity-60",
        ),
    )


def file_card(item: dict[str, str]) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("file-check-2", class_name="h-4 w-4 text-cyan-500"),
            rx.el.div(
                rx.el.p(item["name"], class_name="break-all text-sm"),
                rx.el.p(
                    f"{item['modality']} / {item['display_size']} / hash verified",
                    class_name="mt-1 text-[11px] opacity-60",
                ),
                class_name="min-w-0 flex-1",
            ),
            rx.el.button(
                rx.icon("x", class_name="h-4 w-4"),
                type="button",
                aria_label=f"Remove {item['name']}",
                on_click=IntakeState.remove_file(item["id"]),
                disabled=IntakeState.busy | IntakeState.uploading,
                class_name="p-2 hover:text-red-500 focus-visible:outline-2 focus-visible:outline-cyan-400",
            ),
            class_name="flex items-center gap-3",
        ),
        rx.cond(
            item["preview"] != "",
            rx.match(
                item["modality"],
                (
                    "image",
                    rx.el.img(
                        src=item["preview"],
                        alt="Attached image preview",
                        class_name="mt-4 max-h-44 rounded-sm object-contain",
                    ),
                ),
                (
                    "video",
                    rx.el.video(
                        src=item["preview"],
                        controls=True,
                        preload="metadata",
                        class_name="mt-4 max-h-44 w-full",
                    ),
                ),
                rx.el.audio(
                    src=item["preview"],
                    controls=True,
                    preload="metadata",
                    class_name="mt-4 w-full",
                ),
            ),
            rx.el.p(
                "Preview omitted for large media. Full input is checked during analysis.",
                class_name="mt-3 text-xs opacity-50",
            ),
        ),
        class_name="mt-3 border border-slate-500/25 p-4",
        key=item["id"],
    )


def evidence_intake() -> rx.Component:
    return rx.el.div(
        rx.cond(
            IntakeState.mode != "text",
            rx.el.div(
                rx.upload.root(
                    rx.icon(
                        "scan-line",
                        class_name="mx-auto mb-4 h-9 w-9 text-cyan-500",
                    ),
                    rx.el.p(
                        "Drop evidence here",
                        class_name="font-['Roboto_Condensed'] text-2xl",
                    ),
                    rx.el.p(
                        "or click to browse files",
                        class_name="mt-2 text-sm text-cyan-500",
                    ),
                    rx.el.p(
                        "One file per modality · Multimodal accepts up to 3 media files",
                        class_name="mt-4 text-xs opacity-50",
                    ),
                    id="evidence",
                    accept=rx.match(
                        IntakeState.mode,
                        (
                            "image",
                            {
                                "image/jpeg": [".jpg", ".jpeg"],
                                "image/png": [".png"],
                                "image/webp": [".webp"],
                            },
                        ),
                        (
                            "video",
                            {
                                "video/mp4": [".mp4"],
                                "video/webm": [".webm"],
                                "video/quicktime": [".mov"],
                            },
                        ),
                        (
                            "audio",
                            {
                                "audio/wav": [".wav"],
                                "audio/mpeg": [".mp3"],
                                "audio/flac": [".flac"],
                                "audio/mp4": [".m4a"],
                            },
                        ),
                        {
                            "image/jpeg": [".jpg", ".jpeg"],
                            "image/png": [".png"],
                            "image/webp": [".webp"],
                            "video/mp4": [".mp4"],
                            "video/webm": [".webm"],
                            "video/quicktime": [".mov"],
                            "audio/wav": [".wav"],
                            "audio/mpeg": [".mp3"],
                            "audio/flac": [".flac"],
                            "audio/mp4": [".m4a"],
                        },
                    ),
                    multiple=IntakeState.mode == "multimodal",
                    disabled=IntakeState.busy | IntakeState.uploading,
                    on_drop=IntakeState.upload(
                        rx.upload_files(
                            upload_id="evidence",
                            on_upload_progress=IntakeState.upload_progress,
                        )
                    ),
                    class_name="cursor-pointer border border-dashed border-cyan-500/40 bg-cyan-500/5 px-5 py-10 text-center hover:bg-cyan-500/10 focus-visible:outline-2 focus-visible:outline-cyan-400",
                    aria_label="Upload evidence. Drop files, or press Enter to browse.",
                ),
                rx.el.p(
                    rx.match(
                        IntakeState.mode,
                        (
                            "image",
                            "JPG, JPEG, PNG, WebP · up to 10 MB · 32 px minimum · 16 MP maximum",
                        ),
                        (
                            "video",
                            "MP4, WebM, MOV · up to 32 MB · up to 120 seconds",
                        ),
                        (
                            "audio",
                            "WAV, MP3, FLAC, M4A · up to 20 MB · 0.25–120 seconds",
                        ),
                        "Image: JPG/PNG/WebP ≤10 MB · Video: MP4/WebM/MOV ≤32 MB · Audio: WAV/MP3/FLAC/M4A ≤20 MB. Media ≤120 seconds.",
                    ),
                    class_name="mt-3 text-xs leading-5 opacity-60",
                ),
                rx.cond(
                    IntakeState.uploading,
                    rx.el.div(
                        rx.el.p(
                            f"Uploading evidence · {IntakeState.progress}%",
                            class_name="mb-2 text-xs text-cyan-500",
                        ),
                        rx.el.progress(
                            value=IntakeState.progress,
                            max=100,
                            class_name="h-1 w-full accent-cyan-400",
                            aria_label="Upload progress",
                        ),
                        role="status",
                    ),
                ),
                rx.foreach(IntakeState.files, file_card),
            ),
        ),
        rx.cond(
            (IntakeState.mode == "text") | (IntakeState.mode == "multimodal"),
            rx.el.div(
                rx.el.label(
                    "Original text",
                    html_for="evidence-text",
                    class_name="text-sm font-medium",
                ),
                rx.el.textarea(
                    id="evidence-text",
                    name="evidence_text",
                    default_value=IntakeState.text_draft,
                    key=IntakeState.text_draft,
                    max_length=20000,
                    placeholder="Paste the original text here. Do not translate it before analysis.",
                    disabled=IntakeState.busy,
                    class_name="mt-3 min-h-56 w-full resize-y rounded-sm border border-slate-500/40 bg-transparent p-4 text-sm leading-6 focus:outline-2 focus:outline-cyan-400",
                ),
                rx.el.p(
                    "Maximum 20,000 characters. Short or mixed-language passages may be inconclusive. AI-origin signals are not factuality assessments.",
                    class_name="mt-2 text-xs leading-5 opacity-60",
                ),
                class_name="mt-6",
            ),
        ),
        rx.cond(
            (IntakeState.files.length() == 0) & (IntakeState.mode != "text"),
            rx.el.p(
                "No evidence attached yet. Choose a source file to begin.",
                class_name="mt-5 text-xs opacity-50",
            ),
        ),
    )


def check_option(
    label: str, checked: rx.Var[bool], handler: rx.event.EventType
) -> rx.Component:
    return rx.el.button(
        rx.el.span(
            rx.cond(
                checked, rx.icon("check", class_name="h-3 w-3"), rx.el.span()
            ),
            class_name="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center border border-cyan-500 text-cyan-500",
        ),
        rx.el.span(label, class_name="text-left text-xs leading-5"),
        role="checkbox",
        aria_checked=checked,
        type="button",
        on_click=handler,
        disabled=IntakeState.busy,
        class_name="flex w-full gap-3 py-3 focus-visible:outline-2 focus-visible:outline-cyan-400",
    )


def workspace() -> rx.Component:
    return shell(
        rx.el.main(
            rx.el.div(
                rx.el.p(
                    "WORKSPACE / EVIDENCE INTAKE",
                    class_name="text-xs tracking-[0.18em] text-cyan-500",
                ),
                rx.el.h1(
                    "Start with the source.",
                    class_name="mt-3 font-['Roboto_Condensed'] text-4xl font-semibold",
                ),
                rx.el.p(
                    "Submit original evidence. Inspect independent signals. Keep uncertainty visible.",
                    class_name="mt-3 text-sm opacity-65",
                ),
                class_name="py-10",
            ),
            rx.el.form(
                rx.el.fieldset(
                    modality_selector(),
                    rx.el.div(
                        rx.el.section(
                            rx.el.div(
                                rx.el.h2(
                                    "01 / Add evidence",
                                    class_name="font-['Roboto_Condensed'] text-xl font-semibold",
                                ),
                                rx.el.button(
                                    "Reset intake",
                                    type="button",
                                    on_click=IntakeState.clear_intake,
                                    disabled=IntakeState.busy
                                    | IntakeState.uploading,
                                    class_name="text-xs opacity-60 hover:text-cyan-500",
                                ),
                                class_name="mb-6 flex items-center justify-between",
                            ),
                            evidence_intake(),
                            class_name="min-w-0 p-5 sm:p-7",
                        ),
                        rx.el.aside(
                            rx.el.h2(
                                "02 / Analysis settings",
                                class_name="mb-6 font-['Roboto_Condensed'] text-xl font-semibold",
                            ),
                            language_selector(),
                            rx.el.div(
                                check_option(
                                    "Include model explanations where available",
                                    IntakeState.explain,
                                    IntakeState.toggle_explain,
                                ),
                                rx.el.p(
                                    "Highlights describe model behavior—not proof of manipulation.",
                                    class_name="text-xs leading-5 opacity-50",
                                ),
                                class_name="my-5 border-y border-slate-500/25 py-3",
                            ),
                            check_option(
                                "I consent to transient processing and retention of hashes, metadata and redacted evidence. Raw media and pasted text are not retained in results.",
                                IntakeState.consent,
                                IntakeState.toggle_consent,
                            ),
                            rx.el.p(
                                "Results are accessible in this browser for 24 hours. Metadata is marked for expiry; immediate erasure is not guaranteed.",
                                class_name="mt-2 text-xs leading-5 opacity-50",
                            ),
                            rx.el.button(
                                rx.cond(
                                    IntakeState.busy,
                                    "Analysis in progress",
                                    "Analyze evidence",
                                ),
                                rx.icon("arrow-right", class_name="h-4 w-4"),
                                type="submit",
                                disabled=IntakeState.busy
                                | IntakeState.uploading,
                                class_name=BUTTON,
                            ),
                            rx.el.p(
                                "No score is returned when a detector is unavailable.",
                                class_name="mt-3 text-xs opacity-50",
                            ),
                            class_name="flex flex-col gap-2 border-t border-slate-500/25 p-5 sm:p-7 lg:border-l lg:border-t-0",
                        ),
                        class_name="grid lg:grid-cols-[1.7fr_1fr]",
                    ),
                    disabled=IntakeState.busy,
                ),
                on_submit=IntakeState.submit,
                class_name="border border-slate-500/25",
            ),
            rx.cond(
                IntakeState.error != "",
                rx.el.div(
                    rx.icon("circle-alert", class_name="h-5 w-5 shrink-0"),
                    IntakeState.error,
                    role="alert",
                    class_name="mt-5 flex gap-3 border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-500",
                ),
            ),
            rx.cond(
                IntakeState.busy,
                rx.el.div(
                    rx.el.div(
                        rx.icon(
                            "loader-circle",
                            class_name="h-5 w-5 text-cyan-500 motion-safe:animate-spin",
                        ),
                        rx.el.p(
                            IntakeState.stage,
                            class_name="text-sm text-cyan-500",
                        ),
                        class_name="flex gap-3",
                    ),
                    rx.el.p(
                        IntakeState.detected,
                        class_name="mt-3 text-xs opacity-60",
                    ),
                    rx.el.div(
                        class_name="mt-5 h-16 rounded-sm bg-slate-500/10 motion-safe:animate-pulse"
                    ),
                    rx.el.p(
                        "CPU processing can take a few minutes. Keep this tab open.",
                        class_name="mt-3 text-xs opacity-50",
                    ),
                    role="status",
                    aria_live="polite",
                    aria_busy=True,
                    class_name="mt-5 border border-cyan-500/25 p-5",
                ),
            ),
            rx.el.div(warning(), class_name="mt-6"),
            id="main",
            class_name="mx-auto w-full max-w-7xl px-5 sm:px-8",
        )
    )
