import streamlit as st
from chat_logic import render_chat_page, render_chat_sidebar
from timeline import render_timeline_page
from digital_twin import render_digital_twin_page

st.set_page_config(
    page_title="Watt's Wrong - Energy Assistant",
    page_icon="🌿",
    layout="wide"
)

st.markdown("""
<style>
/* Primary buttons — teal instead of red */
div.stButton > button[kind="primary"] {
    background-color: #1a6b5a;
    border: 1px solid #2fbf71;
    color: #e0f5ec;
    font-weight: 600;
}
div.stButton > button[kind="primary"]:hover {
    background-color: #2fbf71;
    color: #0a0f1a;
    border-color: #2fbf71;
}
/* Secondary buttons */
div.stButton > button[kind="secondary"] {
    background-color: #0e1a2e;
    border: 1px solid #2a3550;
    color: #c9d1d9;
}
div.stButton > button[kind="secondary"]:hover {
    background-color: #1a2a40;
    border-color: #4a6fa5;
}
</style>
""", unsafe_allow_html=True)

st.title("Watt's Wrong")
st.markdown("---")

st.sidebar.header("Navigation")

if st.session_state.get("nav_to_chat"):
    st.session_state["nav_to_chat"] = False
    default_page = "Chat Assistant"
else:
    default_page = "Digital Twin"

pages = ["Digital Twin", "Fault Analysis", "Chat Assistant"]
page = st.sidebar.selectbox("Choose a page", pages, index=pages.index(default_page))

if page == "Digital Twin":
    render_digital_twin_page()

elif page == "Fault Analysis":
    render_timeline_page()

elif page == "Chat Assistant":
    if "pending_chat_question" in st.session_state:
        q = st.session_state.pop("pending_chat_question")
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": q})
    render_chat_page()

if page == "Chat Assistant":
    render_chat_sidebar()
