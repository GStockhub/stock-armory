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
                bias = ((current_price - ma20) / ma20) * 100
                
                # 取得大概的產業別
                raw_sector = ticker.info.get('sector', '未知')
                industry = sector_translation.get(raw_sector, raw_sector)
                if industry == '未知': industry = ticker.info.get('industry', '未知') # 備用
                
                results.append({
                    '股票代號': code, '產業類別': industry,
                    '目前股價': current_price, '壓力價(近20日高)': high20,
                    '支撐價(月線20MA)': ma20, '底線價(近20日低)': low20, '乖離率(%)': bias
                })
        except: pass
    return pd.DataFrame(results)

# ================= 戰情室介面 =================
st.divider()

with st.spinner('情報兵正在黑暗中為將軍描繪最新戰場地圖...'):
    historical_data = get_last_3_trading_days_data()

if len(historical_data) >= 3:
    sorted_dates = sorted(list(historical_data.keys()), reverse=True)
    day1_date, day2_date, day3_date = sorted_dates[0], sorted_dates[1], sorted_dates[2]
    
    df_latest = historical_data[day1_date].copy()
    df_yesterday = historical_data[day2_date][['股票代號', '投信買賣超(張)']].rename(columns={'投信買賣超(張)': '昨日投信買超(張)'})
    df_daybefore = historical_data[day3_date][['股票代號', '投信買賣超(張)']].rename(columns={'投信買賣超(張)': '前日投信買超(張)'})
    
    merged_df = pd.merge(df_latest, df_yesterday, on='股票代號', how='left').fillna(0)
    merged_df = pd.merge(merged_df, df_daybefore, on='股票代號', how='left').fillna(0)
    
    tab1, tab2, tab3 = st.tabs(["🛡️ 防割韭菜 (含 AI 推薦)", "📈 專屬持股 / 觀察名單", "🔥 單日籌碼全覽"])
    
    # ---------------- 分頁 1: 防割韭菜與 AI 推薦 ----------------
    with tab1:
        condition_buy = (merged_df['投信買賣超(張)'] > 0) & (merged_df['昨日投信買超(張)'] > 0)
        potential_stocks = merged_df[condition_buy].copy()
        
        def check_streak(row):
            if row['前日投信買超(張)'] > 0: return "連買 3 天以上"
            else: return "剛連買 2 天 (極新鮮⭐)"
        
        if not potential_stocks.empty:
            potential_stocks['建倉狀態'] = potential_stocks.apply(check_streak, axis=1)
            stock_codes = potential_stocks['股票代號'].tolist()
            ma_df = get_price_levels_and_industry(stock_codes)
            
            if not ma_df.empty:
                final_df = pd.merge(potential_stocks, ma_df, on='股票代號')
                safe_df = final_df[final_df['乖離率(%)'] < 10].copy()
                
                if not safe_df.empty:
                    # ====== AI 戰術推薦模組 ======
                    safe_df['戰力分數'] = (safe_df['投信買賣超(張)'] * 1.5) + safe_df['外資買賣超(張)'] - (safe_df['乖離率(%)'] * 50)
                    top_3_df = safe_df.sort_values(by='戰力分數', ascending=False).head(3)
                    
                    st.markdown("### 👑 <span class='highlight-gold'>大將軍專屬：今日 Top 3 戰術突擊目標</span>", unsafe_allow_html=True)
                    st.write("綜合【大戶籌碼熱度】與【位階安全性】精選，土洋合買且防守容易的最佳標的：")
                    
                    cols = st.columns(3)
                    # 【修復重點】：改用 iterrows() 陣型，完美迴避括號錯誤
                    for idx, (_, row) in enumerate(top_3_df.iterrows()):
                        with cols[idx]:
                            st.markdown(f"""
                            <div style="background-color: #2D2D2D; padding: 15px; border-radius: 10px; border-left: 5px solid #FFD700;">
                                <h4 style="margin:0; color:#FFD700;">{row['股票名稱']} ({row['股票代號']})</h4>
                                <p style="margin:5px 0; color:#00FFFF;">{row['產業類別']}</p>
                                <b>狀態：</b>{row['建倉狀態']}<br>
                                <b>目前股價：</b>{row['目前股價']:.2f}<br>
                                <b>月線支撐：</b>{row['支撐價(月線20MA)']:.2f}<br>
                                <b>土洋合力：</b>投信買 {row['投信買賣超(張)']:.0f} 張 / 外資買 {row['外資買賣超(張)']:.0f} 張
                            </div>
                            """, unsafe_allow_html=True)
                    
                    st.markdown("---")
                    
                    st.markdown("### 🎯 <span class='highlight-cyan'>完整初建倉安全名單</span>", unsafe_allow_html=True)
                    safe_df_display = safe_df[['股票代號', '股票名稱', '產業類別', '建倉狀態', 
                                       '投信買賣超(張)', '外資買賣超(張)', 
                                       '目前股價', '支撐價(月線20MA)', '乖離率(%)']]
                    safe_df_display = safe_df_display.sort_values(by='乖離率(%)', ascending=True)
                    st.dataframe(
                        safe_df_display.style.format({
                            "投信買賣超(張)": "{:,.0f}", "外資買賣超(張)": "{:,.0f}", 
                            "目前股價": "{:.2f}", "支撐價(月線20MA)": "{:.2f}", "乖離率(%)": "{:.2f}%"
                        }), height=400, use_container_width=True
                    )
                else:
                    st.info("今日雖然有投信買超，但股價皆已噴發（乖離率過高），為了防割韭菜，系統已全部過濾。")
            else:
                st.warning("暫時無法取得報價資料。可能是 Yahoo Finance 伺服器繁忙，請稍後重試。")
        else:
            st.info("今日沒有符合條件的標的。")

    # ---------------- 分頁 2: 專屬持股 / 觀察名單 ----------------
    with tab2:
        st.markdown("### 📊 <span class='highlight-cyan'>大將軍的兵力佈署圖</span>", unsafe_allow_html=True)
        st.write("大將軍，您可在下方直接修改代號。若要永久保存，請修改原始碼內的預設值！")
        
        # ⚠️ 將軍請注意！修改這裡引號內的數字，就能永久儲存您的名單！ ⚠️
        default_holdings = "3189, 4958"    # <--- 修改這裡：您的持股
        default_watchlist = "2313, 2368"   # <--- 修改這裡：您的觀察名單
        
        col_h, col_w = st.columns(2)
        with col_h:
            holdings_input = st.text_input("🟢 目前重兵持股 (逗號隔開)：", value=default_holdings)
        with col_w:
            watchlist_input = st.text_input("🔵 雷達觀察名單 (逗號隔開)：", value=default_watchlist)
            
        if st.button("🚀 執行雙線價位掃描"):
            with st.spinner("正在為您計算三段價位與產業定位..."):
                if holdings_input:
                    st.markdown("#### 🟢 您的持股戰況")
                    h_list = [c.strip() for c in holdings_input.split(',')]
                    h_df = get_price_levels_and_industry(h_list)
                    if not h_df.empty:
                        h_df = pd.merge(h_df, df_latest[['股票代號', '股票名稱']], on='股票代號', how='left').fillna('未知')
                        h_df = h_df[['股票代號', '股票名稱', '產業類別', '壓力價(近20日高)', '目前股價', '支撐價(月線20MA)', '底線價(近20日低)']]
                        st.dataframe(h_df.style.format({"壓力價(近20日高)": "{:.2f}", "目前股價": "{:.2f}", "支撐價(月線20MA)": "{:.2f}", "底線價(近20日低)": "{:.2f}"}), use_container_width=True)
                
                if watchlist_input:
                    st.markdown("#### 🔵 觀察名單狙擊點")
                    w_list = [c.strip() for c in watchlist_input.split(',')]
                    w_df = get_price_levels_and_industry(w_list)
                    if not w_df.empty:
                        w_df = pd.merge(w_df, df_latest[['股票代號', '股票名稱']], on='股票代號', how='left').fillna('未知')
                        w_df = w_df[['股票代號', '股票名稱', '產業類別', '壓力價(近20日高)', '目前股價', '支撐價(月線20MA)', '底線價(近20日低)']]
                        st.dataframe(w_df.style.format({"壓力價(近20日高)": "{:.2f}", "目前股價": "{:.2f}", "支撐價(月線20MA)": "{:.2f}", "底線價(近20日低)": "{:.2f}"}), use_container_width=True)

    # ---------------- 分頁 3: 單日全覽 ----------------
    with tab3:
        st.subheader("🔥 單日三大法人籌碼總覽")
        df_all = df_latest.sort_values(by='投信買賣超(張)', ascending=False)
        st.dataframe(df_all.style.format({"外資買賣超(張)": "{:,.0f}", "投信買賣超(張)": "{:,.0f}"}), height=600, use_container_width=True)
else:
    st.error("情報截獲失敗，可能是國定假日或證交所連線異常。")
