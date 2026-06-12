import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from chat import PlantAChatbot


def _get_bot() -> PlantAChatbot:
    if "bot" not in st.session_state:
        st.session_state.bot = PlantAChatbot()
    return st.session_state.bot


def generate_response(prompt: str) -> str:
    return _get_bot().chat(prompt, verbose=False)


def render_chat_page():
    st.header("Watt's Wrong Assistant")
    st.markdown("Ask me anything about Plant A — faults, downtime, revenue impact, or PV engineering!")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "👋 Hello! I'm your Plant A energy analyst.\n\n"
                    "I can answer questions like:\n"
                    "- *Which inverters broke most in 2023?*\n"
                    "- *What were the major outages in 2021 and what did they cost?*\n"
                    "- *What does error code 0A0003 mean?*\n\n"
                    "What would you like to know?"
                ),
            }
        ]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask about Plant A..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Analysing plant data..."):
                response = generate_response(prompt)
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})


def render_chat_sidebar():
    st.sidebar.header("Chat Info")

    if "messages" in st.session_state:
        st.sidebar.info(f"Messages in conversation: {len(st.session_state.messages)}")

    st.sidebar.markdown("**Try asking:**")
    for q in [
        "Which inverters broke most in 2023?",
        "What were the major outages in 2021?",
        "What does error code 0A0003 mean?",
        "Revenue loss from grid faults?",
        "Error trend for INV 01.09.062",
    ]:
        if st.sidebar.button(q, use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.spinner("Thinking..."):
                answer = generate_response(q)
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("🗑️ Clear Chat History", use_container_width=True):
        _get_bot().reset()
        st.session_state.messages = [
            {"role": "assistant", "content": "👋 Hello! I'm your Plant A energy analyst. What would you like to know?"}
        ]
        st.rerun()
