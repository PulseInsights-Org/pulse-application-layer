import time
import os

import requests
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

API_BASE_URL = os.getenv("PULSE_API_BASE_URL", "http://127.0.0.1:8000")
API_URL = f"{API_BASE_URL.rstrip('/')}/api/query"
ORG_NAME = os.getenv("X_ORG_NAME", "pulse-dev")

st.set_page_config(
    page_title="Pulse Chat UI",
    layout="centered",
)

# --- Basic Styling ---
st.markdown(
    """
    <style>
    /* App background */
    .stApp {
        background-color: #020617;
    }

    .pulse-container {
        max-width: 780px;
        margin: 1.8rem auto 1.6rem;
    }
    .pulse-chat {
        background-color: #020617;
        border-radius: 1.25rem;
        padding: 0.9rem 1.5rem 1.0rem;
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.18);
    }
    .pulse-header {
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 0.15rem;
        color: #e5e7eb;
    }
    .pulse-subtitle {
        display: none;
    }
    .msg-list {
        display: flex;
        flex-direction: column;
        gap: 0.55rem;
        margin-bottom: 0.8rem;
    }
    .msg-row {
        display: flex;
        width: 100%;
    }
    .msg-row-user {
        justify-content: flex-end;
    }
    .msg-row-assistant {
        justify-content: flex-start;
    }
    .msg-bubble {
        max-width: 82%;
        padding: 0.65rem 0.9rem;
        border-radius: 0.9rem;
        font-size: 0.93rem;
    }
    .msg-user {
        background-color: #1d4ed8;
        color: #f9fafb;
        border-bottom-right-radius: 0.25rem;
    }
    .msg-assistant {
        background-color: #020617;
        border: 1px solid #1f2937;
        color: #e5e7eb;
        border-bottom-left-radius: 0.25rem;
    }
    .msg-role {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #9ca3af;
        margin-bottom: 0.1rem;
    }
    .msg-text {
        line-height: 1.4;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []  # Each item: {"role": "user"|"assistant", "content": str}


def call_backend(question: str) -> str:
    """Call FastAPI /api/query and return the model's text response.

    Expects backend to respond with JSON: {"response": <str>, ...}.
    """
    try:
        resp = requests.post(
            API_URL,
            json={"question": question},
            headers={"x-org-name": ORG_NAME},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "") or "(Empty response from model)"
    except Exception as exc:
        return f"Error contacting backend: {exc}"


# --- Layout ---
with st.container():
    st.markdown('<div class="pulse-container"><div class="pulse-chat">', unsafe_allow_html=True)
    st.markdown('<div class="pulse-header">PulseLive Assistant</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pulse-subtitle"></div>',
        unsafe_allow_html=True,
    )

    # Render chat history
    st.markdown('<div class="msg-list">', unsafe_allow_html=True)
    for msg in st.session_state.messages:
        role = msg["role"]
        is_user = role == "user"
        row_cls = "msg-row msg-row-user" if is_user else "msg-row msg-row-assistant"
        bubble_cls = "msg-bubble msg-user" if is_user else "msg-bubble msg-assistant"
        label = "You" if is_user else "Assistant"
        st.markdown(
            f'<div class="{row_cls}"><div class="{bubble_cls}"><div class="msg-role">{label}</div>'
            f'<div class="msg-text">{msg["content"]}</div></div></div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # Input area embedded in the card
    with st.form("pulse-chat-input", clear_on_submit=True):
        user_input = st.text_input("", "", placeholder="Type your question and press Enter", label_visibility="collapsed")
        submitted = st.form_submit_button("Send")

    if submitted and user_input:
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": user_input})

        with st.spinner("Contacting model..."):
            answer = call_backend(user_input)

        # Simulated streaming of the text response for a smoother feel
        placeholder = st.empty()
        streamed = ""
        for ch in answer:
            streamed += ch
            placeholder.markdown(
                '<div class="msg-list">'
                f'<div class="msg-row msg-row-assistant"><div class="msg-bubble msg-assistant">'
                '<div class="msg-role">Assistant</div>'
                f'<div class="msg-text">{streamed}</div></div></div></div>',
                unsafe_allow_html=True,
            )
            time.sleep(0.01)

        # Store final assistant message and refresh so history renders cleanly
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

    st.markdown("</div></div>", unsafe_allow_html=True)
