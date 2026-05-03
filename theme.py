import streamlit as st

# =========================
# 🎨 戰情室專屬調色盤庫
# =========================
THEMES = {
    "gold": {
        "bg": "#121212", "card": "#1E1E1E", "border": "#333333",
        "text": "#F8F9FA", "subtext": "#A0AEC0", "primary": "#D4AF37",
        "accent": "#5A8DEE", "green": "#2F855A", "red": "#E53E3E"
    },
    "gray": {
        "bg": "#181A1B", "card": "#242526", "border": "#3A3D41",
        "text": "#E5E7EB", "subtext": "#9CA3AF", "primary": "#9CA3AF",
        "accent": "#D1D5DB", "green": "#22C55E", "red": "#EF4444"
    },
    "navy": {
        # 🦈 全新「鯊魚腹淺藍」專屬調色盤
        "bg": "#E3EAEF",       # 鯊魚腹部的極淺灰藍色
        "card": "#F0F5F9",     # 卡片稍亮，帶有一點點水光感
        "border": "#BDCADA",   # 乾淨的鋼鐵藍灰邊框
        "text": "#1A2530",     # 深海軍藍，取代純黑，更具高階質感
        "subtext": "#6B7C8E",  # 沉穩的灰藍色副標題
        "primary": "#2D74B4",  # 經典海軍藍，作為主按鈕和高亮
        "accent": "#5FA5D9",   # 鯊魚背部的清澈亮灰藍
        "green": "#20A05D",    # 柔和不刺眼的獲利綠
        "red": "#D94848"       # 柔和不刺眼的停損紅
    },
    "milktea_tech": { 
        "bg": "#191614", "card": "#26211D", "border": "#3B342E",
        "text": "#F1E9E0", "subtext": "#8FA3B0", "primary": "#D8B08C",
        "accent": "#8FA3B0", "green": "#59C9A5", "red": "#E57373"
    },
    "milktea_light": { 
        "bg": "#F5F2ED", "card": "#FFFFFF", "border": "#E0D8D0",
        "text": "#2C2A29", "subtext": "#8A827B", "primary": "#A68A75",
        "accent": "#6C7A89", "green": "#2E8B57", "red": "#D64040"
    }
}

def apply_custom_theme(mode="navy"):
    t = THEMES.get(mode, THEMES["navy"])

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');

    /* =========================
       🌑 全局
    ========================= */
    .stApp {{ background-color: {t['bg']}; }}
    h1, h2, h3, h4, h5, h6, p, div, span, label, li {{ color: {t['text']} !important; font-family: 'Inter', sans-serif; }}
    table, [data-testid="stDataFrame"] {{ font-family: 'Roboto Mono', monospace !important; }}

    /* =========================
       🎯 高亮色 
    ========================= */
    .highlight-primary {{ color: {t['primary']} !important; font-weight: 700; }}
    .highlight-accent {{ color: {t['accent']} !important; font-weight: 700; }}
    .highlight-red {{ color: {t['red']} !important; font-weight: 700; }}
    .highlight-green {{ color: {t['green']} !important; font-weight: 700; }}
    .text-sub {{ color: {t['subtext']} !important; }}

    /* =========================
       🎛️ 強制覆蓋 Streamlit 原生元件
    ========================= */
    input[type="text"], input[type="number"], div[data-baseweb="input"] input {{
        color: {t['text']} !important;
        -webkit-text-fill-color: {t['text']} !important;
        background-color: {t['card']} !important;
    }}
    div[data-baseweb="base-input"], div[data-baseweb="select"] > div {{
        background-color: {t['card']} !important;
        border-color: {t['border']} !important;
    }}
    div[data-baseweb="select"] span {{ color: {t['text']} !important; }}
    
    div[data-baseweb="popover"], div[data-baseweb="popover"] > div, div[data-baseweb="popover"] ul {{
        background-color: {t['card']} !important;
        border-color: {t['border']} !important;
    }}
    div[data-baseweb="popover"] li {{ background-color: transparent !important; }}
    div[data-baseweb="popover"] li span {{ color: {t['text']} !important; }}
    div[data-baseweb="popover"] li:hover {{ background-color: {t['bg']} !important; }}

    div[data-testid="stAlert"] {{
        background-color: {t['card']} !important;
        border: 1px solid {t['border']} !important;
        border-left: 4px solid {t['primary']} !important; 
        color: {t['text']} !important;
    }}
    div[data-testid="stAlert"] > div {{ background-color: transparent !important; }}
    div[data-testid="stAlert"] p, div[data-testid="stAlert"] span {{ color: {t['text']} !important; }}

    [data-testid="stExpander"] details {{
        background-color: {t['card']} !important;
        border: 1px solid {t['border']} !important;
        border-radius: 8px;
    }}
    [data-testid="stExpander"] summary {{ background-color: {t['card']} !important; color: {t['text']} !important; }}
    [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span {{ color: {t['text']} !important; font-weight: 600 !important; }}
    [data-testid="stExpander"] summary svg {{ fill: {t['text']} !important; }}

    /* =========================
       📊 Tabs
    ========================= */
    .stTabs [data-baseweb="tab-list"] {{ display: flex; flex-wrap: wrap; gap: 8px; background-color: transparent; padding-bottom: 10px; }}
    .stTabs [data-baseweb="tab"] {{ flex-grow: 1; text-align: center; background-color: {t['card']}; border: 1px solid {t['border']}; color: {t['subtext']}; border-radius: 6px; padding: 8px 15px; transition: 0.2s; font-weight: 600; }}
    .stTabs [data-baseweb="tab"]:hover {{ border-color: {t['primary']}; color: {t['text']}; }}
    .stTabs [aria-selected="true"] {{ background-color: {t['card']} !important; color: {t['primary']} !important; border-bottom: 3px solid {t['primary']} !important; }}
    .stTabs [data-baseweb="tab-highlight"] {{ background-color: transparent !important; display: none !important; }}

    /* =========================
       🧾 卡片與表格
    ========================= */
    .tier-card {{ background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
    [data-testid="stDataFrame"] {{ border-radius: 8px !important; border: 1px solid {t['border']}; overflow: hidden; }}

    /* 👑 V3 核心：持股動態發光裝甲 */
    @keyframes pulse-glow {{
        0% {{ box-shadow: 0 0 5px {t['bg']}; border-color: {t['border']}; }}
        50% {{ box-shadow: 0 0 15px {t['primary']}; border-color: {t['primary']}; }}
        100% {{ box-shadow: 0 0 5px {t['bg']}; border-color: {t['border']}; }}
    }}
    .glow-s-tier {{
        animation: pulse-glow 2s infinite ease-in-out;
    }}
    .holding-card {{
        background-color: {t['card']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 15px;
        transition: 0.3s;
    }}
    .holding-card:hover {{ border-color: {t['primary']} !important; }}


    /* =========================
       🧱 永久 UI 裝甲：卡片等高、標籤保護、長名稱自適應
       這段統一放 theme.py，避免 app.py 改版時漏掉。
    ========================= */
    [data-testid="column"] > div {{
        height: 100%;
    }}
    [data-testid="column"] [data-testid="stVerticalBlock"] {{
        height: 100%;
    }}
    .tier-badge {{
        display: inline-block;
        padding: 1px 6px;
        border-radius: 3px;
        font-size: 11px;
        font-weight: 700;
        white-space: nowrap !important;
        flex-shrink: 0;
    }}
    .badge-s {{ background-color: rgba(255, 75, 75, 0.10); color: #FF4B4B !important; border: 1px solid #FF4B4B; }}
    .badge-a {{ background-color: rgba(255, 165, 0, 0.10); color: #FFA500 !important; border: 1px solid #FFA500; }}
    .tier-card {{
        background-color: {t['card']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.08);
        display: flex;
        flex-direction: column;
        box-sizing: border-box;
        margin-bottom: 12px;
        min-height: 100%;
    }}
    .stock-title {{
        margin: 0;
        font-size: clamp(15px, 1.2rem, 19px);
        line-height: 1.25;
        white-space: normal;
        word-break: break-word;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }}
    .info-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; width: 100%; }}
    .info-label {{ font-size: 13px; opacity: 0.8; white-space: nowrap; }}
    .info-value {{ font-size: 13px; font-weight: 500; text-align: right; white-space: nowrap; }}

    @media (max-width: 768px) {{
        .rwd-flex-header {{ flex-direction: column !important; align-items: flex-start !important; gap: 8px; }}
        .rwd-flex-title {{ flex-direction: column !important; gap: 4px !important; }}
        .rwd-flex-profit {{ text-align: left !important; width: 100%; border-bottom: 1px dashed {t['border']}; padding-bottom: 8px; }}
        .rwd-flex-info {{ flex-direction: column !important; gap: 8px !important; }}
        .rwd-flex-info > div {{ white-space: normal !important; }}
    }}

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
    .stButton > button:hover, .stDownloadButton > button:hover {{ background-color: {t['primary']} !important; color: {t['card']} !important; border-color: {t['primary']} !important; box-shadow: 0 0 10px {t['primary']}55 !important; }}
    #MainMenu, footer, .stDeployButton {{ display: none; }}
    [data-testid="stHeader"] {{ background: transparent; }}
    </style>
    """, unsafe_allow_html=True)
    
    return t
