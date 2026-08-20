"""
app.py
Entry point. Port of ui.R's dashboardPage/secure_app + server.R's
sidebar_menu, built as a single-page app with a custom sidebar router
(see the "UI parity approach" section of the PRD for why: Streamlit's
native multipage nav doesn't match shinydashboard's persistent sidebar).
"""
import os

import streamlit as st

import auth
import meta
from pages_content import (
    backend_data,
    dashboard,
    export_data,
    location_status,
    master_list,
    section_form,
    user_management,
)

st.set_page_config(page_title="Block Epi Info - NTEP", layout="wide", page_icon="🩺")


def _inject_css():
    css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "custom.css")
    with open(css_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    st.markdown(
        '<link rel="stylesheet" '
        'href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">',
        unsafe_allow_html=True,
    )


_inject_css()

if not auth.is_logged_in():
    auth.login_screen()
    st.stop()

user = auth.current_user()

# ---- Top bar ----------------------------------------------------------------
tcol1, tcol2 = st.columns([6, 1])
with tcol1:
    st.markdown('<div class="app-topbar">Block Epi Info — NTEP Data Capture</div>', unsafe_allow_html=True)
with tcol2:
    st.write("")
    if st.button("Log out", key="btn_logout", width="stretch"):
        auth.logout()
        st.rerun()

if user["is_master_admin"]:
    who = "Master Admin"
else:
    parts = [p for p in (user.get("state"), user.get("district"), user.get("block")) if p]
    who = f"{user['scope_type'].title()} user — {', '.join(parts)}"
    if auth.has_dashboard_access():
        who += " (dashboard access granted)"
st.caption(f"Logged in as **{user['username']}** — {who}")

# ---- Sidebar menu (role-based, mirrors server.R's output$sidebar_menu) -----
menu_items = []
if not user["is_master_admin"]:
    menu_items.append(("loc", "Location & Status", "🧭"))
    for s in meta.SECTIONS:
        menu_items.append((f"sec_{meta.sec_id(s)}", s, "📋"))
if auth.has_dashboard_access():
    menu_items.append(("dashboard", "Admin Dashboard", "📈"))
if user["is_master_admin"]:
    menu_items.append(("master_list", "Master Location List", "🗺️"))
    menu_items.append(("backend_data", "Backend Data", "🖥️"))
if auth.has_dashboard_access():
    menu_items.append(("export", "Export Data", "📊"))
if user["is_master_admin"]:
    menu_items.append(("users", "User Management", "🔑"))

if not menu_items:
    st.warning("Your account has no accessible sections yet. Contact the master admin.")
    st.stop()

if "current_tab" not in st.session_state or st.session_state["current_tab"] not in {t for t, _, _ in menu_items}:
    st.session_state["current_tab"] = menu_items[0][0]

with st.sidebar:
    st.markdown("### Block Epi Info")
    for tab_id, label, icon in menu_items:
        active = st.session_state["current_tab"] == tab_id
        st.markdown(f'<div class="{"nav-active" if active else ""}">', unsafe_allow_html=True)
        if st.button(f"{icon}  {label}", key=f"nav_{tab_id}", width="stretch"):
            st.session_state["current_tab"] = tab_id
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# ---- Routing ------------------------------------------------------------
tab = st.session_state["current_tab"]
_section_by_tab = {f"sec_{meta.sec_id(s)}": s for s in meta.SECTIONS}

if tab == "loc":
    location_status.render()
elif tab in _section_by_tab:
    section_form.render(_section_by_tab[tab])
elif tab == "dashboard":
    dashboard.render()
elif tab == "master_list":
    master_list.render()
elif tab == "backend_data":
    backend_data.render()
elif tab == "export":
    export_data.render()
elif tab == "users":
    user_management.render()
