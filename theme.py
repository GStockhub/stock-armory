import streamlit as st

def apply_custom_theme(mode="ocean"):

    # =========================
    # 🎨 主題配色定義
    # =========================
    themes = {

        # 👑 黑金專業盤手
        "gold": {
            "bg": "#181A1B",
            "card": "#232629",
            "border": "#3A3F44",
            "text": "#F8F9FA",
            "subtext": "#A0AEC0",
            "primary": "#D4AF37",
            "accent": "#5A8DEE",
            "green": "#2FBF71",
            "red": "#E5484D"
        },

        # 🧘 極簡灰（冷靜）
        "gray": {
            "bg": "#1E1F22",
            "card": "#2A2D31",
            "border": "#3A3F44",
            "text": "#E5E7EB",
            "subtext": "#9CA3AF",
            "primary": "#9CA3AF",
            "accent": "#D1D5DB",
            "green": "#22C55E",
            "red": "#EF4444"
        },

        # 🌊 深海藍（推薦🔥）
        "ocean": {
            "bg": "#0B132B",
            "card": "#1C2541",
            "border": "#2C3A5A",
            "text": "#E0E6F1",
            "subtext": "#9FB3C8",
            "primary": "#5BC0BE",
            "accent": "#CDE7F0",
            "green": "#6FFFB0",
            "red": "#FF6B6B"
        }
    }

    t = themes.get(mode, themes["ocean"])

    st.markdown(f"""
    <style>

    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Roboto+Mono:wght@400;600&display=swap');

    /* =========================
       🌑 全局
    ========================= */
    .stApp {{ background-color: {t['bg']}; }}

    h1, h2, h3, h4, h5, h6, p, div, span, label, li {{
        color: {t['text']} !important;
        font-family: 'Inter', sans-serif;
    }}

    table, [data-testid="stDataFrame"] {{
        font-family: 'Roboto Mono', monospace !important;
    }}

    /* =========================
       🎯 高亮色
    ========================= */
    .highlight-primary {{ color: {t['primary']} !important; font-weight: 700; }}
    .highlight-accent {{ color: {t['accent']} !important; font-weight: 700; }}
    .highlight-red {{ color: {t['red']} !important; font-weight: 700; }}
    .highlight-green {{ color: {t['green']} !important; font-weight: 700; }}

    /* =========================
       📊 Tabs
    ========================= */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
    }}

    .stTabs [data-baseweb="tab"] {{
        background-color: {t['card']};
        border: 1px solid {t['border']};
        color: {t['subtext']};
        border-radius: 6px;
        padding: 8px 15px;
        transition: 0.2s;
    }}

    .stTabs [data-baseweb="tab"]:hover {{
        border-color: {t['primary']};
        color: {t['text']};
    }}

    .stTabs [aria-selected="true"] {{
        background-color: {t['card']} !important;
        color: {t['primary']} !important;
        border-bottom: 3px solid {t['primary']} !important;
    }}

    /* =========================
       🧾 卡片
    ========================= */
    .tier-card {{
        background-color: {t['card']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    }}

    /* =========================
       📋 DataFrame
    ========================= */
    [data-testid="stDataFrame"] {{
        border-radius: 8px;
        border: 1px solid {t['border']};
        overflow: hidden;
    }}

    /* 盈虧強化（很重要🔥） */
    .profit {{
        color: {t['green']} !important;
        font-weight: 600;
    }}

    .loss {{
        color: {t['red']} !important;
        font-weight: 600;
    }}

    /* =========================
       📌 Sidebar
    ========================= */
    [data-testid="stSidebar"] {{
        background-color: {t['bg']};
        border-right: 1px solid {t['border']};
    }}

    /* =========================
       🎯 按鈕
    ========================= */
    .stButton > button {{
        background-color: {t['card']} !important;
        color: {t['primary']} !important;
        border: 1px solid {t['border']} !important;
        border-radius: 6px;
        transition: 0.3s;
    }}

    .stButton > button:hover {{
        background-color: {t['primary']} !important;
        color: {t['bg']} !important;
        border-color: {t['primary']} !important;
        box-shadow: 0 0 10px {t['primary']}55;
    }}

    /* =========================
       🧼 UI 清理
    ========================= */
    #MainMenu, footer, .stDeployButton {{
        display: none;
    }}

    [data-testid="stHeader"] {{
        background: transparent;
    }}

    /* =========================
       🖱️ 滾輪
    ========================= */
    ::-webkit-scrollbar {{
        width: 8px;
    }}

    ::-webkit-scrollbar-thumb {{
        background: {t['border']};
        border-radius: 4px;
    }}

    ::-webkit-scrollbar-thumb:hover {{
        background: {t['primary']};
    }}

    </style>
    """, unsafe_allow_html=True)
