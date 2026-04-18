import streamlit as st
import pandas as pd
import numpy as np
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf
import concurrent.futures
import ssl

# 👑 解決大將軍環境的 SSL 憑證錯誤 (CERTIFICATE_VERIFY_FAILED)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# 👑 導入您專屬的外部軍火庫 (教戰手冊與開發史)
from manual import MANUAL_TEXT, HISTORY_TEXT

# ==============================================================================
# 【第一區塊：系統底層與現代化防禦配置】
# ==============================================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="游擊隊終極軍火庫 v24.2",
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
    st.markdown("### ⚙️ 總部紀律設定")
    st.markdown("---")
    sheet_url = st.text_input("輸入【持股部位】CSV 網址：", value="", placeholder="貼上持股分頁網址")
    aar_sheet_url = st.text_input("輸入【交易日誌】CSV 網址：", value="", placeholder="貼上日誌分頁網址(供AAR使用)")
    
    st.markdown("---")
    st.markdown("#### 💰 機構級資金控管")
    total_capital = st.number_input("作戰本金 (元)", value=200000, step=10000)
    risk_tolerance_pct = st.slider("單筆最大虧損容忍 (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
    risk_amount = total_capital * (risk_tolerance_pct / 100)
    st.info(f"🛡️ **單筆保命底線：{risk_amount:,.0f} 元**\n\n*(依此反推單筆最多買進張數)*")
    
    st.markdown("---")
    st.markdown("#### ⚖️ 真實稅費參數")
    fee_discount = st.slider("券商手續費折數 (無折扣=1.0, 五折=0.5)", min_value=0.1, max_value=1.0, value=1.0, step=0.05)
    
    st.markdown("---")
    st.markdown("#### 🛡️ 總曝險與戰略預備金")
    MAX_EXPOSURE_RATE = 0.60
    max_market_cap = total_capital * MAX_EXPOSURE_RATE
    st.warning(f"⚔️ **最高作戰資金 (60%)：{max_market_cap:,.0f} 元**\n\n🛡️ **戰略預備部隊 (40%)：{total_capital - max_market_cap:,.0f} 元**\n*(雷打不動，極端避險與股災專用)*")

    st.markdown("---")
    if st.button("🔄 一鍵清空情報快取"):
        st.cache_data.clear()
        st.success("快取已清除！請重新載入。")

st.markdown("<h1 style='text-align: center;' class='highlight-gold'>⚔️ 游擊隊終極軍火庫 v24.2</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9CA3AF;'>—— 終極番號 ✕ 自訂稅費精算 ✕ 戰術覆盤 ——</p>", unsafe_allow_html=True)

current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
st.caption(f"<div style='text-align: center; color: #6B7280;'>📡 雷達最後掃描時間：{current_time}</div>", unsafe_allow_html=True)

# ==============================================================================
# 【第三區塊：強效大盤診斷與本地產業字典】
# ==============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def load_industry_map():
    ind_map, name_map = {}, {}
    try:
        df = pd.read_csv("industry_map.csv", dtype=str)
        for _, row in df.iterrows():
            cid = str(row['代號']).strip()
            ind_map[cid] = str(row['產業']).strip()
            name_map[cid] = str(row['名稱']).strip()
    except Exception as e:
        pass 
    return ind_map, name_map

TWSE_IND_MAP, TWSE_NAME_MAP = load_industry_map()

LOCAL_PATCH = {
    "2330": "半導體業", "2317": "其他電子業", "2454": "半導體業", "2308": "電子零組件業",
    "2382": "電腦及週邊設備業", "2881": "金融保險業", "2882": "金融保險業", "2891": "金融保險業",
    "3231": "電腦及週邊設備業", "2603": "航運業", "3008": "光電業", "2303": "半導體業",
    "3711": "半導體業", "2886": "金融保險業", "2884": "金融保險業", "2002": "鋼鐵工業"
}

def safe_download(sid, retries=2):
    for suffix in [".TW", ".TWO"]:
        for _ in range(retries):
            try:
                sym = f"{sid}{suffix}"
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
        hist = safe_download(main_sym.replace('^','')) 
        if hist.empty:
            hist = yf.Ticker(fallback_sym).history(period="3mo")
            if not hist.empty:
                display_name = f"{base_name} (備援: {fallback_sym.replace('.TW','')})"
        
        if hist.empty:
            macro_data.append({"戰區": display_name, "現值": "抓取失敗", "月線": "-", "狀態": "⚪ 斷線"})
            continue
            
        try:
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
# 【第四區塊：實戰量化回測引擎】
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

def fetch_single_stock_batch(sid):
    df = safe_download(sid)
    if not df.empty: return sid, df
    return sid, None

@st.cache_data(ttl=1800, show_spinner=False)
def level2_quant_engine(id_tuple):
    id_list = list(id_tuple)
    intel_results = []
    if not id_list: return pd.DataFrame()
    
    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_single_stock_batch, sid): sid for sid in id_list}
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
            if "金融" in ind or "保險" in ind: continue
            
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
# 【第五區塊：軍事化分頁渲染與系統顯示】
# ==============================================================================

if MACRO_SCORE <= 3:
    st.error(f"🔴 **最高紅色警戒 (大盤分數 {MACRO_SCORE}/10)**：市場極度恐慌！系統建議：**【全面停止交易】**，保留 100% 現金。", icon="🚨")
elif MACRO_SCORE <= 5:
    st.warning(f"🟡 **黃色警戒 (大盤分數 {MACRO_SCORE}/10)**：大盤偏弱。系統建議：**【只做乖離<3%的股票，且資金減半】**。", icon="⚠️")

with st.spinner('情報兵正在進行職業級波段回測與籌碼精算...'):
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
        "🎯 戰術指揮所 (S/A/B/C)", "📡 情報局 (法人籌碼)", "🏦 總司令部 (風控與AAR)", "📖 游擊兵工廠 (教戰手冊)", "🏛️ 軍史館 (系統演進)"
    ])

    # --------------------------------------------------------------------------
    # Tab 1: 🎯 戰術指揮所
    # --------------------------------------------------------------------------
    with t_rank:
        st.markdown("### 🎯 <span class='highlight-gold'>前線狙擊目標清單</span>", unsafe_allow_html=True)
        st.caption("💡 **盤前鐵律**：跳空>2%不買、9:05前不下單、單日限3筆、未達+6%不賣。詳細規範請見兵工廠教範。")

        with st.expander("🌍 查看全球大盤診斷表"):
            if not MACRO_DF.empty:
                st.dataframe(MACRO_DF.style.set_properties(**{'text-align': 'center'}).map(lambda x: 'color: #10B981;' if '多頭' in str(x) or '安定' in str(x) else ('color: #EF4444;' if '空頭' in str(x) or '恐慌' in str(x) else ''), subset=['狀態']), use_container_width=True, hide_index=True)

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
                
                # 👑 S, A, B 完全獨立瀑布流，互不遮蔽
                s_mask = (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] >= 55) & (rank_sorted['均報(%)'] >= 1.5) & (rank_sorted['今日放量'] == True) & (rank_sorted['連買'] >= 2)
                a_mask = (~s_mask) & (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] >= 50) & (rank_sorted['均報(%)'] >= 1.0) & (rank_sorted['連買'] >= 1)
                b_mask = (~s_mask) & (~a_mask) & (rank_sorted['勝率(%)'] > 50) & (rank_sorted['成交量'] >= 1.5) & (rank_sorted['連買'] >= 1) & (rank_sorted['乖離(%)'] < 10)
                c_mask = (~s_mask) & (~a_mask) & (~b_mask) & (rank_sorted['成交量'] >= 1.5) & (rank_sorted['連買'] >= 1)

                if MACRO_SCORE <= 5:
                    s_mask = s_mask & (rank_sorted['乖離(%)'] < 3)
                    a_mask = a_mask & (rank_sorted['乖離(%)'] < 3)
                    b_mask = b_mask & (rank_sorted['乖離(%)'] < 3)

                s_tier = rank_sorted[s_mask].head(3).copy()
                if not s_tier.empty: s_tier['評級'] = 'S'
                
                a_tier = rank_sorted[a_mask].head(3).copy()
                if not a_tier.empty: a_tier['評級'] = 'A'
                
                b_tier = rank_sorted[b_mask].head(7).copy()
                if not b_tier.empty: b_tier['評級'] = 'B'
                
                c_tier = rank_sorted[c_mask].copy()
                if not c_tier.empty: c_tier['評級'] = 'C'

                master_list = pd.concat([s_tier, a_tier, b_tier, c_tier]).reset_index(drop=True).head(20)
                
                if not master_list.empty:
                    master_list['名次'] = master_list.index + 1
                    export_df = master_list[['名次', '評級', '代號', '名稱_x', '產業', '勝率(%)', '均報(%)', '現價', '停損價', '建議買量(張)']].rename(columns={'名稱_x':'名稱'}).copy()
                    export_df['勝率(%)'] = export_df['勝率(%)'].round(1)
                    export_df['均報(%)'] = export_df['均報(%)'].round(2)
                    export_df['現價'] = export_df['現價'].round(2)
                    export_df['停損價'] = export_df['停損價'].round(2)
                    
                    csv_data = export_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="💾 一鍵下載今日作戰清單 (Top 20 菁英)",
                        data=csv_data,
                        file_name=f"Tactical_List_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                    )
                
                ui_s = master_list[master_list['評級'] == 'S']
                ui_a = master_list[master_list['評級'] == 'A']
                ui_b = master_list[master_list['評級'] == 'B']
                ui_c = master_list[master_list['評級'] == 'C']

                def risk_color(val):
                    try:
                        v = int(val)
                        if v >= 8: return 'color: #10B981; font-weight: bold;'
                        elif v <= 3: return 'color: #EF4444; font-weight: bold;'
                        return 'color: #F59E0B; font-weight: bold;'
                    except: return ''

                # ==========================
                # 🥇 渲染 S 級部隊
                # ==========================
                st.markdown("#### 🥇 <span class='highlight-gold'>【S級】完美狙擊</span>", unsafe_allow_html=True)
                if ui_s.empty:
                    st.info("💡 今日無 S 級標的符合。")
                else:
                    cols_s = st.columns(3)
                    for i in range(len(ui_s)):
                        r = ui_s.iloc[i]
                        with cols_s[i]:
                            st.markdown(f"""
                            <div class="tier-card" style="border-top: 5px solid #F59E0B;">
                                <h3 style="margin:0; color:#F59E0B;">{r['名次']}. {r['名稱_x']} ({r['代號']})</h3>
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

                # ==========================
                # 🥈 渲染 A 級部隊
                # ==========================
                st.markdown("#### 🥈 <span class='highlight-cyan'>【A級】伏擊備援</span>", unsafe_allow_html=True)
                if ui_a.empty:
                    st.info("💡 今日無 A 級標的符合。")
                else:
                    a_disp = ui_a[['名次','評級','代號','名稱_x','產業','安全指數','勝率(%)','均報(%)','現價','停損價','建議買量(張)','連買']].rename(columns={'名稱_x':'名稱'})
                    styled_a = (a_disp.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '停損價':'{:.2f}', '勝率(%)':'{:.1f}%', '均報(%)':'{:.2f}%'})
                                    .map(risk_color, subset=['安全指數'])
                                    .map(lambda x: 'color: #10B981; font-weight: bold;' if x > 60 else '', subset=['勝率(%)']))
                    st.dataframe(styled_a, use_container_width=True, hide_index=True)

                # ==========================
                # ⚔️ 渲染 B 級部隊
                # ==========================
                st.markdown("#### ⚔️ <span class='highlight-cyan'>【B級】穩健波段 (勝率 > 50%)</span>", unsafe_allow_html=True)
                if ui_b.empty:
                    st.info("💡 今日無 B 級標的符合。")
                else:
                    b_disp = ui_b[['名次','評級','代號','名稱_x','產業','安全指數','勝率(%)','均報(%)','現價','停損價','建議買量(張)','連買']].rename(columns={'名稱_x':'名稱'})
                    styled_b = (b_disp.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '停損價':'{:.2f}', '勝率(%)':'{:.1f}%', '均報(%)':'{:.2f}%'})
                                    .map(risk_color, subset=['安全指數'])
                                    .map(lambda x: 'color: #10B981; font-weight: bold;' if x > 60 else '', subset=['勝率(%)']))
                    st.dataframe(styled_b, use_container_width=True, hide_index=True)

                st.markdown("---")
                st.markdown("### 📡 <span class='highlight-gold'>【C級】潛伏遺珠 (Top 20 觀察名單)</span>", unsafe_allow_html=True)
                
                if ui_c.empty:
                    st.info("💡 今日無 C 級潛伏標的。")
                else:
                    ui_c['戰術'] = ui_c.apply(lambda r: "💎 低檔潛伏" if r['乖離(%)'] < 3 else ("🚀 突破點火" if r['今日放量'] else "⏳ 盤整"), axis=1)
                    styled_c = (ui_c[['名次','評級','代號','名稱_x','產業','安全指數','勝率(%)','現價','乖離(%)','連買','戰術']].rename(columns={'名稱_x':'名稱'})
                                    .style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '勝率(%)':'{:.1f}%', '乖離(%)':'{:.1f}%'})
                                    .map(risk_color, subset=['安全指數']))
                    st.dataframe(styled_c, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # Tab 2: 📡 情報局
    # --------------------------------------------------------------------------
    with t_chip:
        st.markdown("### 📡 <span class='highlight-gold'>聯合作戰情報：主力兵力動向</span>", unsafe_allow_html=True)
        st.caption("💡 **籌碼流向**：當日全台股外資、投信、自營商買賣超部署 Top 200。")
        
        surprise_atk = today_df[(today_df['連買'] == 1) & (today_df['投信(張)'] > 0) & (today_df['外資(張)'] > 0)].sort_values('三大法人合計', ascending=False).head(3)
        if not surprise_atk.empty:
            st.markdown("#### 🚨 <span class='highlight-red'>土洋合擊！首日突擊部隊</span>", unsafe_allow_html=True)
            st.dataframe(surprise_atk[['代號','名稱','外資(張)','投信(張)','自營(張)','三大法人合計']].style.format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}','自營(張)':'{:,.0f}','三大法人合計':'{:,.0f}'}), use_container_width=True, hide_index=True)
            st.markdown("---")
            
        st.markdown("#### <span class='highlight-cyan'>穩健建倉部隊 (依三大法人合計排序)</span>", unsafe_allow_html=True)
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

    # --------------------------------------------------------------------------
    # Tab 3: 🏦 總司令部 (持股風控 + AAR)
    # --------------------------------------------------------------------------
    with t_cmd:
        st.markdown("### 🏦 <span class='highlight-gold'>司令部：戰備資金精算</span>", unsafe_allow_html=True)
        st.caption("💡 **資金風控**：個人現役持股盈虧計算機 (依自訂折數計算真實稅費)。")
        
        if not sheet_url:
            st.info("請在左側邊欄輸入您的【持股部位】CSV 網址以啟用風控檢查。")
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
                        
                        # 👑 依據將軍側邊欄設定的折數來算稅費
                        active_fee_rate = 0.001425 * fee_discount
                        
                        for _, r in m_df.iterrows():
                            try:
                                sid = str(r['代號']).strip()
                                p_now = float(r['現價'])
                                p_cost = float(r['成本價']) if pd.notna(r['成本價']) else 0
                                qty = float(r['庫存張數']) if pd.notna(r['庫存張數']) else 0
                                
                                # 👑 修復：ETF (00開頭) 交易稅降為千分之1
                                tax_rate = 0.001 if sid.startswith('00') else 0.003
                                
                                buy_fee = int((p_cost * qty * 1000) * active_fee_rate)
                                sell_fee = int((p_now * qty * 1000) * active_fee_rate)
                                sell_tax = int((p_now * qty * 1000) * tax_rate)
                                
                                buy_cost_total = (p_cost * qty * 1000) + buy_fee
                                sell_revenue_net = (p_now * qty * 1000) - sell_fee - sell_tax
                                
                                pnl = sell_revenue_net - buy_cost_total
                                ret = (pnl / buy_cost_total) * 100 if buy_cost_total > 0 else 0
                                
                                current_exposure += (p_now * qty * 1000)
                                total_pnl += pnl
                                
                                act = "✅ 抱緊處理"
                                if ret >= 10: act = "💰 +10% 達標 (強制全出)"
                                elif ret >= 6: act = "🛡️ +6% 達標 (賣出一半鎖利)"
                                elif p_now < r['M10'] or ret <= -3: act = "💀 破線硬停損 (無情砍倉)"
                                
                                res_h.append({'代號': r['代號'], '名稱': r['名稱_y'] if '名稱_y' in r else r.get('名稱',''), '現價': p_now, '成本': p_cost, '張數': format_lots(qty * 1000), '真實淨報酬(%)': ret, '淨損益(元)': pnl, '作戰指示': act})
                            except: continue
                            
                        df_res = pd.DataFrame(res_h)
                        p_color = "#EF4444" if total_pnl > 0 else "#10B981"
                        st.markdown(f"#### 💰 目前總淨損益：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                        
                        styled_h = (df_res.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '成本':'{:.2f}', '真實淨報酬(%)':'{:.2f}%', '淨損益(元)':'{:,.0f}'})
                                    .map(lambda x: 'color: #EF4444; font-weight: bold;' if x > 0 else ('color: #10B981; font-weight: bold;' if x < 0 else ''), subset=['真實淨報酬(%)', '淨損益(元)']))
                        st.dataframe(styled_h, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"❌ 讀取持股部位失敗：{e}")

        st.markdown("---")
        st.markdown("### 📊 <span class='highlight-cyan'>AAR 戰術覆盤室</span>", unsafe_allow_html=True)
        st.caption("💡 **戰術覆盤**：解析歷史戰役與心理盲點，由 AI 精算錯失利潤以精進戰術。")
        
        if not aar_sheet_url:
            st.info("請在左側邊欄輸入您的【交易日誌】CSV 網址，喚醒 AI 覆盤引擎。")
        else:
            try:
                aar_df = pd.read_csv(aar_sheet_url, dtype=str)
                aar_df.columns = aar_df.columns.str.strip()
                
                required_cols = ['代號', '買進日期', '買進價', '賣出日期', '賣出價', '張數', '心理標籤']
                if not all(col in aar_df.columns for col in required_cols):
                    st.error(f"❌ 欄位不符！請確保包含：{', '.join(required_cols)}")
                else:
                    review_results = []
                    total_realized_pnl = 0
                    active_fee_rate = 0.001425 * fee_discount
                    
                    with st.spinner('🕵️ 情報兵正在調閱歷史戰報，計算錯失利潤與心理盲點...'):
                        for idx, row in aar_df.iterrows():
                            try:
                                if pd.isna(row['代號']): continue
                                sid = str(row['代號']).strip()
                                b_date = pd.to_datetime(row['買進日期'])
                                b_price = float(row['買進價'])
                                shares = float(row['張數'])
                                tag = str(row['心理標籤'])
                                if pd.isna(tag) or tag.lower() == "nan": tag = ""
                                
                                # 👑 修復：ETF 交易稅
                                tax_rate = 0.001 if sid.startswith('00') else 0.003
                                
                                buy_fee = int((b_price * shares * 1000) * active_fee_rate)
                                cost = (b_price * shares * 1000) + buy_fee
                            except Exception:
                                continue 
                            
                            diagnosis = "✅ 戰報已收錄" 
                            s_price = 0.0
                            s_date = None
                            
                            if pd.isna(row['賣出日期']) or pd.isna(row['賣出價']) or str(row['賣出價']).strip() == "":
                                hist_current = pd.DataFrame()
                                for suffix in [".TW", ".TWO"]:
                                    try:
                                        hist_current = yf.Ticker(f"{sid}{suffix}").history(period="1mo")
                                        if not hist_current.empty: break
                                    except Exception: pass
                                
                                if not hist_current.empty:
                                    s_price = float(hist_current['Close'].iloc[-1])
                                    diagnosis = "⚪ 尚未平倉 (計算目前帳面損益)"
                                else:
                                    s_price = b_price
                                    diagnosis = "⚪ 尚未平倉 (API阻擋，無法取得現價)"
                            else:
                                s_date = pd.to_datetime(row['賣出日期'])
                                s_price = float(row['賣出價'])
                                
                                future_end = s_date + timedelta(days=15)
                                future_hist = pd.DataFrame() 
                                
                                # 👑 修復：抓取 6 個月資料，用 pandas 自己切割，保證 100% 抓到資料
                                try:
                                    for suffix in [".TW", ".TWO"]:
                                        hist_full = yf.Ticker(f"{sid}{suffix}").history(period="6mo")
                                        if not hist_full.empty:
                                            # 去除時區避免比對錯誤
                                            hist_full.index = pd.to_datetime(hist_full.index).tz_localize(None)
                                            # 切割賣出後 15 天內的資料
                                            mask = (hist_full.index > s_date) & (hist_full.index <= future_end)
                                            future_hist = hist_full.loc[mask]
                                            if not future_hist.empty:
                                                break 
                                except Exception:
                                    pass 
                                
                                if future_hist.empty:
                                    if (datetime.now() - s_date).days <= 1:
                                        diagnosis = "⏳ 剛賣出不久，尚無足夠未來數據比對"
                                    else:
                                        diagnosis = "⚠️ API 阻擋或查無該區間數據，無法診斷"
                                else:
                                    max_future_price = future_hist['High'].max()
                                    if '恐高早退' in tag or '失去耐心' in tag:
                                        if max_future_price > s_price * 1.02:
                                            missed_profit = (max_future_price - s_price) * shares * 1000
                                            diagnosis = f"⚠️ 錯失飆漲！後續最高達 {max_future_price:.1f}，少賺約 +{missed_profit:,.0f}元。"
                                        else:
                                            diagnosis = "✅ 賣出後未見創高，此撤退時機精準！"
                                    elif '恐慌砍倉' in tag:
                                        if max_future_price > b_price:
                                            diagnosis = "🩸 賣出後股價成功反彈解套，被洗出局了。"
                                        else:
                                            diagnosis = "🛡️ 後續未反彈，提早砍倉算是不幸中大幸。"
                                    elif '紀律' in tag:
                                        diagnosis = "👑 嚴格執行紀律，無須留戀後續漲跌！"
                                    else:
                                        diagnosis = "✅ 已結案"

                            sell_fee = int((s_price * shares * 1000) * active_fee_rate)
                            sell_tax = int((s_price * shares * 1000) * tax_rate)
                            
                            revenue = (s_price * shares * 1000) - sell_fee - sell_tax
                            net_profit = revenue - cost
                            roi = (net_profit / cost) * 100
                            total_realized_pnl += net_profit
                            
                            held_days = (s_date - b_date).days if s_date else (datetime.now() - b_date).days

                            review_results.append({
                                '代號': sid,
                                '持股天數': held_days,
                                '淨利(元)': net_profit,
                                '報酬(%)': roi,
                                '心魔檢定': tag.split('(')[0].strip() if '(' in tag else tag, 
                                'AI 毒舌診斷': diagnosis
                            })
                            time.sleep(1.5) 

                    if review_results:
                        res_df = pd.DataFrame(review_results)
                        p_color = "#EF4444" if total_realized_pnl > 0 else "#10B981"
                        st.markdown(f"#### 💰 歷史戰役總淨利：<span style='color:{p_color}; font-size:24px;'>{total_realized_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                        
                        styled_res = (res_df.style.set_properties(**{'text-align': 'center'})
                                    .format({'淨利(元)':'{:,.0f}', '報酬(%)':'{:.2f}%'})
                                    .map(lambda x: 'color: #EF4444; font-weight: bold;' if x > 0 else ('color: #10B981;' if x < 0 else ''), subset=['淨利(元)', '報酬(%)']))
                        st.dataframe(styled_res, use_container_width=True, hide_index=True)
                    else:
                        st.warning("日誌中無有效交易紀錄。")
            except Exception as e:
                st.error(f"❌ 讀取交易日誌失敗：{e}")

    # --------------------------------------------------------------------------
    # Tab 4: 📖 游擊兵工廠
    # --------------------------------------------------------------------------
    with t_book:
        st.markdown("### 📖 <span class='highlight-gold'>實戰準則與系統圖示教範</span>", unsafe_allow_html=True)
        st.caption("💡 **兵工廠教範**：系統所有名詞定義、篩網嚴格定義與圖示意義。")
        st.markdown(MANUAL_TEXT, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # Tab 5: 🏛️ 軍史館
    # --------------------------------------------------------------------------
    with t_hist:
        st.markdown("### 🏛️ <span class='highlight-cyan'>皇家軍史館：兵器開發檔案</span>", unsafe_allow_html=True)
        st.caption("💡 **開發檔案**：歷代軍火庫升級、戰略轉型與重大修復之機密卷宗。")
        st.markdown(HISTORY_TEXT, unsafe_allow_html=True)

else:
    st.error("⚠️ 資料匯入失敗。請檢查網路或稍後再試。")

st.divider()
st.markdown("<p style='text-align: center; color: #9CA3AF;'>© 游擊隊軍火部 - v24.2 (純淨修復版)</p>", unsafe_allow_html=True)
