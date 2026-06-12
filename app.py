"""
Plant A Energy Chatbot — Streamlit UI
======================================
Run:  streamlit run app.py

RAG teammate integration:
    Once your RAG pipeline is ready, update retrieve_handbook() in chat.py.
    No changes needed here.
"""

import streamlit as st
from chat import PlantAChatbot

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Plant A — Energy Chatbot",
    page_icon="🌞",
    layout="centered",
)

st.title("🌞 Plant A Energy Chatbot")
st.caption("Powered by EnerParc data · Claude claude-opus-4-8 · Ask anything about Plant A")

# ── Session state ──────────────────────────────────────────────────────────────
if "bot" not in st.session_state:
    st.session_state.bot = PlantAChatbot()

if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role": "user"|"assistant", "content": str}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Plant A")
    st.markdown("""
    **Capacity:** 1,897 kWp
    **Inverters:** 65
    **Data:** 2017 → 2026
    **Tariff:** ~11.5–40 ct/kWh
    """)

    st.divider()
    st.markdown("**Try asking:**")
    example_questions = [
        "Which inverters broke most in 2023?",
        "What were the major outages in 2021?",
        "What does error code 0A0003 mean?",
        "What was the revenue loss from grid faults?",
        "Show the error trend for INV 01.09.062",
    ]
    for q in example_questions:
        if st.button(q, use_container_width=True):
            st.session_state.pending_question = q

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.bot.reset()
        st.session_state.messages = []
        st.rerun()

# ── Chat history ───────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Handle sidebar button click ────────────────────────────────────────────────
if "pending_question" in st.session_state:
    question = st.session_state.pop("pending_question")
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Analysing plant data..."):
            answer = st.session_state.bot.chat(question, verbose=False)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.rerun()

# ── Chat input ─────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask about Plant A..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analysing plant data..."):
            answer = st.session_state.bot.chat(prompt, verbose=False)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.rerun()
