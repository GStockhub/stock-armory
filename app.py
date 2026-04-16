import streamlit as st
import pandas as pd
import numpy as np
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf
import concurrent.futures

# ==============================================================================
# 【第一區塊：系統底層與現代化防禦配置】
# ==============================================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="游擊隊終極軍火庫 v23",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded" 
)

st.markdown("""
    <style>
    .stApp { background-color: #121619; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, li { color: #D1D5DB !important; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
    .highlight-gold { color: #F59E0B !important; font-weight: 900; }
    .highlight-cyan { color: #38BDF8 !important; font-weight: 800; }
    .highlight-red { color: #EF4444 !important; font-weight: 900; }
    .highlight-green { color: #10B981 !important; font-weight: 900; }
    .stTabs [data-baseweb="tab-list"] { display: flex; flex-wrap: wrap; gap: 8px; background-color: transparent; padding-bottom: 10px; }
    .stTabs [data-baseweb="tab"] { flex-grow: 1; text-align: center; height: auto; min-height: 45px; background-color: #1F2937; border-radius: 8px; color: #9CA3AF; border: 1px solid #374151; font-size: 16px; font-weight: bold; padding: 8px 15px; white-space: nowrap; }
    .stTabs [aria-selected="true"] { background-color: #374151 !important; color: #F59E0B !important; border-bottom: 4px solid #F59E0B !important; }
    .tier-card { background-color: #1F2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; margin-bottom: 15px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5); }
    [data-testid="stSidebar"] { background-color: #0F1115; border-right: 1px solid #1F2937; }
    [data-testid="stDataFrame"] { border-radius: 10px !important; overflow: hidden; }
    .discipline-box { background-color: #2D1A1A; border-left: 5px solid #EF4444; padding: 15px; margin-bottom: 15px; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 【第二區塊：側邊欄 (Sidebar) & 總部紀律風控】
# ==============================================================================

with st.sidebar:
    st.markdown("### ⚙️ 總部紀律設定 (v23)")
    st.markdown("---")
    sheet_url = st.text_input("輸入 Google Sheets CSV 網址：", value="", placeholder="https://docs.google.com/.../pub?output=csv")
    st.markdown("---")
    st.markdown("#### 💰 機構級資金控管")
    total_capital = st.number_input("作戰本金 (元)", value=200000, step=10000)
    risk_tolerance_pct = st.slider("單筆最大虧損容忍 (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
    risk_amount = total_capital * (risk_tolerance_pct / 100)
    
    st.info(f"🛡️ **單筆保命底線：{risk_amount:,.0f} 元**\n\n*(依此反推單筆最多買進張數)*")
    
    st.markdown("#### 🛡️ 總曝險與戰略預備金")
    MAX_EXPOSURE_RATE = 0.60
    max_market_cap = total_capital * MAX_EXPOSURE_RATE
    st.warning(f"⚔️ **最高作戰資金 (60%)：{max_market_cap:,.0f} 元**\n\n🛡️ **戰略預備部隊 (40%)：{total_capital - max_market_cap:,.0f} 元**\n*(雷打不動，極端避險與股災專用)*")

    st.markdown("---")
    if st.button("🔄 一鍵清空情報快取"):
        st.cache_data.clear()
        st.success("快取已清除！請重新載入。")

st.markdown("<h1 style='text-align: center;' class='highlight-gold'>⚔️ 游擊隊終極軍火庫 v23</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9CA3AF;'>—— 終極紀律版 ✕ 稅費扣血真實精算 ✕ EOD 實戰決策系統 ——</p>", unsafe_allow_html=True)

current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
st.caption(f"<div style='text-align: center; color: #6B7280;'>📡 雷達最後掃描時間：{current_time}</div>", unsafe_allow_html=True)

# ==============================================================================
# 【第三區塊：強效大盤診斷與三層產業字典】
# ==============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def load_industry_map():
    ind_map, name_map = {}, {}
    try:
        # 🛡️ 雲端穿甲彈：透過 AllOrigins 代理伺服器，完美繞過證交所封鎖 Streamlit 的 IP！
        url = "https://api.allorigins.win/raw?url=https%3A%2F%2Fopenapi.twse.com.tw%2Fv1%2Fopendata%2Ft187ap03_L"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            for item in res.json():
                cid = str(item.get('公司代號', '')).strip()
                ind_map[cid] = str(item.get('產業類別', '其他')).strip()
                name_map[cid] = str(item.get('公司名稱', cid)).strip()
    except: pass

    # ★ 完美修正：方法二 (終極防線，當 API 被擋時，直接暴力解析證交所網頁)
    if len(ind_map) < 100:
        try:
            res = requests.get("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", headers=headers, verify=False, timeout=10)
            res.encoding = 'big5'
            dfs = pd.read_html(res.text)
            df = dfs[0]
            df.columns = df.iloc[0]
            for _, row in df.iterrows():
                if pd.isna(row.get('產業別')): continue
                sec_str = str(row.get('有價證券代號及名稱', ''))
                if '　' in sec_str:
                    parts = sec_str.split('　')
                    cid = parts[0].strip()
                    if cid.isdigit() and len(cid) == 4:
                        ind_map[cid] = str(row['產業別']).strip()
                        name_map[cid] = parts[1].strip()
        except: pass

    return ind_map, name_map

TWSE_IND_MAP, TWSE_NAME_MAP = load_industry_map()

# 第二道防線：本地權值股補丁
LOCAL_PATCH = {
    "2330": "電子與半導體", "2317": "電腦及週邊", "2454": "半導體", "2308": "電子零組件",
    "2382": "電腦及週邊", "2881": "金融保險", "2882": "金融保險", "2891": "金融保險",
    "3231": "電腦及週邊", "2603": "航運業", "3008": "光電業", "2303": "半導體",
    "3711": "半導體", "2886": "金融保險", "2884": "金融保險", "2002": "鋼鐵工業"
}

def safe_download(sym, retries=3):
    for _ in range(retries):
        try:
            df = yf.Ticker(sym).history(period="3mo")
            if not df.empty and len(df) > 5: return df
        except:
            time.sleep(0.5 + np.random.rand())
    return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_dashboard():
    score = 5.0
    macro_data = []
    
    indices = {
        "^TWII": ("台股加權", "2330.TW"),
        "^PHLX_SO": ("美費半導體", "SOXX"),
        "^IXIC": ("那斯達克", "QQQ"),
        "^VIX": ("恐慌指數", "VIXY")
    }
    
    for main_sym, (base_name, fallback_sym) in indices.items():
        display_name = base_name
        hist = safe_download(main_sym)
        
        # 啟動備援機制
        if hist.empty:
            hist = safe_download(fallback_sym)
            if not hist.empty:
                display_name = f"{base_name} (備援: {fallback_sym.replace('.TW','')})"
        
        if hist.empty:
            macro_data.append({"戰區": display_name, "現值": "抓取失敗", "月線": "-", "狀態": "⚪ 斷線"})
            continue
            
        try:
            # history() 回傳的不會有 MultiIndex 結構，直接取 Close 即可
            close_s = hist['Close']
            last_p = float(close_s.iloc[-1])
            ma20 = float(close_s.rolling(20).mean().iloc[-1])
            status = "🟢 多頭" if last_p > ma20 else "🔴 空頭"
            
            if base_name == "恐慌指數":
                status = "🔴 恐慌" if last_p > 25 else ("🟡 警戒" if last_p > 18 else "🟢 安定")
                if last_p > 25: score -= 2
                elif last_p < 18: score += 1
            else:
                if last_p > ma20: score += 1
                else: score -= 1
                
            macro_data.append({"戰區": display_name, "現值": f"{last_p:.2f}", "月線": f"{ma20:.2f}", "狀態": status})
        except: 
            macro_data.append({"戰區": display_name, "現值": "計算失敗", "月線": "-", "狀態": "⚪ 斷線"})
            continue
        
    return max(1, min(10, int(score))), pd.DataFrame(macro_data)

MACRO_SCORE, MACRO_DF = get_macro_dashboard()

# ==============================================================================
# 【第四區塊：真・實戰定檔量化回測引擎 (v23)】
# ==============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_chips_data():
    chip_dict = {}
    date_ptr = datetime.now()
    attempts = 0
    while len(chip_dict) < 10 and attempts < 15:
        if date_ptr.weekday() < 5:
            d_str = date_ptr.strftime("%Y%m%d")
            url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={d_str}&selectType=ALLBUT0999&response=json"
            try:
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5, verify=False).json()
                if res.get('stat') == 'OK':
                    df = pd.DataFrame(res['data'], columns=res['fields'])
                    tru_cols = [c for c in df.columns if '投信' in c and '買賣超' in c]
                    for_cols = [c for c in df.columns if '外資' in c and '買賣超' in c]
                    self_cols = [c for c in df.columns if '自營' in c and '買賣超' in c]
                    
                    def parse_col(col_name):
                        return pd.to_numeric(df[col_name].astype(str).str.replace(',', ''), errors='coerce').fillna(0) / 1000

                    clean = pd.DataFrame()
                    clean['代號'] = df[[c for c in df.columns if '代號' in c][0]]
                    clean['名稱'] = df[[c for c in df.columns if '名稱' in c][0]]
                    clean['投信(張)'] = parse_col(tru_cols[0]) if tru_cols else 0
                    clean['外資(張)'] = sum(parse_col(c) for c in for_cols)
                    clean['自營(張)'] = sum(parse_col(c) for c in self_cols)
                    clean['三大法人合計'] = clean['投信(張)'] + clean['外資(張)'] + clean['自營(張)']
                    
                    chip_dict[d_str] = clean
                    time.sleep(0.2)
            except: pass
        date_ptr -= timedelta(days=1)
        attempts += 1
    return chip_dict

def format_lots(shares):
    shares = int(shares)
    lots = shares / 1000
    if lots <= 0: return "0"
    return f"{lots:.3f}".rstrip('0').rstrip('.')

def fetch_single_stock(sid):
    try:
        df = yf.Ticker(f"{sid}.TW").history(period="3mo")
        if not df.empty and len(df) >= 20:
            return sid, df
    except: pass
    return sid, None

@st.cache_data(ttl=1800, show_spinner=False)
def level2_quant_engine(id_tuple):
    id_list = list(id_tuple)
    intel_results = []
    if not id_list: return pd.DataFrame()
    
    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_single_stock, sid): sid for sid in id_list}
        for future in concurrent.futures.as_completed(futures):
            sid, df = future.result()
            if df is not None:
                bulk_data[sid] = df
            
    for sid in id_list:
        try:
            if not sid.startswith('00') and not sid.isdigit():
                continue

            ind = TWSE_IND_MAP.get(sid) or LOCAL_PATCH.get(sid) or "其他"
            if sid.startswith('00'): ind = "ETF"
            if ind == "金融保險": continue
            
            df_stock = bulk_data.get(sid)
            if df_stock is None or df_stock.empty: continue
            
            close_s = df_stock['Close']
            open_s = df_stock['Open']
            vol_s = df_stock['Volume']
            
            p_now = float(close_s.iloc[-1])
            vol_now = float(vol_s.iloc[-1]) / 1000
            
            if p_now < 20 or vol_now < 1.5: continue
            
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            vol_ma5 = float(vol_s.rolling(5).mean().iloc[-1]) / 1000
            
            bias = ((p_now - m20) / m20) * 100
            
            trend_strength = (m5 > m10) and (m10 > m20)
            last_10_max = close_s.iloc[-10:].max()
            last_20_max = close_s.iloc[-20:].max()
            recent_high = (last_10_max >= last_20_max) 
            pullback_stand = (p_now >= m5) and (p_now <= m5 * 1.03) 
            
            is_candidate = trend_strength and recent_high and pullback_stand
            is_volume_breakout = (vol_now > 1.5) and (vol_now > vol_ma5 * 1.2) 
            
            df_bt = pd.DataFrame({'Close': close_s, 'Open': open_s})
            df_bt['MA5'] = df_bt['Close'].rolling(5).mean()
            df_bt['MA10'] = df_bt['Close'].rolling(10).mean()
            df_bt['MA20'] = df_bt['Close'].rolling(20).mean()
            df_bt['RollMax20'] = df_bt['Close'].rolling(20).max()
            
            sig_mask = (
                (df_bt['MA5'] > df_bt['MA10']) & (df_bt['MA10'] > df_bt['MA20']) &
                (df_bt['Close'] >= df_bt['MA5']) & (df_bt['Close'] >= df_bt['RollMax20'] * 0.98)
            )
            signals_idx = df_bt[sig_mask].index
            
            sim_returns = []
            for i in range(len(signals_idx)):
                idx = signals_idx[i]
                loc_idx = df_bt.index.get_loc(idx)
                if loc_idx + 1 >= len(df_bt): continue 
                
                entry_p = df_bt.iloc[loc_idx + 1]['Open']
                prev_close = df_bt.iloc[loc_idx]['Close']
                
                if entry_p > prev_close * 1.02: continue
                
                future_data = df_bt.iloc[loc_idx + 1 : loc_idx + 11] 
                if future_data.empty: continue
                
                stop_loss = max(df_bt.iloc[loc_idx]['MA10'], entry_p * 0.97) 
                sold_half = False
                ret = 0.0
                
                for f_idx, row in future_data.iterrows():
                    curr_p = row['Close']
                    if curr_p > entry_p * 1.05: stop_loss = max(stop_loss, entry_p) 
                    
                    if curr_p < stop_loss:
                        if sold_half: ret = 0.5 * 0.06 + 0.5 * ((stop_loss - entry_p) / entry_p)
                        else: ret = (stop_loss - entry_p) / entry_p
                        break
                    
                    if not sold_half and curr_p >= entry_p * 1.06:
                        sold_half = True
                        if curr_p >= entry_p * 1.10: 
                            ret = 0.5 * 0.06 + 0.5 * 0.10
                            break
                    elif sold_half and curr_p >= entry_p * 1.10:
                        ret = 0.5 * 0.06 + 0.5 * 0.10
                        break
                else: 
                    final_p = future_data['Close'].iloc[-1]
                    if sold_half: ret = 0.5 * 0.06 + 0.5 * ((final_p - entry_p) / entry_p)
                    else: ret = (final_p - entry_p) / entry_p
                    
                sim_returns.append(ret)
                
            win_rate, avg_ret = ((np.array(sim_returns) > 0).mean() * 100, np.array(sim_returns).mean() * 100) if sim_returns else (50.0, 0.0)

            name = TWSE_NAME_MAP.get(sid, sid)
            s_score = MACRO_SCORE
            if p_now > m5: s_score += 1
            if p_now > m20: s_score += 1
            else: s_score -= 2
            if bias > 10: s_score -= 2
            elif 0 <= bias <= 5: s_score += 2

            stop_loss = max(m10, p_now * 0.97) 
            take_profit = p_now * 1.10 
            
            intel_results.append({
                '代號': sid, '名稱': name, '產業': ind, '現價': p_now, '成交量': vol_now, '今日放量': is_volume_breakout,
                'M5': m5, 'M10': m10, 'M20': m20, '乖離(%)': bias, '基本達標': is_candidate,
                '安全指數': max(1, min(10, int(s_score))),
                '勝率(%)': win_rate, '均報(%)': avg_ret,
                '停損價': stop_loss, '停利價': take_profit, 
                '原始風險差額': p_now - stop_loss
            })
        except: continue
            
    return pd.DataFrame(intel_results)

# ==============================================================================
# 【第五區塊：旗艦分頁渲染 (EOD 輸出與風控)】
# ==============================================================================

if MACRO_SCORE <= 3:
    st.error(f"🔴 **最高紅色警戒 (大盤分數 {MACRO_SCORE}/10)**：市場極度恐慌！系統建議：**【全面停止交易】**，保留 100% 現金。", icon="🚨")
elif MACRO_SCORE <= 5:
    st.warning(f"🟡 **黃色警戒 (大盤分數 {MACRO_SCORE}/10)**：大盤偏弱。系統建議：**【只做乖離<3%的股票，且資金減半】**。", icon="⚠️")

with st.spinner('情報兵正在進行職業級波段回測與籌碼精算 (v23 紀律版)...'):
    chip_db = fetch_chips_data()

if len(chip_db) >= 3:
    dates = sorted(list(chip_db.keys()), reverse=True)
    today_df = chip_db[dates[0]].copy()
    
    for i, d in enumerate(dates):
        today_df = pd.merge(today_df, chip_db[d][['代號', '投信(張)']].rename(columns={'投信(張)': f'D{i}'}), on='代號', how='left').fillna(0)
    
    def get_streak(r):
        s = 0
        for i in range(len(dates)):
            if r.get(f'D{i}', 0) > 0: s += 1
            else: break
        return s
    today_df['連買'] = today_df.apply(get_streak, axis=1)

    top_80_chips = today_df.sort_values('投信(張)', ascending=False).head(80)['代號'].tolist()
    
    t_rank, t_chip, t_cmd, t_book, t_hist = st.tabs([
        "🎯 職業波段 S/A/B 推薦", "🔥 三大法人籌碼流向", "🏦 司令部資金風控", "📖 實戰與名詞教範", "📜 系統演進史"
    ])

    with t_rank:
        st.markdown("### 👑 <span class='highlight-gold'>今日 AI 戰神決策清單 (EOD 輸出版)</span>", unsafe_allow_html=True)
        
        st.markdown("""
        <div class="discipline-box">
            <h4 style="color: #EF4444; margin-top: 0;">🛑 盤前/盤中執行鐵律 (不符合嚴禁買進)</h4>
            1. <b>過濾跳空</b>：開盤價若比昨收 <b>高出 2% 以上</b>，直接放棄不買。<br>
            2. <b>開盤五分鐘法則</b>：9:00~9:05 嚴禁下單。9:05 後若股價 <b>跌破今日開盤價</b> 或 <b>跌破 5MA</b>，當日放棄。<br>
            3. <b>單日交易上限</b>：每天 <b>最多只開 3 筆新單</b>，挑名單最上面的買。<br>
            4. <b>死抱鐵律</b>：進場後，沒到 <b>+6%</b> 絕對不准賣！沒跌破 <b>-3% (或10MA)</b> 絕對不准砍！
        </div>
        """, unsafe_allow_html=True)

        with st.expander("🌍 查看全球大盤診斷表 (Level 1)"):
            if not MACRO_DF.empty:
                st.dataframe(MACRO_DF.style.set_properties(**{'text-align': 'center'}).map(lambda x: 'color: #10B981;' if '多頭' in str(x) or '安定' in str(x) else ('color: #EF4444;' if '空頭' in str(x) or '恐慌' in str(x) else ''), subset=['狀態']), use_container_width=True, hide_index=True)
                if "抓取失敗" in MACRO_DF['現值'].values:
                    st.warning("⚠️ 部分大盤數據 API 阻擋，已啟用備援或忽略該指數。")
            else:
                st.warning("⚠️ 大盤數據抓取異常。")

        pool_ids = today_df[today_df['連買'] >= 1]['代號'].tolist() 
        calc_list = tuple(set(pool_ids + top_80_chips))
        
        if calc_list and MACRO_SCORE > 3: 
            intel_df = level2_quant_engine(calc_list).copy() 
            
            if not intel_df.empty:
                def calc_suggested_lots(row):
                    if row['原始風險差額'] > 0:
                        max_shares = risk_amount / row['原始風險差額']
                        capital_limit_shares = (total_capital * 0.15) / row['現價'] 
                        suggested_shares = min(max_shares, capital_limit_shares)
                    else: suggested_shares = 0
                    if MACRO_SCORE <= 5: suggested_shares *= 0.5
                    return format_lots(suggested_shares)
                    
                intel_df['建議買量(張)'] = intel_df.apply(calc_suggested_lots, axis=1)
                final_rank = pd.merge(today_df, intel_df, on='代號')

                final_rank['Score'] = (
                    final_rank['均報(%)'] * 150 +  
                    final_rank['勝率(%)'] * 15 +   
                    final_rank['安全指數'] * 100 - 
                    abs(final_rank['乖離(%)']) * 50
                )
                final_rank.loc[final_rank['今日放量'] == True, 'Score'] += 100 
                
                rank_sorted = final_rank.sort_values('Score', ascending=False).reset_index(drop=True)
                
                strict_mask = (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] >= 55) & (rank_sorted['均報(%)'] >= 1.5) & (rank_sorted['今日放量'] == True) & (rank_sorted['連買'] >= 2)
                s_minus_mask = (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] >= 50) & (rank_sorted['均報(%)'] >= 1.0) & (rank_sorted['連買'] >= 1)
                med_mask = (~strict_mask) & (~s_minus_mask) & (rank_sorted['勝率(%)'] > 50) & (rank_sorted['成交量'] >= 1.5) & (rank_sorted['連買'] >= 1) & (rank_sorted['乖離(%)'] < 10)
                scout_mask = (~strict_mask) & (~s_minus_mask) & (~med_mask) & (rank_sorted['成交量'] >= 1.5) & (rank_sorted['連買'] >= 1)

                if MACRO_SCORE <= 5:
                    strict_mask = strict_mask & (rank_sorted['乖離(%)'] < 3)
                    s_minus_mask = s_minus_mask & (rank_sorted['乖離(%)'] < 3)
                    med_mask = med_mask & (rank_sorted['乖離(%)'] < 3)

                s_tier = rank_sorted[strict_mask].head(3)
                using_s_minus = False
                if s_tier.empty:
                    using_s_minus = True
                    s_tier = rank_sorted[s_minus_mask].head(3)
                
                ab_tier = rank_sorted[med_mask].head(7)
                scout_tier = rank_sorted[scout_mask].head(20)
                
                display_list = pd.concat([s_tier, ab_tier]).reset_index(drop=True)
                display_list['名次'] = display_list.index + 1
                
                # ★ 完美修正：您指定的 CSV 強制修剪小數點模組
                if not display_list.empty:
                    # 1. 先把要匯出的資料獨立抓出來
                    export_df = display_list[['名次', '代號', '名稱_x', '產業', '勝率(%)', '均報(%)', '現價', '停損價', '建議買量(張)']].rename(columns={'名稱_x':'名稱'}).copy()
                    
                    # 2. 強制修剪小數點 (戰場淨化)
                    export_df['勝率(%)'] = export_df['勝率(%)'].round(1)
                    export_df['均報(%)'] = export_df['均報(%)'].round(2)
                    export_df['現價'] = export_df['現價'].round(2)
                    export_df['停損價'] = export_df['停損價'].round(2)
                    
                    # 3. 轉成 CSV 匯出
                    csv_data = export_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="💾 一鍵下載今日作戰清單 (供明日盤中快速對照執行)",
                        data=csv_data,
                        file_name=f"Tactical_List_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                    )
                
                if using_s_minus:
                    st.warning("⚠️ **系統判定：今日無完美 S 級標的。自動啟動【S-級】次級伏擊備援名單！**", icon="🛡️")
                    st.markdown("#### 🥈 【S-級】次級伏擊備援 (勝率>50, 均報>1.0)")
                    border_color, title_color = "#38BDF8", "#38BDF8"
                else:
                    st.markdown("#### 🥇 【S級】強勢回檔狙擊核心 (符合極嚴格職業濾網)")
                    border_color, title_color = "#F59E0B", "#F59E0B"

                if s_tier.empty:
                    st.info("💡 今日連 S- 級備援都無標的符合。市場極難操作，請空手觀望！")
                else:
                    cols_s = st.columns(3)
                    for i in range(len(s_tier)):
                        r = display_list.iloc[i]
                        with cols_s[i]:
                            st.markdown(f"""
                            <div class="tier-card" style="border-top: 5px solid {border_color};">
                                <h3 style="margin:0; color:{title_color};">{r['名次']}. {r['名稱_x']} ({r['代號']})</h3>
                                <p style="color:#9CA3AF; margin:5px 0 10px 0;">{r['產業']} | 投信連買 {r['連買']} 天</p>
                                <div style="background-color: #111827; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
                                    📊 <b>職業回測 (隔日進場/-3%損):</b><br>
                                    勝率：<span class="highlight-green">{r['勝率(%)']:.1f}%</span> | 均報：<span class="highlight-cyan">+{r['均報(%)']:.2f}%</span>
                                </div>
                                <div style="font-size: 15px; line-height: 1.6;">
                                    🛡️ <b>安全指數：</b> {r['安全指數']} 分<br>
                                    💰 <b>現價(進場)：</b> <span class="highlight-gold">{r['現價']:.2f}</span> (乖離 {r['乖離(%)']:.1f}%)<br>
                                    🚨 <b>防爆停損：</b> <span class="highlight-red">{r['停損價']:.2f}</span><br>
                                    ⚖️ <b>AI 建議買量：</b> <span class="highlight-cyan">{r['建議買量(張)']}</span> 張
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                
                def risk_color(val):
                    try:
                        v = int(val)
                        if v >= 8: return 'color: #10B981; font-weight: bold;'
                        elif v <= 3: return 'color: #EF4444; font-weight: bold;'
                        return 'color: #F59E0B; font-weight: bold;'
                    except: return ''

                st.markdown("#### ⚔️ 【A/B級】次級波段與伏擊清單 (勝率 > 50%)")
                if ab_tier.empty:
                    st.info("💡 今日無次級符合標的。")
                else:
                    ab_disp = display_list.iloc[len(s_tier):][['名次','代號','名稱_x','產業','安全指數','勝率(%)','均報(%)','現價','停損價','建議買量(張)','連買']].rename(columns={'名稱_x':'名稱'})
                    styled_ab = (ab_disp.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '停損價':'{:.2f}', '勝率(%)':'{:.1f}%', '均報(%)':'{:.2f}%'})
                                    .map(risk_color, subset=['安全指數'])
                                    .map(lambda x: 'color: #10B981; font-weight: bold;' if x > 60 else '', subset=['勝率(%)']))
                    st.dataframe(styled_ab, use_container_width=True, hide_index=True)

                st.markdown("---")
                st.markdown(f"### 📡 隱藏版投信建倉遺珠 (階梯放寬版，共 {len(scout_tier)} 檔)")
                if scout_tier.empty:
                    st.info("💡 今日全市場無任何法人連買觀察標的。")
                else:
                    scout_tier['名次'] = range(len(display_list)+1, len(display_list)+1+len(scout_tier))
                    scout_tier['戰術'] = scout_tier.apply(lambda r: "💎 低檔潛伏" if r['乖離(%)'] < 3 else ("🚀 突破點火" if r['今日放量'] else "⏳ 盤整"), axis=1)
                    styled_scout = (scout_tier[['名次','代號','名稱_x','產業','安全指數','勝率(%)','現價','乖離(%)','連買','戰術']].rename(columns={'名稱_x':'名稱'})
                                    .style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '勝率(%)':'{:.1f}%', '乖離(%)':'{:.1f}%'})
                                    .map(risk_color, subset=['安全指數']))
                    st.dataframe(styled_scout, use_container_width=True, hide_index=True)
        else:
            if MACRO_SCORE > 3:
                st.warning("⚔️ 報告將軍，今日無資料或無標的符合。")

    with t_chip:
        st.markdown("### 🔥 全市場三大法人籌碼流向")
        surprise_atk = today_df[(today_df['連買'] == 1) & (today_df['投信(張)'] > 0) & (today_df['外資(張)'] > 0)].sort_values('三大法人合計', ascending=False).head(3)
        if not surprise_atk.empty:
            st.markdown("#### 🚨 土洋合擊！首日突擊部隊")
            st.write("昨日未買，今日**「外資與投信同步大買」**的極強勢起漲訊號：")
            st.dataframe(surprise_atk[['代號','名稱','外資(張)','投信(張)','自營(張)','三大法人合計']].style.format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}','自營(張)':'{:,.0f}','三大法人合計':'{:,.0f}'}), use_container_width=True, hide_index=True)
            st.markdown("---")
            
        st.markdown("#### 穩健建倉部隊 (依三大法人合計買超排序，過濾 Top 200 以防卡頓)")
        main_chips = today_df.sort_values('三大法人合計', ascending=False).head(200)
        
        if 'intel_df' in locals() and not intel_df.empty:
            main_chips = pd.merge(main_chips, intel_df[['代號', '安全指數']], on='代號', how='left')
            main_chips['安全指數'] = main_chips['安全指數'].apply(lambda x: f"{int(x)}" if pd.notna(x) else "-")
        else:
            main_chips['安全指數'] = '-'
            
        st.dataframe(main_chips[['代號','名稱','連買','安全指數','外資(張)','投信(張)','自營(張)','三大法人合計']]
                     .style.set_properties(**{'text-align': 'center'})
                     .format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}','自營(張)':'{:,.0f}','三大法人合計':'{:,.0f}'})
                     .map(risk_color, subset=['安全指數']), height=500, use_container_width=True, hide_index=True)

    with t_cmd:
        st.markdown("### 🏦 <span class='highlight-gold'>司令部：帳戶風控與真實稅費精算</span>", unsafe_allow_html=True)
        if not sheet_url:
            st.info("💡 **行動指南**：請在左側邊欄輸入您的 Google Sheets CSV 網址以啟用風控檢查。")
        else:
            try:
                sheet_df = pd.read_csv(sheet_url, dtype=str)
                sheet_df.columns = sheet_df.columns.str.strip()
                h_df = sheet_df[sheet_df['分類'] == '持股'].copy()
                
                if not h_df.empty:
                    h_intel = level2_quant_engine(tuple(h_df['代號'].tolist()))
                    if not h_intel.empty:
                        m_df = pd.merge(h_df, h_intel, on='代號', how='inner')
                        m_df = pd.merge(m_df, today_df[['代號', '名稱']], on='代號', how='left').fillna('未知')
                        res_h, total_pnl, current_exposure = [], 0, 0
                        
                        for _, r in m_df.iterrows():
                            try:
                                p_now = float(r['現價'])
                                p_cost = float(r['成本價']) if pd.notna(r['成本價']) else 0
                                qty = float(r['庫存張數']) if pd.notna(r['庫存張數']) else 0
                                
                                # ★ v23 稅費真實計算 (手續費預設 5 折，買賣皆收 + 賣出收千分之3證交稅)
                                fee_rate = 0.001425 * 0.5
                                tax_rate = 0.003
                                
                                buy_fee = (p_cost * qty * 1000) * fee_rate
                                sell_fee = (p_now * qty * 1000) * fee_rate
                                sell_tax = (p_now * qty * 1000) * tax_rate
                                
                                buy_cost_total = (p_cost * qty * 1000) + buy_fee
                                sell_revenue_net = (p_now * qty * 1000) - sell_fee - sell_tax
                                
                                pnl = sell_revenue_net - buy_cost_total
                                ret = (pnl / buy_cost_total) * 100 if buy_cost_total > 0 else 0
                                
                                current_exposure += (p_now * qty * 1000)
                                total_pnl += pnl
                                
                                act = "✅ 抱緊處理 (未達+6%)"
                                if ret >= 10: act = "💰 +10% 達標 (強制全出)"
                                elif ret >= 6: act = "🛡️ +6% 達標 (賣出一半鎖利)"
                                elif p_now < r['M10'] or ret <= -3: act = "💀 破線硬停損 (無情砍倉)"
                                
                                if '買進日期' in r and pd.notna(r['買進日期']):
                                    try:
                                        days_held = (datetime.now() - pd.to_datetime(r['買進日期'])).days
                                        if days_held >= 10 and ret < 6 and act == "✅ 抱緊處理 (未達+6%)": 
                                            act = "⏳ 資金卡死 (≥10天強制換股)"
                                    except: pass
                                
                                res_h.append({'代號': r['代號'], '名稱': r['名稱_y'] if '名稱_y' in r else r.get('名稱',''), '現價': p_now, '成本': p_cost, '張數': format_lots(qty * 1000), '真實淨報酬(%)': ret, '淨損益(元)': pnl, '作戰指示': act})
                            except: continue
                            
                        df_res = pd.DataFrame(res_h)
                        p_color = "#EF4444" if total_pnl > 0 else "#10B981"
                        st.markdown(f"#### 💰 目前總淨損益 (已扣稅費)：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                        st.caption("ℹ️ *系統已自動內扣千分之3證交稅與5折買賣手續費，此數字即為您實際可放進口袋的真金白銀。*")
                        
                        if current_exposure > max_market_cap:
                            st.error(f"🚨 **【一級警報】總市場曝險 ({current_exposure:,.0f} 元) 已超過 60% 戰備上限！嚴禁開立任何新單，請優先保護 40% 戰略預備金！**", icon="🛑")
                        else:
                            st.success(f"✅ 總資金健康。戰略預備金仍有餘裕 (目前市場曝險佔比：{(current_exposure/total_capital)*100:.1f}%)")
                            
                        if total_pnl < -total_capital * 0.02:
                            st.error("🚨 **【單日虧損斷路器】今日帳面虧損已達總本金 2%！系統判定情緒不穩，今日強制收手，請關閉看盤軟體！**", icon="🛑")
                            
                        styled_h = (df_res.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '成本':'{:.2f}', '真實淨報酬(%)':'{:.2f}%', '淨損益(元)':'{:,.0f}'})
                                    .map(lambda x: 'color: #EF4444; font-weight: bold;' if x > 0 else ('color: #10B981; font-weight: bold;' if x < 0 else ''), subset=['真實淨報酬(%)', '淨損益(元)']))
                        st.dataframe(styled_h, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"❌ 讀取 Google Sheets 失敗：{e}")

    # --------------------------------------------------------------------------
    # Tab 4: 教戰手冊 (100% 完整無遺漏版 + v23 更新)
    # --------------------------------------------------------------------------
    with t_book:
        st.markdown("### 📖 <span class='highlight-gold'>游擊兵工廠：名詞、圖示與實戰教範大全 (v23 紀律版)</span>", unsafe_allow_html=True)
        
        st.markdown("""
        #### 🔣 系統圖示 (Icons) 權威指南
        * 👑 **今日 AI 戰神決策清單**：系統精算後的最高殿堂。
        * 🥇 **【S級】強勢回檔狙擊核心**：綜合排名前 3 名。符合「多頭排列、創高拉回、高勝率、高均報」的完美標的。
        * 🥈 **【S-級】次級伏擊備援**：當 S 級因大盤惡劣選不出股票時，系統自動啟動的替代名單，以青藍色顯示。
        * ⚔️ **【A/B級】次級波段與伏擊清單**：排名 4~10 名，勝率 > 50% 的穩健標的。
        * 🚨 **警報 / 停損 / 突擊部隊**：代表危險的停損線，或是主力同步暴買的「土洋合擊」。
        * 💀 **破線硬停損 (無情砍倉)**：持股若跌破 10MA 或虧損達 3%，必須無情砍倉。
        * 🛡️ **鎖利保本**：持股獲利超過 5%，停損點自動拉高到「買進成本價」，確保這筆交易絕對不虧錢。
        * ✅ **續抱**：股價健康上攻，讓獲利飛奔。
        * 🎯 **雷達 / S/A/B 推薦**：偵測到的主力作戰目標。
        * 🚀 **突破點火**：今日成交量大於 5日均量 1.2 倍，動能爆發。
        * 💎 **低檔潛伏**：乖離率 < 3% 的未爆發股，風險極低。
        * ⏳ **盤整**：籌碼雖好，但股價還在均線糾結處睡覺。
        * 🏦 **司令部資金精算**：個人持股盈虧計算機 (已內扣真實稅費)。
        * 🔥 **三大法人籌碼流向**：當日全台股外資、投信、自營商買賣超 Top 200。
        * 📡 **隱藏版投信建倉遺珠**：放寬條件後的後備觀察名單。

        #### 🏫 核心名詞與數據指標解釋
        * **實戰回測 (隔日進場/-3%損/+10%利)**：這是系統最核心的引擎。它模擬在歷史上出現相同訊號時，**「隔天開盤價買進（若跳空>2%則過濾不買）」**。買進後，若達 +6% 先賣一半，達 +10% 賣剩下一半；若跌破 10MA 或虧損 3% 則強制停損。
        * **均報 (%)**：在上述嚴格模擬下，平均每次出手的「真實報酬率」。公式排名極度看重此數值，> 1.5% 屬於頂級印鈔機。
        * **勝率 (%)**：在上述模擬下，能成功獲利出場的機率。
        * **安全指數 (1~10 分)**：大盤 VIX 狀態、個股均線強弱與乖離率的綜合防禦分數。滿分 10 分。
        * **乖離率 (Bias %)**：股價偏離 20 日均線(月線)的百分比。`0% ~ 5%` 為黃金建倉區，`> 10%` 屬於過熱，系統會給予嚴格扣分懲罰。

        #### 🕵️ 系統選股考量與避開陷阱 (將軍必讀)
        * **終極進場條件 (強勢回檔再攻)**：系統嚴格要求 `M5 > M10 > M20` (多頭排列)，且近 10 天曾創過 20 日新高，但現在價格稍微拉回、靠近 M5 才買進。**絕對不追高！**
        * **大盤備援機制**：若大盤加權指數 API 抓取失敗，系統將自動以「台積電 (2330.TW)」或 ETF 替身作為大盤多空判斷基準。
        * **排除妖股與牛皮股**：本系統已自動為您過濾掉「股價小於 20 元」、「成交量低於 1500 張」以及「金融保險業」，專注狙擊具備波動度與流動性的主戰場標的。
        * **大盤宏觀切換 (風控核心)**：
          - 大盤分數 `<= 3`：系統亮紅燈，**停止任何新交易**。
          - 大盤分數 `<= 5`：系統亮黃燈，**只買乖離 < 3% 的股票，且建議資金減半**。

        #### 💰 V23 核心金律：職業級波段風控與紀律
        * **🛡️ 40% 戰略預備金**：系統嚴格要求最高市場曝險為 60%。剩下的 40% 是您的救命錢與股災抄底的核武，平時絕對禁止投入股市。
        * **⏱️ 盤中三道防護線**：
            1. **開盤跳空 > 2% 絕對不買**（避開主力出貨）。
            2. **開盤前 5 分鐘絕不下單**，確認 9:05 後站穩開盤價與 5MA 再進場。
            3. **一天最多只買 3 檔**，挑名單最上面的買，絕不濫射。
        * **🧠 強制出場鐵律**：
            - **獲利端**：未達 +6% **絕對禁止**手癢停利。達 +6% 賣一半鎖利，達 +10% 賣全部。
            - **虧損端**：跌破 10MA 或 -3% 無情砍倉。
            - **時間端**：抱了 10 天還沒達標 +6%，代表資金卡死，直接出場換股。
        * **🛑 單日虧損斷路器**：如果今日帳面虧損達總本金 2%，強制關閉看盤軟體，當日停止交易！
        """)

    # --------------------------------------------------------------------------
    # Tab 5: 系統演進史 (V1~V23 完全無刪減保留)
    # --------------------------------------------------------------------------
    with t_hist:
        st.markdown("### 📜 <span class='highlight-cyan'>游擊兵工廠：開發史 (Chronicles)</span>", unsafe_allow_html=True)
        st.markdown("""
        * **v23.1 (稅費校正熱修復)**：**解決 yfinance API MultiIndex 崩潰問題，全面改用更穩定的 Ticker.history() 提升大盤與個股下載妥善率。司令部實裝「稅費扣血真實精算 (內扣千分之3證交稅與5折手續費)」，讓未實現損益 100% 貼合券商真實淨利。針對 TWSE OpenAPI 添加請求 Headers，完美解決產業別顯示「其他」的 Bug，並透過正則邏輯將非 ETF 且含英文字母之特別股完全剔除。**
        * **v23.0 (終極紀律版)**：從選股工具躍升為 EOD 決策系統。導入盤前作戰清單一鍵匯出 (CSV)。新增 40% 戰略預備金風控鎖、總曝險警報器、單日虧損斷路器。實裝「+6%半出/+10%全出」與「10天資金卡死」強制出場指示。回測跳空過濾嚴格化至 2%。
        * **v22.0 (機構級完全體)**：導入三層資料防護網（TWSE快取+本地權值股+不依賴yfinance）。大盤加入具名備援 ETF 替身。下載引擎降頻至 3 線程防鎖，期間縮短為 3 個月極速版。導入狼性攻擊評分公式，並徹底過濾低價股、低量股與金融股。
        * **v21.5 (機構級戰略版)**：結合頂級戰略思維，寫入 `safe_download` 3 次 Retry 防護裝甲。新增大盤失聯時自動切換「台積電 (2330.TW)」的精準備援機制。實裝 S 級嚴格鐵血防線與 S- 級 (次級伏擊) 自動備援切換，兼顧本金保護與戰術彈性。
        * **v21.1 (極速修復版)**：導入 `concurrent.futures` 多執行緒引擎。
        * **v21.0 (實戰定檔版)**：【停止功能貪婪，回歸穩定】。廢除不穩定的 bulk_download，改用穩定版迴圈防封鎖機制。
        * **v20.0 (職業波段狙擊版)**：進場改為「強勢回檔再攻」；回測改為「隔日開盤價進場且過濾跳空」；停利改為「6%半出/10%全出」；加入「大盤 <=3 停下交易」風控。
        * **v19.0 (攻擊爆發版)**：停利波段拉長至 10%，回測週期延長至 10 天。
        * **v18.0 (實戰真劍勝負版)**：重寫回測引擎，導入真實模擬 (-3%硬停損)。加入「5MA>10MA>20MA」嚴格趨勢濾網。
        * **v17.8 (極致純粹無閹割版)**：為追求極速，無情拔除單兵雷達。
        * **v17.7 (閃電記憶體版)**：導入 `@st.cache_data` 全面包覆 Level 2 量化引擎。
        * **v17.6 (閃電極速版)**：徹底拔除 YFinance `info` 延遲毒瘤，改用靜態 API 字典秒讀產業與名稱。
        * **v17.5 (專注主戰場版)**：拔除上櫃 (.TWO) 掃描邏輯，專注上市市場運算。
        * **v17.4 (洞悉戰場版)**：修剪小數點至兩位以內、排除金融股霸榜疑慮。
        * **v17.3 (實戰無死角版)**：解決外資倒賣顯示異常、張數去零優化。
        * **v17.2 (量化完全體)**：重排分頁順序、籌碼淨化突擊部隊。
        * **v17.1 (熱修復版)**：解決 `AttributeError: applymap` 崩潰問題。
        * **v17.0 (戰神量化版)**：實裝自動換行雙排 Tab 標籤；導入 Level 2 回測引擎；新增側邊欄資金控管。
        * **v16.0 (全裝甲旗艦版)**：確立全球市場戰略桌 (Macro Scan) 機制。
        * **v14.0 (終極兵法版)**：首創「自動化作戰建議」。
        * **v12.0 (量能覺醒版)**：引進成交量 > 1000 張流動性過濾門檻。
        * **v10.0 (雲端司令部)**：首次對接 Google Sheets，實踐雲端資產損益精算。
        * **v8.0 (數據擴充版)**：加入乖離率與均線過濾。
        * **v6.0 (籌碼雷達版)**：對接三大法人數據，確立投信連買核心追蹤。
        * **v4.0 (闇黑統帥版)**：確立 Dark Mode 戰術黑底視覺風格，推出 S/A/B 分級卡片。
        * **v2.0 (防禦升級版)**：加入錯誤捕捉機制。
        * **v1.0 (拓荒基礎版)**：草創期，克服基礎爬蟲與 Streamlit 框架對接。
        """, unsafe_allow_html=True)

else:
    st.error("⚠️ 證交所資料匯入失敗。請檢查網路或稍後再試。")

st.divider()
st.markdown("<p style='text-align: center; color: #9CA3AF;'>© 游擊隊軍火部 - v23.1 終極紀律版 (EOD 實戰系統)</p>", unsafe_allow_html=True)
