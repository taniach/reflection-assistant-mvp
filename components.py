
"""
Reflection Assistant — UI Components

Contains reusable components for rendering the guided
reflection conversation, processing AI response markers,
and displaying the assistant's mascot.

Visual styling is maintained separately in assets/styles.css.
"""

# ============================================================
# 1. IMPORTS
# ============================================================

import re
import streamlit as st
import streamlit.components.v1 as st_components
import json

from html import escape
from pathlib import Path
from base64 import b64encode
from functools import lru_cache
from typing import Tuple, Dict


# ============================================================
# 2. CONFIGURATION
# ============================================================

ASSETS_DIR = Path(__file__).parent / "assets"
MASCOT_PATH = ASSETS_DIR / "mascot.png"

# Markers used by the AI to communicate reflection metadata.
CUE_MARKER = "[CUE]"

CUE_PATTERN = re.compile(
    r"\[\s*CUE\s*\]",
    re.IGNORECASE
)

READINESS_PATTERN = re.compile(
    r"\[\s*READY\s*\]\s*(true|false)\s*$",
    re.IGNORECASE
)

PROGRESS_PATTERN = re.compile(
    r"\[\s*PROGRESS\s*\]\s*(\{[^{}]*\})",
    re.IGNORECASE
)

FALLBACK_CUE_PATTERN = re.compile(
    r"\[([^\[\]\n]+)\]\s*$"
)

REFLECTION_DOMAINS = {
    "experience": "Exploring your experience",
    "emotions": "Understanding your emotions",
    "perspectives": "Considering different perspectives",
    "meaning": "Making sense of the experience",
    "future": "Connecting to your future practice",
}

VALID_PROGRESS_STATES = {
    "pending",
    "exploring",
    "explored",
}

# ============================================================
# 3. ASSET MANAGEMENT
# ============================================================

@lru_cache(maxsize=1)
def get_mascot() -> str:
    """
    Return the mascot image as a Base64-encoded string.

    Caching avoids repeatedly reading the image from disk
    whenever Streamlit renders a conversation message.
    """
    return b64encode(
        MASCOT_PATH.read_bytes()
    ).decode("utf-8")


# ============================================================
# 4. AI RESPONSE PROCESSING
# ============================================================

def extract_readiness(content: str) -> Tuple[str, bool]:
    """
    Extract the reflection readiness status from an AI response.

    The AI returns [READY] true when sufficient reflective
    material has been gathered, or [READY] false otherwise.

    Returns:
        clean_content: Response without the readiness marker.
        ready: Whether the AI recommends generating a draft.

    If no readiness marker exists, readiness defaults to False.
    """

    match = READINESS_PATTERN.search(content)

    if not match:
        return content, False

    ready = match.group(1).lower() == "true"
    clean_content = content[:match.start()].strip()

    return clean_content, ready


def extract_cue(content: str) -> Tuple[str, str]:
    """
    Separate the conversational response from its
    reflective cue.

    Supports flexible spacing and capitalisation
    in AI-generated markers.
    """

    # Preferred format: [CUE] or [ CUE ]
    match = CUE_PATTERN.search(content)

    if match:
        question = content[:match.start()].strip()
        cue = content[match.end():].strip()

        return question, cue

    # Fallback for bracketed reflective cues.
    match = FALLBACK_CUE_PATTERN.search(content)

    if match:
        question = content[:match.start()].strip()
        cue = match.group(1).strip()

        return question, cue

    # No reflective cue provided.
    return content.strip(), ""

def extract_progress(content: str) -> Tuple[str, Dict[str, str]]:
    """
    Extract rubric-informed progress metadata from an AI response.

    Returns:
        clean_content: Response without the progress marker.
        progress: Validated statuses for the reflective domains.

    Invalid or missing metadata returns an empty dictionary,
    allowing the application to retain its previous progress.
    """

    match = PROGRESS_PATTERN.search(content)

    if not match:
        return content, {}

    # Remove internal metadata before displaying the message.
    clean_content = PROGRESS_PATTERN.sub("", content).strip()

    try:
        progress = json.loads(match.group(1))

        if not isinstance(progress, dict):
            return clean_content, {}

        # Validate every domain and its status.
        if set(progress) != set(REFLECTION_DOMAINS):
            return clean_content, {}

        if any(
            not isinstance(status, str)
            or status not in VALID_PROGRESS_STATES
            for status in progress.values()
        ):
            return clean_content, {}

        return clean_content, progress

    except (json.JSONDecodeError, TypeError):
        return clean_content, {}


# ============================================================
# 5. REFLECTIVE CUE COMPONENT
# ============================================================

def build_cue_html(cue: str) -> str:
    """
    Build the optional reflective cue displayed beneath
    an assistant message.

    Returns an empty string when no cue is available.
    """

    if not cue:
        return ""

    return f"""
        <div class="reflective-cue">
            <span class="cue-icon">✧</span>
            {escape(cue)}
        </div>
    """


# ============================================================
# 6. ASSISTANT MESSAGE COMPONENT
# ============================================================

def render_assistant_message(content: str) -> None:
    """
    Render an assistant message with the mascot,
    conversational response and optional reflective cue.

    Internal AI metadata is removed before rendering
    so that students only see the intended response.
    """

    # Remove the readiness marker before extracting the cue.
    # Readiness is handled separately by app.py.
        # Remove internal AI metadata before rendering.
    clean_content, _ = extract_readiness(content)
    clean_content, _ = extract_progress(clean_content)

    # Separate the conversational response and reflective cue.
    question, cue = extract_cue(clean_content)

    mascot = get_mascot()
    cue_html = build_cue_html(cue)

    # Keep message text on the same line as its HTML tags.
    # This prevents unintended whitespace when CSS uses
    # white-space: pre-wrap.
    st.html(f"""
        <div class="chat-row assistant-row">

            <img
                src="data:image/png;base64,{mascot}"
                class="chat-avatar"
                alt="Mirror Bot"
            />

            <div class="chat-bubble assistant-bubble">

                <div class="chat-label">Mirror Bot</div>

                <div class="chat-content">{escape(question)}</div>

                {cue_html}

            </div>

        </div>
    """)


# ============================================================
# 7. STUDENT MESSAGE COMPONENT
# ============================================================

def render_user_message(content: str) -> None:
    """
    Render a student's response in a right-aligned
    conversation bubble.

    HTML escaping ensures student-entered text is displayed
    as text rather than interpreted as HTML.
    """

    st.html(f"""
        <div class="chat-row user-row">

            <div class="chat-bubble user-bubble">

                <div class="chat-label">You</div>

                <div class="chat-content">{escape(content.strip())}</div>

            </div>

        </div>
    """)


# ============================================================
# 8. MAIN MESSAGE RENDERER
# ============================================================

def render_message(message: Dict[str, str]) -> None:
    """
    Render a conversation message using the appropriate
    component based on its role.

    Expected message structure:
        {
            "role": "assistant" or "user",
            "content": "Message text"
        }

    This is the main rendering function called by app.py.
    """

    role = message["role"]
    content = message["content"]

    if role == "assistant":
        render_assistant_message(content)

    elif role == "user":
        render_user_message(content)


# ============================================================
# 9. SCROLL MANAGEMENT
# ============================================================

def scroll_to_readiness() -> None:
    """
    Scroll the page to the reflection readiness card.

    Called when the AI first determines that sufficient
    reflective material has been gathered.

    JavaScript is maintained separately in assets/scroll.js.
    """

    script_path = ASSETS_DIR / "scroll.js"
    script = script_path.read_text(encoding="utf-8")

    st_components.html(
        f"<script>{script}</script>",
        height=0,
        width=0
    )

# ============================================================
# 10. REFLECTION JOURNEY COMPONENT
# ============================================================

def render_reflection_journey(
    progress: Dict[str, str]
) -> None:
    """
    Display rubric-informed reflection progress.

    Progress represents the domains meaningfully explored,
    rather than the number of questions answered or an
    academic assessment score.
    """

    explored_count = sum(
        progress.get(domain) == "explored"
        for domain in REFLECTION_DOMAINS
    )

    total_domains = len(REFLECTION_DOMAINS)

    percentage = explored_count / total_domains * 100

    status_icons = {
        "pending": "●",
        "exploring": "◉",
        "explored": "✓",
    }

    rows = []

    # Build an individual row for each reflective domain.
    for domain, label in REFLECTION_DOMAINS.items():

        status = progress.get(domain, "pending")

        if status not in VALID_PROGRESS_STATES:
            status = "pending"

        icon = status_icons[status]

        status_label = (
            "Exploring" if status == "exploring" else ""
        )

        rows.append(f"""
            <div class="journey-row {status}">
                <span class="journey-icon">{icon}</span>
                <span class="journey-label">{escape(label)}</span>
                <span class="journey-status">{status_label}</span>
            </div>
        """)

    # HTML progress element avoids inline CSS.
    st.html(f"""
        <div class="journey-card">

            <div class="journey-header">
                <span class="journey-title">
                    Your reflection journey
                </span>
                <span class="journey-count">
                    {explored_count} of {total_domains} explored
                </span>
            </div>

            <progress
                class="journey-progress"
                value="{percentage}"
                max="100"
                aria-label="Reflective domains explored"
            ></progress>

            <div class="journey-domains">
                {"".join(rows)}
            </div>

            <div class="journey-footer">
                ✧ Your journey adapts to your experiences
                and insights.
            </div>

        </div>
    """)