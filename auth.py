# -*- coding: utf-8 -*-
"""
auth.py — 登入門禁（從 app.py 抽出）

安全性改進：
1. 移除硬編碼密碼 fallback。密碼必須設定在 st.secrets 或環境變數：
   - st.secrets["admin_pwd"] / 環境變數 ADMIN_PWD
   - st.secrets["guest_pwd"] / 環境變數 GUEST_PWD
2. 未設定密碼時直接顯示設定教學並停止，而不是用預設密碼放行。

Streamlit Cloud 設定方式：App settings → Secrets 貼上：
    admin_pwd = "你的統帥密碼"
    guest_pwd = "你的友軍密碼"
    fm_token  = "你的FinMind token"

本機開發可在專案根目錄建立 .streamlit/secrets.toml（記得加入 .gitignore）。
"""

import os
import time

import streamlit as st


def _get_secret(key: str, env_key: str) -> str:
    try:
        val = st.secrets.get(key, "")
    except Exception:
        val = ""
    if not val:
        val = os.environ.get(env_key, "")
    return str(val).strip()


def get_fm_token() -> str:
    return _get_secret("fm_token", "FM_TOKEN")


def ensure_authenticated():
    """回傳 (auth_status, controller)。未通過驗證時會自行 st.stop()。"""
    admin_pwd = _get_secret("admin_pwd", "ADMIN_PWD")
    guest_pwd = _get_secret("guest_pwd", "GUEST_PWD")

    controller = None
    auth_status = st.session_state.get("v3_auth_token", None)
    try:
        from streamlit_cookies_controller import CookieController
        controller = CookieController()
        try:
            cookie_val = controller.get("v3_auth_token")
            if cookie_val:
                auth_status = cookie_val
        except Exception:
            pass
    except Exception:
        controller = None

    if auth_status in ["admin_auth", "guest_auth"]:
        return auth_status, controller

    st.markdown("<h1 style='text-align: center; margin-top: 100px;'>🔒 終極戰情室 - 軍事管制區</h1>", unsafe_allow_html=True)

    if not admin_pwd and not guest_pwd:
        st.error(
            "⚠️ 尚未設定通行密碼。請在 Streamlit Secrets 或環境變數中設定 "
            "`admin_pwd` / `guest_pwd` 後重新啟動。\n\n"
            "（安全性更新：系統已移除內建預設密碼，避免原始碼外流時門禁失效。）"
        )
        st.stop()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("請輸入通行密碼：", type="password", placeholder="輸入密碼後按下 Enter 或點擊解鎖")
        if st.button("🔓 驗證並解鎖", use_container_width=True) or pwd:
            if admin_pwd and pwd == admin_pwd:
                _grant(controller, "admin_auth", "✅ 統帥確認：...正在為您開啟專屬戰情室...")
            elif guest_pwd and pwd == guest_pwd:
                _grant(controller, "guest_auth", "✅ 友軍確認：...正在開啟系統...")
            elif pwd != "":
                st.error("❌ 密碼錯誤！防禦系統已啟動。")
    st.stop()


def _grant(controller, token: str, msg: str):
    st.session_state["v3_auth_token"] = token
    try:
        if controller is not None:
            controller.set("v3_auth_token", token, max_age=2592000)
    except Exception:
        pass
    st.success(msg)
    time.sleep(1.2)
    st.rerun()
