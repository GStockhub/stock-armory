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
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR8WTv-KY303bD4qPlhoyZaAhlJujrfD5fxLpCNjyKvxk5NOxYMsMUAigsvmMV6q-A8HI4hlBk3V4bB/pub?output=csv"

# ================= UI 視覺優化 =================
st.markdown("""
    <style>
    .stApp { background-color: #1E1E1E; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, li { color: #E0E0E0 !important; }
    .highlight-gold { color: #FFD700; font-weight: bold; }
    .highlight-silver { color: #C0C0C0; font-weight: bold; }
    .highlight-bronze { color: #CD7F32; font-weight: bold; }
    .highlight-cyan { color: #00FFFF; font-weight: bold; }
    .dataframe th, .dataframe td { text-align: center !important; white-space: nowrap; }
    [data-testid="stDataFrame"] { background-color: #2D2D2D; border-radius: 10px; padding: 10px; width: 100%; }
    .stTabs [data-baseweb="tab-list"] { background-color: #1E1E1E; }
    .stTabs [data-baseweb="tab"] { color: #A0A0A0; }
    .stTabs [aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚔️ 游擊隊專屬軍火庫 (v13.0 絕對防禦磐石版)")
st.write("大將軍，演算法已切換為【安全優先】！結合美股、VIX恐慌指數與台股均線，為短線游擊嚴格把關！")

# ================= 戰場情報與風險獲取模組 =================

sector_translation = {
    'Technology': '電子科技', 'Semiconductors': '半導體', 'Consumer Electronics': '消費電子',
    'Industrials': '工業製造', 'Basic Materials': '原物料', 'Financial Services': '金融',
    'Consumer Cyclical': '循環消費', 'Healthcare': '生技醫療', 'Communication Services': '通訊網路',
    'Energy': '能源', 'Utilities': '公用事業', 'Real Estate': '房地產'
}

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

# 【核心升級】宏觀安全評分引擎 (滿分10分)
@st.cache_data(ttl=3600)
def get_macro_risk_score():
    score = 5 # 基礎分數 5
    try:
        # 抓取台股、費半、那斯達克、恐慌指數
        tickers = yf.Tickers("^TWII ^SOX ^IXIC ^VIX")
        hist_tw = tickers.tickers['^TWII'].history(period="1mo")
        hist_sox = tickers.tickers['^SOX'].history(period="1mo")
        hist_ixic = tickers.tickers['^IXIC'].history(period="1mo")
        hist_vix = tickers.tickers['^VIX'].history(period="5d")
        
        # 1. 台股大盤趨勢 (+1 或 -1)
        if hist_tw['Close'].iloc[-1] > hist_tw['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        
        # 2. 美股費半趨勢 (+1 或 -1)
        if hist_sox['Close'].iloc[-1] > hist_sox['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        
        # 3. 美股那斯達克趨勢 (+1 或 -1)
        if hist_ixic['Close'].iloc[-1] > hist_ixic['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        
        # 4. VIX 恐慌指數 (決定生死)
        vix_latest = hist_vix['Close'].iloc[-1]
        if vix_latest > 25: score -= 3 # 國際大恐慌，重罰
        elif vix_latest > 20: score -= 1
        elif vix_latest < 16: score += 1 # 天下太平
        
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
            time.sleep(0.2) 
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
                ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
                ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                high20 = hist['High'].rolling(window=20).max().iloc[-1]
                low20 = hist['Low'].rolling(window=20).min().iloc[-1]
                bias = ((current_price - ma20) / ma20) * 100
                
                industry = official_industry_map.get(code, "未知")
                if industry == "未知":
                    raw_sector = ticker.info.get('sector', '未知')
                    industry = sector_translation.get(raw_sector, raw_sector)
                
                # 【個股短線防禦力精算】
                final_score = macro_base_score
                
                # 短線動能(5MA)與波段支撐(20MA)
                if current_price > ma5: final_score += 1 # 站上5日線，短線強
                if current_price > ma20: final_score += 1 # 站上月線，波段穩
                else: final_score -= 2 # 跌破月線，極度危險
                
                # 乖離率(防追高機制)：越靠近0越安全
                if bias > 12: final_score -= 3 # 噴太遠，隨時回檔(極危險)
                elif bias > 8: final_score -= 1 # 有點高
                elif bias < -5: final_score -= 1 # 弱勢探底
                elif 0 <= bias <= 5: final_score += 2 # 剛站上月線附近，最安全黃金點！
                
                final_score = max(1, min(10, final_score))
                
                data_dict = {
                    '代號': code, '產業': industry,
                    '股價': current_price, '近20日高': high20,
                    '月線支撐': ma20, '近20日低': low20, '乖離(%)': bias,
                    '綜合風險(1-10分)': final_score
                }
                
                if need_volume:
                    data_dict['成交量(張)'] = hist['Volume'].iloc[-1] / 1000
                    data_dict['5日均量(張)'] = hist['Volume'].rolling(window=5).mean().iloc[-1] / 1000
                    
                results.append(data_dict)
        except: pass
    return pd.DataFrame(results)

def load_google_sheet():
    if not GOOGLE_SHEET_CSV_URL.startswith("http"): return pd.DataFrame(), pd.DataFrame()
    if "pub?output=csv" not in GOOGLE_SHEET_CSV_URL:
        st.error("🚨 警告：將軍，您的網址似乎不是『發布為 CSV』的格式！請確保網址裡面有包含 `pub?output=csv` 字眼。")
        return pd.DataFrame(), pd.DataFrame()
        
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV_URL, dtype=str)
        df.columns = df.columns.str.strip()
        df_holdings = df[df['分類'] == '持股'].copy()
        df_watchlist = df[df['分類'] == '觀察'].copy()
        return df_holdings, df_watchlist
    except Exception as e: 
        st.error(f"🚨 讀取 CSV 失敗，可能是格式不對或權限未公開：{e}")
        return pd.DataFrame(), pd.DataFrame()

def process_holdings_data(df_holdings):
    if df_holdings.empty: return pd.DataFrame()
    results = []
    codes = df_holdings['代號'].dropna().tolist()
    tech_df = get_price_levels_and_industry(codes, need_volume=False)
    if tech_df.empty: return pd.DataFrame()
    
    for _, row in df_holdings.iterrows():
        code = str(row.get('代號', '')).strip()
        stock_info = tech_df[tech_df['代號'] == code]
        if stock_info.empty: continue
        stock_info = stock_info.iloc[0]
        
        current_price = stock_info['股價']
        final_score = stock_info['綜合風險(1-10分)']
        industry = stock_info['產業']
        
        cost = float(row.get('成本價', 0)) if pd.notna(row.get('成本價')) and str(row.get('成本價')).strip() != '' else 0
        qty = float(row.get('庫存張數', 0)) if pd.notna(row.get('庫存張數')) and str(row.get('庫存張數')).strip() != '' else 0
        
        if cost > 0 and qty > 0:
            profit_loss = (current_price - cost) * qty * 1000
            return_rate = ((current_price - cost) / cost) * 100
        else:
            profit_loss, return_rate = 0, 0
            
        results.append({
            '代號': code, '產業': industry,
            '股價': current_price, '成本價': cost if cost > 0 else '-', '庫存(張)': qty if qty > 0 else '-',
            '報酬率(%)': return_rate, '預估損益(元)': profit_loss,
            '綜合風險(1-10分)': final_score
        })
    return pd.DataFrame(results)

def color_pnl(val):
    if isinstance(val, (int, float)):
        if val > 0: return 'color: #FF4B4B; font-weight: bold;' 
        elif val < 0: return 'color: #00FF00; font-weight: bold;' 
    return 'color: #E0E0E0;'

def color_risk(val):
    if isinstance(val, (int, float)):
        if val >= 8: return 'color: #00FF00; font-weight: bold;' 
        elif val >= 4: return 'color: #FFD700; font-weight: bold;' 
        else: return 'color: #FF4B4B; font-weight: bold;' 
    return 'color: #E0E0E0;'

# ================= 戰情室介面 =================
st.divider()

with st.spinner('情報兵正在運算美股連動、VIX恐慌指數與台股安全防禦分佈...'):
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
    
    tab1, tab2, tab3 = st.tabs(["🛡️ 安全優先：Top 10 防割推薦", "📊 司令部：持股庫存與觀察名單", "🔥 單日籌碼全覽"])
    
    # ---------------- 分頁 1: 安全優先 Top 10 分級推薦 ----------------
    with tab1:
        potential_stocks = base_df[base_df['連買天數'] >= 2].copy()
        if not potential_stocks.empty:
            stock_codes = potential_stocks['代號'].tolist()
            ma_df = get_price_levels_and_industry(stock_codes, need_volume=True)
            
            if not ma_df.empty:
                final_df = pd.merge(potential_stocks, ma_df, on='代號')
                
                # 防禦底線：成交量必須 > 1000張 (確保流動性)
                safe_df = final_df[final_df['成交量(張)'] >= 1000].copy()
                
                if not safe_df.empty:
                    # 🛡️ 【短線安全算分法】：分數越高越排前面！
                    # 權重：綜合風險(大環境+均線)佔比最重！籌碼次之。乖離率太大直接重扣。
                    safe_df['乖離懲罰'] = safe_df['乖離(%)'].apply(lambda x: x*50 if x > 8 else x*10)
                    safe_df['安全戰力'] = (safe_df['綜合風險(1-10分)'] * 500) + (safe_df['投信(張)']) + (safe_df['外資(張)'] * 0.5) - safe_df['乖離懲罰']
                    safe_df = safe_df.sort_values(by='安全戰力', ascending=False)
                    
                    top_10_df = safe_df.head(10)
                    top_1_to_3 = top_10_df.iloc[0:3]
                    top_4_to_7 = top_10_df.iloc[3:7]
                    top_8_to_10 = top_10_df.iloc[7:10]
                    
                    st.markdown("### 👑 <span class='highlight-gold'>【S級】絕對防禦 (Top 1~3)：大環境護航、位階極度安全</span>", unsafe_allow_html=True)
                    cols_s = st.columns(3)
                    for idx, (_, row) in enumerate(top_1_to_3.iterrows()):
                        with cols_s[idx]:
                            st.markdown(f"""
                            <div style="background-color: #2D2D2D; padding: 15px; border-radius: 10px; border-left: 5px solid #FFD700; height: 100%;">
                                <h4 style="margin:0; color:#FFD700;">{row['名稱']} ({row['代號']})</h4>
                                <span style="font-size: 14px;">
                                <b>🛡️ 安全評級：</b><span style='color:#00FF00; font-weight:bold;'>{row['綜合風險(1-10分)']} 分</span><br>
                                <b>防守月線：</b>{row['月線支撐']:.2f} (乖離 {row['乖離(%)']:.1f}%)<br>
                                <b>大戶佈局：</b>投信 {row['投信(張)']:.0f}張<br>
                                <b>熱度：</b>今 {row['成交量(張)']:.0f} 張
                                </span>
                            </div>
                            """, unsafe_allow_html=True)
                            
                    st.markdown("### ⚔️ <span class='highlight-silver'>【A級】穩健部隊 (Top 4~7)：短線支撐強勁</span>", unsafe_allow_html=True)
                    cols_a = st.columns(4)
                    for idx, (_, row) in enumerate(top_4_to_7.iterrows()):
                        with cols_a[idx]:
                            st.markdown(f"""
                            <div style="background-color: #2D2D2D; padding: 15px; border-radius: 10px; border-left: 5px solid #C0C0C0; height: 100%;">
                                <h5 style="margin:0; color:#C0C0C0;">{row['名稱']} ({row['代號']})</h5>
                                <span style="font-size: 13px;">安全 {row['綜合風險(1-10分)']} 分 | 乖離 {row['乖離(%)']:.1f}%</span>
                            </div>
                            """, unsafe_allow_html=True)
                            
                    st.markdown("### 🛡️ <span class='highlight-bronze'>【B級】伏擊觀察 (Top 8~10)：籌碼醞釀中</span>", unsafe_allow_html=True)
                    cols_b = st.columns(3)
                    for idx, (_, row) in enumerate(top_8_to_10.iterrows()):
                        with cols_b[idx]:
                            st.markdown(f"""
                            <div style="background-color: #2D2D2D; padding: 15px; border-radius: 10px; border-left: 5px solid #CD7F32; height: 100%;">
                                <h5 style="margin:0; color:#CD7F32;">{row['名稱']} ({row['代號']})</h5>
                                <span style="font-size: 13px;">安全 {row['綜合風險(1-10分)']} 分 | 乖離 {row['乖離(%)']:.1f}%</span>
                            </div>
                            """, unsafe_allow_html=True)

                    st.markdown("---")
                    st.markdown("### 🎯 <span class='highlight-cyan'>安全建倉雷達總表 (已排序，優先考慮安全分數 8 分以上)</span>", unsafe_allow_html=True)
                    
                    safe_df_display = safe_df[['代號', '名稱', '產業', '投信狀態', '綜合風險(1-10分)', '外資(張)', '投信(張)', '股價', '成交量(張)', '乖離(%)']]
                    
                    st.dataframe(
                        safe_df_display.style.set_properties(**{'text-align': 'center'})\
                        .map(color_risk, subset=['綜合風險(1-10分)'])\
                        .format({
                            "外資(張)": "{:,.0f}", "投信(張)": "{:,.0f}", 
                            "股價": "{:.2f}", "成交量(張)": "{:,.0f}", "乖離(%)": "{:.2f}%"
                        }), use_container_width=True, hide_index=True
                    )
                else: st.info("今日無符合流動性底線（大於 1000 張）的股票。")
            else: st.warning("技術面報價資料讀取中斷，請稍後重試。")
        else: st.info("今日沒有符合『連買 2 天以上』的標的。")

    # ---------------- 分頁 2: 司令部：持股與觀察名單 ----------------
    with tab2:
        st.markdown("### 🏦 <span class='highlight-gold'>大將軍的雲端兵力佈署圖</span>", unsafe_allow_html=True)
        
        df_holdings, df_watchlist = load_google_sheet()
        
        if df_holdings.empty and df_watchlist.empty:
            st.warning("⚠️ 尚未讀取到資料。請確認第 14 行 CSV 網址是否正確，且網址中必須包含 `pub?output=csv`。")
        else:
            if not df_holdings.empty:
                st.markdown("#### 🟢 第一軍團：現有重兵持股與損益")
                h_result = process_holdings_data(df_holdings)
                if not h_result.empty:
                    h_result = pd.merge(h_result, base_df[['代號', '名稱']], on='代號', how='left').fillna('未知')
                    cols = ['代號', '名稱', '產業', '股價', '成本價', '庫存(張)', '報酬率(%)', '預估損益(元)', '綜合風險(1-10分)']
                    h_result = h_result[cols]

                    styled_h = h_result.style.set_properties(**{'text-align': 'center'})\
                        .map(color_pnl, subset=['報酬率(%)', '預估損益(元)'])\
                        .map(color_risk, subset=['綜合風險(1-10分)'])\
                        .format({
                            "股價": "{:.2f}", 
                            "報酬率(%)": lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) and x != 0 else "-", 
                            "預估損益(元)": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and x != 0 else "-"
                        })
                    st.dataframe(styled_h, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            if not df_watchlist.empty:
                st.markdown("#### 🔵 第二軍團：雷達觀察狙擊名單")
                w_list = df_watchlist['代號'].dropna().tolist()
                w_result = get_price_levels_and_industry(w_list, need_volume=False)
                if not w_result.empty:
                    w_result = pd.merge(w_result, base_df[['代號', '名稱']], on='代號', how='left').fillna('未知')
                    w_result = w_result[['代號', '名稱', '產業', '綜合風險(1-10分)', '近20日高', '股價', '月線支撐', '近20日低']]
                    styled_w = w_result.style.set_properties(**{'text-align': 'center'})\
                        .map(color_risk, subset=['綜合風險(1-10分)'])\
                        .format({"近20日高": "{:.2f}", "股價": "{:.2f}", "月線支撐": "{:.2f}", "近20日低": "{:.2f}"})
                    st.dataframe(styled_w, use_container_width=True, hide_index=True)

    # ---------------- 分頁 3: 單日籌碼全覽 ----------------
    with tab3:
        st.markdown("### 🔥 <span class='highlight-cyan'>單日三大法人籌碼總覽 (全市場)</span>", unsafe_allow_html=True)
        df_all = base_df[['代號', '名稱', '投信狀態', '外資(張)', '投信(張)', '三大法人(張)']]
        df_all = df_all.sort_values(by='投信(張)', ascending=False)
        st.dataframe(
            df_all.style.set_properties(**{'text-align': 'center'}).format({
                "外資(張)": "{:,.0f}", "投信(張)": "{:,.0f}", "三大法人(張)": "{:,.0f}"
            }), height=600, use_container_width=True, hide_index=True
        )
else:
    st.error("情報截獲失敗，可能是國定假日或證交所連線異常。")
