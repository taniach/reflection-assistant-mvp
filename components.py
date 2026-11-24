import streamlit as st
import re

from html import escape
from pathlib import Path
from base64 import b64encode


ASSETS = Path(__file__).parent / "assets"


def get_mascot():
    return b64encode(
        (ASSETS / "mascot.png").read_bytes()
    ).decode("utf-8")


def extract_cue(content):
    if "[CUE]" in content:
        question, cue = content.split("[CUE]", 1)
        return question.strip(), cue.strip()

    # Handle AI responses using [Reflective cue]
    match = re.search(r"\[([^\[\]\n]+)\]\s*$", content)

    if match:
        question = content[:match.start()].strip()
        return question, match.group(1).strip()

    return content, ""


def render_message(message):
    role = message["role"]
    content = message["content"]

    if role == "assistant":
        question, cue = extract_cue(content)
        mascot = get_mascot()

        cue_html = ""

        if cue:
            cue_html = f"""
                <div class="reflective-cue">
                    <span class="cue-icon">✧</span>
                    {escape(cue)}
                </div>
            """

        st.html(f"""
            <div class="chat-row assistant-row">
                <img
                    src="data:image/png;base64,{mascot}"
                    class="chat-avatar"
                    alt="Reflection Assistant"
                />
                <div class="chat-bubble assistant-bubble">
                    <div class="chat-label">
                        Reflection Assistant
                    </div>
                    <div class="chat-content">{escape(question.strip())}</div>
                    {cue_html}
                </div>
            </div>
        """)

    elif role == "user":
        st.html(f"""
            <div class="chat-row user-row">
                <div class="chat-bubble user-bubble">
                    <div class="chat-label">You</div>
                    <div class="chat-content">{escape(content.strip())}</div>
                </div>
            </div>
        """)