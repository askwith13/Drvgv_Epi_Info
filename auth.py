"""
auth.py
Login screen + session-state role/scope, replacing shinymanager's
secure_app()/secure_server()/check_credentials() from the R app.
"""
import streamlit as st

import db


def current_user():
    return st.session_state.get("user")


def is_logged_in() -> bool:
    return current_user() is not None


def is_master_admin() -> bool:
    u = current_user()
    return bool(u and u["is_master_admin"])


def has_dashboard_access() -> bool:
    """Master admin always has it; state/district users only if flagged;
    block users never do."""
    u = current_user()
    if not u:
        return False
    if u["is_master_admin"]:
        return True
    return u["scope_type"] in ("state", "district") and bool(u["dashboard_access"])


def scope_type() -> str | None:
    u = current_user()
    return u["scope_type"] if u else None


def logout():
    st.session_state.pop("user", None)
    st.session_state.pop("current_tab", None)


def login_screen():
    st.markdown(
        '<div class="login-wrapper"><h3 style="text-align:center;">'
        "Block Epi Info &mdash; NTEP Data Capture</h3></div>",
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        with st.container(border=True):
            st.markdown("#### Sign in")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.button("Log in", type="primary", width="stretch")
            if submitted:
                if not username or not password:
                    st.error("Enter both username and password.")
                else:
                    user = db.verify_login(username.strip(), password)
                    if user is None:
                        st.error("Invalid username/password, or this account is deactivated.")
                    else:
                        st.session_state["user"] = user
                        st.rerun()
