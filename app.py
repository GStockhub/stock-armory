import streamlit as st
import pandas as pd
import numpy as np
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf

# ==============================================================================
# 【第一區塊：系統底層與現代化防禦配置】
# ==============================================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="游擊隊終極軍火庫 v21.0",
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
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 【第二區塊：側邊欄 (Sidebar) & 時間戳】
# ==============================================================================

with st.sidebar:
    st.markdown("### ⚙️ 指揮中心設定")
    st.markdown("---")
    sheet_url = st.text_input("輸入 Google Sheets CSV 網址：", value="", placeholder="https://docs.google.com/.../pub?output=csv")
    st.markdown("---")
    st.markdown("#### 💰 資金與風險控管 (Level 2)")
    total_capital = st.number_input("作戰本金 (元)", value=200000, step=10000)
    risk_tolerance_pct = st.slider("單筆最大虧損容忍 (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
    risk_amount = total_capital * (risk_tolerance_pct / 100)
    
    st.info(f"🛡️ **保命底線：{risk_amount:,.0f} 元**\n\n依此反推單筆最多買進張數。")
    st.markdown("---")
    if st.button("🔄 一鍵清空情報快取"):
        st.cache_data.clear()
        st.success("快取已清除！請重新載入。")

st.markdown("<h1 style='text-align: center;' class='highlight-gold'>⚔️ 游擊隊終極軍火庫 v21.0</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9CA3AF;'>—— 實戰定檔版 ✕ 職業波段狙擊 ✕ 極限防禦 ——</p>", unsafe_allow_html=True)

current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
st.caption(f"<div style='text-align: center; color: #6B7280;'>📡 雷達最後掃描時間：{current_time}</div>", unsafe_allow_html=True)

# ==============================================================================
# 【第三區塊：強效大盤診斷與台股產業字典】
# ==============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_official_twse_industry():
    ind_mapping = {}
    name_mapping = {}
    try:
        res = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False, timeout=10)
        if res.status_code == 200:
            for item in res.json():
                cid = str(item['公司代號']).strip()
                ind_mapping[cid] = item['產業類別']
                name_mapping[cid] = item['公司名稱']
    except: pass
    return ind_mapping, name_mapping

TWSE_IND_MAP, TWSE_NAME_MAP = fetch_official_twse_industry()

def get_yfinance_industry(sid):
    try:
        info = yf.Ticker(f"{sid}.TW").info
        sector = info.get('sector', '')
        if 'Technology' in sector: return '電子與半導體'
        elif 'Financial' in sector: return '金融保險'
        elif 'Healthcare' in sector: return '生技醫療'
        elif 'Consumer' in sector: return '民生消費'
        elif 'Industrials' in sector: return '工業機電'
        return '其他'
    except: return '未知產業'

@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_dashboard():
    score = 5.0
    macro_data = []
    indices = {"^TWII": "台股加權", "^SOX": "美費半導體", "^IXIC": "那斯達克", "^VIX": "恐慌指數(VIX)"}
    
    for sym, name in indices.items():
        try:
            hist = yf.download(sym, period="1mo", progress=False) 
            if hist.empty: continue
            
            last_p = float(hist['Close'].iloc[-1])
            ma20 = float(hist['Close'].rolling(20).mean().iloc[-1])
            status = "🟢 多頭" if last_p > ma20 else "🔴 空頭"
            
            if sym == "^VIX":
                status = "🔴 恐慌" if last_p > 25 else ("🟡 警戒" if last_p > 18 else "🟢 安定")
                if last_p > 25: score -= 2
                elif last_p < 18: score += 1
            else:
                if last_p > ma20: score += 1
                else: score -= 1
                
            macro_data.append({"戰區": name, "現值": f"{last_p:.2f}", "月線": f"{ma20:.2f}", "狀態": status})
        except: continue
        
    return max(1, min(10, int(score))), pd.DataFrame(macro_data)

MACRO_SCORE, MACRO_DF = get_macro_dashboard()

if MACRO_SCORE <= 3:
    st.error(f"🔴 **最高紅色警戒 (大盤分數 {MACRO_SCORE}/10)**：市場極度恐慌！系統建議：**【全面停止交易】**，現金為王。", icon="🚨")
elif MACRO_SCORE <= 5:
    st.warning(f"🟡 **黃色警戒 (大盤分數 {MACRO_SCORE}/10)**：大盤偏弱。系統建議：**【只做乖離<3%的股票，絕不追高】**。", icon="⚠️")

# ==============================================================================
# 【第四區塊：真・實戰定檔量化回測引擎 (v21)】
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

@st.cache_data(ttl=1800, show_spinner=False)
def level2_quant_engine(id_tuple):
    id_list = list(id_tuple)
    intel_results = []
    if not id_list: return pd.DataFrame()
    
    # --- ★ v21 終極修復 ①：穩定版單檔迴圈抓取 (防封鎖與空值) ---
    bulk_data = {}
    for sid in id_list:
        try:
            df = yf.download(f"{sid}.TW", period="6mo", progress=False)
            if not df.empty and len(df) >= 30:
                bulk_data[sid] = df
            time.sleep(0.1)  # 防封鎖
        except:
            continue
            
    for sid in id_list:
        try:
            df_stock = bulk_data.get(sid)
            if df_stock is None or df_stock.empty:
                continue
            
            close_s = df_stock['Close'].squeeze()
            open_s = df_stock['Open'].squeeze()
            vol_s = df_stock['Volume'].squeeze()
            
            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            vol_now = float(vol_s.iloc[-1]) / 1000
            vol_ma5 = float(vol_s.rolling(5).mean().iloc[-1]) / 1000
            
            bias = ((p_now - m20) / m20) * 100
            
            # 強勢回檔再攻判定
            trend_strength = (m5 > m10) and (m10 > m20)
            last_10_max = close_s.iloc[-10:].max()
            last_20_max = close_s.iloc[-20:].max()
            recent_high = (last_10_max >= last_20_max) 
            pullback_stand = (p_now >= m5) and (p_now <= m5 * 1.03) 
            
            is_candidate = trend_strength and recent_high and pullback_stand
            is_volume_breakout = (vol_now > 1) and (vol_now > vol_ma5 * 1.2) 
            
            # 回測引擎設定
            df_bt = pd.DataFrame({'Close': close_s, 'Open': open_s})
            df_bt['MA5'] = df_bt['Close'].rolling(5).mean()
            df_bt['MA10'] = df_bt['Close'].rolling(10).mean()
            df_bt['MA20'] = df_bt['Close'].rolling(20).mean()
            df_bt['RollMax20'] = df_bt['Close'].rolling(20).max()
            
            # --- ★ v21 終極修復 ②：嚴格過濾回測假訊號 (接近突破才算) ---
            sig_mask = (
                (df_bt['MA5'] > df_bt['MA10']) &
                (df_bt['MA10'] > df_bt['MA20']) &
                (df_bt['Close'] >= df_bt['MA5']) &
                (df_bt['Close'] >= df_bt['RollMax20'] * 0.98)
            )
            signals_idx = df_bt[sig_mask].index
            
            sim_returns = []
            for i in range(len(signals_idx)):
                idx = signals_idx[i]
                loc_idx = df_bt.index.get_loc(idx)
                if loc_idx + 1 >= len(df_bt): continue 
                
                # 隔天開盤進場
                entry_p = df_bt.iloc[loc_idx + 1]['Open']
                prev_close = df_bt.iloc[loc_idx]['Close']
                
                # 跳空 > +3% 放棄交易
                if entry_p > prev_close * 1.03: continue
                
                future_data = df_bt.iloc[loc_idx + 1 : loc_idx + 11] 
                if future_data.empty: continue
                
                stop_loss = max(df_bt.iloc[loc_idx]['MA10'], entry_p * 0.97) 
                sold_half = False
                ret = 0.0
                
                for f_idx, row in future_data.iterrows():
                    curr_p = row['Close']
                    if curr_p > entry_p * 1.05: stop_loss = max(stop_loss, entry_p) # 保本
                    
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
                
            if sim_returns:
                sim_arr = np.array(sim_returns)
                win_rate = (sim_arr > 0).mean() * 100
                avg_ret = sim_arr.mean() * 100
            else:
                win_rate, avg_ret = 50.0, 0.0

            ind = TWSE_IND_MAP.get(sid, "")
            if not ind: ind = get_yfinance_industry(sid)
            name = TWSE_NAME_MAP.get(sid, "未知代號")
            if sid.startswith('00'): ind = "ETF"

            s_score = MACRO_SCORE
            if p_now > m5: s_score += 1
            if p_now > m20: s_score += 1
            else: s_score -= 2
            if bias > 10: s_score -= 2
            elif 0 <= bias <= 5: s_score += 2

            momentum_bonus = 50 if vol_now > vol_ma5 * 1.5 else 0
            twenty_high = float(close_s.rolling(20).max().shift(1).iloc[-1])
            if p_now > twenty_high: 
                momentum_bonus += 100 

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
# 【第五區塊：旗艦分頁渲染 (階梯式名單)】
# ==============================================================================

with st.spinner('情報兵正在進行職業級波段回測與籌碼精算 (實戰定檔版)...'):
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
        "🎯 職業波段 S/A/B 推薦", "🔥 三大法人籌碼流向", "🏦 司令部資金精算", "📖 實戰與名詞教範", "📜 系統演進史"
    ])

    # --------------------------------------------------------------------------
    # Tab 1: AI 推薦 & 階梯式遺珠
    # --------------------------------------------------------------------------
    with t_rank:
        st.markdown("### 👑 <span class='highlight-gold'>今日 AI 戰神決策清單 (實戰定檔版)</span>", unsafe_allow_html=True)
        
        with st.expander("🌍 查看全球大盤診斷表 (Level 1)"):
            if not MACRO_DF.empty:
                st.dataframe(MACRO_DF.style.set_properties(**{'text-align': 'center'}).map(lambda x: 'color: #10B981;' if '多頭' in str(x) or '安定' in str(x) else ('color: #EF4444;' if '空頭' in str(x) or '恐慌' in str(x) else ''), subset=['狀態']), use_container_width=True, hide_index=True)
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

                # --- ★ v21 終極修復 ③：重均報的狼性排名公式 ---
                final_rank['Score'] = (
                    final_rank['均報(%)'] * 120 +
                    final_rank['勝率(%)'] * 10 +
                    final_rank['安全指數'] * 200 -
                    abs(final_rank['乖離(%)']) * 40
                )
                final_rank.loc[final_rank['今日放量'] == True, 'Score'] += 100 
                
                rank_sorted = final_rank.sort_values('Score', ascending=False).reset_index(drop=True)
                
                strict_mask = (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] > 55) & (rank_sorted['均報(%)'] > 1.5) & (rank_sorted['今日放量'] == True) & (rank_sorted['連買'] >= 2)
                med_mask = (~strict_mask) & (rank_sorted['勝率(%)'] > 50) & (rank_sorted['成交量'] >= 1) & (rank_sorted['連買'] >= 1) & (rank_sorted['乖離(%)'] < 10)
                scout_mask = (~strict_mask) & (~med_mask) & (rank_sorted['成交量'] >= 1) & (rank_sorted['連買'] >= 1)

                if MACRO_SCORE <= 5:
                    strict_mask = strict_mask & (rank_sorted['乖離(%)'] < 3)
                    med_mask = med_mask & (rank_sorted['乖離(%)'] < 3)

                s_tier = rank_sorted[strict_mask].head(3)
                ab_tier = rank_sorted[med_mask].head(7)
                scout_tier = rank_sorted[scout_mask].head(20)
                
                display_list = pd.concat([s_tier, ab_tier]).reset_index(drop=True)
                display_list['名次'] = display_list.index + 1
                
                st.markdown("#### 🥇 【S級】強勢回檔狙擊核心 (符合極嚴格職業濾網)")
                if s_tier.empty:
                    st.info("💡 今日無標的完美符合「勝率>55%、均報>1.5%、爆量回檔」之頂級條件。寧缺勿濫！")
                else:
                    cols_s = st.columns(3)
                    for i in range(len(s_tier)):
                        r = display_list.iloc[i]
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
            if MACRO_SCORE <= 3:
                st.error("⚔️ 報告將軍，大盤極度恐慌 (分數 <= 3)。風控系統已啟動：今日強制停止交易，保護本金！")
            else:
                st.warning("⚔️ 報告將軍，今日無資料或無標的符合。")

    # --------------------------------------------------------------------------
    # Tab 2: 三大法人籌碼流向 
    # --------------------------------------------------------------------------
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
                     .map(risk_color, subset=['安全指數']), 
                     height=500, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # Tab 3: 司令部：資產精算 
    # --------------------------------------------------------------------------
    with t_cmd:
        st.markdown("### 🏦 <span class='highlight-gold'>司令部：雲端資產盤點與決策</span>", unsafe_allow_html=True)
        if not sheet_url:
            st.info("💡 **行動指南**：請在左側邊欄輸入您的 Google Sheets CSV 網址以啟用司令部功能。")
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
                        
                        res_h = []
                        total_pnl = 0
                        for _, r in m_df.iterrows():
                            try:
                                p_now = float(r['現價'])
                                p_cost = float(r['成本價']) if pd.notna(r['成本價']) else 0
                                qty = float(r['庫存張數']) if pd.notna(r['庫存張數']) else 0
                                pnl = (p_now - p_cost) * qty * 1000
                                ret = ((p_now - p_cost) / p_cost) * 100 if p_cost > 0 else 0
                                total_pnl += pnl
                                
                                act = "✅ 續抱"
                                if ret > 5: act = "🛡️ 鎖利保本 (停損改成本價)"
                                elif p_now < r['M10'] or ret <= -3: act = "💀 破線硬停損 (無情砍倉)"
                                
                                res_h.append({'代號': r['代號'], '名稱': r['名稱_y'] if '名稱_y' in r else r.get('名稱',''), '現價': p_now, '成本': p_cost, '張數': format_lots(qty * 1000), '報酬(%)': ret, '損益(元)': pnl, '作戰指示': act})
                            except: continue
                        
                        df_res = pd.DataFrame(res_h)
                        p_color = "#EF4444" if total_pnl > 0 else "#10B981"
                        st.markdown(f"#### 💰 目前總損益：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                        st.warning("🛡️ **連續停損保護機制**：若您在實戰中遭遇 **『連續 3 筆虧損停損』**，請嚴格遵守紀律：**停止交易 2 天**！讓心態歸零，避免情緒化報復性下單。")
                        
                        styled_h = (df_res.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '成本':'{:.2f}', '報酬(%)':'{:.2f}%', '損益(元)':'{:,.0f}'})
                                    .map(lambda x: 'color: #EF4444; font-weight: bold;' if x > 0 else ('color: #10B981; font-weight: bold;' if x < 0 else ''), subset=['報酬(%)', '損益(元)']))
                        st.dataframe(styled_h, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"❌ 讀取 Google Sheets 失敗：{e}")

    # --------------------------------------------------------------------------
    # Tab 4: 教戰手冊 (100% 完整無遺漏版)
    # --------------------------------------------------------------------------
    with t_book:
        st.markdown("### 📖 <span class='highlight-gold'>游擊兵工廠：名詞、圖示與實戰教範大全 (v21 最終定檔版)</span>", unsafe_allow_html=True)
        
        st.markdown("""
        #### 🔣 系統圖示 (Icons) 權威指南
        * 👑 **今日 AI 戰神決策清單**：系統精算後的最高殿堂。
        * 🥇 **【S級】強勢回檔狙擊核心**：綜合排名前 3 名。符合「多頭排列、創高拉回、高勝率、高均報」的完美標的。
        * ⚔️ **【A/B級】次級波段與伏擊清單**：排名 4~10 名，勝率 > 50% 的穩健標的。
        * 🚨 **警報 / 停損 / 突擊部隊**：代表危險的停損線，或是主力同步暴買的「土洋合擊」。
        * 💀 **破線硬停損 (無情砍倉)**：持股若跌破 10MA 或虧損達 3%，必須無情砍倉。
        * 🛡️ **鎖利保本**：持股獲利超過 5%，停損點自動拉高到「買進成本價」，確保這筆交易絕對不虧錢。
        * ✅ **續抱**：股價健康上攻，讓獲利飛奔。
        * 🎯 **雷達 / S/A/B 推薦**：偵測到的主力作戰目標。
        * 🚀 **突破點火**：今日成交量大於 5日均量 1.2 倍，動能爆發。
        * 💎 **低檔潛伏**：乖離率 < 3% 的未爆發股，風險極低。
        * ⏳ **盤整**：籌碼雖好，但股價還在均線糾結處睡覺。
        * 🏦 **司令部資金精算**：個人持股盈虧計算機。
        * 🔥 **三大法人籌碼流向**：當日全台股外資、投信、自營商買賣超 Top 200。
        * 📡 **隱藏版投信建倉遺珠**：放寬條件後的後備觀察名單。
        * 📖 **實戰與名詞教範**：即本說明書。
        * 📜 **系統演進史**：紀錄本軍火庫的版本沿革。

        #### 🏫 核心名詞與數據指標解釋
        * **實戰回測 (隔日進場/-3%損/+10%利)**：這是系統最核心的引擎。它模擬在歷史上出現相同訊號時，**「隔天開盤價買進（若跳空>3%則不買）」**。買進後，若達 +6% 先賣一半，達 +10% 賣剩下一半；若跌破 10MA 或虧損 3% 則強制停損。
        * **均報 (%)**：在上述嚴格模擬下，平均每次出手的「真實報酬率」。公式排名極度看重此數值，> 1.5% 屬於頂級印鈔機。
        * **勝率 (%)**：在上述模擬下，能成功獲利出場的機率。
        * **安全指數 (1~10 分)**：大盤 VIX 狀態、個股均線強弱與乖離率的綜合防禦分數。滿分 10 分。
        * **乖離率 (Bias %)**：股價偏離 20 日均線(月線)的百分比。`0% ~ 5%` 為黃金建倉區，`> 10%` 屬於過熱，系統會給予嚴格扣分懲罰。
        * **M5 / M10 / M20**：分別代表 5日(攻擊線)、10日(防守線)、20日(生命線) 移動平均價。

        #### 🕵️ 系統選股考量與避開陷阱 (將軍必讀)
        * **終極進場條件 (強勢回檔再攻)**：系統嚴格要求 `M5 > M10 > M20` (多頭排列)，且近 10 天曾創過 20 日新高，但現在價格稍微拉回、靠近 M5 才買進。**絕對不追高！**
        * **大盤宏觀切換 (風控核心)**：
          - 大盤分數 `<= 3`：系統亮紅燈，**停止任何新交易**。
          - 大盤分數 `<= 5`：系統亮黃燈，**只買乖離 < 3% 的股票，且建議資金減半**。
        * **階梯式名單過濾**：如果大盤偏弱，S 級名單可能完全空蕩蕩（選不出股票），這不是 Bug，這是系統在保護您的本金。此時請往下看 A/B 級或遺珠名單。

        #### 💰 核心金律：職業級波段風控
        * **單股資金限制**：單一檔股票投入資金，絕對不超過總本金的 **15%**。
        * **連續停損保護**：實戰中若遭遇**「連續 3 筆交易虧損停損」**，請強制自己**停止交易 2 天**！
        * **分批停利法**：帳上獲利 +6% 時賣出 50% 鎖住利潤，剩下的放到 +10% 或直到跌破 5MA 再出，讓獲利極大化。
        """)

    # --------------------------------------------------------------------------
    # Tab 5: 系統演進史 (V1~V21 完全保留)
    # --------------------------------------------------------------------------
    with t_hist:
        st.markdown("### 📜 <span class='highlight-cyan'>游擊兵工廠：開發史 (Chronicles)</span>", unsafe_allow_html=True)
        st.markdown("""
        * **v21.0 (實戰定檔版)**：**【停止功能貪婪，回歸穩定】。廢除不穩定的 bulk_download，改用穩定版迴圈防封鎖機制。嚴格過濾回測假訊號，確保只在「接近突破或剛創高」才判定。套用狼性評分公式（均報權重最高），直接作為實戰封測版本。**
        * **v20.0 (職業波段狙擊版)**：進場改為「強勢回檔再攻」；回測改為「隔日開盤價進場且過濾跳空」；停利改為「6%半出/10%全出」；加入「大盤 <=3 停下交易」風控；名單改為階梯式過濾。徹底修復大盤與產業抓取異常。
        * **v19.0 (攻擊爆發版)**：停利波段拉長至 10%，回測週期延長至 10 天。加入「20日新高突破」動能加權。籌碼表擴充三大法人。大幅限制渲染行數 (Top 200) 解決網頁卡頓問題。
        * **v18.0 (實戰真劍勝負版)**：重寫回測引擎，導入真實模擬 (-3%硬停損)。加入「5MA>10MA>20MA」嚴格趨勢濾網。加入大盤保護機制。
        * **v17.8 (極致純粹無閹割版)**：為追求極速，無情拔除單兵雷達。為籌碼套用顏色判定。
        * **v17.7 (閃電記憶體版)**：導入 `@st.cache_data` 全面包覆 Level 2 量化引擎，解決重新整理時重複下載數據的痛點。
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
st.markdown("<p style='text-align: center; color: #9CA3AF;'>© 游擊隊軍火部 - v21.0 實戰定檔版</p>", unsafe_allow_html=True)
