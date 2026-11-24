
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


# ============================================================
# 11. FEEDBACK RESPONSE PROCESSING
# ============================================================

def parse_feedback(content: str) -> Dict:
    """
    Parse and validate the AI's structured feedback.

    Supports plain JSON and JSON enclosed in Markdown
    code fences.

    Returns an empty dictionary if the response is invalid,
    allowing the application to display a fallback.
    """

    if not isinstance(content, str):
        return {}

    try:

        # Remove optional Markdown code fences.
        content = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            content.strip(),
            flags=re.IGNORECASE
        )

        feedback = json.loads(content)

        if not isinstance(feedback, dict):
            return {}

        # Validate reflective themes.
        themes = feedback.get("themes")

        if not isinstance(themes, list):
            return {}

        if not all(
            isinstance(theme, str)
            for theme in themes
        ):
            return {}

        # Validate central insight.
        if not isinstance(
            feedback.get("central_insight"), str
        ):
            return {}

        # Validate strengths and growth areas.
        for field, text_key in (
            ("strengths", "description"),
            ("growth_areas", "question"),
        ):

            items = feedback.get(field)

            if not isinstance(items, list):
                return {}

            if not all(
                isinstance(item, dict)
                and isinstance(item.get("title"), str)
                and isinstance(item.get(text_key), str)
                for item in items
            ):
                return {}

        return feedback

    except (json.JSONDecodeError, TypeError, AttributeError):

        return {}


# ============================================================
# 12. REFLECTION COMPLETION BANNER
# ============================================================

def render_completion_banner() -> None:
    """
    Celebrate the student's reflective journey without
    implying a formal assessment result.
    """

    mascot = get_mascot()

    st.html(f"""
        <div class="completion-banner">

            <div class="completion-content">

                <div class="completion-label">
                    ✓ REFLECTION COMPLETE
                </div>

                <div class="completion-title">
                    A moment of growth.
                </div>

                <div class="completion-description">
                    You've taken time to explore your
                    experiences, consider your perspectives
                    and reflect on the physician you
                    are becoming.
                </div>

            </div>

            <img
                src="data:image/png;base64,{mascot}"
                class="completion-mascot"
                alt="Mirror Bot mascot"
            />

        </div>
    """)


# ============================================================
# 13. SUMMARY ICONS AND SHARED COMPONENTS
# ============================================================

SUMMARY_ICONS = {

    "sparkles": """
        <path d="M12 3L14.5 9.5L21 12L14.5 14.5
                 L12 21L9.5 14.5L3 12L9.5 9.5Z"/>
        <path d="M5 3V7M3 5H7M19 17V21M17 19H21"/>
    """,

    "sprout": """
        <path d="M12 22V12"/>
        <path d="M12 12C5 12 3 8 3 3
                 C9 3 12 6 12 12Z"/>
        <path d="M12 16C12 9 16 6 22 6
                 C22 12 18 16 12 16Z"/>
        <path d="M5 22H19"/>
    """,

    "lightbulb": """
        <path d="M9 18H15M10 22H14"/>
        <path d="M8 14C5 12 4 10 5 7
                 C7 0 17 0 19 7
                 C20 10 19 12 16 14
                 L15 18H9Z"/>
    """,

    "heart": """
        <path d="M20.8 4.6
                 C18.5 2.3 14.5 3.2 12 6
                 C9.5 3.2 5.5 2.3 3.2 4.6
                 C-1 9 5 15 12 21
                 C19 15 25 9 20.8 4.6Z"/>
    """,

    "check": """
        <circle cx="12" cy="12" r="9"/>
        <path d="M8 12L11 15L16 9"/>
    """,

    "users": """
        <circle cx="9" cy="7" r="3"/>
        <path d="M2 21V18A7 7 0 0 1 16 18V21"/>
        <path d="M17 4A3 3 0 0 1 17 10"/>
        <path d="M18 14C21 15 22 17 22 21"/>
    """,

    "growth": """
        <path d="M3 18L10 11L14 15L21 5"/>
        <path d="M15 5H21V11"/>
    """,
}


def summary_icon(name: str) -> str:
    """
    Render an SVG icon as a Base64-encoded image.

    This avoids issues with Streamlit sanitising
    inline SVG markup.
    """

    paths = SUMMARY_ICONS.get(
        name,
        SUMMARY_ICONS["sparkles"]
    )

    svg = f"""
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            width="24"
            height="24"
            fill="none"
            stroke="#000000"
            stroke-width="1.7"
            stroke-linecap="round"
            stroke-linejoin="round"
        >
            {paths}
        </svg>
    """

    encoded = b64encode(
        svg.encode("utf-8")
    ).decode("utf-8")

    return f"""
        <img
            src="data:image/svg+xml;base64,{encoded}"
            class="summary-svg-icon"
            alt=""
        />
    """


def build_feedback_header(
    icon: str,
    title: str,
    subtitle: str
) -> str:
    """
    Build a consistent heading for each summary card.
    """

    return f"""
        <div class="feedback-header">

            <div class="feedback-icon">
                {summary_icon(icon)}
            </div>

            <div class="feedback-heading">

                <div class="feedback-title">
                    {escape(title)}
                </div>

                <div class="feedback-subtitle">
                    {escape(subtitle)}
                </div>

            </div>

        </div>
    """

# ============================================================
# 14. REFLECTIVE THEMES CARD
# ============================================================

def render_reflective_themes(feedback: Dict) -> None:
    """
    Display reflective themes as compact tags and
    highlight the student's central insight.
    """

    themes = feedback.get("themes", [])
    insight = feedback.get("central_insight", "")

    header = build_feedback_header(
        "sparkles",
        "Reflective themes",
        "The ideas at the heart of your experience"
    )

    tags = "".join(
        f'<span class="summary-theme-tag">'
        f'{escape(theme)}</span>'
        for theme in themes
    )

    st.html(f"""
        <div class="feedback-card summary-themes-card">

            {header}

            <div class="summary-theme-tags">
                {tags}
            </div>

            <div class="central-insight">

                <div class="insight-label">
                    YOUR CENTRAL INSIGHT
                </div>

                <div class="insight-text">
                    {escape(insight)}
                </div>

            </div>

        </div>
    """)


# ============================================================
# 15. REFLECTIVE STRENGTHS CARD
# ============================================================

def render_strengths(feedback: Dict) -> None:
    """
    Display personalised reflective strengths using
    individual cards and a soft sage-green palette.
    """

    strengths = feedback.get("strengths", [])

    header = build_feedback_header(
        "sprout",
        "Your strengths",
        "Qualities you demonstrated while reflecting"
    )

    cards = []

    icons = ["heart", "users", "growth"]

    for index, strength in enumerate(strengths):

        title = escape(strength["title"])

        description = escape(strength["description"])

        icon = icons[index % len(icons)]

        cards.append(f"""
            <div class="strength-item">

                <div class="strength-icon">
                    {summary_icon(icon)}
                </div>

                <div class="strength-content">

                    <div class="strength-title">
                        {title}
                    </div>

                    <div class="strength-description">
                        {description}
                    </div>

                </div>

                <div class="strength-check">
                    {summary_icon("check")}
                </div>

            </div>
        """)

    empty_message = """
        <div class="feedback-subtitle">
            Further reflection may help you identify
            additional personal insights and strengths.
        </div>
    """

    st.html(f"""
        <div class="feedback-card strengths-card">

            {header}

            <div class="feedback-items">
                {"".join(cards) if cards else empty_message}
            </div>

        </div>
    """)


# ============================================================
# 16. AREAS FOR FURTHER REFLECTION
# ============================================================

def render_growth_areas(feedback: Dict) -> None:
    """
    Present further reflective questions as opportunities
    for growth rather than academic deficiencies.
    """

    growth_areas = feedback.get("growth_areas", [])

    header = build_feedback_header(
        "lightbulb",
        "Areas to think more about",
        "A little curiosity can lead to meaningful growth"
    )

    cards = []

    for index, area in enumerate(growth_areas, start=1):

        title = escape(area["title"])

        question = escape(area["question"])

        cards.append(f"""
            <div class="growth-item">

                <div class="growth-item-header">

                    <span class="growth-number">
                        {index:02d}
                    </span>

                    <span class="growth-title">
                        {title}
                    </span>

                </div>

                <div class="growth-question">
                    {question}
                </div>

            </div>
        """)

    empty_message = """
        <div class="feedback-subtitle">
            You can revisit this experience whenever
            you feel ready to explore it further.
        </div>
    """

    st.html(f"""
        <div class="feedback-card growth-card">

            {header}

            <div class="feedback-items">
                {"".join(cards) if cards else empty_message}
            </div>

            <div class="growth-footer">
                You don't need to have all the answers today.
                These are ideas to carry with you.
            </div>

        </div>
    """)


# ============================================================
# 17. WELL-BEING CHECK
# ============================================================

WELLBEING_OPTIONS = {

    "Doing okay": {
        "key": "okay",
        "icon": "☺",
        "title": "Keep taking care of yourself",
        "message": (
            "Remember to make time for yourself as you "
            "continue your clinical journey."
        ),
    },

    "A bit overwhelmed": {
        "key": "overwhelmed",
        "icon": "😐",
        "title": "Give yourself some space",
        "message": (
            "Consider taking a break or speaking with "
            "someone you trust. You may also wish to "
            "reach out to Student Affairs or a faculty "
            "mentor for support."
        ),
    },

    "Not coping well": {
        "key": "distressed",
        "icon": "☹",
        "title": "Support is available to you",
        "message": (
            "Consider reaching out to Student Affairs, "
            "a faculty mentor or a qualified health "
            "professional. If you are in immediate "
            "danger, call 995 and seek emergency assistance."
        ),
    },
}


def set_wellbeing(choice: str) -> None:
    """
    Store the student's optional emotional check-in.
    """

    st.session_state.wellbeing = choice


def render_wellbeing_check() -> None:
    """
    Render an optional, non-diagnostic well-being check.

    The selection remains in session state and does not
    trigger an AI request or automatic notification.
    """

    state = st.session_state

    with st.container(key="wellbeing_card"):

        header = build_feedback_header(
            "heart",
            "Well-being check",
            "A moment to check in with yourself"
        )

        st.html(header)

        st.write(
            "Having reflected on this experience, "
            "how are you feeling now?"
        )

        columns = st.columns(3)

        for column, (label, option) in zip(
            columns,
            WELLBEING_OPTIONS.items()
        ):

            with column:

                selected = state.get("wellbeing") == label

                # The named container controls the button colour.
                container_key = f"mood_{option['key']}"

                if selected:
                    container_key += "_selected"

                with st.container(key=container_key):

                    button_label = (
                        f"{option['icon']}\n\n{label}"
                    )

                    if selected:
                        button_label += " ✓"

                    st.button(
                        button_label,
                        key=f"select_{option['key']}",
                        use_container_width=True,
                        on_click=set_wellbeing,
                        args=(label,)
                    )

        # Display guidance for the selected emotional state.
        choice = state.get("wellbeing")

        if choice in WELLBEING_OPTIONS:

            option = WELLBEING_OPTIONS[choice]

            st.html(f"""
                <div class="wellbeing-response {option['key']}">

                    <div class="wellbeing-response-title">
                        {escape(option['title'])}
                    </div>

                    <div class="wellbeing-response-message">
                        {escape(option['message'])}
                    </div>

                </div>
            """)

            st.button(
                "Clear selection",
                key="clear_wellbeing",
                on_click=set_wellbeing,
                args=(None,)
            )

        st.html("""
            <div class="wellbeing-privacy">
                ♡ Optional check-in. Your selection is
                not sent to the AI, and nobody is
                automatically notified.
            </div>
        """)


# ============================================================
# 18. REFLECTION CLOSING BANNER
# ============================================================

def render_closing_banner() -> None:
    """
    Provide a calm and encouraging ending to the
    student's reflection journey.

    Encode the SVG illustration as an image to avoid
    inline SVG sanitisation by Streamlit.
    """

    landscape_svg = """
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 240 85"
            width="240"
            height="85"
        >

            <!-- Sun -->
            <circle
                cx="155"
                cy="23"
                r="19"
                fill="#FFD36A"
            />

            <!-- Distant mountains -->
            <path
                d="M0 65 Q35 15 79 54
                   Q110 0 160 49
                   Q202 16 240 65 V85 H0Z"
                fill="#EBD5A1"
            />

            <!-- Rolling hills -->
            <path
                d="M0 72 Q45 37 90 67
                   Q142 34 184 64
                   Q218 42 240 67 V85 H0Z"
                fill="#C9D6AC"
            />

            <!-- Foreground -->
            <path
                d="M0 81 Q57 58 100 79
                   Q180 58 240 77 V85 H0Z"
                fill="#A8BC90"
            />

            <!-- Small plants -->
            <g
                stroke="#7E9B6B"
                fill="none"
                stroke-width="2"
                stroke-linecap="round"
            >
                <path d="M45 79V45"/>
                <path d="M45 59Q30 57 29 45Q40 43 45 59"/>
                <path d="M45 52Q47 39 58 39Q61 48 45 52"/>

                <path d="M194 79V50"/>
                <path d="M194 62Q179 57 182 47Q192 47 194 62"/>
            </g>

        </svg>
    """

    # Convert the illustration into a Base64 image.
    encoded_landscape = b64encode(
        landscape_svg.encode("utf-8")
    ).decode("utf-8")

    st.html(f"""
        <div class="closing-banner">

            <div class="closing-illustration">

                <img
                    src="data:image/svg+xml;base64,{encoded_landscape}"
                    class="closing-landscape"
                    alt="A peaceful landscape with rolling hills and sunshine"
                />

            </div>

            <div class="closing-title">
                Becoming a physician is a journey.
            </div>

            <div class="closing-subtitle">
                One experience, one insight,
                one reflection at a time.
            </div>

        </div>
    """)