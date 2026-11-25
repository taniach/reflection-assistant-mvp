"""Mirror Bot — CARE Reflection Assistant.

Application setup, rubric management, AI requests and four-step workflow.
Reusable chat components live in components.py, AI instructions in prompts.py,
and visual styling in assets/styles.css.
"""

# ============================================================
# 1. IMPORTS
# ============================================================

import os
from base64 import b64encode
from html import escape
from pathlib import Path
from typing import Optional

import streamlit as st
from docx import Document
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from pypdf import PdfReader

from prompts import BASE, DRAFT, FEEDBACK, QUESTION

from components import (
    # Guided conversation components
    render_message,
    extract_readiness,
    extract_progress,
    render_reflection_journey,
    scroll_to_readiness,

    # Reflection summary components
    parse_feedback,
    render_completion_banner,
    render_reflective_themes,
    render_strengths,
    render_growth_areas,
    render_wellbeing_check,
    render_closing_banner,
)


# ============================================================
# 2. CONFIGURATION
# ============================================================

ROOT = Path(__file__).parent
ASSETS_DIR = ROOT / "assets"
ICON_PATH = ASSETS_DIR / "mascot.png"
CSS_PATH = ASSETS_DIR / "styles.css"
DEFAULT_RUBRIC_PATH = ROOT / "rubric.txt"

TOTAL_STEPS = 4
MIN_DRAFT_RESPONSES = 2
MAX_RUBRIC_CHARACTERS = 40_000
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_OUTPUT_TOKENS = 1800
API_TIMEOUT = 45
API_MAX_RETRIES = 1

THEMES = [
    "Patient loss or adverse outcome",
    "Ethical or value conflict",
    "Challenging interaction",
    "Caring for patients with long-term needs",
    "Personal well-being and balance",
    "Other — my own experience",
]

OPENING_QUESTION = (
    "Tell me about a situation related to this theme that stayed with you. "
    "What happened, and what was your role?"
)

CONTINUE_INSTRUCTIONS = """
The student has chosen to continue reflecting.
Ask a new question exploring an additional relevant perspective or insight.
Return [READY] false for this response.
"""

# Preserve the educator's active rubric when starting a new reflection.
REFLECTION_STATE_KEYS = (
    "step", "messages", "draft", "feedback", "theme", "wellbeing", "edited", "ack"
)

load_dotenv(ROOT / ".env")

with Image.open(ICON_PATH) as icon_image:
    st.set_page_config(
        page_title="Mirror Bot",
        page_icon=icon_image,
        layout="centered",
        initial_sidebar_state="collapsed",
    )

DEFAULT_RUBRIC = DEFAULT_RUBRIC_PATH.read_text(encoding="utf-8")
s = st.session_state


# ============================================================
# 3. APPLICATION SETUP & SESSION STATE
# ============================================================

def load_css(file_path: Path) -> None:
    """Load the external stylesheet on every Streamlit rerun."""
    css = file_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def initialise_session() -> None:
    """Set defaults only for missing keys, preserving ongoing conversations."""
    defaults = {
        "step": 1,
        "messages": [],
        "rubric": DEFAULT_RUBRIC,
        "draft": "",
        "feedback": "",
        "theme": "",
        "wellbeing": None,
        "previously_ready": False,
        "reflection_progress": {
            "experience": "exploring",
            "emotions": "pending",
            "perspectives": "pending",
            "meaning": "pending",
            "future": "pending",
        },
    }

    for key, value in defaults.items():
        if key not in s:
            s[key] = value


def go(step: int) -> None:
    """Navigate to another workflow screen and refresh the interface."""
    s.step = step
    st.rerun()


def reset_reflection() -> None:
    """Clear the current reflection without discarding the active rubric."""
    for key in REFLECTION_STATE_KEYS:
        s.pop(key, None)
    # Reset readiness tracking for the new conversation.
    s.previously_ready = False
    s.pop("reflection_progress", None)
    st.rerun()


def get_image_base64(path: Path) -> str:
    """Encode a local image for embedding in the custom HTML header."""
    return b64encode(path.read_bytes()).decode("utf-8")


# ============================================================
# 4. RUBRIC MANAGEMENT
# ============================================================

def extract(upload) -> str:
    """Extract rubric text from a DOCX, PDF or UTF-8 text upload.

    For Word files, prioritise the CARE2 rubric table rather than unrelated
    document instructions. Preserve the table's row and column structure.
    """
    extension = Path(upload.name).suffix.lower()
    upload.seek(0)

    if extension == ".docx":
        document = Document(upload)
        rubric_tables = [
            table
            for table in document.tables
            if any(
                "Required Component" in " ".join(cell.text.split())
                for row in table.rows
                for cell in row.cells
            )
        ]

        if rubric_tables:
            return "\n".join(
                " | ".join(cell.text.replace("\n", " ") for cell in row.cells)
                for table in rubric_tables
                for row in table.rows
            )

        # Fallback for other educator-approved Word rubric formats.
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        table_rows = [
            " | ".join(cell.text for cell in row.cells)
            for table in document.tables
            for row in table.rows
        ]
        return "\n".join(paragraphs + table_rows)

    if extension == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(upload).pages)

    return upload.getvalue().decode("utf-8")


def render_educator_settings() -> None:
    """Display collapsed educator settings in the native Streamlit sidebar."""
    with st.sidebar.expander("⚙️ Educator Settings", expanded=False):
        st.caption(
            "CARE2 Appendix B is already loaded. Replace only with an "
            "approved, non-sensitive rubric."
        )

        # Prevent a rubric change midway through a guided conversation.
        upload = st.file_uploader(
            "Upload rubric",
            type=["docx", "pdf", "txt"],
            disabled=s.step != 1,
        )

        if upload and st.button("Load rubric", disabled=s.step != 1):
            try:
                content = extract(upload)
                if not content.strip() or len(content) > MAX_RUBRIC_CHARACTERS:
                    st.error("Use a readable rubric under 40,000 characters.")
                else:
                    s.rubric = content
                    st.success("Rubric loaded")
            except Exception:
                st.error("Unable to read document.")

        with st.expander("Active rubric"):
            st.text(s.rubric)

        if st.button("Restore default rubric", disabled=s.step != 1):
            s.rubric = DEFAULT_RUBRIC
            st.rerun()

        if st.button("New reflection"):
            reset_reflection()


# ============================================================
# 5. OPENAI API INTEGRATION
# ============================================================

def ask_ai(task: str, messages: list[dict[str, str]]) -> str:
    """Send the selected task, active rubric and conversation to OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Missing API key. Configure OPENAI_API_KEY and restart.")

    client = OpenAI(
        api_key=api_key,
        timeout=API_TIMEOUT,
        max_retries=API_MAX_RETRIES,
    )

    instructions = (
        f"{BASE}\n\n"
        f"Rubric reference:\n{s.rubric}\n\n"
        f"Task:\n{task}\n"
        f"Theme: {s.theme}"
    )

    result = client.responses.create(
        model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        instructions=instructions,
        input=messages,
        store=False,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    if not result.output_text.strip():
        raise RuntimeError("No text returned. Try again.")

    return result.output_text


def call(task: str, messages: list[dict[str, str]]) -> Optional[str]:
    """Show request progress and handle API errors without crashing the UI."""
    try:
        with st.spinner("Reflecting…"):
            return ask_ai(task, messages)
    except Exception as error:
        # Avoid exposing credentials or raw API error details to students.
        st.error(
            f"Unable to complete request ({type(error).__name__}). "
            "Check your API key, billing, model access and internet "
            "connection, then retry."
        )
        return None


# ============================================================
# 6. SHARED UI & CONVERSATION HELPERS
# ============================================================

def render_header() -> None:
    """Display the branded header, privacy notice and workflow progress."""
    icon_base64 = get_image_base64(ICON_PATH)

    st.markdown(f"""
        <div class="app-header">
            <img src="data:image/png;base64,{icon_base64}"
                 class="app-header-icon" alt="Mirror Bot mascot" />
            <div class="app-header-text">
                <div class="app-title">Mirror Bot: CARE Reflection Assistant</div>
                <div class="app-subtitle">
                    A guided, conversational tool that helps medical students turn
                    clinical experiences into meaningful, personalised reflections.
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.caption("Your experiences. Your insights. Your professional growth.")
    st.warning(
        "School prototype. Text and rubric are sent to an external AI API. "
        "Do not enter patient identifiers or real sensitive disclosures. "
        "Not a clinical or crisis service."
    )
    st.progress(s.step / TOTAL_STEPS, text=f"Step {s.step} of {TOTAL_STEPS}")


def render_theme_card() -> None:
    """Display the chosen theme using the existing external CSS classes."""
    st.markdown(f"""
        <div class="theme-card">
            <div class="theme-label">Your selected theme</div>
            <div class="theme-value">{escape(s.theme)}</div>
        </div>
    """, unsafe_allow_html=True)


def append_assistant_reply(reply: str) -> None:
    """
    Store an assistant reply and update the student's
    rubric-informed reflection progress.
    """

    # Extract validated reflection progress from AI metadata.
    _, progress = extract_progress(reply)

    if progress:
        s.reflection_progress = progress

    # Preserve the original response, including metadata,
    # for conversation history and readiness detection.
    s.messages.append({
        "role": "assistant",
        "content": reply
    })


def generate_draft() -> None:
    """Generate a new reflection and move to the editor on success."""
    draft = call(DRAFT, s.messages)
    if draft:
        s.draft = draft
        # Discard the old editor value so it cannot override a fresh draft.
        s.pop("edited", None)
        go(3)


def render_readiness_card(response_count: int) -> None:
    """Offer explicit next steps when the AI reports sufficient reflection."""
    with st.container(key="reflection_ready", border=True):
        st.subheader("✨ Your reflection is ready")
        st.write("You have explored enough meaningful insights to generate your reflection.")

        if st.button(
            "✨ Generate my reflection",
            key="generate_ready",
            type="primary",
            use_container_width=True,
        ):
            generate_draft()

        if st.button(
            "Continue reflecting",
            key="continue_ready",
            use_container_width=True,
        ):
            reply = call(QUESTION + "\n" + CONTINUE_INSTRUCTIONS, s.messages)
            if reply:
                append_assistant_reply(reply)
                st.rerun()


# ============================================================
# 7. STEP 1 — THEME SELECTION
# ============================================================

def render_theme_selection() -> None:
    """Let the student select a theme and acknowledge the privacy notice."""
    st.header("Choose a reflective theme")
    theme = st.radio("What would you like to reflect on?", THEMES)
    acknowledged = st.checkbox("I will not enter patient identifiers.", key="ack")

    if st.button(
        "Start reflection",
        type="primary",
        disabled=not acknowledged
    ):
        s.theme = theme

        # Reset reflective domain progress for a new conversation.
        s.reflection_progress = {
            "experience": "exploring",
            "emotions": "pending",
            "perspectives": "pending",
            "meaning": "pending",
            "future": "pending",
        }

        # Reset automatic scroll tracking.
        s.previously_ready = False

        # Keep your existing opening message here.
        s.messages = [
            {
                "role": "assistant",
                "content": (
                    "Tell me about a situation related to this "
                    "theme that stayed with you. What happened, "
                    "and what was your role?"
                )
            }
        ]

        go(2)


# ============================================================
# 8. STEP 2 — GUIDED CONVERSATION
# ============================================================

def render_guided_conversation() -> None:
    """Render guided reflection and conversation controls."""

    st.header("Guided conversation")

    render_theme_card()

    # --------------------------------------------------------
    # Floating reflection journey panel
    # --------------------------------------------------------

    st.caption(
        "One question at a time. You can skip a question, "
        "continue or stop."
    )

    # Existing conversation history
    for message in s.messages:
        render_message(message)

    with st.container(key="floating_journey"):
        render_reflection_journey(s.reflection_progress)

    response_count = sum(message["role"] == "user" for message in s.messages)
    last_message = s.messages[-1] if s.messages else None

    # A last user message without an assistant reply indicates a pending request.
    pending = bool(last_message and last_message["role"] == "user")
    ready = False
    if last_message and last_message["role"] == "assistant":
        _, ready = extract_readiness(last_message["content"])

    # Only one of the readiness, retry and chat-input controls is shown.
    # --------------------------------------------------------
    # Reflection readiness and automatic scrolling
    # --------------------------------------------------------

    previously_ready = s.get("previously_ready", False)

    # Detect the transition into readiness.
    newly_ready = ready and not previously_ready

    # Remember readiness across Streamlit reruns.
    s.previously_ready = ready

    if ready:
        render_readiness_card(response_count)

        # Scroll only when the readiness card first appears.
        if newly_ready:
            scroll_to_readiness()

    elif pending:
        if st.button("Retry follow-up", key="retry_followup"):
            reply = call(QUESTION, s.messages)
            if reply:
                append_assistant_reply(reply)
                st.rerun()

    else:

        # --------------------------------------------------------
        # Chat input
        # --------------------------------------------------------

        text = st.chat_input(
            "Choose an option above to proceed."
            if ready else "Share your thoughts...",
            key="reflection_input",
            disabled=ready or pending
        )

        if text and text.strip() and not ready and not pending:
            s.messages.append({
                "role": "user",
                "content": text.strip()
            })

            reply = call(QUESTION, s.messages)

            if reply:
                append_assistant_reply(reply)

            st.rerun()

    # --------------------------------------------------------
    # Navigation controls
    # --------------------------------------------------------

    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center"
    ):
        # Return to theme selection.
        if st.button(
            "← Back to themes",
            key="back_to_themes"
        ):
            go(1)

        # Allow early reflection generation.
        if not ready:
            if st.button(
                "Generate my reflection →",
                key="generate_early",
                type="primary",
                disabled=response_count < MIN_DRAFT_RESPONSES,
                use_container_width=False
            ):
                generate_draft()


# ============================================================
# 9. STEP 3 — REFLECTION DRAFT & EDITOR
# ============================================================

def render_reflection_editor() -> None:
    """Allow review, editing, word counting and download of the AI draft."""
    st.header("Your reflection")
    st.caption(
        "AI-generated draft. Review for accuracy and ownership. "
        "Follow your school’s AI-use rules before submitting anything."
    )

    edited = st.text_area(
        "Edit your reflection",
        value=s.draft,
        height=360,
        key="edited",
    )
    st.caption(f"Word count: {len(edited.split())} words")
    st.download_button("Download reflection", edited, file_name="reflection.txt")

    if st.button("View personalised insights", type="primary"):
        # Feedback is based on the student's underlying conversation.
        feedback = call(FEEDBACK, s.messages)
        if feedback:
            s.feedback = feedback
            s.draft = edited
            go(4)

    if st.button("Continue reflecting"):
        s.draft = edited
        go(2)



# ============================================================
# STEP 4 — REFLECTION SUMMARY AND WELL-BEING
# ============================================================

def render_reflection_summary() -> None:
    """
    Render the student's personalised reflection report.

    AI-generated feedback is presented as structured
    visual cards.

    The optional well-being check remains independent
    of the AI.
    """

    # --------------------------------------------------------
    # Completion banner
    # --------------------------------------------------------

    render_completion_banner()

    st.header("Your reflection summary")

    st.caption(
        "Personalised insights from your reflective conversation."
    )

    # --------------------------------------------------------
    # Personalised reflective feedback
    # --------------------------------------------------------

    feedback = parse_feedback(s.feedback)

    if feedback:

        render_reflective_themes(feedback)

        render_strengths(feedback)

        render_growth_areas(feedback)

    else:

        # Support feedback generated before the JSON update.
        with st.container(border=True):

            st.markdown(s.feedback)

    # --------------------------------------------------------
    # Optional well-being check
    # --------------------------------------------------------

    render_wellbeing_check()

    # --------------------------------------------------------
    # Closing illustration and message
    # --------------------------------------------------------

    render_closing_banner()

    # --------------------------------------------------------
    # Navigation controls
    # --------------------------------------------------------

    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center"
    ):

        if st.button(
            "← Return to reflection",
            key="return_to_reflection"
        ):
            go(3)

        st.download_button(
            "↓ Download reflection",
            data=s.get("edited", s.draft),
            file_name="reflection.txt",
            mime="text/plain",
            key="download_final_reflection",
            type="primary"
        )

    st.caption(
        "Mirror Bot · Your experiences. "
        "Your insights. Your professional growth."
    )


# ============================================================
# 11. APPLICATION ENTRY POINT
# ============================================================

def main() -> None:
    """Initialise the interface and render the current workflow screen."""
    load_css(CSS_PATH)
    initialise_session()
    render_educator_settings()
    render_header()

    if s.step == 1:
        render_theme_selection()
    elif s.step == 2:
        render_guided_conversation()
    elif s.step == 3:
        render_reflection_editor()
    elif s.step == 4:
        render_reflection_summary()
    else:
        go(1)


if __name__ == "__main__":
    main()
