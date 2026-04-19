import streamlit as st

def apply_custom_theme():
    st.markdown("""
    <style>
    /* 導入 Google 現代字體 (Inter 處理介面，Roboto Mono 處理數字) */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Roboto+Mono:wght@400;600&display=swap');

    /* 全局背景與字體設定 (消光炭灰) */
    .stApp { background-color: #181A1B; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, li { 
        color: #F8F9FA !important; 
        font-family: 'Inter', 'Helvetica Neue', sans-serif; 
    }
    
    /* 讓表格數字強制等寬，完美對齊小數點 */
    table, [data-testid="stDataFrame"] { 
        font-family: 'Roboto Mono', monospace !important; 
    }

    /* 奢華貴族色彩庫 (實色、無發光、低飽和沉穩色) */
    .highlight-gold { color: #D4AF37 !important; font-weight: 700; } /* 香檳金 */
    .highlight-cyan { color: #4A90E2 !important; font-weight: 700; } /* 沉靜灰藍 */
    .highlight-red { color: #E53E3E !important; font-weight: 700; }  /* 磚紅 */
    .highlight-green { color: #38A169 !important; font-weight: 700; }/* 穩重森林綠 */

    /* 分頁 (Tabs) 貴族化設計 */
    .stTabs [data-baseweb="tab-list"] { display: flex; flex-wrap: wrap; gap: 8px; background-color: transparent; padding-bottom: 10px; }
    .stTabs [data-baseweb="tab"] { 
        flex-grow: 1; text-align: center; height: auto; min-height: 45px; 
        background-color: #242729; border-radius: 6px; color: #A0AEC0; 
        border: 1px solid #3A3F44; font-size: 16px; font-weight: 600; 
        padding: 8px 15px; white-space: nowrap; transition: all 0.2s ease;
    }
    .stTabs [data-baseweb="tab"]:hover { border-color: #D4AF37; color: #F8F9FA; }
    .stTabs [aria-selected="true"] { 
        background-color: #2D3134 !important; color: #D4AF37 !important; 
        border-bottom: 3px solid #D4AF37 !important; 
    }

    /* 戰情報告卡片設計 (扁平化、微圓角) */
    .tier-card { 
        background-color: #242729; padding: 20px; border-radius: 8px; 
        border: 1px solid #3A3F44; margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); 
    }

    /* 側邊欄與表格柔化 */
    [data-testid="stSidebar"] { background-color: #141516; border-right: 1px solid #242729; }
    [data-testid="stDataFrame"] { border-radius: 8px !important; overflow: hidden; border: 1px solid #3A3F44; }

    /* =========================================
       👑 新增：三大去網頁化魔鬼細節 
       ========================================= */

    /* 1. 隱藏右上角官方標記與選單 */
    [data-testid="stHeader"] { background-color: transparent; }
    #MainMenu, .stDeployButton { display: none; }
    footer { display: none; }

    /* 2. 隱形戰術滾輪 (WebKit 專用) */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #141516; }
    ::-webkit-scrollbar-thumb { background: #3A3F44; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #D4AF37; }

    /* 3. 貴金屬按鈕設計 */
    .stButton > button, .stDownloadButton > button {
        background-color: #242729 !important; 
        color: #D4AF37 !important;
        border: 1px solid #3A3F44 !important; 
        border-radius: 6px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        border-color: #D4AF37 !important; 
        color: #181A1B !important; 
        background-color: #D4AF37 !important;
        box-shadow: 0 0 10px rgba(212, 175, 55, 0.3) !important;
    }
    </style>
    """, unsafe_allow_html=True)
