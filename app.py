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
    page_title="游擊隊終極軍火庫 v19.0",
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
# 【第二區塊：側邊欄 (Sidebar)】
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

st.markdown("<h1 style='text-align: center;' class='highlight-gold'>⚔️ 游擊隊終極軍火庫 v19.0</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9CA3AF;'>—— 攻擊爆發版 ✕ 嚴格風控 ✕ 土洋合擊 ——</p>", unsafe_allow_html=True)

current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
st.caption(f"<div style='text-align: center; color: #6B7280;'>📡 雷達最後掃描時間：{current_time}</div>", unsafe_allow_html=True)

# ==============================================================================
# 【第三區塊：極速產業字典與宏觀診斷 (修復版)】
# ==============================================================================

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_official_twse_industry():
    ind_mapping = {}
    name_mapping = {}
    try:
        res = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False, timeout=8)
        if res.status_code == 200:
            for item in res.json():
                cid = str(item['公司代號']).strip()
                ind_mapping[cid] = item['產業類別']
                name_mapping[cid] = item['公司名稱']
    except: pass
    return ind_mapping, name_mapping

TWSE_IND_MAP, TWSE_NAME_MAP = fetch_official_twse_industry()

@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_dashboard():
    score = 5.0
    macro_data = []
    indices = {"^TWII": "台股加權", "^SOX": "美費半導體", "^IXIC": "那斯達克", "^VIX": "恐慌指數(VIX)"}
    for sym, name in indices.items():
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="1mo")
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

if MACRO_SCORE < 4:
    st.error(f"🔴 **最高紅色警戒 (大盤分數 {MACRO_SCORE}/10)**：市場極度脆弱。強烈建議：空手觀望，或將「建議買量」自動減半！", icon="🚨")

# ==============================================================================
# 【第四區塊：真・實戰量化回測引擎 (v19 攻擊版)】
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
    
    tickers_str = " ".join([f"{sid}.TW" for sid in id_list])
    try:
        bulk_data = yf.download(tickers_str, period="6mo", group_by="ticker", threads=True, progress=False)
    except: bulk_data = pd.DataFrame() 
    
    for sid in id_list:
        try:
            if len(id_list) == 1: df_stock = bulk_data
            else: 
                if f"{sid}.TW" in bulk_data: df_stock = bulk_data[f"{sid}.TW"]
                else: continue
            
            if df_stock.empty or len(df_stock) < 30: continue
            
            close_s = df_stock['Close'].squeeze()
            vol_s = df_stock['Volume'].squeeze()
            
            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            vol_now = float(vol_s.iloc[-1]) / 1000
            vol_ma5 = float(vol_s.rolling(5).mean().iloc[-1]) / 1000
            
            bias = ((p_now - m20) / m20) * 100
            
            # --- 嚴格多頭排列 ---
            trend_strength = (m5 > m10) and (m10 > m20)
            if not trend_strength: continue 
            
            # --- ★ v19 升級：真實交易模擬回測 (10%停利 / 10天波段) ---
            df_bt = pd.DataFrame({'Close': close_s})
            df_bt['MA5'] = df_bt['Close'].rolling(5).mean()
            df_bt['MA10'] = df_bt['Close'].rolling(10).mean()
            
            signals_idx = df_bt[(df_bt['Close'] > df_bt['MA5']) & (df_bt['MA5'] > df_bt['MA10'])].index
            
            sim_returns = []
            for idx in signals_idx:
                try:
                    entry_p = df_bt.loc[idx, 'Close']
                    future_data = df_bt.loc[idx:].iloc[1:11] # 觀察未來 10 天
                    if future_data.empty: continue
                    
                    exit_p = future_data['Close'].iloc[-1] 
                    
                    for _, row in future_data.iterrows():
                        curr_p = row['Close']
                        # 停損：-3% 或是跌破進場當下的 10MA
                        if curr_p < df_bt.loc[idx, 'MA10'] or (curr_p - entry_p)/entry_p < -0.03:
                            exit_p = curr_p
                            break
                        # ★ 停利：波段放大至 10%
                        elif (curr_p - entry_p)/entry_p >= 0.10:
                            exit_p = curr_p
                            break
                            
                    ret = (exit_p - entry_p) / entry_p
                    sim_returns.append(ret)
                except: continue
                
            if sim_returns:
                sim_arr = np.array(sim_returns)
                win_rate = (sim_arr > 0).mean() * 100
                avg_ret = sim_arr.mean() * 100
            else:
                win_rate, avg_ret = 50.0, 0.0

            ind = TWSE_IND_MAP.get(sid, "科技/其他")
            name = TWSE_NAME_MAP.get(sid, "未知代號")
            if sid.startswith('00'): ind = "ETF"

            s_score = MACRO_SCORE
            if p_now > m5: s_score += 1
            if p_now > m20: s_score += 1
            else: s_score -= 2
            if bias > 10: s_score -= 2
            elif 0 <= bias <= 5: s_score += 2

            # --- ★ v19 升級：動能與突破判定 ---
            momentum_bonus = 50 if vol_now > vol_ma5 * 1.5 else 0
            twenty_high = float(close_s.rolling(20).max().shift(1).iloc[-1])
            if p_now > twenty_high: 
                momentum_bonus += 100 # 創20日新高，暴加動能分數！

            stop_loss = max(m10, p_now * 0.97) 
            take_profit = p_now * 1.10 # 對應回測的 10% 停利
            
            intel_results.append({
                '代號': sid, '名稱': name, '產業': ind, '現價': p_now, '成交量': vol_now, '動能加權': momentum_bonus,
                'M5': m5, 'M10': m10, 'M20': m20, '乖離(%)': bias, 
                '安全指數': max(1, min(10, int(s_score))),
                '勝率(%)': win_rate, '均報(%)': avg_ret,
                '停損價': stop_loss, '停利價': take_profit, 
                '原始風險差額': p_now - stop_loss
            })
        except: continue
            
    return pd.DataFrame(intel_results)

# ==============================================================================
# 【第五區塊：旗艦分頁渲染】
# ==============================================================================

with st.spinner('情報兵正在進行波段爆發回測與籌碼精算...'):
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
        "🎯 游擊隊 S/A/B 推薦", "🔥 三大法人籌碼流向", "🏦 司令部資金精算", "📖 實戰與名詞教範", "📜 系統演進史"
    ])

    # --------------------------------------------------------------------------
    # Tab 1: AI 推薦 & 遺珠
    # --------------------------------------------------------------------------
    with t_rank:
        st.markdown("### 👑 <span class='highlight-gold'>今日 AI 戰神決策清單 (10% 波段攻擊版)</span>", unsafe_allow_html=True)
        
        with st.expander("🌍 查看全球大盤診斷表 (Level 1)"):
            if not MACRO_DF.empty:
                st.dataframe(MACRO_DF.style.set_properties(**{'text-align': 'center'}).map(lambda x: 'color: #10B981;' if '多頭' in str(x) or '安定' in str(x) else ('color: #EF4444;' if '空頭' in str(x) or '恐慌' in str(x) else ''), subset=['狀態']), use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ 國際大盤抓取延遲，請稍後重試。")

        pool_ids = today_df[today_df['連買'] >= 2]['代號'].tolist()
        calc_list = tuple(set(pool_ids + top_80_chips))
        
        if calc_list:
            intel_df = level2_quant_engine(calc_list).copy() 
            
            if not intel_df.empty:
                def calc_suggested_lots(row):
                    if row['原始風險差額'] > 0:
                        max_shares = risk_amount / row['原始風險差額']
                        capital_limit_shares = (total_capital * 0.2) / row['現價']
                        suggested_shares = min(max_shares, capital_limit_shares)
                    else: suggested_shares = 0
                    if MACRO_SCORE < 4: suggested_shares *= 0.5
                    return format_lots(suggested_shares)
                    
                intel_df['建議買量(張)'] = intel_df.apply(calc_suggested_lots, axis=1)

                final_rank = pd.merge(today_df[today_df['連買'] >= 2], intel_df, on='代號')
                final_rank = final_rank[final_rank['成交量'] >= 1000].copy()
                
                # --- ★ v19 升級：更狼性的排名公式 (大幅提高均報權重) ---
                final_rank['Score'] = (final_rank['安全指數'] * 600) + (final_rank['勝率(%)'] * 10) + (final_rank['均報(%)'] * 40) - (abs(final_rank['乖離(%)']) * 25) + final_rank['動能加權']
                
                rank_sorted = final_rank.sort_values('Score', ascending=False).reset_index(drop=True)
                rank_sorted['名次'] = rank_sorted.index + 1
                
                top10 = rank_sorted.head(10)
                
                st.markdown("#### 🥇 【S級】攻擊型防禦核心 (Top 1~3)")
                cols_s = st.columns(3)
                for i in range(min(3, len(top10))):
                    r = top10.iloc[i]
                    with cols_s[i]:
                        st.markdown(f"""
                        <div class="tier-card" style="border-top: 5px solid #F59E0B;">
                            <h3 style="margin:0; color:#F59E0B;">{r['名次']}. {r['名稱_x']} ({r['代號']})</h3>
                            <p style="color:#9CA3AF; margin:5px 0 10px 0;">{r['產業']} | 投信連買 {r['連買']} 天</p>
                            <div style="background-color: #111827; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
                                📊 <b>實戰波段 (-3%損 / +10%利)：</b><br>
                                勝率：<span class="highlight-green">{r['勝率(%)']:.1f}%</span> | 均報：<span class="highlight-cyan">+{r['均報(%)']:.2f}%</span>
                            </div>
                            <div style="font-size: 15px; line-height: 1.6;">
                                🛡️ <b>安全指數：</b> {r['安全指數']} 分<br>
                                💰 <b>進場現價：</b> <span class="highlight-gold">{r['現價']:.2f}</span> (乖離 {r['乖離(%)']:.1f}%)<br>
                                🚨 <b>嚴格停損：</b> <span class="highlight-red">{r['停損價']:.2f}</span><br>
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

                if len(top10) > 3:
                    st.markdown("#### ⚔️ 【A/B級】主升段伏擊清單 (Top 4~10)")
                    other_disp = top10.iloc[3:10][['名次','代號','名稱_x','產業','安全指數','勝率(%)','均報(%)','現價','停損價','建議買量(張)','連買']].rename(columns={'名稱_x':'名稱'}).copy()
                    
                    styled_other = (other_disp.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '停損價':'{:.2f}', '勝率(%)':'{:.1f}%', '均報(%)':'{:.2f}%'})
                                    .map(risk_color, subset=['安全指數'])
                                    .map(lambda x: 'color: #10B981; font-weight: bold;' if x > 60 else '', subset=['勝率(%)']))
                    st.dataframe(styled_other, use_container_width=True, hide_index=True)

                st.markdown("---")
                actual_pool_size = len(rank_sorted)
                st.markdown(f"### 📡 隱藏版投信建倉遺珠 (Top 11 ~ {actual_pool_size})")
                st.info(f"💡 **將軍須知**：今日全台股符合「均線多頭排列 + 投信連買≥2天 + 成交≥1000張」極嚴格標準的標的，**僅有 {actual_pool_size} 檔**。寧缺勿濫！")
                
                if actual_pool_size > 10:
                    scout = rank_sorted.iloc[10:30].copy()
                    scout['戰術'] = scout.apply(lambda r: "💎 低檔潛伏" if r['乖離(%)'] < 3 else ("🚀 突破點火" if r['動能加權'] >= 100 else "⏳ 盤整"), axis=1)
                    styled_scout = (scout[['名次','代號','名稱_x','產業','安全指數','勝率(%)','現價','乖離(%)','連買','戰術']].rename(columns={'名稱_x':'名稱'})
                                    .style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '勝率(%)':'{:.1f}%', '乖離(%)':'{:.1f}%'})
                                    .map(risk_color, subset=['安全指數'])
                                    .map(lambda x: 'color: #10B981; font-weight: bold;' if x > 60 else '', subset=['勝率(%)']))
                    st.dataframe(styled_scout, use_container_width=True, hide_index=True)
            else:
                st.warning("⚔️ 報告將軍，今日無任何標的符合「均線多頭排列」之波段攻擊標準。建議空手觀望！")

    # --------------------------------------------------------------------------
    # Tab 2: 三大法人籌碼流向 (解決滑動 LAG 與加入土洋合擊)
    # --------------------------------------------------------------------------
    with t_chip:
        st.markdown("### 🔥 全市場三大法人籌碼流向")
        
        # --- ★ v19 升級：土洋合擊突擊部隊 ---
        surprise_atk = today_df[(today_df['連買'] == 1) & (today_df['投信(張)'] > 0) & (today_df['外資(張)'] > 0)].sort_values('三大法人合計', ascending=False).head(3)
        if not surprise_atk.empty:
            st.markdown("#### 🚨 土洋合擊！首日突擊部隊")
            st.write("昨日未買，今日**「外資與投信同步大買」**的極強勢起漲訊號：")
            st.dataframe(surprise_atk[['代號','名稱','外資(張)','投信(張)','自營(張)','三大法人合計']].style.format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}','自營(張)':'{:,.0f}','三大法人合計':'{:,.0f}'}), use_container_width=True, hide_index=True)
            st.markdown("---")
            
        st.markdown("#### 穩健建倉部隊 (依三大法人合計買超排序，過濾 Top 200 以防卡頓)")
        
        # 解決網頁 LAG 核心：限制渲染行數
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
                                if p_now < r['M10']: act = "💀 破10MA停損"
                                elif p_now < r['M5']: act = "⚠️ 減碼50%"
                                
                                res_h.append({'代號': r['代號'], '名稱': r['名稱_y'] if '名稱_y' in r else r.get('名稱',''), '現價': p_now, '成本': p_cost, '張數': format_lots(qty * 1000), '報酬(%)': ret, '損益(元)': pnl, '作戰指示': act})
                            except: continue
                        
                        df_res = pd.DataFrame(res_h)
                        p_color = "#EF4444" if total_pnl > 0 else "#10B981"
                        st.markdown(f"#### 💰 目前總損益：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                        
                        styled_h = (df_res.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '成本':'{:.2f}', '報酬(%)':'{:.2f}%', '損益(元)':'{:,.0f}'})
                                    .map(lambda x: 'color: #EF4444; font-weight: bold;' if x > 0 else ('color: #10B981; font-weight: bold;' if x < 0 else ''), subset=['報酬(%)', '損益(元)']))
                        st.dataframe(styled_h, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"❌ 讀取 Google Sheets 失敗：{e}")

    # --------------------------------------------------------------------------
    # Tab 4: 教戰手冊 (真・實戰版)
    # --------------------------------------------------------------------------
    with t_book:
        st.markdown("### 📖 <span class='highlight-gold'>游擊兵工廠：名詞、圖示與實戰教範大全</span>", unsafe_allow_html=True)
        
        st.markdown("""
        #### 🔣 系統圖示 (Icons) 權威指南
        * 👑 **今日 AI 戰神決策清單**：系統精算後的最高殿堂。
        * 🥇 **【S級】絕對防禦核心**：綜合排名前 3 名的頂級戰力標的。
        * ⚔️ **【A/B級】主升段伏擊清單**：排名 4~10 名，適合做波段攻擊配置。
        * 🚨 **警報 / 停損 / 突擊部隊**：代表極度危險的停損線，或是主力同步暴買的「土洋合擊」。
        * 💀 **破 10MA 停損**：持股若出現此圖示，代表防線崩潰，必須無情砍倉。
        * ⚠️ **減碼 50%**：持股跌破 5MA 短線攻擊線，動能熄火，建議先收割一半戰果。
        * ✅ **續抱**：股價沿著均線上攻，非常健康，請讓獲利飛奔。
        * 🚀 **突破點火**：股價突破 20 日新高，隨時可能拉出主升段長紅。
        * 💎 **低檔潛伏**：乖離率 < 3% 的未爆發股，風險極低。

        #### 🏫 核心名詞與數據指標解釋
        * **實戰波段 (-3%損 / +10%利)**：這是 **v19 最大的波段進化**。系統真實模擬過去半年，在符合條件進場後，若獲利達 10% 才停利；若跌破 10MA 或虧損達 3% 則「強制停損」。
        * **均報 (%)**：在上述嚴格的實戰模擬下，平均每次出手的真實報酬率。我們大幅拉高了它的排名權重！
        * **勝率 (%)**：在上述模擬下，能成功獲利出場的機率。
        * **安全指數 (1~10 分)**：基於大盤 VIX、個股均線與乖離算出的防禦力分數，滿分為 10 分。

        #### 🕵️ 系統選股考量與避開陷阱 (將軍必讀)
        * **嚴格多頭濾網 (v19)**：系統現在**只會挑選 `5MA > 10MA > 20MA` (多頭排列)** 的強勢股。
        * **創高動能加權 (v19)**：只要股價突破 20 日高點，系統會判定為「突破起漲」，大幅提升其排名，這能幫您精準抓到最會飆的怪物股。
        * **大盤宏觀濾網**：若大盤安全分數低於 4 分，系統會發出紅色警戒，並「自動將建議買進張數減半」。

        #### 💰 核心金律：20萬翻40萬的「波段風控」
        * 嚴格限制單筆虧損額度 (側邊欄設定)。若容忍 1 萬虧損，系統會反推「最多只能買幾張」。
        * **分批停利**：建議到達 6% 先出一半，剩下的一半放著讓它跑到 10%~15% 以上，吃到完整主升段。
        * **極速停損**：停損價現在設定為「10MA」與「現價 -3%」的 **最高者**。絕不允許單筆交易虧損超過 3%！
        """)

    # --------------------------------------------------------------------------
    # Tab 5: 系統演進史
    # --------------------------------------------------------------------------
    with t_hist:
        st.markdown("### 📜 <span class='highlight-cyan'>游擊兵工廠：開發史 (Chronicles)</span>", unsafe_allow_html=True)
        st.markdown("""
        * **v19.0 (攻擊爆發版)**：**全面採納 Path A 戰略！停利波段拉長至 10%，回測週期延長至 10 天。加入「20日新高突破」動能加權。籌碼表擴充三大法人，並將突擊部隊升級為「土洋合擊」。大幅限制渲染行數 (Top 200) 徹底解決網頁卡頓問題。優化產業辨識 API。**
        * **v18.0 (實戰真劍勝負版)**：重寫回測引擎，導入真實模擬 (-3%硬停損)。加入「5MA>10MA>20MA」嚴格趨勢濾網。加入大盤保護機制。
        * **v17.8 (極致純粹無閹割版)**：為追求極速，無情拔除單兵雷達。為籌碼套用顏色判定。
        * **v17.7 (閃電記憶體版)**：導入 `@st.cache_data` 全面包覆 Level 2 量化引擎，解決重新整理時重複下載數據的痛點。
        * **v17.6 (閃電極速版)**：徹底拔除 YFinance `info` 延遲毒瘤，改用靜態 API 字典秒讀產業與名稱。
        * **v17.5 (專注主戰場版)**：拔除上櫃 (.TWO) 掃描邏輯，專注上市市場運算。
        * **v17.4 (洞悉戰場版)**：修剪小數點至兩位以內、排除金融股霸榜疑慮。
        * **v17.0 (戰神量化版)**：實裝自動換行雙排 Tab 標籤；導入 Level 2 回測引擎；新增側邊欄資金控管。
        * **v16.0 (全裝甲旗艦版)**：確立全球市場戰略桌 (Macro Scan) 機制。
        * **v14.0 (終極兵法版)**：首創「自動化作戰建議」。
        * **v10.0 (雲端司令部)**：首次對接 Google Sheets。
        * **v6.0 (籌碼雷達版)**：對接三大法人數據。
        """, unsafe_allow_html=True)

else:
    st.error("⚠️ 證交所資料匯入失敗。請檢查網路或稍後再試。")

st.divider()
st.markdown("<p style='text-align: center; color: #9CA3AF;'>© 游擊隊軍火部 - v19.0 攻擊爆發版</p>", unsafe_allow_html=True)
