import streamlit as st

# =========================
# 🎨 戰情室專屬調色盤庫
# =========================
THEMES = {
    "gold": { # 👑 黑金專業盤手
        "bg": "#121212", "card": "#1E1E1E", "border": "#333333",
        "text": "#F8F9FA", "subtext": "#A0AEC0", "primary": "#D4AF37",
        "accent": "#5A8DEE", "green": "#2F855A", "red": "#E53E3E"
    },
    "gray": { # 🧘 極簡灰 (冷靜)
        "bg": "#181A1B", "card": "#242526", "border": "#3A3D41",
        "text": "#E5E7EB", "subtext": "#9CA3AF", "primary": "#9CA3AF",
        "accent": "#D1D5DB", "green": "#22C55E", "red": "#EF4444"
    },
    "navy": { # 🦈 鯊魚海軍藍 (藍灰質感，絕非藍屏)
        "bg": "#0D1117", "card": "#161B22", "border": "#30363D",
        "text": "#C9D1D9", "subtext": "#8B949E", "primary": "#58A6FF",
        "accent": "#79C0FF", "green": "#3FB950", "red": "#FF7B72"
    },
    "milktea_tech": { # ☕ 奶茶科技 (量化溫暖)
        "bg": "#191614", "card": "#26211D", "border": "#3B342E",
        "text": "#F1E9E0", "subtext": "#8FA3B0", "primary": "#D8B08C",
        "accent": "#8FA3B0", "green": "#59C9A5", "red": "#E57373"
    },
    "milktea_light": { # ☀️ 奶茶極簡 (日戰護目鏡)
        "bg": "#F5F2ED", "card": "#FFFFFF", "border": "#E0D8D0",
        "text": "#2C2A29", "subtext": "#8A827B", "primary": "#A68A75",
        "accent": "#D1C7BD", "green": "#2E8B57", "red": "#D64040"
    }
}

def apply_custom_theme(mode="navy"):
    t = THEMES.get(mode, THEMES["navy"])

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');

    /* =========================
       🌑 全局背景與字體
    ========================= */
    .stApp {{ background-color: {t['bg']}; }}
    h1, h2, h3, h4, h5, h6, p, div, span, label, li {{ color: {t['text']} !important; font-family: 'Inter', sans-serif; }}

    /* =========================
       🎯 戰術高亮色 
    ========================= */
    .highlight-primary {{ color: {t['primary']} !important; font-weight: 700; }}
    .highlight-accent {{ color: {t['accent']} !important; font-weight: 700; }}
    .highlight-red {{ color: {t['red']} !important; font-weight: 700; }}
    .highlight-green {{ color: {t['green']} !important; font-weight: 700; }}
    .text-sub {{ color: {t['subtext']} !important; }}

    /* =========================
       🎛️ 強制覆蓋：終極防瞎眼裝甲 (修復輸入框白底白字)
    ========================= */
    /* 輸入框本體 */
    input[type="text"], input[type="number"], div[data-baseweb="input"] input {{
        color: {t['text']} !important;
        -webkit-text-fill-color: {t['text']} !important; /* 強制 Chrome 渲染字體顏色 */
        background-color: {t['card']} !important;
    }}
    /* 輸入框外框與下拉選單 */
    div[data-baseweb="base-input"], div[data-baseweb="select"] > div {{
        background-color: {t['card']} !important;
        border-color: {t['border']} !important;
    }}
    /* 下拉選單的文字 */
    div[data-baseweb="select"] span {{ color: {t['text']} !important; }}
    /* 彈出選單底色 */
    div[data-baseweb="popover"] {{ background-color: {t['card']} !important; border: 1px solid {t['border']} !important; }}
    ul[role="listbox"] li {{ background-color: {t['card']} !important; color: {t['text']} !important; }}
    /* 提示框 (st.info / st.warning) 去除原本的藍黃色 */
    div[data-testid="stAlert"] {{
        background-color: {t['card']} !important; 
        border: 1px solid {t['primary']} !important; 
        color: {t['text']} !important; 
    }}

    /* =========================
       📊 Tabs 分頁自適應
    ========================= */
    .stTabs [data-baseweb="tab-list"] {{ display: flex; flex-wrap: wrap; gap: 8px; background-color: transparent; padding-bottom: 10px; }}
    .stTabs [data-baseweb="tab"] {{ flex-grow: 1; text-align: center; background-color: {t['card']}; border: 1px solid {t['border']}; color: {t['subtext']}; border-radius: 6px; padding: 8px 15px; transition: 0.2s; font-weight: 600; }}
    .stTabs [data-baseweb="tab"]:hover {{ border-color: {t['primary']}; color: {t['text']}; }}
    .stTabs [aria-selected="true"] {{ background-color: {t['card']} !important; color: {t['primary']} !important; border-bottom: 3px solid {t['primary']} !important; }}
    .stTabs [data-baseweb="tab-highlight"] {{ display: none; }}

    /* =========================
       🧾 卡片與表格
    ========================= */
    .tier-card {{ background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
    [data-testid="stDataFrame"] {{ border-radius: 8px !important; border: 1px solid {t['border']}; overflow: hidden; }}

    /* =========================
       📌 Sidebar & 滾輪
    ========================= */
    [data-testid="stSidebar"] {{ background-color: {t['bg']}; border-right: 1px solid {t['border']}; }}
    ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    ::-webkit-scrollbar-track {{ background: {t['bg']}; }}
    ::-webkit-scrollbar-thumb {{ background: {t['border']}; border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: {t['primary']}; }}

    /* =========================
       🎯 按鈕與清理
    ========================= */
    .stButton > button, .stDownloadButton > button {{ background-color: {t['card']} !important; color: {t['primary']} !important; border: 1px solid {t['border']} !important; border-radius: 6px; font-weight: 600 !important; transition: 0.3s; }}
    .stButton > button:hover, .stDownloadButton > button:hover {{ background-color: {t['primary']} !important; color: {t['bg']} !important; border-color: {t['primary']} !important; box-shadow: 0 0 10px {t['primary']}55 !important; }}
    #MainMenu, footer, .stDeployButton {{ display: none; }}
    [data-testid="stHeader"] {{ background: transparent; }}
    </style>
    """, unsafe_allow_html=True)
    
    return t
