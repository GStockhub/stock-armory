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

# 👑 導入您專屬的外部軍火庫與 AAR 獨立模組
from manual import MANUAL_TEXT, HISTORY_TEXT
import aar  # 👈 呼叫外掛的 AAR 模組

# ==============================================================================
# 【第一區塊：系統底層與防禦配置】
# ==============================================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="我要賺大錢",
    page_icon="💰️",
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
# 【第二區塊：側邊欄 (Sidebar) & 紀律風控】
# ==============================================================================

with st.sidebar:
    st.markdown("### ⚙️ 紀律設定")
    st.markdown("---")
    sheet_url = st.text_input("輸入【持股部位】CSV 網址：", value="", placeholder="貼上持股分頁網址")
    aar_sheet_url = st.text_input("輸入【交易日誌】CSV 網址：", value="", placeholder="貼上日誌分頁網址(供AAR使用)")
    
    st.markdown("---")
    st.markdown("#### 💰 資金控管")
    total_capital = st.number_input("作戰本金 (元)", value=200000, step=10000)
    risk_tolerance_pct = st.slider("單筆最大虧損容忍 (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
    risk_amount = total_capital * (risk_tolerance_pct / 100)
    st.info(f"🛡️ **單筆保命底線：{risk_amount:,.0f} 元**\n\n*(依此反推單筆最多買進張數)*")
    
    st.markdown("---")
    st.markdown("#### ⚖️ 真實稅費參數")
    fee_discount = st.slider("券商手續費折數 (無折扣=1.0, 五折=0.5)", min_value=0.1, max_value=1.0, value=1.0, step=0.05)
    
    st.markdown("---")
    st.markdown("#### 🛡️ 總曝險與預備金")
    MAX_EXPOSURE_RATE = 0.60
    max_market_cap = total_capital * MAX_EXPOSURE_RATE
    st.markdown(f"""
    <div style="background-color: #2D2A1A; padding: 15px; border-radius: 8px; border-left: 5px solid #F59E0B; margin-bottom: 15px;">
        <div style="margin-bottom: 12px; text-align: left;">
            ⚔️ <b style="color: #D1D5DB;">最高資金 (60%)：</b><br>
            <span style="font-size: 18px; font-weight: bold; color: #F59E0B;">{max_market_cap:,.0f} 元</span>
        </div>
        <div style="text-align: left;">
            🛡️ <b style="color: #D1D5DB;">預備部隊 (40%)：</b><br>
            <span style="font-size: 18px; font-weight: bold; color: #38BDF8;">{total_capital - max_market_cap:,.0f} 元</span><br>
            <span style="font-size: 14px; color: #9CA3AF;">*(極端避險與股災專用)*</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🔄 一鍵清空情報快取"):
        st.cache_data.clear()
        st.success("快取已清除！請重新載入。")

st.markdown("<h1 style='text-align: center;' class='highlight-gold'>💰️ 我要賺大錢 v24.3</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9CA3AF;'>—— 終極番號 ✕ 交易教練 V2 完全體 ——</p>", unsafe_allow_html=True)

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
# 【第四區塊：量化回測引擎】
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
            
            ind = TWSE_IND_MAP.get(sid) or "其他"
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

def risk_color(val):
    try:
        v = int(val)
        if v >= 8: return 'color: #10B981; font-weight: bold;'
        elif v <= 3: return 'color: #EF4444; font-weight: bold;'
        return 'color: #F59E0B; font-weight: bold;'
    except: return ''

# ==============================================================================
# 【第五區塊：分頁渲染與系統顯示】
# ==============================================================================

if MACRO_SCORE <= 3:
    st.error(f"🔴 **最高紅色警戒 (大盤分數 {MACRO_SCORE}/10)**：市場恐慌！系統建議：**【全面停止交易】**，保留 100% 現金。", icon="🚨")
elif MACRO_SCORE <= 5:
    st.warning(f"🟡 **黃色警戒 (大盤分數 {MACRO_SCORE}/10)**：大盤偏弱。系統建議：**【只做乖離<3%的股票，且資金減半】**。", icon="⚠️")

with st.spinner('情報兵正在進行職業級波段回測與籌碼精算...'):
    chip_db = fetch_chips_data()

m_df = pd.DataFrame() # 預防未輸入網址時出錯

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

    # 👑 戰略前置：在進入分頁前，提早將「現役持股」結算完畢！(供一鍵下載與總部共用)
    if sheet_url:
        try:
            sheet_df = pd.read_csv(sheet_url, dtype=str)
            sheet_df.columns = sheet_df.columns.str.strip()
            h_df = sheet_df[sheet_df['分類'] == '持股'].copy()
            if not h_df.empty:
                h_intel = level2_quant_engine(tuple(h_df['代號'].tolist()))
                if not h_intel.empty:
                    m_df = pd.merge(h_df, h_intel, on='代號', how='inner')
                    m_df = pd.merge(m_df, today_df[['代號', '名稱']], on='代號', how='left').fillna('未知')
        except Exception as e:
            st.error(f"❌ 讀取持股部位失敗：{e}")
    
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
                
                s_mask = (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] >= 55) & (rank_sorted['均報(%)'] >= 1.5) & (rank_sorted['今日放量'] == True) & (rank_sorted['連買'] >= 2)
                a_mask = (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] >= 50) & (rank_sorted['均報(%)'] >= 1.0) & (rank_sorted['連買'] >= 1)
                b_mask = (~s_mask) & (~a_mask) & (rank_sorted['勝率(%)'] > 50) & (rank_sorted['成交量'] >= 1.5) & (rank_sorted['連買'] >= 1) & (rank_sorted['乖離(%)'] < 10)
                c_mask = (~s_mask) & (~a_mask) & (~b_mask) & (rank_sorted['成交量'] >= 1.5) & (rank_sorted['連買'] >= 1)

                if MACRO_SCORE <= 5:
                    s_mask = s_mask & (rank_sorted['乖離(%)'] < 3)
                    a_mask = a_mask & (rank_sorted['乖離(%)'] < 3)
                    b_mask = b_mask & (rank_sorted['乖離(%)'] < 3)

                s_tier = rank_sorted[s_mask].head(3).copy()
                a_tier = rank_sorted[a_mask].head(3).copy()
                b_tier = rank_sorted[b_mask].head(7).copy()
                c_tier = rank_sorted[c_mask].copy()

                using_a_tier = False
                if s_tier.empty:
                    using_a_tier = True
                    top_tier = a_tier
                    top_tier['評級'] = 'A'
                else:
                    top_tier = s_tier
                    top_tier['評級'] = 'S'
                
                b_tier['評級'] = 'B'
                c_tier['評級'] = 'C'

                master_list = pd.concat([top_tier, b_tier, c_tier]).reset_index(drop=True).head(20)
                master_list['名次'] = master_list.index + 1
                
                # ==============================================================
                # 👑 縫合手術：打造手機版【終極作戰地圖 (含持股與狙擊)】
                # ==============================================================
                if not master_list.empty:
                    export_rows = []
                    active_fee_rate = 0.001425 * fee_discount

                    # 1. 🛡️ 優先排入現役持股 (先防守)
                    if not m_df.empty:
                        for _, r in m_df.iterrows():
                            try:
                                p_now = float(r['現價'])
                                p_cost = float(r['成本價']) if pd.notna(r['成本價']) else 0
                                qty = float(r['庫存張數']) if pd.notna(r['庫存張數']) else 0

                                buy_fee = int((p_cost * qty * 1000) * active_fee_rate)
                                sell_fee = int((p_now * qty * 1000) * active_fee_rate)
                                sell_tax = int((p_now * qty * 1000) * 0.003)

                                buy_cost_total = (p_cost * qty * 1000) + buy_fee
                                sell_revenue_net = (p_now * qty * 1000) - sell_fee - sell_tax

                                pnl = sell_revenue_net - buy_cost_total
                                ret = (pnl / buy_cost_total) * 100 if buy_cost_total > 0 else 0

                                act = "✅ 續抱"
                                if ret >= 10: act = "💰 +10% 強制全出"
                                elif ret >= 6: act = "🛡️ +6% 一半鎖利"
                                elif p_now < r['M10'] or ret <= -3: act = "💀 破線硬停損"

                                export_rows.append({
                                    "戰區": "🛡️ 現役持股",
                                    "代號": r['代號'],
                                    "名稱": r['名稱_y'] if '名稱_y' in r else r.get('名稱',''),
                                    "戰術行動": act,
                                    "現價": round(p_now, 2),
                                    "防守底線": round(r['停損價'], 2),
                                    "次要數據": f"帳面 {ret:.2f}%",
                                    "產業": r['產業']
                                })
                            except: continue

                    # 👑 插入空白行：如果手上有持股，在持股與狙擊名單中間安插一行空白，方便視覺區隔
                    if not m_df.empty:
                        export_rows.append({
                            "戰區": "", "代號": "", "名稱": "", "戰術行動": "",
                            "現價": "", "防守底線": "", "次要數據": "", "產業": ""
                        })

                    # 2. 🎯 接續排入狙擊兵力 (後進攻，開放 Top 20 包含 C 級潛伏名單)
                    tier_names = {'S': '🥇 S級狙擊', 'A': '🥈 A級狙擊', 'B': '⚔️ B級穩健', 'C': '📡 C級潛伏'}
                    for _, r in master_list.iterrows():
                        # 👑 C級名單專屬防呆：既然是無聊觀察用，戰術行動就改為「觀察」，避免盤中手癢誤買
                        if r['評級'] == 'C':
                            act_str = "👀 列入觀察"
                        else:
                            act_str = f"建議買 {r['建議買量(張)']} 張"

                        export_rows.append({
                            "戰區": tier_names.get(r['評級'], ""),
                            "代號": r['代號'],
                            "名稱": r['名稱_x'],
                            "戰術行動": act_str,
                            "現價": round(r['現價'], 2),
                            "防守底線": round(r['停損價'], 2),
                            "次要數據": f"勝率 {r['勝率(%)']:.1f}%",
                            "產業": r['產業']
                        })

                    final_export_df = pd.DataFrame(export_rows)
                    csv_data = final_export_df.to_csv(index=False).encode('utf-8-sig')
                    
                    st.download_button(
                        label="📱 一鍵下載明日作戰地圖 (含持股與狙擊)",
                        data=csv_data,
                        file_name=f"Tactical_Map_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                    )
                
                ui_top = master_list[master_list['評級'].isin(['S', 'A'])]
                ui_b = master_list[master_list['評級'] == 'B']
                ui_c = master_list[master_list['評級'] == 'C']

                if using_a_tier:
                    st.warning("⚠️ **系統判定：今日無完美 S 級標的。自動啟動【A 級】伏擊備援名單！**", icon="🛡️")
                    st.markdown("#### 🥈 <span class='highlight-cyan'>【A級】伏擊備援</span>", unsafe_allow_html=True)
                    border_color, title_color = "#38BDF8", "#38BDF8"
                else:
                    st.markdown("#### 🥇 <span class='highlight-gold'>【S級】完美狙擊</span>", unsafe_allow_html=True)
                    border_color, title_color = "#F59E0B", "#F59E0B"

                if ui_top.empty:
                    st.info("💡 今日無主戰力標的符合。")
                else:
                    cols_s = st.columns(3)
                    for i in range(len(ui_top)):
                        r = ui_top.iloc[i]
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

                st.markdown("#### ⚔️ <span class='highlight-cyan'>【B級】穩健波段 (勝率 > 50%)</span>", unsafe_allow_html=True)
                if ui_b.empty:
                    st.info("💡 今日無 B 級符合標的。")
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
            st.markdown("#### 🚨 <span class='highlight-green'>土洋合擊區</span>", unsafe_allow_html=True)
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
            if not m_df.empty:
                res_h, total_pnl, current_exposure = [], 0, 0
                active_fee_rate = 0.001425 * fee_discount
                
                for _, r in m_df.iterrows():
                    try:
                        p_now = float(r['現價'])
                        p_cost = float(r['成本價']) if pd.notna(r['成本價']) else 0
                        qty = float(r['庫存張數']) if pd.notna(r['庫存張數']) else 0
                        
                        buy_fee = int((p_cost * qty * 1000) * active_fee_rate)
                        sell_fee = int((p_now * qty * 1000) * active_fee_rate)
                        sell_tax = int((p_now * qty * 1000) * 0.003)
                        
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

        st.markdown("---")
        st.markdown("### 📊 <span class='highlight-cyan'>AAR 戰術覆盤室</span>", unsafe_allow_html=True)
        st.caption("💡 **戰術覆盤**：解析歷史戰役與心理盲點，由 AI 精算錯失利潤以精進戰術。")
        
        fm_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiZGVraTEwMjMiLCJlbWFpbCI6ImRla2kxMDIzQGdtYWlsLmNvbSJ9.-wVo_6BD8ac8cGCOi8C3J58KUGZ1c0CMwTU9lYPltNM"
        aar.render_aar_tab(aar_sheet_url, fee_discount, fm_token)

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
st.markdown("<p style='text-align: center; color: #9CA3AF;'>© 游擊隊軍火部 - v24.3</p>", unsafe_allow_html=True)
