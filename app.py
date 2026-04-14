import streamlit as st
import pandas as pd
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

# ================= UI 視覺優化 (深灰闇黑統帥質感) =================
st.markdown("""
    <style>
    /* 設定全站深灰背景 */
    .stApp { background-color: #1E1E1E; }
    /* 設定主標題與一般字體顏色為高質感淺灰/白 */
    h1, h2, h3, h4, h5, h6, p, div, span, label, li { color: #E0E0E0 !important; }
    /* 強調色：金黃色與湖水綠 */
    .highlight-gold { color: #FFD700; font-weight: bold; }
    .highlight-cyan { color: #00FFFF; font-weight: bold; }
    /* 調整表格字體與背景顏色 */
    .dataframe { color: #FFFFFF !important; }
    [data-testid="stDataFrame"] { background-color: #2D2D2D; border-radius: 10px; padding: 10px; }
    /* 分頁標籤樣式調整 */
    .stTabs [data-baseweb="tab-list"] { background-color: #1E1E1E; }
    .stTabs [data-baseweb="tab"] { color: #A0A0A0; }
    .stTabs [aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚔️ 游擊隊專屬軍火庫 (v5.1 闇黑統帥修復版)")
st.write("大將軍，基地已進入最高警戒模式。深色塗裝完畢，AI 戰術推薦系統已上線！")

# ================= 戰場情報獲取模組 =================

# 產業類別翻譯蒟蒻 (將 Yahoo 英文產業轉為中文)
sector_translation = {
    'Technology': '電子科技', 'Semiconductors': '半導體', 'Consumer Electronics': '消費電子',
    'Industrials': '工業製造', 'Basic Materials': '原物料', 'Financial Services': '金融',
    'Consumer Cyclical': '循環性消費', 'Healthcare': '生技醫療', 'Communication Services': '通訊網路',
    'Energy': '能源', 'Utilities': '公用事業', 'Real Estate': '房地產'
}

def fetch_twse_t86(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALLBUT0999&response=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        data = res.json()
        if data['stat'] == 'OK':
            df = pd.DataFrame(data['data'], columns=data['fields'])
            col_code = [c for c in df.columns if '代號' in c][0]
            col_name = [c for c in df.columns if '名稱' in c][0]
            foreign_cols = [c for c in df.columns if '外' in c and '買賣超' in c and '不含' in c]
            col_foreign = foreign_cols[0] if foreign_cols else [c for c in df.columns if '外' in c and '買賣超' in c][0]
            col_trust = [c for c in df.columns if '投信' in c and '買賣超' in c][0]
            
            res_df = df[[col_code, col_name]].copy()
            res_df.columns = ['股票代號', '股票名稱']
            res_df['外資買賣超(張)'] = pd.to_numeric(df[col_foreign].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            res_df['投信買賣超(張)'] = pd.to_numeric(df[col_trust].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            return res_df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_last_3_trading_days_data():
    dates_to_try = [(datetime.now() - timedelta(days=i)) for i in range(10)]
    valid_data = {}
    for d in dates_to_try:
        if len(valid_data) >= 3: break
        if d.weekday() >= 5: continue
        date_str = d.strftime("%Y%m%d")
        df = fetch_twse_t86(date_str)
        if not df.empty:
            valid_data[date_str] = df
            time.sleep(0.5) 
    return valid_data

# 啟動月線與產業探測器 (加入 Yahoo Finance 產業別)
def get_price_levels_and_industry(stock_list):
    results = []
    for code in stock_list:
        code = str(code).strip()
        if not code: continue
        try:
            ticker = yf.Ticker(f"{code}.TW")
            hist = ticker.history(period="3mo")
            if len(hist) >= 20:
                current_price = hist['Close'].iloc[-1]
                ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                high20 = hist['High'].rolling(window=20).max().iloc[-1]
                low20 = hist['Low'].rolling(window=20).min().iloc[-1]
                bias = ((
