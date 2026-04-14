import streamlit as st
import pandas as pd
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

# ⚠️ 大將軍！請將下方引號內的網址，換成您的 Google 試算表「發布為 CSV」的網址！ ⚠️
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1FJGW_TAIJGHAl7oSD_eZEnqWUhEVvQMb_ZqIIL_RQGM/edit?usp=sharing"

# ================= UI 視覺優化 =================
st.markdown("""
    <style>
    .stApp { background-color: #1E1E1E; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, li { color: #E0E0E0 !important; }
    .highlight-gold { color: #FFD700; font-weight: bold; }
    .highlight-cyan { color: #00FFFF; font-weight: bold; }
    .dataframe th, .dataframe td { text-align: center !important; white-space: nowrap; }
    [data-testid="stDataFrame"] { background-color: #2D2D2D; border-radius: 10px; padding: 10px; width: 100%; }
    .stTabs [data-baseweb="tab-list"] { background-color: #1E1E1E; }
    .stTabs [data-baseweb="tab"] { color: #A0A0A0; }
    .stTabs [aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚔️ 游擊隊專屬軍火庫 (v9.0 全面統御版)")
st.write("大將軍，損益精算引擎與 1-10分綜合風險雷達已上線！所有陣地將由 Google 雲端自動同步！")

# ================= 戰場情報獲取模組 =================

@st.cache_data(ttl=86400)
def get_twse_industry_map():
    ind_map = {}
    try:
        res = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False, timeout=5)
        for item in res.json():
            ind_map[item['公司代號']] = item['產業類別']
    except: pass
    return ind_map
official_industry_map = get_twse_industry_map()

# 獲取總經宏觀分數 (每日更新一次)
@st.cache_data(ttl=3600)
def get_macro_risk_score():
    score = 5 # 基礎分數 5
    try:
        # 抓取大盤、費半、恐慌指數
        tickers = yf.Tickers("^TWII ^SOX ^VIX")
        hist_tw = tickers.tickers['^TWII'].history(period="1mo")
        hist_sox = tickers.tickers['^SOX'].history(period="1mo")
        hist_vix = tickers.tickers['^VIX'].history(period="5d")
        
        # 台股大盤趨勢 (+1 或 -1)
        if hist_tw['Close'].iloc[-1] > hist_tw['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        
        # 費半趨勢 (+1 或 -1)
        if hist_sox['Close'].iloc[-1] > hist_sox['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        
        # 恐慌指數 VIX (判斷國際新聞/風險)
        vix_latest = hist_vix['Close'].iloc[-1]
        if vix_latest > 25: score -= 2 # 極度恐慌，大扣分
        elif vix_latest < 18: score += 1 # 風平浪靜
    except: pass
    return score

macro_base_score = get_macro_risk_score()

# 讀取 Google 試算表 (強制將所有欄位讀取為字串，解決 0050 被吃掉 00 的問題)
def load_google_sheet():
    if "http" not in GOOGLE_SHEET_CSV_URL: return pd.DataFrame(), pd.DataFrame()
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV_URL, dtype=str)
        # 清理欄位空白
        df.columns = df.columns.str.strip()
        
        df_holdings = df[df['分類'] == '持股'].copy()
        df_watchlist = df[df['分類'] == '觀察'].copy()
        
        return df_holdings, df_watchlist
    except: return pd.DataFrame(), pd.DataFrame()

# 取得股價與精算風險、損益
def process_holdings_data(df_holdings):
    if df_holdings.empty: return pd.DataFrame()
    
    results = []
    for _, row in df_holdings.iterrows():
        code = str(row.get('代號', '')).strip()
        if not code: continue
        try:
            ticker = yf.Ticker(f"{code}.TW")
            hist = ticker.history(period="1mo")
            if len(hist) >= 20:
                current_price = hist['Close'].iloc[-1]
                ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                bias = ((current_price - ma20) / ma20) * 100
                
                # 計算個股風險分數
                final_score = macro_base_score
                if current_price > ma20: final_score += 1
                else: final_score -= 1
                
                if bias > 15: final_score -= 2 # 噴太高，高風險
                elif bias < -5: final_score -= 1 # 弱勢破底
                else: final_score += 1 # 位階安全
                
                # 限制分數在 1~10 之間
                final_score = max(1, min(10, final_score))
                
                # 計算損益
                cost = float(row.get('成本價', 0))
                qty = float(row.get('庫存張數', 0))
                if cost > 0 and qty > 0:
                    profit_loss = (current_price - cost) * qty * 1000
                    return_rate = ((current_price - cost) / cost) * 100
                else:
                    profit_loss = 0
                    return_rate = 0
                
                industry = official_industry_map.get(code, "未知")
                
                results.append({
                    '代號': code, '產業': industry,
                    '目前股價': current_price, '成本價': cost, '庫存(張)': qty,
                    '報酬率(%)': return_rate, '預估損益(元)': profit_loss,
                    '綜合風險分數': final_score
                })
        except: pass
    return pd.DataFrame(results)

def process_watchlist_data(df_watchlist):
    if df_watchlist.empty: return pd.DataFrame()
    results = []
    for _, row in df_watchlist.iterrows():
        code = str(row.get('代號', '')).strip()
        if not code: continue
        try:
            ticker = yf.Ticker(f"{code}.TW")
            hist = ticker.history(period="3mo")
            if len(hist) >= 20:
                current_price = hist['Close'].iloc[-1]
                ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                high20 = hist['High'].rolling(window=20).max().iloc[-1]
                low20 = hist['Low'].rolling(window=20).min().iloc[-1]
                
                industry = official_industry_map.get(code, "未知")
                results.append({
                    '代號': code, '產業': industry,
                    '目前股價': current_price, '壓力價(20日高)': high20,
                    '月線支撐': ma20, '防守底線(20日低)': low20
                })
        except: pass
    return pd.DataFrame(results)

# 顏色格式化功能
def color_pnl(val):
    if val > 0: return 'color: #FF4B4B; font-weight: bold;' # 賺錢紅色
    elif val < 0: return 'color: #00FF00; font-weight: bold;' # 賠錢綠色
    return 'color: #E0E0E0;'

def color_risk(val):
    if val >= 8: return 'color: #00FF00; font-weight: bold;' # 安全(綠)
    elif val >= 4: return 'color: #FFD700; font-weight: bold;' # 中等(黃)
    else: return 'color: #FF4B4B; font-weight: bold;' # 危險(紅)

# ================= 戰情室介面 =================
st.divider()

tab1, tab2 = st.tabs(["📊 司令部：持股庫存與觀察名單", "🔥 情報局：請保留原有的單日籌碼功能(選用)"])

with tab1:
    st.markdown("### 🏦 <span class='highlight-gold'>大將軍的雲端兵力佈署圖</span>", unsafe_allow_html=True)
    
    with st.spinner("正在連線 Google 試算表，並啟動風險損益精算引擎..."):
        df_holdings, df_watchlist = load_google_sheet()
        
        if df_holdings.empty and df_watchlist.empty:
            st.warning("⚠️ 尚未偵測到 Google 試算表資料。請確認 CSV 網址是否正確，且表格標題包含『分類』、『代號』、『成本價』、『庫存張數』。")
        else:
            # ---------------- 處理持股區塊 ----------------
            if not df_holdings.empty:
                st.markdown("#### 🟢 第一軍團：現有重兵持股與損益")
                h_result = process_holdings_data(df_holdings)
                if not h_result.empty:
                    # 套用顏色
                    styled_h = h_result.style.set_properties(**{'text-align': 'center'})\
                        .map(color_pnl, subset=['報酬率(%)', '預估損益(元)'])\
                        .map(color_risk, subset=['綜合風險分數'])\
                        .format({
                            "目前股價": "{:.2f}", "成本價": "{:.2f}", "庫存(張)": "{:,.0f}",
                            "報酬率(%)": "{:.2f}%", "預估損益(元)": "{:,.0f}"
                        })
                    st.dataframe(styled_h, use_container_width=True, hide_index=True)
                else:
                    st.info("無法解析持股代號，請檢查 Google 試算表。")
            
            st.markdown("---")
            
            # ---------------- 處理觀察名單區塊 ----------------
            if not df_watchlist.empty:
                st.markdown("#### 🔵 第二軍團：雷達觀察狙擊名單 (三段價位)")
                w_result = process_watchlist_data(df_watchlist)
                if not w_result.empty:
                    styled_w = w_result.style.set_properties(**{'text-align': 'center'})\
                        .format({
                            "目前股價": "{:.2f}", "壓力價(20日高)": "{:.2f}", 
                            "月線支撐": "{:.2f}", "防守底線(20日低)": "{:.2f}"
                        })
                    st.dataframe(styled_w, use_container_width=True, hide_index=True)
                else:
                    st.info("無法解析觀察名單代號，請檢查 Google 試算表。")

with tab2:
    st.write("大將軍，此分頁可整合前一版本的『防割韭菜與大戶籌碼』程式碼，維持您的全方位情報網。為聚焦您的持股需求，此處暫作預留空間。")
