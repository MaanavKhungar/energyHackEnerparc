import streamlit as st
import pandas as pd
from chat_logic import render_chat_page, render_chat_sidebar
from plant_twin import render_plant_twin_page
from timeline import render_timeline_page
from digital_twin import render_digital_twin_page

st.set_page_config(
    page_title="Watt's Wrong - Energy Assistant",
    page_icon="🌿",
    layout="wide"
)

st.title("Watt's Wrong")
st.markdown("---")

st.sidebar.header("Navigation")

# Auto-navigate to chat if digital twin queued a question
if st.session_state.get("nav_to_chat"):
    st.session_state["nav_to_chat"] = False
    default_page = "Chat Assistant"
else:
    default_page = "Home"

pages = ["Home", "Data Analysis", "Digital Twin", "Fault Timeline", "Chat Assistant"]
page = st.sidebar.selectbox("Choose a page", pages,
                            index=pages.index(default_page))

if page == "Home":
    st.header("Welcome to Watt's Wrong!")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Capacity", "1,897 kWp")
    with col2:
        st.metric("Inverters", "65")
    with col3:
        st.metric("Data Since", "2017")

elif page == "Data Analysis":
    st.header("Data Analysis")
    data = pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=30, freq='D'),
        'Energy Usage': [100 + i*2 + (i%7)*10 for i in range(30)],
        'Cost': [50 + i*1.5 + (i%5)*5 for i in range(30)]
    })
    st.subheader("Energy Usage Data")
    st.dataframe(data, use_container_width=True)
    st.subheader("Upload Your Data")
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.write(df)

elif page == "Digital Twin":
    render_digital_twin_page()

elif page == "Fault Timeline":
    render_timeline_page()

elif page == "Chat Assistant":
    # Pick up pre-loaded question from digital twin
    if "pending_chat_question" in st.session_state:
        q = st.session_state.pop("pending_chat_question")
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": q})
    render_chat_page()

if page == "Chat Assistant":
    render_chat_sidebar()
