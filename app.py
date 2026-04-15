import streamlit as st
import pandas as pd
import numpy as np
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf
import random

# ==============================================================================
# 【第一區塊：系統底層與現代化防禦配置】
# ==============================================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 初始化 Streamlit 頁面配置
st.set_page_config(
    page_title="游擊隊終極軍火庫 v17.1",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded" 
)

# ==============================================================================
# 【第二區塊：全武裝視覺裝甲】
# ==============================================================================

st.markdown("""
    <style>
    /* 核心背景：戰術深灰 */
    .stApp { background-color: #121619; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, li { color: #D1D5DB !important; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
    
    /* 戰略強調色系統 */
    .highlight-gold { color: #F59E0B !important; font-weight: 900; }
    .highlight-cyan { color: #38BDF8 !important; font-weight: 800; }
    .highlight-red { color: #EF4444 !important; font-weight: 900; }
    .highlight-green { color: #10B981 !important; font-weight: 900; }

    /* 分頁標籤自適應兩排 (不需左右滑動) */
    .stTabs [data-baseweb="tab-list"] {
        display: flex;
        flex-wrap: wrap; 
        gap: 8px;
        background-color: transparent;
        padding-bottom: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        flex-grow: 1; 
        text-align: center;
        height: auto;
        min-height: 45px;
        background-color: #1F2937;
        border-radius: 8px;
        color: #9CA3AF;
        border: 1px solid #374151;
        font-size: 16px;
        font-weight: bold;
        padding: 8px 15px;
        white-space: nowrap;
    }
    .stTabs [aria-selected="true"] {
        background-color: #374151 !important;
        color: #F59E0B !important;
        border-bottom: 4px solid #F59E0B !important;
    }

    /* 頂級卡片設計 */
    .tier-card {
        background-color: #1F2937;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #374151;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
    }
    
    /* 側邊欄與表格美化 */
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
    sheet_url = st.text_input("輸入 Google Sheets CSV 網址：", value="", placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv")
    
    st.markdown("---")
    st.markdown("#### 💰 資金與風險控管 (Level 2)")
    total_capital = st.number_input("作戰本金 (元)", value=200000, step=10000)
    risk_tolerance_pct = st.slider("單筆最大虧損容忍 (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
    risk_amount = total_capital * (risk_tolerance_pct / 100)
    st.info(f"🛡️ 嚴格紀律：單筆交易最大虧損上限 **{risk_amount:,.0f} 元**")
    
    st.markdown("---")
    st.markdown("#### 🔄 戰場快取管理")
    if st.button("一鍵清空情報快取 (強制重抓)"):
        st.cache_data.clear()
        st.success("快取已清除！請重新載入頁面。")

st.markdown("<h1 style='text-align: center;' class='highlight-gold'>⚔️ 游擊隊終極軍火庫 v17.1</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9CA3AF;'>—— 整合 Level 2 量化回測與資金精算 ——</p>", unsafe_allow_html=True)

# ==============================================================================
# 【第四區塊：產業字典與宏觀診斷】
# ==============================================================================

SECTOR_MAP = {
    'Technology': '電子科技', 'Semiconductors': '半導體', 'Consumer Electronics': '消費電子',
    'Industrials': '工業與重工', 'Basic Materials': '基礎原物料', 'Financial Services': '金融保險',
    'Consumer Cyclical': '循環性消費', 'Healthcare': '生技與醫療', 'Communication Services': '通訊網路',
    'Consumer Defensive': '必需性消費', 'Energy': '能源產業', 'Utilities': '公用事業',
    'Real Estate': '房地產與營建', 'Electronic Components': '電子零組件', 'Computer Hardware': '電腦硬體',
    'Software': '軟體服務', 'Auto Manufacturers': '汽車工業', 'Airlines': '航運業', 'Packaging & Containers': '包裝工業',
    'Semiconductor Equipment & Materials': '半導體設備材料', 'Electronic Equipment & Instruments': '電子儀器設備'
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
    except Exception as e:
        st.sidebar.warning("⚠️ 國際行情抓取延遲。")
        
    return max(1, min(10, int(score))), pd.DataFrame(macro_data)

MACRO_SCORE, MACRO_DF = get_macro_dashboard()

def get_dynamic_roast(score):
    if score >= 8: return "📈 **戰況：** 滿街都是股神。外資大放送，將軍請盡情收割，但記得見好就收！"
    elif score >= 4: return "🌊 **戰況：** 盤勢洗刷激烈。別追高，等回測 5MA 才是我們游擊隊的獵場。"
    else: return "🚨 **戰況：** 熊市出沒，血流成河。我們手握現金，看韭菜互砍，香啊！"

st.write(get_dynamic_roast(MACRO_SCORE))

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

def level2_quant_engine(id_list):
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
            high_s = df_stock['High'].squeeze()
            vol_s = df_stock['Volume'].squeeze()
            
            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            h5 = float(high_s.rolling(5).max().iloc[-1])
            vol_now = float(vol_s.iloc[-1]) / 1000
            
            bias = ((p_now - m20) / m20) * 100
            
            # --- 🚀 Level 2 回測模組 ---
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
            
            risk_per_share = p_now - stop_loss
            if risk_per_share > 0:
                max_shares = risk_amount / risk_per_share
                capital_limit_shares = (total_capital * 0.2) / p_now
                suggested_shares = min(max_shares, capital_limit_shares)
            else:
                suggested_shares = 0

            intel_results.append({
                '代號': sid, '產業': ind, '現價': p_now, '成交量': vol_now,
                'H5': h5, 'M5': m5, 'M10': m10, 'M20': m20, '乖離(%)': bias, 
                '風險': max(1, min(10, s_score)),
                '勝率(%)': win_rate, '均報(%)': avg_ret,
                '停損價': stop_loss, '停利價': take_profit, '建議張數': int(suggested_shares / 1000) if suggested_shares > 1000 else round(suggested_shares, 0)
            })
        except Exception as e:
            continue
            
    return pd.DataFrame(intel_results)

# ==============================================================================
# 【第六區塊：旗艦分頁渲染 (修復 pandas .map 語法)】
# ==============================================================================

with st.spinner('情報兵正在進行向量化回測與數據採集...'):
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

    t_rank, t_cmd, t_chip, t_radar, t_book, t_hist = st.tabs([
        "🎯 S/A/B 防割推薦 (含回測)", "🏦 司令部資金精算", "🔥 全市場法人籌碼", "📡 隱藏遺珠雷達", "📖 20萬翻倍實戰教範", "📜 系統演進史"
    ])

    # --------------------------------------------------------------------------
    # Tab 1: AI 推薦 
    # --------------------------------------------------------------------------
    with t_rank:
        st.markdown("### 👑 <span class='highlight-gold'>今日 AI 戰神決策清單</span>", unsafe_allow_html=True)
        
        with st.expander("🌍 查看全球大盤診斷表 (Level 1)"):
            if not MACRO_DF.empty:
                # ⚠️ 熱修復：將 .applymap 替換為 .map 解決 AttributeError
                st.dataframe(MACRO_DF.style.set_properties(**{'text-align': 'center'}).map(lambda x: 'color: #10B981;' if '多頭' in str(x) or '安定' in str(x) else ('color: #EF4444;' if '空頭' in str(x) or '恐慌' in str(x) else ''), subset=['狀態']), use_container_width=True, hide_index=True)

        pool = today_df[today_df['連買'] >= 2].copy()
        if not pool.empty:
            intel_df = level2_quant_engine(pool['代號'].tolist())
            if not intel_df.empty:
                final_rank = pd.merge(pool, intel_df, on='代號')
                final_rank = final_rank[final_rank['成交量'] >= 1000].copy()
                final_rank['Score'] = (final_rank['風險'] * 1000) + (final_rank['勝率(%)'] * 10) - (final_rank['乖離(%)'] * 20)
                rank_sorted = final_rank.sort_values('Score', ascending=False)
                
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
                                ⚖️ <b>AI 建議買量：</b> <span class="highlight-cyan">{r['建議張數']}</span> (單位:張/股)
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                
                if len(top10) > 3:
                    st.markdown("#### ⚔️ 【A/B級】穩健與伏擊清單 (Top 4~10)")
                    other_disp = top10.iloc[3:10][['代號','名稱','風險','勝率(%)','現價','停損價','建議張數','連買']].copy()
                    # ⚠️ 熱修復：將 .applymap 替換為 .map
                    styled_other = (other_disp.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '停損價':'{:.2f}', '勝率(%)':'{:.1f}%'})
                                    .map(lambda x: 'color: #10B981; font-weight: bold;' if x > 60 else '', subset=['勝率(%)']))
                    st.dataframe(styled_other, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # Tab 2: 司令部：資產精算
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
                                elif p_now >= r['H5']: act = "🎯 遇壓停利"
                                
                                res_h.append({'代號': r['代號'], '名稱': r['名稱'], '現價': p_now, '成本': p_cost, '張數': f"{qty:g}", '報酬(%)': ret, '損益(元)': pnl, '作戰指示': act})
                            except: continue
                        
                        df_res = pd.DataFrame(res_h)
                        p_color = "#EF4444" if total_pnl > 0 else "#10B981"
                        st.markdown(f"#### 💰 目前總損益：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                        
                        # ⚠️ 熱修復：將 .applymap 替換為 .map
                        styled_h = (df_res.style.set_properties(**{'text-align': 'center'})
                                    .format({'現價':'{:.2f}', '成本':'{:.2f}', '報酬(%)':'{:.2f}%', '損益(元)':'{:,.0f}'})
                                    .map(lambda x: 'color: #EF4444; font-weight: bold;' if x > 0 else ('color: #10B981; font-weight: bold;' if x < 0 else ''), subset=['報酬(%)', '損益(元)']))
                        st.dataframe(styled_h, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"❌ 讀取 Google Sheets 失敗：{e}")

    # --------------------------------------------------------------------------
    # Tab 3: 單日籌碼全覽
    # --------------------------------------------------------------------------
    with t_chip:
        st.markdown("### 🔥 全市場法人動態")
        st.dataframe(today_df[['代號','名稱','連買','外資(張)','投信(張)']].sort_values('投信(張)', ascending=False).style.format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}'}), height=600, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # Tab 4: 全軍索敵觀察哨
    # --------------------------------------------------------------------------
    with t_radar:
        st.markdown("### 📡 隱藏版投信建倉雷達")
        if 'rank_sorted' in locals():
            scout = rank_sorted.iloc[10:45].copy()
            if not scout.empty:
                scout['戰術'] = scout.apply(lambda r: "💎 低檔潛伏" if r['乖離(%)'] < 3 else ("🚀 突破點火" if r['現價'] > r['M5'] else "⏳ 盤整"), axis=1)
                st.dataframe(scout[['代號','名稱','風險','勝率(%)','現價','乖離(%)','連買','戰術']].style.format({'現價':'{:.2f}', '勝率(%)':'{:.1f}%', '乖離(%)':'{:.1f}%'}), use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # Tab 5: 實戰教範 
    # --------------------------------------------------------------------------
    with t_book:
        st.markdown("### 📖 <span class='highlight-gold'>游擊兵工廠：20萬翻倍實戰教範</span>", unsafe_allow_html=True)
        st.markdown("""
        #### 💰 核心金律：20萬翻40萬的「複利與風控」
        不要幻想一次賺 100%。真正的量化交易是靠**「高勝率 + 嚴格風控」**。
        * **單筆風險限制**：如同左側欄設定，嚴格限制單筆虧損額度。
        * **資金分散**：20 萬本金最多拆分成 3~5 檔操作，絕不 All-in。
        * **獲利期望值**：我們系統抓出的 S 級股票，勝率多在 60% 以上。只要確保「賺的時候賺 6%，賠的時候賠 3%」，穩定重複 30 次出手，資金自然會翻倍。

        #### ⚔️ 兵種操典一：當沖 / 隔日沖 (快打部隊)
        * **選股條件**：鎖定 Tab 1 中「投信剛連買 2 天」且「股價接近短壓 H5」的標的。
        * **進場**：尾盤 13:20 確認 5MA 不破，進場卡位。
        * **出場 (隔日)**：隔天開盤 15 分鐘內，若無法爆量突破 H5 短壓，**直接市價停利/停損**。絕不留倉變存股。

        #### 🛡️ 兵種操典二：短波段操作 (主力部隊)
        * **選股條件**：乖離率在 `0% ~ 4%` 的黃金伏擊區（剛站上月線）。
        * **進場**：依據 S 級卡片上的「AI 建議買量」投入資金。
        * **出場**：
          1. **向上**：股價沿著 5MA 走，讓獲利奔跑。跌破 5MA 先減碼一半。
          2. **向下**：跌破 10MA（系統顯示的🚨停損價），**無視任何理由，無情腰斬出場**。
        """)

    # --------------------------------------------------------------------------
    # Tab 6: 系統演進史
    # --------------------------------------------------------------------------
    with t_hist:
        st.markdown("### 📜 <span class='highlight-cyan'>游擊兵工廠：開發史 (Chronicles)</span>", unsafe_allow_html=True)
        st.markdown("""
        * **v17.1 (熱修復版)**：
          - [Hotfix]：全面升級 Pandas 相容性，解決 `AttributeError: applymap` 環境崩潰問題。
        * **v17.0 (戰神量化版)**：
          - [UI/UX]：實裝**自動換行雙排 Tab 標籤**，完美適配手機版。
          - [量化]：導入 **Level 2 向量化回測引擎**，即時算出歷史勝率與停損利點位。
          - [風控]：側邊欄新增「本金與風險%」設定，系統自動給出精確的「建議買進張數」。
        * **v16.x (全裝甲旗艦版)**：解決 DataFrame 崩潰、API 防禦備援、加入動態嘲諷系統。
        * **v10.x (Google 雲端版)**：首次對接 Google Sheets，實踐雲端司令部。
        * **v1.0 (拓荒版)**：草創三大法人籌碼篩選邏輯。
        """, unsafe_allow_html=True)

else:
    st.error("⚠️ 證交所資料匯入失敗。請檢查網路或稍後再試。")

st.divider()
st.markdown("<p style='text-align: center; color: #9CA3AF;'>© 游擊隊軍火部 - v17.1 Level 2 戰神量化系統</p>", unsafe_allow_html=True)
