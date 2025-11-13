# pages/auth.py
import streamlit as st


def render_auth():
    st.header("🔐 Sign in / Sign up")
    st.caption("Authenticate to access the Finsights 10-K chatbot.")

    mode = st.radio("Mode", ["Sign in", "Create account"], horizontal=True)

    with st.form(key="auth_form"):
        email = st.text_input("Work email", placeholder="you@fund.com")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Continue")

    if submitted:
        if not email or not password:
            st.error("Please enter both email and password.")
            return

        # TODO: replace with real backend calls
        if mode == "Create account":
            st.success("Account created (demo). You are now signed in.")
        else:
            st.success("Signed in successfully (demo).")

        st.session_state.is_authenticated = True
        st.session_state.user_email = email

    st.markdown("---")
    st.info(
        "In production, call your backend’s `/signup` and `/login` endpoints, "
        "store tokens securely, and reuse them for the Q&A API."
    )
