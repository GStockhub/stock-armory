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

st.title("⚔️ 游擊隊專屬軍火庫 (v15.0 傳奇軍師版)")

# ================= 戰場情報與風險獲取模組 =================

sector_translation = {
    'Technology': '電子科技', 'Semiconductors': '半導體', 'Consumer Electronics': '消費電子',
    'Industrials': '工業製造', 'Basic Materials': '原物料', 'Financial Services': '金融',
    'Consumer Cyclical': '循環消費', 'Healthcare': '生技醫療', 'Communication Services': '通訊網路'
}

@st.cache_data(ttl=86400)
def get_twse_industry_map():
    ind_map = {}
    try:
        res = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False, timeout=5)
        for item in res.json():
            ind_map[str(item['公司代號']).strip()] = item['產業類別']
    except: pass
    return ind_map
official_industry_map = get_twse_industry_map()

@st.cache_data(ttl=3600)
def get_macro_risk_score():
    score = 5 
    try:
        tickers = yf.Tickers("^TWII ^SOX ^IXIC ^VIX")
        hist_tw = tickers.tickers['^TWII'].history(period="1mo")
        hist_sox = tickers.tickers['^SOX'].history(period="1mo")
        hist_ixic = tickers.tickers['^IXIC'].history(period="1mo")
        hist_vix = tickers.tickers['^VIX'].history(period="5d")
        
        if hist_tw['Close'].iloc[-1] > hist_tw['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        if hist_sox['Close'].iloc[-1] > hist_sox['Close'].rolling(20).mean().iloc[-1]: score += 1
        else: score -= 1
        
        vix_latest = hist_vix['Close'].iloc[-1]
        if vix_latest > 25: score -= 3 
        elif vix_latest > 20: score -= 1
        elif vix_latest < 16: score += 1 
    except: pass
    return score
macro_base_score = get_macro_risk_score()

# ================= 每日動態嘲諷/鼓勵系統 (取代原本單調的 st.write) =================
if macro_base_score >= 7:
    st.write("📈 **【今日戰報】**：大將軍！大盤一片紅通通，別只顧著數鈔票，記得留點骨頭給外面追高的韭菜吃啊！ 😎")
elif macro_base_score >= 4:
    st.write("🌊 **【今日戰報】**：大將軍！最近大盤跟渣男一樣忽冷忽熱，請握緊您的 5MA 攻擊線，手腳要快，別被甩下車了！ 🏃‍♂️")
else:
    st.write("🚨 **【今日戰報】**：大將軍！外面血流成河啦！別人在公園鋪紙箱，我們滿手現金在基地裡看戲，真香！ 🍿")

# ================= 資料處理模組 =================

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
                high5 = hist['High'].rolling(window=5).max().iloc[-1]
                ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
                ma10 = hist['Close'].rolling(window=10).mean().iloc[-1]
                ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                bias = ((current_price - ma20) / ma20) * 100
                
                if code.startswith('00'):
                    industry = "ETF"
                else:
                    industry = official_industry_map.get(code, "未知")
                    if industry == "未知":
                        raw_sector = ticker.info.get('industry', '未知')
                        industry = sector_translation.get(raw_sector, raw_sector)
                
                final_score = macro_base_score
                if current_price > ma5: final_score += 1 
                if current_price > ma20: final_score += 1 
                else: final_score -= 2 
                
                if bias > 12: final_score -= 3 
                elif bias > 8: final_score -= 1 
                elif bias < -5: final_score -= 1 
                elif 0 <= bias <= 5: final_score += 2 
                
                final_score = max(1, min(10, final_score))
                
                data_dict = {
                    '代號': code, '產業': industry,
                    '股價': current_price, '短壓(5日高)': high5,
                    '攻擊線(5MA)': ma5, '防守線(10MA)': ma10, '月線支撐': ma20,
                    '乖離(%)': bias, '綜合風險(1-10分)': final_score
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
        st.error("🚨 警告：您的網址似乎不是『發布為 CSV』格式！請確保網址包含 `pub?output=csv`。")
        return pd.DataFrame(), pd.DataFrame()
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
    codes = df_holdings['代號'].dropna().tolist()
    tech_df = get_price_levels_and_industry(codes, need_volume=False)
    if tech_df.empty: return pd.DataFrame()
    
    for _, row in df_holdings.iterrows():
        code = str(row.get('代號', '')).strip()
        stock_info = tech_df[tech_df['代號'] == code]
        if stock_info.empty: continue
        stock_info = stock_info.iloc[0]
        
        current_price = stock_info['股價']
        cost = float(row.get('成本價', 0)) if pd.notna(row.get('成本價')) and str(row.get('成本價')).strip() != '' else 0
        qty = float(row.get('庫存張數', 0)) if pd.notna(row.get('庫存張數')) and str(row.get('庫存張數')).strip() != '' else 0
        
        if cost > 0 and qty > 0:
            profit_loss = (current_price - cost) * qty * 1000
            return_rate = ((current_price - cost) / cost) * 100
        else:
            profit_loss, return_rate = 0, 0
            
        results.append({
            '代號': code, '產業': stock_info['產業'],
            '股價': current_price, '成本價': cost if cost > 0 else '-', '庫存(張)': qty if qty > 0 else '-',
            '報酬率(%)': return_rate, '預估損益(元)': profit_loss,
            '綜合風險(1-10分)': stock_info['綜合風險(1-10分)'],
            '短壓(5日高)': stock_info['短壓(5日高)'], '攻擊線(5MA)': stock_info['攻擊線(5MA)'], '防守線(10MA)': stock_info['防守線(10MA)']
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

with st.spinner('情報兵正在深度掃描籌碼與同步 Google 糧草庫...'):
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
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛡️ 安全優先：Top 10 防割推薦", "📊 司令部：持股庫存與觀察名單", "🔥 單日籌碼全覽", "📖 游擊隊戰術手冊", "📜 軍火庫開發史"])
    
    # ---------------- 分頁 1: 安全優先 Top 10 ----------------
    with tab1:
        potential_stocks = base_df[base_df['連買天數'] >= 2].copy()
        if not potential_stocks.empty:
            stock_codes = potential_stocks['代號'].tolist()
            ma_df = get_price_levels_and_industry(stock_codes, need_volume=True)
            
            if not ma_df.empty:
                final_df = pd.merge(potential_stocks, ma_df, on='代號')
                safe_df = final_df[final_df['成交量(張)'] >= 1000].copy()
                
                if not safe_df.empty:
                    safe_df['乖離懲罰'] = safe_df['乖離(%)'].apply(lambda x: x*50 if x > 8 else x*10)
                    safe_df['安全戰力'] = (safe_df['綜合風險(1-10分)'] * 500) + (safe_df['投信(張)']) + (safe_df['外資(張)'] * 0.5) - safe_df['乖離懲罰']
                    safe_df = safe_df.sort_values(by='安全戰力', ascending=False)
                    
                    top_10_df = safe_df.head(10)
                    
                    def render_card(row, tier, color):
                        return f"""
                        <div style="background-color: #2D2D2D; padding: 15px; border-radius: 10px; border-left: 5px solid {color}; height: 100%; margin-bottom: 10px;">
                            <h4 style="margin:0; color:{color};">{row['名稱']} ({row['代號']})</h4>
                            <p style="margin:5px 0; color:#00FFFF; font-size: 14px;">{row['產業']}</p>
                            <span style="font-size: 14px;">
                            <b>🛡️ 安全：</b><span style='color:#00FF00; font-weight:bold;'>{row['綜合風險(1-10分)']} 分</span><br>
                            <b>股價：</b>{row['股價']:.2f} (防守線 {row['防守線(10MA)']:.2f})<br>
                            <b>大戶：</b>投信 {row['投信(張)']:.0f} / 外資 {row['外資(張)']:.0f}<br>
                            <b>熱度：</b>今 {row['成交量(張)']:.0f} 張 (乖離 {row['乖離(%)']:.1f}%)
                            </span>
                        </div>
                        """

                    st.markdown("### 👑 <span class='highlight-gold'>【S級】絕對防禦 (Top 1~3)：大環境護航、位階極度安全</span>", unsafe_allow_html=True)
                    cols_s = st.columns(3)
                    for idx, (_, row) in enumerate(top_10_df.iloc[0:3].iterrows()):
                        with cols_s[idx]: st.markdown(render_card(row, 'S', '#FFD700'), unsafe_allow_html=True)
                            
                    st.markdown("### ⚔️ <span class='highlight-silver'>【A級】穩健部隊 (Top 4~7)：籌碼穩定潛力股</span>", unsafe_allow_html=True)
                    cols_a = st.columns(4)
                    for idx, (_, row) in enumerate(top_10_df.iloc[3:7].iterrows()):
                        with cols_a[idx]: st.markdown(render_card(row, 'A', '#C0C0C0'), unsafe_allow_html=True)
                            
                    st.markdown("### 🛡️ <span class='highlight-bronze'>【B級】伏擊觀察 (Top 8~10)：過底線準備發動</span>", unsafe_allow_html=True)
                    cols_b = st.columns(3)
                    for idx, (_, row) in enumerate(top_10_df.iloc[7:10].iterrows()):
                        with cols_b[idx]: st.markdown(render_card(row, 'B', '#CD7F32'), unsafe_allow_html=True)

                    st.markdown("---")
                    st.markdown("### 🎯 <span class='highlight-cyan'>安全建倉雷達總表 (優先考慮安全分數 8 分以上)</span>", unsafe_allow_html=True)
                    
                    safe_df_display = safe_df[['代號', '名稱', '產業', '投信狀態', '綜合風險(1-10分)', '外資(張)', '投信(張)', '股價', '防守線(10MA)', '乖離(%)']]
                    st.dataframe(
                        safe_df_display.style.set_properties(**{'text-align': 'center'})\
                        .map(color_risk, subset=['綜合風險(1-10分)'])\
                        .format({
                            "外資(張)": "{:,.0f}", "投信(張)": "{:,.0f}", 
                            "股價": "{:.2f}", "防守線(10MA)": "{:.2f}", "乖離(%)": "{:.2f}%"
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
            st.warning("⚠️ 尚未讀取到資料。請確認第 14 行 CSV 網址是否正確。")
        else:
            if not df_holdings.empty:
                st.markdown("#### 🟢 第一軍團：現有重兵持股與損益")
                h_result = process_holdings_data(df_holdings)
                if not h_result.empty:
                    h_result = pd.merge(h_result, base_df[['代號', '名稱']], on='代號', how='left').fillna('未知')
                    cols = ['代號', '名稱', '產業', '股價', '成本價', '庫存(張)', '報酬率(%)', '預估損益(元)', '綜合風險(1-10分)']
                    
                    styled_h = h_result[cols].style.set_properties(**{'text-align': 'center'})\
                        .map(color_pnl, subset=['報酬率(%)', '預估損益(元)'])\
                        .map(color_risk, subset=['綜合風險(1-10分)'])\
                        .format({
                            "股價": "{:.2f}", 
                            "庫存(張)": lambda x: f"{x:g}" if isinstance(x, (int, float)) else x,
                            "報酬率(%)": lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) and x != 0 else "-", 
                            "預估損益(元)": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and x != 0 else "-"
                        })
                    st.dataframe(styled_h, use_container_width=True, hide_index=True)
                    
                    st.markdown("#### 🚨 第一軍團附屬：自動化作戰計畫 (游擊紀律)")
                    plan_df = h_result[['代號', '名稱', '股價', '短壓(5日高)', '攻擊線(5MA)', '防守線(10MA)']].copy()
                    
                    def generate_plan(row):
                        price = row['股價']
                        ma5 = row['攻擊線(5MA)']
                        ma10 = row['防守線(10MA)']
                        high5 = row['短壓(5日高)']
                        
                        if price < ma10:
                            return "💀 跌破 10MA 防線！建議：3天內站不回請無情認賠/停利出場。"
                        elif price < ma5:
                            return "⚠️ 跌破 5MA 攻擊線。建議：減碼 30%~50% 確保獲利，剩餘看 10MA。"
                        elif price >= high5 * 0.98: 
                            return "🎯 逼近短線壓力區。建議：遇壓不過可先收割 50% 落袋為安。"
                        else:
                            return "✅ 股價在 5MA 之上。建議：抱牢，讓子彈飛！"
                            
                    plan_df['作戰建議'] = plan_df.apply(generate_plan, axis=1)
                    plan_df = plan_df[['代號', '名稱', '股價', '短壓(5日高)', '攻擊線(5MA)', '防守線(10MA)', '作戰建議']]
                    st.dataframe(
                        plan_df.style.set_properties(**{'text-align': 'center', 'white-space': 'normal'})\
                        .format({"股價": "{:.2f}", "短壓(5日高)": "{:.2f}", "攻擊線(5MA)": "{:.2f}", "防守線(10MA)": "{:.2f}"}),
                        use_container_width=True, hide_index=True
                    )
            
            st.markdown("---")
            
            if not df_watchlist.empty:
                st.markdown("#### 🔵 第二軍團：雷達觀察狙擊名單")
                w_list = df_watchlist['代號'].dropna().tolist()
                w_result = get_price_levels_and_industry(w_list, need_volume=False)
                if not w_result.empty:
                    w_result = pd.merge(w_result, base_df[['代號', '名稱']], on='代號', how='left').fillna('未知')
                    w_result = w_result[['代號', '名稱', '產業', '綜合風險(1-10分)', '短壓(5日高)', '股價', '攻擊線(5MA)', '防守線(10MA)']]
                    styled_w = w_result.style.set_properties(**{'text-align': 'center'})\
                        .map(color_risk, subset=['綜合風險(1-10分)'])\
                        .format({"短壓(5日高)": "{:.2f}", "股價": "{:.2f}", "攻擊線(5MA)": "{:.2f}", "防守線(10MA)": "{:.2f}"})
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

    # ---------------- 分頁 4: 游擊隊戰術手冊 (含每日輪播小知識) ----------------
    with tab4:
        st.markdown("### 📖 <span class='highlight-gold'>游擊隊戰術手冊 (短線進出必備)</span>", unsafe_allow_html=True)
        
        # 每日動態輪播小知識系統
        daily_tips = [
            "【游擊鐵則】買股票就像搭公車，錯過這班還有下一班，千萬別去追那台已經開上國道狂飆的！",
            "【停損奧義】停損就像切盲腸，切的時候很痛，但不切會要命。跌破10MA請無情揮刀！",
            "【資金控管】永遠不要把子彈一次打光！留得青山在，不怕沒底抄。",
            "【看盤心法】別人恐慌我貪婪，但別人跳樓你別跟著跳。看懂 VIX 恐慌指數，勝過聽一百個大師。",
            "【籌碼識人】外資常常隔日沖，投信才是真愛粉。跟著投信大哥連續買超的腳步，吃香喝辣！",
            "【獲利心魔】賺錢賣飛不可恥，可恥的是抱到變虧錢！遇壓記得先收割一半，入袋為安。",
            "【均線理論】5MA是油門，10MA是煞車。煞車壞了(跌破10MA)還不跑，神仙也難救！"
        ]
        day_of_year = datetime.now().timetuple().tm_yday
        today_tip = daily_tips[day_of_year % len(daily_tips)]
        
        st.info(f"💡 **【每日游擊錦囊】** {today_tip}")
        
        st.markdown("""
        #### 1. 什麼是「乖離率 (Bias)」？
        * **白話文：** 就是「股價目前跑離均線(月線)有多遠」。想像月線是主人，股價是小狗，狗跑太遠總會被拉回來。
        * **實戰判斷：** 乖離率 `> 10%` 代表小狗暴衝，隨時會被拉回倒貨（極高風險）！乖離率落在 `0% ~ 5%` 之間，代表股價剛在均線附近熱身，是最安全的切入點。
        
        #### 2. 短線游擊三線：5MA / 10MA / 月線(20MA)
        * **攻擊線 (5MA)：** 過去 5 天的平均成本。股價站在它上面，代表正在「飆車」。跌破 5MA，代表短線油門鬆了，游擊隊應該**開始減碼 30%~50% 鎖定獲利**。
        * **防守線 (10MA)：** 過去 10 天的平均成本。跌破代表短波段趨勢轉弱。游擊戰最忌諱長抱，**跌破 10MA 且 3 天站不回，應無條件停損/停利全出**！
        * **生命線 (月線 20MA)：** 股票的生死交界。跌破月線的股票，游擊隊**絕對不碰**。
        
        #### 3. 投信籌碼狀態：連買 2~3 天最好！
        * **剛卡位 (1天)：** 還在試水溫，不用急。
        * **⭐ 建倉 (2-3天)：** 最佳伏擊點！大戶剛進場，股價通常還沒飛太遠。
        * **⚠️ 追高 (4-7天)：** 新聞開始大報，散戶進場，肉剩不多，容易被洗盤。
        * **💀 危險 (8天以上)：** 投信準備結帳，隨時可能大倒貨，誰買誰當接盤俠！
        
        #### 4. 綜合風險評分 (1~10 分) 怎麼看？
        這是系統綜合了「美股指數(費半/那指)跌破月線沒」、「VIX恐慌指數有沒有飆高」、「個股乖離率」與「個股有沒有站穩均線」算出來的防禦力分數。
        * **🟢 8~10分：** 大環境順風順水，個股位階安全，可以大膽佈局。
        * **🟡 4~7分：** 盤勢震盪，請嚴控資金，別重壓。
        * **🔴 1~3分：** 大盤烏雲密布或個股漲翻天，請綁死手上的現金！
        """)

    # ---------------- 分頁 5: 軍火庫開發史 ----------------
    with tab5:
        st.markdown("### 📜 <span class='highlight-silver'>軍火庫開發史 (Version History)</span>", unsafe_allow_html=True)
        st.markdown("""
        這是一座由大將軍親自指揮，從零打造的現代化台股游擊兵工廠。
        
        * **v15.0 傳奇軍師版：** 新增動態嘲諷士氣問候語、戰術手冊每日輪播小知識、第五分頁版本歷史紀錄。
        * **v14.0 終極游擊兵法版：** 廢除無用的20日高低點，改採短線游擊三線(5MA/10MA)。新增 ETF 精準識別、第一軍團附屬「自動化作戰計畫」與小數點去零優化，並建立游擊隊戰術手冊。
        * **v13.0 絕對防禦磐石版：** 演算法核心大改，導入美股(費半/那指)與 VIX 恐慌指數連動。將「最安全、防禦力最高」的標的排在 S 級 Top 3，徹底落實不追高的保本兵法。
        * **v12.0 戰神金字塔版：** 導入「AI 量能權重演算法」，將流動性底線強制拉高至 1000 張，剔除無量殭屍股。
        * **v11.0 戰神分級版：** 條件放寬並首創 S/A/B 級分級推薦制度，解決嚴苛條件下標的過少的問題。
        * **v9.0 ~ v10.0 霸王完全體：** 導入最高科技的「Google 雲端試算表自動同步」，並加入持股損益自動精算（紅綠燈顯示）與 1-10分綜合風險評估。
        * **v8.0 量能覺醒版：** 導入突破 5 日均量的攻擊點火訊號。
        * **v6.0 ~ v7.0 現代化指揮中心：** 三大法人全數歸位，新增 10 日投信連買追蹤雷達，並對接台股官方產業字典。
        * **v4.0 ~ v5.0 闇黑統帥版：** 全面黑化高質感 UI 上線，加入 Top 3 戰術推薦卡片。
        * **v1.0 ~ v3.0 拓荒時期：** 在歷經無數次滑鼠沒圈好、括號沒關閉的 Bug 陣痛期中，奠定了軍火庫的基礎。
        """)
else:
    st.error("情報截獲失敗，可能是國定假日或證交所連線異常。")
