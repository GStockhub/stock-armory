import streamlit as st

# =========================
# 🎨 戰情室專屬調色盤庫
# =========================
THEMES = {
    # 👑 黑金專業盤手 (原方案 C 進化)
    "gold": {
        "bg": "#181A1B",
        "card": "#232629",
        "border": "#3A3F44",
        "text": "#F8F9FA",
        "subtext": "#A0AEC0",
        "primary": "#D4AF37", # 主色金
        "accent": "#5A8DEE",  # 輔色藍
        "green": "#2F855A",
        "red": "#E53E3E"
    },
    # 🧘 極簡灰 (冷靜理智)
    "gray": {
        "bg": "#1E1F22",
        "card": "#2A2D31",
        "border": "#3A3F44",
        "text": "#E5E7EB",
        "subtext": "#9CA3AF",
        "primary": "#9CA3AF", # 主色灰
        "accent": "#D1D5DB",  # 輔色亮灰
        "green": "#22C55E",
        "red": "#EF4444"
    },
    # 🌊 深海藍 (暗黑量化神殿)
    "ocean": {
        "bg": "#0B132B",
        "card": "#1C2541",
        "border": "#2C3A5A",
        "text": "#E0E6F1",
        "subtext": "#9FB3C8",
        "primary": "#5BC0BE", # 主色海藍
        "accent": "#CDE7F0",  # 輔色冰藍
        "green": "#6FFFB0",
        "red": "#FF6B6B"
    }
}

def apply_custom_theme(mode="ocean"):
    # 抓取選擇的主題，找不到就預設 ocean
    t = THEMES.get(mode, THEMES["ocean"])

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
       🎯 高亮色 (配合 GPT 改名 primary/accent)
    ========================= */
    .highlight-primary {{ color: {t['primary']} !important; font-weight: 700; }}
    .highlight-accent {{ color: {t['accent']} !important; font-weight: 700; }}
    .highlight-red {{ color: {t['red']} !important; font-weight: 700; }}
    .highlight-green {{ color: {t['green']} !important; font-weight: 700; }}
    .text-sub {{ color: {t['subtext']} !important; }}

    /* =========================
       📊 Tabs
    ========================= */
    .stTabs [data-baseweb="tab-list"] {{ gap: 8px; background-color: transparent; padding-bottom: 10px; }}
    .stTabs [data-baseweb="tab"] {{
        background-color: {t['card']};
        border: 1px solid {t['border']};
        color: {t['subtext']};
        border-radius: 6px;
        padding: 8px 15px;
        transition: 0.2s;
        font-weight: 600;
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
       🧾 卡片與表格
    ========================= */
    .tier-card {{
        background-color: {t['card']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }}
    [data-testid="stDataFrame"] {{
        border-radius: 8px !important;
        border: 1px solid {t['border']};
        overflow: hidden;
    }}

    /* =========================
       📌 Sidebar & 滾輪
    ========================= */
    [data-testid="stSidebar"] {{
        background-color: {t['bg']};
        border-right: 1px solid {t['border']};
    }}
    ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    ::-webkit-scrollbar-track {{ background: {t['bg']}; }}
    ::-webkit-scrollbar-thumb {{ background: {t['border']}; border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: {t['primary']}; }}

    /* =========================
       🎯 按鈕與清理
    ========================= */
    .stButton > button, .stDownloadButton > button {{
        background-color: {t['card']} !important;
        color: {t['primary']} !important;
        border: 1px solid {t['border']} !important;
        border-radius: 6px;
        font-weight: 600 !important;
        transition: 0.3s;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        background-color: {t['primary']} !important;
        color: {t['bg']} !important;
        border-color: {t['primary']} !important;
        box-shadow: 0 0 10px {t['primary']}55 !important;
    }}
    #MainMenu, footer, .stDeployButton {{ display: none; }}
    [data-testid="stHeader"] {{ background: transparent; }}
    </style>
    """, unsafe_allow_html=True)
    
    # 👑 關鍵：回傳當前選定的顏色字典，給 app.py 畫表格用！
    return t
