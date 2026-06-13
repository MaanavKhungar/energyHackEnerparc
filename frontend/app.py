import streamlit as st
import pandas as pd
from chat_logic import render_chat_page, render_chat_sidebar
from plant_twin import render_plant_twin_page

# Page configuration
st.set_page_config(
    page_title="Watt's Wrong - Energy Assistant",
    page_icon="",
    layout="wide"
)


st.title("Watt's Wrong")
st.markdown("---")

st.sidebar.header("Navigation")
page = st.sidebar.selectbox(
    "Choose a page",
    ["Home", "Data Analysis", "Digital Twin", "Chat Assistant"]
)

# Main content based on page selection
if page == "Home":
    st.header("Welcome to Watt's Wrong!")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Users", "1,234", "12%")

    with col2:
        st.metric("Energy Saved", "45.6 kWh", "8%")

    with col3:
        st.metric("Carbon Reduced", "23.1 kg", "15%")


elif page == "Data Analysis":
    st.header("Data Analysis")

    # Sample data
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
    render_plant_twin_page()

elif page == "Chat Assistant":
    render_chat_page()

# Add chat sidebar when on chat page
if page == "Chat Assistant":
    render_chat_sidebar()