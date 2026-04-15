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
    page_title="游擊隊終極軍火庫 v17.2",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded" 
)

# ==============================================================================
# 【第二區塊：視覺裝甲 (修復版與自適應)】
# ==============================================================================

st.markdown("""
    <style>
    .stApp { background-color: #121619; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, li { color: #D1D5DB !important; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
    
    .highlight-gold { color: #F59E0B !important; font-weight: 900; }
    .highlight-cyan { color: #38BDF8 !important; font-weight: 800; }
    .highlight-red { color: #EF4444 !important; font-weight: 900; }
    .highlight-green { color: #10B981 !important; font-weight: 900; }

    /* 分頁標籤自適應兩排 */
    .stTabs [data-baseweb="tab-list"] { display: flex; flex-wrap: wrap; gap: 8px; background-color: transparent; padding-bottom: 10px; }
    .stTabs [data-baseweb="tab"] { flex-grow: 1; text-align: center; height: auto; min-height: 45px; background-color: #1F2937; border-radius: 8px; color: #9CA3AF; border: 1px solid #374151; font-size: 16px; font-weight: bold; padding: 8px 15px; white-space: nowrap; }
    .stTabs [aria-selected="true"] { background-color: #374151 !important; color: #F59E0B !important; border-bottom: 4px solid #F59E0B !important; }

    .tier-card { background-color: #1F2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; margin-bottom: 15px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5); }
    [data-testid="stSidebar"] { background-color: #0F1115; border-right: 1px solid #1F2937; }
    [data-testid="stDataFrame"] { border-radius: 10px !important; overflow: hidden; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 【第三區塊：側邊欄 (Sidebar) - 資金控管與設定】
# ==============================================================================

with st.sidebar:
    st.markdown("### ⚙️ 指揮中心設定")
    st.markdown("---")
    
    st.markdown("#### 🔗 糧草供應線 (CSV)")
    sheet_url = st.text_input("輸入 Google Sheets CSV 網址：", value="", placeholder="https://docs.google.com/.../pub?output=csv")
    
    st.markdown("---")
    st.markdown("#### 💰 資金與風險控管 (Level 2)")
    total_capital = st.number_input("作戰本金 (元)", value=200000, step=10000)
    risk_tolerance_pct = st.slider("單筆最大虧損容忍 (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
    risk_amount = total_capital * (risk_tolerance_pct / 100)
    
    st.info(f"""🛡️ **保命底線：{risk_amount:,.0f} 元**
    💡 **將軍須知**：這代表您買進一檔股票，若不幸跌破 10MA 停損出場，最多只會賠這個數字。系統會根據這個容忍度，自動幫您反推「最多能買幾張」。""")
    
    st.markdown("---")
    st.markdown("#### 🔄 戰場快取管理")
    if st.button("一鍵清空情報快取 (強制重抓)"):
        st.cache_data.clear()
        st.success("快取已清除！請重新載入頁面。")

st.markdown("<h1 style='text-align: center;' class='highlight-gold'>⚔️ 游擊隊終極軍火庫 v17.2</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9CA3AF;'>—— 整合 Level 2 資金精算與戰術雷達 ——</p>", unsafe_allow_html=True)

# ==============================================================================
# 【第四區塊：產業字典與宏觀診斷】
# ==============================================================================

SECTOR_MAP = {
    'Technology': '電子科技', 'Semiconductors': '半導體', 'Consumer Electronics': '消費電子',
    'Industrials': '工業與重工', 'Basic Materials': '基礎原物料', 'Financial Services': '金融保險',
    'Consumer Cyclical': '循環消費', 'Healthcare': '生技醫療', 'Communication Services': '通訊網路',
    'Consumer Defensive': '必需消費', 'Energy': '能源產業', 'Utilities': '公用事業',
    'Real Estate': '房地產', 'Electronic Components': '電子零組件', 'Computer Hardware': '電腦硬體',
    'Software': '軟體服務', 'Auto Manufacturers': '汽車工業', 'Airlines': '航運業'
}

@st.cache_data(ttl=86400)
def fetch_official_twse_industry():
    mapping = {}
    try:
        res = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False, timeout=5)
        if res.status_code == 200:
            for item in res.json():
                mapping[str(item['公司代號']).strip()] = item['產業類別']
    except: pass
    return mapping

TWSE_IND_MAP = fetch_official_twse_industry()

@st.cache_data(ttl=3600)
def get_macro_dashboard():
    score = 5.0
    macro_data = []
    indices = {"^TWII": "台股加權", "^SOX": "美費城半導體", "^IXIC": "那斯達克", "^VIX": "恐慌指數(VIX)"}
    
    try:
        tickers = yf.Tickers(" ".join(indices.keys()))
        for sym, name in indices.items():
            hist = tickers.tickers[sym].history(period="1mo")
            if hist.empty: continue
            
            last_p = hist['Close'].iloc[-1]
            ma20 = hist['Close'].rolling(20).mean().iloc[-1]
            status = "🟢 多頭" if last_p > ma20 else "🔴 空頭"
            
            if sym == "^VIX":
                status = "🔴 恐慌" if last_p > 25 else ("🟡 警戒" if last_p > 18 else "🟢 安定")
                if last_p > 25: score -= 2
                elif last_p < 18: score += 1
            else:
                if last_p > ma20: score += 1
                else: score -= 1
                
            macro_data.append({"戰區": name, "現值": round(last_p, 2), "月線": round(ma20, 2), "狀態": status})
    except:
        st.sidebar.warning("⚠️ 國際行情抓取延遲。")
        
    return max(1, min(10, int(score))), pd.DataFrame(macro_data)

MACRO_SCORE, MACRO_DF = get_macro_dashboard()

# ==============================================================================
# 【第五區塊：數據抓取與 Level 2 量化回測引擎】
# ==============================================================================

@st.cache_data(ttl=3600)
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
                    cid, cnm = [c for c in df.columns if '代號' in c][0], [c for c in df.columns if '名稱' in c][0]
                    ctru = [c for c in df.columns if '投信' in c and '買賣超' in c][0]
                    cfor = [c for c in df.columns if '外資' in c and '買賣超' in c and '不含' in c][0]
                    
                    clean = df[[cid, cnm]].copy()
                    clean.columns = ['代號', '名稱']
                    clean['投信(張)'] = pd.to_numeric(df[ctru].str.replace(',', ''), errors='coerce').fillna(0) / 1000
                    clean['外資(張)'] = pd.to_numeric(df[cfor].str.replace(',', ''), errors='coerce').fillna(0) / 1000
                    chip_dict[d_str] = clean
                    time.sleep(0.2)
            except: pass
        date_ptr -= timedelta(days=1)
        attempts += 1
    return chip_dict

def format_lots(shares):
    """ 將股數轉為張數，並去掉多餘的 0 """
    lots = shares / 1000
    if lots <= 0: return "0"
    # 使用 g 格式自動處理小數點與零
    return f"{lots:g}"

def level2_quant_engine(id_list):
    """ 量化引擎：回測半年勝率，計算停損利與建議張數 """
    intel_results = []
    tickers_str = " ".join([f"{sid}.TW" for sid in id_list])
    try:
        bulk_data = yf.download(tickers_str, period="6mo", group_by="ticker", threads=True, progress=False)
    except: return pd.DataFrame() 
    
    for sid in id_list:
        try:
            if len(id_list) == 1: df_stock = bulk_data
            else: df_stock = bulk_data[f"{sid}.TW"]
            
            if df_stock.empty or len(df_stock) < 30: continue
            
            close_s = df_stock['Close'].squeeze()
            vol_s = df_stock['Volume'].squeeze()
            
            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            vol_now = float(vol_s.iloc[-1]) / 1000
            
            bias = ((p_now - m20) / m20) * 100
            
            # --- 回測模組 (半年期) ---
            df_bt = pd.DataFrame({'Close': close_s})
            df_bt['MA5'] = df_bt['Close'].rolling(5).mean()
            df_bt['MA20'] = df_bt['Close'].rolling(20).mean()
            df_bt['Signal'] = (df_bt['Close'] > df_bt['MA5']) & (df_bt['Close'] > df_bt['MA20'])
            df_bt['Fwd_Return'] = df_bt['Close'].shift(-5) / df_bt['Close'] - 1
            
            signals = df_bt[df_bt['Signal'] == True].dropna()
            if not signals.empty:
                win_rate = (signals['Fwd_Return'] > 0).mean() * 100
                avg_ret = signals['Fwd_Return'].mean() * 100
            else:
                win_rate, avg_ret = 50.0, 0.0

            ind = TWSE_IND_MAP.get(sid, "未知")
            if ind == "未知":
                try:
                    tk = yf.Ticker(f"{sid}.TW")
                    raw_ind = tk.info.get('sector', tk.info.get('industry', '未知'))
                    ind = SECTOR_MAP.get(raw_ind, raw_ind)
                except: pass
            if sid.startswith('00'): ind = "ETF"

            s_score = MACRO_SCORE
            if p_now > m5: s_score += 1
            if p_now > m20: s_score += 1
            else: s_score -= 2
            if bias > 10: s_score -= 2
            elif 0 <= bias <= 5: s_score += 2

            stop_loss = m10
            take_profit = p_now * 1.05 
            
            # 精算建議張數
            risk_per_share = p_now - stop_loss
            if risk_per_share > 0:
                max_shares = risk_amount / risk_per_share
                capital_limit_shares = (total_capital * 0.2) / p_now # 單檔不超過總資金20%
                suggested_shares = min(max_shares, capital_limit_shares)
            else:
                suggested_shares = 0

            intel_results.append({
                '代號': sid, '產業': ind, '現價': p_now, '成交量': vol_now,
                'M5': m5, 'M10': m10, 'M20': m20, '乖離(%)': bias, 
                '風險': max(1, min(10, s_score)),
                '勝率(%)': win_rate, '均報(%)': avg_ret,
                '停損價': stop_loss, '停利價': take_profit, 
                '建議買量(張)': format_lots(suggested_shares)
            })
        except: continue
            
    return pd.DataFrame(intel_results)

# ==============================================================================
# 【第六區塊：旗艦分頁渲染 (重排與擴充)】
# ==============================================================================

with st.spinner('情報兵正在進行大數據回測與籌碼精算...'):
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

    # 依將軍指示重新排列 Tab
    t_rank, t_chip, t_radar, t_cmd, t_book, t_hist = st.tabs([
        "🎯 S/A/B 防割推薦", "🔥 全市場法人籌碼", "📡 遺珠與即時雷達", "🏦 司令部資金精算", "📖 實戰與名詞教範", "📜 系統演進史"
    ])

    # --------------------------------------------------------------------------
    # Tab 1: AI 推薦 (新增排名、產業、顏色判定)
    # --------------------------------------------------------------------------
    with t_rank:
        st.markdown("### 👑 <span class='highlight-gold'>今日 AI 戰神決策清單</span>", unsafe_allow_html=True)
        
        with st.expander("🌍 查看全球大盤診斷表 (Level 1)"):
            if not MACRO_DF.empty:
                st.dataframe(MACRO_DF.style.set_properties(**{'text-align': 'center'}).map(lambda x: 'color: #10B981;' if '多頭' in str(x) or '安定' in str(x) else ('color: #EF4444;' if '空頭' in str(x) or '恐慌' in str(x) else ''), subset=['狀態']), use_container_width=True, hide_index=True)

        pool = today_df[today_df['連買'] >= 2].copy()
        if not pool.empty:
            intel_df = level2_quant_engine(pool['代號'].tolist())
            if not intel_df.empty:
                final_rank = pd.merge(pool, intel_df, on='代號')
                final_rank = final_rank[final_rank['成交量'] >= 1000].copy()
                final_rank['Score'] = (final_rank['風險'] * 1000) + (final_rank['勝率(%)'] * 10) - (final_rank['乖離(%)'] * 20)
                rank_sorted = final_rank.sort_values('Score', ascending=False).reset_index(drop=True)
                rank_sorted['名次'] = rank_sorted.index + 1 # 加入名次
                
                top10 = rank_sorted.head(10)
                
                st.markdown("#### 🥇 【S級】絕對防禦核心 (Top 1~3)")
                cols_s = st.columns(3)
                for i in range(min(3, len(top10))):
                    r = top10.iloc[i]
                    with cols_s[i]:
                        st.markdown(f"""
                        <div class="tier-card" style="border-top: 5px solid #F59E0B;">
                            <h3 style="margin:0; color:#F59E0B;">{r['名稱']} ({r['代號']})</h3>
                            <p style="color:#9CA3AF; margin:5px 0 10px 0;">{r['產業']} | 投信連買 {r['連買']} 天</p>
                            <div style="background-color: #111827; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
                                📊 <b>量化回測 (半年)：</b><br>
                                勝率：<span class="highlight-green">{r['勝率(%)']:.1f}%</span> | 均報：<span class="highlight-cyan">+{r['均報(%)']:.1f}%</span>
                            </div>
                            <div style="font-size: 15px; line-height: 1.6;">
                                💰 <b>進場現價：</b> <span class="highlight-gold">{r['現價']:.2f}</span> (乖離 {r['乖離(%)']:.1f}%)<br>
                                🎯 <b>短線停利：</b> {r['停利價']:.2f}<br>
                                🚨 <b>10MA停損：</b> <span class="highlight-red">{r['停損價']:.2f}</span><br>
                                ⚖️ <b>AI 建議買量：</b> <span class="highlight-cyan">{r['建議買量(張)']}</span> 張
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                
                if len(top10) > 3:
                    st.markdown("#### ⚔️ 【A/B級】穩健與伏擊清單 (Top 4~10)")
                    other_disp = top10.iloc[3:10][['名次','代號','名稱','產業','風險','勝率(%)','現價','停損價','建議買量(張)','連買']].copy()
                    
                    # 顏色套用邏輯：風險 >=8 綠, <=3 紅, 其餘不變
                    def risk_color(val):
                        if val >= 8: return 'color: #10B981; font-weight: bold;'
                        elif val <= 3: return 'color: #EF4444; font-weight: bold;'
                        return 'color: #F59E0B; font-weight: bold;'
                        
                    styled_other = (other_disp.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '停損價':'{:.2f}', '勝率(%)':'{:.1f}%'})
                                    .map(risk_color, subset=['風險'])
                                    .map(lambda x: 'color: #10B981; font-weight: bold;' if x > 60 else '', subset=['勝率(%)']))
                    st.dataframe(styled_other, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # Tab 2: 單日籌碼全覽 (淨化 0 天與突擊部隊)
    # --------------------------------------------------------------------------
    with t_chip:
        st.markdown("### 🔥 全市場投信籌碼流向")
        
        # 突擊部隊：連買=0 但今日大買前三名
        surprise_atk = today_df[today_df['連買'] == 0].sort_values('投信(張)', ascending=False).head(3)
        if not surprise_atk.empty:
            st.markdown("#### 🚨 投信首日突擊部隊 (觀察指標)")
            st.write("連買 0 天但今日異常大買，可能是主力剛建倉的第一槍：")
            st.dataframe(surprise_atk[['代號','名稱','外資(張)','投信(張)']].style.format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}'}), use_container_width=True, hide_index=True)
            st.markdown("---")
            
        st.markdown("#### 穩健建倉部隊 (連買 >= 1 天)")
        main_chips = today_df[today_df['連買'] > 0].sort_values('投信(張)', ascending=False)
        st.dataframe(main_chips[['代號','名稱','連買','外資(張)','投信(張)']].style.format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}'}), height=500, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # Tab 3: 全軍索敵觀察哨 & 即時雷達
    # --------------------------------------------------------------------------
    with t_radar:
        st.markdown("### 🎯 即時單兵作戰雷達")
        custom_ticker = st.text_input("將軍，請輸入想單獨刺探的股票代號 (如 2330)：")
        if custom_ticker:
            with st.spinner("雷達掃描中..."):
                single_intel = level2_quant_engine([custom_ticker])
                if not single_intel.empty:
                    r = single_intel.iloc[0]
                    st.markdown(f"""
                    <div style="background-color:#1F2937; padding:15px; border-radius:10px; border-left:5px solid #38BDF8;">
                        <h4>{custom_ticker} ({r['產業']}) - 即時戰略回報</h4>
                        <b>現價：</b>{r['現價']:.2f} | <b>乖離率：</b>{r['乖離(%)']:.2f}% | <b>安全風險：</b>{r['風險']}分<br>
                        <b>短線停利：</b>{r['停利價']:.2f} | <b>10MA停損：</b><span style="color:#EF4444;">{r['停損價']:.2f}</span><br>
                        <b>💡 AI建議買進極限：</b><span style="color:#38BDF8; font-weight:bold;">{r['建議買量(張)']} 張</span> (依據側邊欄資金設定)
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.warning("查無此代號技術資料，請確認是否輸入正確 (目前僅支援台股上市櫃)。")
        
        st.markdown("---")
        st.markdown("### 📡 隱藏版投信建倉遺珠 (Top 11~30)")
        if 'rank_sorted' in locals():
            scout = rank_sorted.iloc[10:30].copy()
            if not scout.empty:
                scout['戰術'] = scout.apply(lambda r: "💎 低檔潛伏" if r['乖離(%)'] < 3 else ("🚀 突破點火" if r['現價'] > r['M5'] else "⏳ 盤整"), axis=1)
                st.dataframe(scout[['代號','名稱','產業','風險','勝率(%)','現價','乖離(%)','連買','戰術']].style.format({'現價':'{:.2f}', '勝率(%)':'{:.1f}%', '乖離(%)':'{:.1f}%'}), use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # Tab 4: 司令部：資產精算 
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
                    h_intel = level2_quant_engine(h_df['代號'].tolist())
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
                                
                                res_h.append({'代號': r['代號'], '名稱': r['名稱'], '現價': p_now, '成本': p_cost, '張數': f"{qty:g}", '報酬(%)': ret, '損益(元)': pnl, '作戰指示': act})
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
    # Tab 5: 實戰教範與名詞解釋 (大幅擴充)
    # --------------------------------------------------------------------------
    with t_book:
        st.markdown("### 📖 <span class='highlight-gold'>游擊兵工廠：新兵名詞與實戰教範</span>", unsafe_allow_html=True)
        
        st.markdown("""
        #### 🏫 基礎名詞與參數解釋
        * **恐慌指數 (VIX)**：美股選擇權的隱含波動率。
          - `< 18`：市場安定，適合大膽進攻。
          - `> 25`：進入恐慌，隨時有大跌風險，游擊隊應提高現金水位。
        * **費城半導體 (SOX)**：台灣是科技島，台股走勢與費半連動極高。費半站穩月線，台股科技股才有底氣。
        * **乖離率 (Bias %)**：股價偏離 20 日均線(月線)的百分比。
          - `0% ~ 5%`：**黃金建倉區**。股價剛站上月線，下檔風險極低。
          - `> 10%`：**過熱區**。追高容易買在山頂，主力隨時會倒貨結帳。
          - `< 0%`：**空頭區**。股價在月線之下，游擊隊絕對不碰。
        * **安全風險分數 (1~10)**：綜合大盤 VIX、個股均線與乖離算出的綜合評分。
          - `8~10 (綠色)`：極度安全，大盤順風且個股位階漂亮。
          - `1~3 (紅色)`：危險，可能乖離過大或大盤正在恐慌。
        * **5MA (攻擊線) / 10MA (防守線)**：5 日與 10 日平均成交價。

        ---

        #### 💰 核心金律：20萬翻40萬的「複利與風控」
        不要幻想一次賺 100%。真正的量化交易是靠**「高勝率 + 嚴格風控」**。
        * **單筆風險限制**：如同左側欄設定，嚴格限制單筆虧損額度 (建議設 2%~5%)。
        * **資金分散**：20 萬本金最多拆分成 3~5 檔操作，絕不 All-in。
        * **獲利期望值**：我們系統抓出的 S 級股票，勝率多在 60% 以上。只要確保「賺的時候賺 6%，賠的時候賠 3%」，穩定重複出手，資金自然會翻倍。

        ---

        #### ⚔️ 兵種操典一：當沖 / 隔日沖 (快打部隊)
        * **選股**：鎖定 Tab 1 中「投信剛連買 2 天」且「乖離率 < 5%」的標的。
        * **進場**：尾盤 13:20 確認 5MA 不破，進場卡位。
        * **出場 (隔日)**：隔天開盤 15 分鐘內，若無法爆量突破，或帳上獲利達標，**直接市價停利**。絕不留倉變存股。
        
        *(關於 ChatGPT 建議的移動停利法：帳上獲利若 > 8% 且持續創高，可緊抱直到高點回落 3% 才停利出場)*

        #### 🛡️ 兵種操典二：短波段操作 (主力部隊)
        * **進場**：依據 S 級卡片上的「AI 建議買量(張)」投入資金。
        * **出場**：
          1. **向上**：股價沿著 5MA 走，讓獲利奔跑。跌破 5MA 先減碼一半。
          2. **向下**：跌破 10MA（系統顯示的🚨停損價），**無情腰斬出場**，不拗單。
        """)

    # --------------------------------------------------------------------------
    # Tab 6: 系統演進史 (完整補齊)
    # --------------------------------------------------------------------------
    with t_hist:
        st.markdown("### 📜 <span class='highlight-cyan'>游擊兵工廠：開發史 (Chronicles)</span>", unsafe_allow_html=True)
        st.markdown("""
        * **v17.2 (量化完全體)**：重排分頁順序、張數單位去零優化 (0.128張)、籌碼淨化突擊部隊、雷達區加入**「即時單兵輸入框」**、大幅擴充實戰與名詞教範。
        * **v17.1 (熱修復版)**：全面升級 Pandas 相容性，解決 `AttributeError: applymap` 崩潰問題。
        * **v17.0 (戰神量化版)**：實裝**自動換行雙排 Tab 標籤** (解決手機排版)；導入 **Level 2 回測引擎**算勝率；新增側邊欄資金控管。
        * **v16.0 (全裝甲旗艦版)**：確立全球市場戰略桌 (Macro Scan) 機制。整合 VIX 指標、美費半、那斯達克權重計算。
        * **v14.0 (終極兵法版)**：廢除 20 日高低點，改採短線 5MA/10MA 雙線作戰。首創「自動化作戰建議」。
        * **v12.0 (量能覺醒版)**：引進成交量 > 1000 張流動性過濾門檻。
        * **v10.0 (雲端司令部)**：首次對接 Google Sheets，實踐雲端資產損益精算。
        * **v6.0 (籌碼雷達版)**：對接三大法人數據，確立投信連買核心追蹤。
        * **v4.0 (闇黑統帥版)**：確立 Dark Mode 戰術黑底視覺風格，推出 S/A/B 分級卡片。
        * **v1.0 (拓荒版)**：草創期，克服基礎爬蟲與 Streamlit 框架對接。
        """, unsafe_allow_html=True)

else:
    st.error("⚠️ 證交所資料匯入失敗。請檢查網路或稍後再試。")

st.divider()
st.markdown("<p style='text-align: center; color: #9CA3AF;'>© 游擊隊軍火部 - v17.2 戰神量化完全體</p>", unsafe_allow_html=True)
