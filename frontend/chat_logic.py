import streamlit as st

def generate_response(prompt):
    """Generate a response based on user input"""
    # TODO: Add your response logic here
    return f"You said: {prompt}"

def render_chat_page():
    st.header("Watt's Wrong Assistant")
    st.markdown("Ask me anything about energy efficiency, sustainability, or your data!")


    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Hello! I'm your Watt's Wrong assistant. How can I help you today?"}
        ]


    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


    if prompt := st.chat_input("Ask me about energy, sustainability, or your data..."):

        st.session_state.messages.append({"role": "user", "content": prompt})


        with st.chat_message("user"):
            st.markdown(prompt)


        with st.chat_message("assistant"):
            response = generate_response(prompt)
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})

def render_chat_sidebar():
    st.sidebar.header("Chat Info")
    if "messages" in st.session_state:
        st.sidebar.info(f"Messages in conversation: {len(st.session_state.messages)}")

    if st.sidebar.button("Clear Chat History"):
        st.session_state.messages = [
            {"role": "assistant", "content": "Hello! I'm your Watt's Wrong assistant. How can I help you today?"}
        ]
        st.rerun()