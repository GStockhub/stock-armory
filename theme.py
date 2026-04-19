import streamlit as st

# ==============================================================================
# 👑 戰情室專屬調色盤：暗黑量化神殿 (改顏色只要改這裡，全軍連動！)
# ==============================================================================
COLORS = {
    "bg_main": "#121417",    # 深灰黑 (背景)
    "bg_card": "#1C1F23",    # 卡片底色
    "border": "#2A2F35",     # 邊框色
    "gold": "#C9A227",       # 主色金 (降飽和高級金)
    "cyan": "#3A7CA5",       # 冷靜藍
    "red": "#C53030",        # 失敗紅 / 警示
    "green": "#2F855A",      # 成功綠 / 安全
    "text_main": "#E8EAED",  # 主文字白
    "text_sub": "#8B949E",   # 次文字灰
    "sidebar": "#0E1013"     # 側邊欄更深
}

def apply_custom_theme():
    # 注意：這裡的 CSS 直接讀取 COLORS 字典，實現 100% 參數化
    st.markdown(f"""
    <style>
    /* 導入 Google 現代字體 (Inter 處理介面，Roboto Mono 處理數字) */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Roboto+Mono:wght@400;600&display=swap');

    /* 全局背景與字體設定 */
    .stApp {{ background-color: {COLORS['bg_main']}; }}
    h1, h2, h3, h4, h5, h6, p, div, span, label, li {{ 
        color: {COLORS['text_main']} !important; 
        font-family: 'Inter', 'Helvetica Neue', sans-serif; 
    }}
    
    /* 讓表格數字強制等寬，完美對齊小數點 */
    table, [data-testid="stDataFrame"] {{ 
        font-family: 'Roboto Mono', monospace !important; 
    }}

    /* 👑 全局戰術文字類別 (讓 Python 可以直接用 class 呼叫) */
    .highlight-gold {{ color: {COLORS['gold']} !important; font-weight: 700; }}
    .highlight-cyan {{ color: {COLORS['cyan']} !important; font-weight: 700; }}
    .highlight-red  {{ color: {COLORS['red']} !important; font-weight: 700; }}
    .highlight-green{{ color: {COLORS['green']} !important; font-weight: 700; }}
    .text-sub {{ color: {COLORS['text_sub']} !important; }}

    /* 分頁 (Tabs) 戰術化設計 */
    .stTabs [data-baseweb="tab-list"] {{ display: flex; flex-wrap: wrap; gap: 8px; background-color: transparent; padding-bottom: 10px; }}
    .stTabs [data-baseweb="tab"] {{ 
        flex-grow: 1; text-align: center; height: auto; min-height: 45px; 
        background-color: {COLORS['bg_card']}; border-radius: 6px; color: {COLORS['text_sub']}; 
        border: 1px solid {COLORS['border']}; font-size: 16px; font-weight: 600; 
        padding: 8px 15px; white-space: nowrap; transition: all 0.2s ease;
    }}
    .stTabs [data-baseweb="tab"]:hover {{ border-color: {COLORS['gold']}; color: {COLORS['text_main']}; }}
    .stTabs [aria-selected="true"] {{ 
        background-color: {COLORS['border']} !important; color: {COLORS['gold']} !important; 
        border-bottom: 3px solid {COLORS['gold']} !important; 
    }}

    /* 戰情報告卡片設計 */
    .tier-card {{ 
        background-color: {COLORS['bg_card']}; padding: 20px; border-radius: 8px; 
        border: 1px solid {COLORS['border']}; margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2); 
    }}

    /* 側邊欄與表格柔化 */
    [data-testid="stSidebar"] {{ background-color: {COLORS['sidebar']}; border-right: 1px solid {COLORS['bg_card']}; }}
    [data-testid="stDataFrame"] {{ border-radius: 8px !important; overflow: hidden; border: 1px solid {COLORS['border']}; }}

    /* =========================================
       🥷 三大去網頁化魔鬼細節 
       ========================================= */

    /* 1. 隱藏右上角官方標記與選單 */
    [data-testid="stHeader"] {{ background-color: transparent; }}
    #MainMenu, .stDeployButton {{ display: none; }}
    footer {{ display: none; }}

    /* 2. 隱形戰術滾輪 */
    ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    ::-webkit-scrollbar-track {{ background: {COLORS['bg_main']}; }}
    ::-webkit-scrollbar-thumb {{ background: {COLORS['border']}; border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: {COLORS['gold']}; }}

    /* 3. 貴金屬按鈕設計 */
    .stButton > button, .stDownloadButton > button {{
        background-color: {COLORS['bg_card']} !important; 
        color: {COLORS['gold']} !important;
        border: 1px solid {COLORS['border']} !important; 
        border-radius: 6px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        border-color: {COLORS['gold']} !important; 
        color: {COLORS['bg_main']} !important; 
        background-color: {COLORS['gold']} !important;
        box-shadow: 0 0 10px rgba(201, 162, 39, 0.3) !important;
    }}
    </style>
    """, unsafe_allow_html=True)
