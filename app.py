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

st.title("⚔️ 游擊隊專屬軍火庫 (v10.0 霸王完全體)")
st.write("大將軍，爆量防割雷達與 AI 推薦已全面回歸！結合 Google 試算表精算引擎，全軍出擊！")

# ================= 戰場情報與風險獲取模組 =================

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

@st.cache_data(ttl=3600)
def get_macro_risk_score():
    score = 5 
    try:
        tickers = yf.Tickers("^TWII ^SOX ^VIX")
        hist_tw = tickers.tickers['^TWII'].history(period="1mo")
        hist_sox = tickers.tickers['^SOX'].history(period="1mo")
        hist_vix = tickers.tickers['^VIX'].history(period="5d")
        
        if hist_tw['Close'].iloc[-1] > hist_tw['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        
        if hist_sox['Close'].iloc[-1] > hist_sox['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        
        vix_latest = hist_vix['Close'].iloc[-1]
        if vix_latest > 25: score -= 2 
        elif vix_latest < 18: score += 1 
    except: pass
    return score
macro_base_score = get_macro_risk_score()

def fetch_twse_t86(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALLBUT0999&response=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5, verify=False)
        data = res.json()
        if data['stat'] == 'OK':
            df = pd.DataFrame(data['data'], columns=data['fields'])
            col_code = [c for c in df.columns if '代號' in c][0]
            col_name = [c for c in df.columns if '名稱' in c][0]
            foreign_cols = [c for c in df.columns if '外' in c and '買賣超' in c and '不含' in c]
            col_foreign = foreign_cols[0] if foreign_cols else [c for c in df.columns if '外' in c and '買賣超' in c][0]
            col_trust = [c for c in df.columns if '投信' in c and '買賣超' in c][0]
            dealer_cols = [c for c in df.columns if '自營商' in c and '買賣超' in c]
            col_dealer = min(dealer_cols, key=len) if dealer_cols else [c for c in df.columns if '自營商' in c][0]
            
            res_df = df[[col_code, col_name]].copy()
            res_df.columns = ['代號', '名稱']
            f_vol = pd.to_numeric(df[col_foreign].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            t_vol = pd.to_numeric(df[col_trust].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            d_vol = pd.to_numeric(df[col_dealer].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            
            res_df['外資(張)'] = f_vol
            res_df['投信(張)'] = t_vol
            res_df['三大法人(張)'] = f_vol + t_vol + d_vol
            return res_df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_10_trading_days_data():
    dates_to_try = [(datetime.now() - timedelta(days=i)) for i in range(20)]
    valid_data = {}
    for d in dates_to_try:
        if len(valid_data) >= 10: break
        if d.weekday() >= 5: continue
        date_str = d.strftime("%Y%m%d")
        df = fetch_twse_t86(date_str)
        if not df.empty:
            valid_data[date_str] = df
            time.sleep(0.3) 
    return valid_data

def get_price_levels_and_industry(stock_list, need_volume=False):
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
                industry = official_industry_map.get(code, "未知")
                
                data_dict = {
                    '代號': code, '產業': industry,
                    '股價': current_price, '近20日高': high20,
                    '月線支撐': ma20, '近20日低': low20, '乖離(%)': bias
                }
                
                if need_volume:
                    data_dict['成交量(張)'] = hist['Volume'].iloc[-1] / 1000
                    data_dict['5日均量(張)'] = hist['Volume'].rolling(window=5).mean().iloc[-1] / 1000
                    
                results.append(data_dict)
        except: pass
    return pd.DataFrame(results)

def load_google_sheet():
    if "http" not in GOOGLE_SHEET_CSV_URL: return pd.DataFrame(), pd.DataFrame()
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV_URL, dtype=str)
        df.columns = df.columns.str.strip()
        df_holdings = df[df['分類'] == '持股'].copy()
        df_watchlist = df[df['分類'] == '觀察'].copy()
        return df_holdings, df_watchlist
    except: return pd.DataFrame(), pd.DataFrame()

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
                
                final_score = macro_base_score
                if current_price > ma20: final_score += 1
                else: final_score -= 1
                
                if bias > 15: final_score -= 2 
                elif bias < -5: final_score -= 1 
                else: final_score += 1 
                
                final_score = max(1, min(10, final_score))
                
                cost = float(row.get('成本價', 0))
                qty = float(row.get('庫存張數', 0))
                if cost > 0 and qty > 0:
                    profit_loss = (current_price - cost) * qty * 1000
                    return_rate = ((current_price - cost) / cost) * 100
                else:
                    profit_loss, return_rate = 0, 0
                
                industry = official_industry_map.get(code, "未知")
                results.append({
                    '代號': code, '產業': industry,
                    '股價': current_price, '成本價': cost, '庫存(張)': qty,
                    '報酬率(%)': return_rate, '預估損益(元)': profit_loss,
                    '綜合風險(1-10分)': final_score
                })
        except: pass
    return pd.DataFrame(results)

def color_pnl(val):
    if val > 0: return 'color: #FF4B4B; font-weight: bold;' 
    elif val < 0: return 'color: #00FF00; font-weight: bold;' 
    return 'color: #E0E0E0;'

def color_risk(val):
    if val >= 8: return 'color: #00FF00; font-weight: bold;' 
    elif val >= 4: return 'color: #FFD700; font-weight: bold;' 
    else: return 'color: #FF4B4B; font-weight: bold;' 

# ================= 戰情室介面 =================
st.divider()

with st.spinner('情報兵正在深度掃描 10 日籌碼與同步 Google 糧草庫...'):
    historical_data = get_10_trading_days_data()

if len(historical_data) >= 3:
    sorted_dates = sorted(list(historical_data.keys()), reverse=True)
    day1_date = sorted_dates[0]
    base_df = historical_data[day1_date].copy()
    
    trust_cols = []
    for i, d in enumerate(sorted_dates):
        col_name = f'Day_{i}'
        temp = historical_data[d][['代號', '投信(張)']].rename(columns={'投信(張)': col_name})
        base_df = pd.merge(base_df, temp, on='代號', how='left')
        trust_cols.append(col_name)
    base_df.fillna(0, inplace=True)
    
    def count_streak(row):
        streak = 0
        for col in trust_cols:
            if row[col] > 0: streak += 1
            else: break
        return streak
    base_df['連買天數'] = base_df.apply(count_streak, axis=1)
    
    def label_streak(s):
        if s == 0: return "無/賣"
        elif s == 1: return "剛卡位"
        elif 2 <= s <= 3: return "建倉 ⭐"
        elif 4 <= s <= 7: return "追高 ⚠️"
        else: return "危險 💀"
    base_df['投信狀態'] = base_df['連買天數'].apply(label_streak)
    
    tab1, tab2, tab3 = st.tabs(["🛡️ 爆量防割熱區 (AI 推薦)", "📊 司令部：持股庫存與觀察名單", "🔥 單日籌碼全覽"])
    
    # ---------------- 分頁 1: 爆量防割熱區 (從 v8.0 完美搬回) ----------------
    with tab1:
        potential_stocks = base_df[(base_df['連買天數'] >= 2) & (base_df['連買天數'] <= 3)].copy()
        if not potential_stocks.empty:
            stock_codes = potential_stocks['代號'].tolist()
            ma_df = get_price_levels_and_industry(stock_codes, need_volume=True)
            
            if not ma_df.empty:
                final_df = pd.merge(potential_stocks, ma_df, on='代號')
                safe_df = final_df[(final_df['乖離(%)'] < 10) & 
                                   (final_df['成交量(張)'] >= 1000) & 
                                   (final_df['成交量(張)'] > final_df['5日均量(張)'])].copy()
                
                if not safe_df.empty:
                    safe_df['量能倍數'] = safe_df['成交量(張)'] / safe_df['5日均量(張)']
                    safe_df['戰力分數'] = (safe_df['投信(張)'] * 2) + safe_df['外資(張)'] + (safe_df['量能倍數'] * 500) - (safe_df['乖離(%)'] * 50)
                    top_3_df = safe_df.sort_values(by='戰力分數', ascending=False).head(3)
                    
                    st.markdown("### 👑 <span class='highlight-gold'>大將軍專屬：今日 Top 3 爆量突擊目標</span>", unsafe_allow_html=True)
                    st.write("精選【連買2-3天】+【突破5日均量(資金點火)】+【位階安全】的最佳標的：")
                    
                    cols = st.columns(3)
                    for idx, (_, row) in enumerate(top_3_df.iterrows()):
                        with cols[idx]:
                            st.markdown(f"""
                            <div style="background-color: #2D2D2D; padding: 15px; border-radius: 10px; border-left: 5px solid #FF4B4B; height: 100%;">
                                <h4 style="margin:0; color:#FFD700;">{row['名稱']} ({row['代號']})</h4>
                                <p style="margin:5px 0; color:#00FFFF; font-size: 14px;">{row['產業']}</p>
                                <span style="font-size: 14px;">
                                <b>狀態：</b>{row['投信狀態']}<br>
                                <b>股價：</b>{row['股價']:.2f} (支撐 {row['月線支撐']:.2f})<br>
                                <b>土洋合力：</b>投信 {row['投信(張)']:.0f} / 外資 {row['外資(張)']:.0f}<br>
                                <b>🔥 攻擊量能：</b>今日 <span style='color:#FF4B4B; font-weight:bold;'>{row['成交量(張)']:.0f}</span> 張<br>
                                </span>
                            </div>
                            """, unsafe_allow_html=True)
                    st.markdown("---")
                    
                    st.markdown("### 🎯 <span class='highlight-cyan'>熱門放量建倉名單 (保證流動性與熱度)</span>", unsafe_allow_html=True)
                    safe_df_display = safe_df[['代號', '名稱', '產業', '投信狀態', '外資(張)', '投信(張)', '三大法人(張)', '股價', '成交量(張)', '乖離(%)']]
                    safe_df_display = safe_df_display.sort_values(by='乖離(%)', ascending=True)
                    st.dataframe(
                        safe_df_display.style.set_properties(**{'text-align': 'center'}).format({
                            "外資(張)": "{:,.0f}", "投信(張)": "{:,.0f}", "三大法人(張)": "{:,.0f}", 
                            "股價": "{:.2f}", "成交量(張)": "{:,.0f}", "乖離(%)": "{:.2f}%"
                        }), use_container_width=True, hide_index=True
                    )
                else: st.info("今日無符合『放量突破+位階安全』的飆股，切勿勉強進場。")
            else: st.warning("技術面報價資料讀取中斷，請稍後重試。")
        else: st.info("今日沒有符合『連買 2-3 天』的極品標的。")

    # ---------------- 分頁 2: 司令部：持股與觀察名單 (從 v9.0 完美繼承) ----------------
    with tab2:
        st.markdown("### 🏦 <span class='highlight-gold'>大將軍的雲端兵力佈署圖</span>", unsafe_allow_html
