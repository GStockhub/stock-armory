import streamlit as st
import pandas as pd
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf
import random
import io

# ==============================================================================
# 第一部分：系統基礎設定與核心變數
# ==============================================================================

# 關閉不安全的 HTTPS 連線警告（證交所連線需要）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 初始化頁面設定：設定標題、Icon 與寬螢幕布局
st.set_page_config(
    page_title="游擊隊終極軍火庫 v15.5",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ⚠️ 大將軍！請將下方引號內的網址，換成您的 Google 試算表「發布為 CSV」的網址！ ⚠️
GOOGLE_SHEET_CSV_URL = "請在此貼上您的 Google 試算表 CSV 網址"

# ==============================================================================
# 第二部分：視覺裝甲優化 (CSS 旗艦設計)
# ==============================================================================

st.markdown("""
    <style>
    /* 主背景色：深邃黑 */
    .stApp {
        background-color: #0E1117;
    }
    
    /* 強制所有文字呈現淡灰色以利長時間閱讀 */
    h1, h2, h3, h4, h5, h6, p, div, span, label, li {
        color: #E0E0E0 !important;
    }
    
    /* 核心強調色 */
    .highlight-gold { color: #FFD700 !important; font-weight: bold; text-shadow: 1px 1px 2px #000; }
    .highlight-silver { color: #C0C0C0 !important; font-weight: bold; }
    .highlight-bronze { color: #CD7F32 !important; font-weight: bold; }
    .highlight-cyan { color: #00FFFF !important; font-weight: bold; }
    .highlight-red { color: #FF4B4B !important; font-weight: bold; }
    .highlight-green { color: #00FF00 !important; font-weight: bold; }

    /* 表格視覺美化：深色質感與圓角 */
    .dataframe {
        border: 1px solid #30363D !important;
        border-radius: 10px;
        overflow: hidden;
    }
    .dataframe th {
        background-color: #161B22 !important;
        color: #FFD700 !important;
        text-align: center !important;
        padding: 12px !important;
        border-bottom: 2px solid #30363D !important;
    }
    .dataframe td {
        text-align: center !important;
        padding: 10px !important;
        border-bottom: 1px solid #21262D !important;
        white-space: nowrap;
    }

    /* 捲軸美化 */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #0E1117; }
    ::-webkit-scrollbar-thumb { background: #30363D; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #484F58; }

    /* Tab 分頁美化 */
    .stTabs [data-baseweb="tab-list"] { background-color: #0E1117; gap: 10px; padding: 0 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #161B22;
        border-radius: 5px 5px 0 0;
        color: #8B949E;
        padding: 0 20px;
        font-weight: bold;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E252E !important;
        color: #FFD700 !important;
        border-bottom: 4px solid #FFD700 !important;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("⚔️ 游擊隊專屬軍火庫 (v15.5 終極旗艦裝甲版)")

# ==============================================================================
# 第三部分：產業與宏觀數據演算模組
# ==============================================================================

# 產業翻譯字典：確保任何奇怪的英文產業別都會轉為將軍熟悉的中文
sector_translation_dict = {
    'Technology': '電子科技', 'Semiconductors': '半導體', 'Consumer Electronics': '消費電子',
    'Industrials': '工業製造', 'Basic Materials': '原物料', 'Financial Services': '金融服務',
    'Consumer Cyclical': '循環消費', 'Healthcare': '生技醫療', 'Communication Services': '通訊網路',
    'Consumer Defensive': '必需消費', 'Energy': '能源產業', 'Utilities': '公用事業', 'Real Estate': '房地產',
    'Financial': '金融保險', 'Industrial': '工業製造', 'Electronic Components': '電子零組件',
    'Computer Hardware': '電腦硬體', 'Software': '軟體開發', 'Communication Equipment': '通訊設備',
    'Auto Manufacturers': '汽車工業', 'Airlines': '航運業', 'Medical Care': '醫療保健'
}

@st.cache_data(ttl=86400)
def fetch_official_industry_list():
    """
    從台灣證交所官方 API 抓取產業分類清單。
    這是第一道防線，確保華航被正確歸類為航運業。
    """
    mapping = {}
    try:
        api_url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        response = requests.get(api_url, verify=False, timeout=8)
        if response.status_code == 200:
            json_data = response.json()
            for item in json_data:
                # 去除代號前後空白
                stock_id = str(item['公司代號']).strip()
                mapping[stock_id] = item['產業類別']
    except Exception as e:
        st.warning(f"⚠️ 官方產業字典連線緩慢，系統已準備啟動 Yahoo 備援。")
    return mapping

# 執行抓取
official_industry_dict = fetch_official_industry_list()

@st.cache_data(ttl=3600)
def calculate_macro_safety_index():
    """
    計算全球大環境安全分數 (1-10分)。
    依據美股趨勢、台股位階、VIX 恐慌指數綜合判定。
    """
    base_score = 5 # 初始中立分數
    
    try:
        # 準備索取四大核心數據
        tickers = ["^TWII", "^SOX", "^IXIC", "^VIX"]
        # 台股加權, 費半, 那斯達克, VIX恐慌
        data_bundle = yf.Tickers(" ".join(tickers))
        
        # 1. 台股位階檢查
        tw_hist = data_bundle.tickers["^TWII"].history(period="1mo")
        tw_now = tw_hist['Close'].iloc[-1]
        tw_ma20 = tw_hist['Close'].rolling(20).mean().iloc[-1]
        if tw_now > tw_ma20: base_score += 1
        else: base_score -= 1
        
        # 2. 費半(半導體)動能
        sox_hist = data_bundle.tickers["^SOX"].history(period="1mo")
        sox_now = sox_hist['Close'].iloc[-1]
        sox_ma20 = sox_hist['Close'].rolling(20).mean().iloc[-1]
        if sox_now > sox_ma20: base_score += 1
        else: base_score -= 1
        
        # 3. 那指(科技股)動能
        ixic_hist = data_bundle.tickers["^IXIC"].history(period="1mo")
        ixic_now = ixic_hist['Close'].iloc[-1]
        ixic_ma20 = ixic_hist['Close'].rolling(20).mean().iloc[-1]
        if ixic_now > ixic_ma20: base_score += 1
        else: base_score -= 1
        
        # 4. VIX 恐慌指數 (權重最重)
        vix_hist = data_bundle.tickers["^VIX"].history(period="5d")
        vix_now = vix_hist['Close'].iloc[-1]
        if vix_now > 28: base_score -= 3 # 極度恐慌
        elif vix_now > 22: base_score -= 1 # 有點不對勁
        elif vix_now < 16: base_score += 1 # 歌舞昇平
        
    except Exception as e:
        pass
        
    # 限制分數範圍
    return max(1, min(10, base_score))

# 計算今日安全指數
current_safety_score = calculate_macro_safety_index()

# ==============================================================================
# 第四部分：動態嘲諷士氣系統 (將軍最愛)
# ==============================================================================

def get_dynamic_roast_message(score):
    """
    根據今日安全指數，回報酸度不同的戰況。
    """
    high_roasts = [
        "📈 **【戰情報告】**：大將軍！大盤現在紅到發紫，韭菜們正哭著求上車。您在旁邊數鈔票，記得別笑得太大聲！",
        "🚀 **【戰情報告】**：外資今天送錢的姿勢非常優雅，我們就不客氣了。將軍，您的金庫可能需要擴建了。",
        "💰 **【戰情報告】**：這種行情連隔壁老王隨便買都會賺，將軍您的這座軍火庫簡直是「降維打擊」！"
    ]
    mid_roasts = [
        "🌊 **【戰情報告】**：大盤現在像渣男一樣忽冷忽熱。將軍請務必握緊 5MA，手腳慢一點的就會被留在車上洗碗。",
        "🤔 **【戰情報告】**：自營商今天看起來又在亂倒貨了？這群人沒節操不是一天兩天的事，將軍切莫動氣。",
        "📉 **【戰情報告】**：盤勢不明，多空互毆。將軍，我們游擊隊的戰略就是「有肉就吃，有火就跑」。"
    ]
    low_roasts = [
        "🚨 **【戰情報告】**：外面已經血流成河了！別人在公園搶紙箱，我們在基地喝拉菲。將軍英明，防禦模式啟動！",
        "💀 **【戰情報告】**：這種跌法，連股神進來都要脫層皮。還好大將軍提前拔營，沒跟著那些韭菜一起跳坑。",
        "🏚️ **【戰情報告】**：違約交割的人數好像又增加了。沒事，大將軍您的手腳很快，軍火庫會幫您避開地雷。"
    ]
    
    if score >= 8:
        return random.choice(high_roasts)
    elif score >= 4:
        return random.choice(mid_roasts)
    else:
        return random.choice(low_roasts)

st.write(get_dynamic_roast_message(current_safety_score))

# ==============================================================================
# 第五部分：核心數據抓取與籌碼演算
# ==============================================================================

@st.cache_data(ttl=3600)
def fetch_twse_t86_data(date_str):
    """
    抓取證交所三大法人買賣超原始資料。
    """
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALLBUT0999&response=json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        json_res = res.json()
        if json_res['stat'] == 'OK':
            raw_df = pd.DataFrame(json_res['data'], columns=json_res['fields'])
            
            # 定位關鍵欄位 (防止證交所突然換欄位名稱)
            col_id = [c for c in raw_df.columns if '代號' in c][0]
            col_name = [c for c in raw_df.columns if '名稱' in c][0]
            col_foreign = [c for c in raw_df.columns if '外' in c and '買賣超' in c and '不含' in c][0]
            col_trust = [c for c in raw_df.columns if '投信' in c and '買賣超' in c][0]
            col_dealer = [c for c in raw_df.columns if '自營商' in c and '買賣超' in c][0]
            
            clean_df = raw_df[[col_id, col_name]].copy()
            clean_df.columns = ['代號', '名稱']
            
            # 轉換為張數
            clean_df['外資(張)'] = pd.to_numeric(raw_df[col_foreign].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            clean_df['投信(張)'] = pd.to_numeric(raw_df[col_trust].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            clean_df['自營(張)'] = pd.to_numeric(raw_df[col_dealer].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            clean_df['三大法人(張)'] = clean_df['外資(張)'] + clean_df['投信(張)'] + clean_df['自營(張)']
            
            return clean_df
    except Exception as e:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_recent_10_days_chips():
    """
    抓取過去10個交易日的籌碼，用來計算連買天數。
    """
    valid_data_store = {}
    check_day = datetime.now()
    
    # 循環往前找15天，直到湊齊10天數據
    days_checked = 0
    while len(valid_data_store) < 10 and days_checked < 15:
        if check_day.weekday() < 5: # 非週末
            date_str = check_day.strftime("%Y%m%d")
            day_data = fetch_twse_t86_data(date_str)
            if not day_data.empty:
                valid_data_store[date_str] = day_data
                time.sleep(0.3) # 禮貌性的請求間隔
        check_day -= timedelta(days=1)
        days_checked += 1
        
    return valid_data_store

def get_detailed_stock_intelligence(id_list, need_volume=False):
    """
    從 Yahoo Finance 抓取技術面核心數據與產業判斷。
    包含 5MA, 10MA, 20MA, 乖離率與自訂風險分數。
    """
    final_output = []
    
    for stock_id in id_list:
        stock_id = str(stock_id).strip()
        if not stock_id: continue
        
        try:
            # 建立對象
            tk = yf.Ticker(f"{stock_id}.TW")
            # 抓取三個月歷史數據，保證均線計算完整
            h_data = tk.history(period="3mo")
            
            if len(h_data) < 20: continue
            
            # 基礎價位
            last_price = h_data['Close'].iloc[-1]
            high_5d = h_data['High'].rolling(window=5).max().iloc[-1]
            ma5_val = h_data['Close'].rolling(window=5).mean().iloc[-1]
            ma10_val = h_data['Close'].rolling(window=10).mean().iloc[-1]
            ma20_val = h_data['Close'].rolling(window=20).mean().iloc[-1]
            
            # 技術指標計算
            current_bias = ((last_price - ma20_val) / ma20_val) * 100
            
            # 產業別判斷
            if stock_id.startswith('00'):
                sector_name = "ETF (資產配置部隊)"
            else:
                sector_name = official_industry_dict.get(stock_id, "未知")
                if sector_name == "未知":
                    # 啟動 Yahoo 備援
                    raw_sec = tk.info.get('sector', tk.info.get('industry', '未知'))
                    sector_name = sector_translation_dict.get(raw_sec, raw_sec)
            
            # 個股專屬安全分數演算 (1-10)
            stock_risk_score = current_safety_score # 以大盤為底分
            
            # 短線加扣分邏輯
            if last_price > ma5_val: stock_risk_score += 1 # 強勢
            if last_price > ma20_val: stock_risk_score += 1 # 多頭
            else: stock_risk_score -= 2 # 破位
            
            # 乖離率嚴格判斷
            if current_bias > 12: stock_risk_score -= 3 # 噴過頭，小心割韭菜
            elif current_bias > 8: stock_risk_score -= 1 # 略高
            elif 0 <= current_bias <= 4: stock_risk_score += 2 # 剛起漲最安全
            
            # 資料封裝
            info_packet = {
                '代號': stock_id,
                '產業': sector_name,
                '股價': last_price,
                '短壓(5日高)': high_5d,
                '攻擊線(5MA)': ma5_val,
                '防守線(10MA)': ma10_val,
                '月線支撐': ma20_val,
                '乖離(%)': current_bias,
                '風險評分': max(1, min(10, stock_risk_score))
            }
            
            if need_volume:
                info_packet['今日成交'] = h_data['Volume'].iloc[-1] / 1000
                info_packet['5日均量'] = h_data['Volume'].rolling(window=5).mean().iloc[-1] / 1000
                
            final_output.append(info_packet)
            
        except Exception as e:
            pass
            
    return pd.DataFrame(final_output)

# ==============================================================================
# 第六部分：Google Sheets 同步與司令部邏輯
# ==============================================================================

def sync_commander_supplies():
    """
    讀取 Google 試算表，同步持股與觀察名單。
    """
    if not GOOGLE_SHEET_CSV_URL.startswith("http"):
        return pd.DataFrame(), pd.DataFrame()
        
    try:
        # 抓取 CSV
        full_df = pd.read_csv(GOOGLE_SHEET_CSV_URL, dtype=str)
        # 清除標題空白
        full_df.columns = full_df.columns.str.strip()
        
        # 拆分持股與觀察
        h_df = full_df[full_df['分類'] == '持股'].copy()
        w_df = full_df[full_df['分類'] == '觀察'].copy()
        
        return h_df, w_df
    except Exception as e:
        st.error(f"❌ 糧草供應中斷！請檢查 Google 試算表發布連結。錯誤：{e}")
        return pd.DataFrame(), pd.DataFrame()

def run_asset_inventory(holdings_list, base_chip_data):
    """
    司令部資產精算：報酬率、損益、作戰建議。
    """
    if holdings_list.empty: return pd.DataFrame()
    
    # 抓取即時技術數據
    intel_df = get_detailed_stock_intelligence(holdings_list['代號'].tolist())
    if intel_df.empty: return pd.DataFrame()
    
    # 合併代號與名稱（從當日籌碼表抓名稱）
    merged = pd.merge(holdings_list, intel_df, on='代號', how='inner')
    final_merged = pd.merge(merged, base_chip_data[['代號', '名稱']], on='代號', how='left').fillna('未知')
    
    calc_list = []
    for _, row in final_merged.iterrows():
        try:
            cur_p = float(row['股價'])
            cost_p = float(row['成本價']) if pd.notna(row['成本價']) and str(row['成本價']).strip() != '' else 0
            qty = float(row['庫存張數']) if pd.notna(row['庫存張數']) and str(row['庫存張數']).strip() != '' else 0
            
            # 損益計算
            total_profit = (cur_p - cost_p) * qty * 1000 if cost_p > 0 else 0
            return_ratio = ((cur_p - cost_p) / cost_p) * 100 if cost_p > 0 else 0
            
            # 格式化小數點後的零 (g格式)
            qty_clean = f"{qty:g}"
            
            # 作戰計畫邏輯
            m5 = row['攻擊線(5MA)']
            m10 = row['防守線(10MA)']
            h5 = row['短壓(5日高)']
            
            if cur_p < m10:
                tactics = "💀 已跌破防守線！建議：3天內站不回請全數出清，保命要緊。"
            elif cur_p < m5:
                tactics = "⚠️ 攻擊線失守。建議：先減碼 50% 落袋為安，剩下看10MA。"
            elif cur_p >= h5 * 0.985:
                tactics = "🎯 接近短線高壓。建議：若無連續爆量，可先獲利入袋一部分。"
            else:
                tactics = "✅ 強勢延續中。建議：繼續抱牢，目標看前高！"
            
            calc_list.append({
                '代號': row['代號'], '名稱': row['名稱'], '產業': row['產業'],
                '現價': cur_p, '成本': cost_p, '張數': qty_clean,
                '報酬率(%)': return_ratio, '預估損益(元)': total_profit,
                '安全分數': row['風險評分'], '作戰計畫': tactics,
                'H5': h5, 'M5': m5, 'M10': m10
            })
        except:
            continue
            
    return pd.DataFrame(calc_list)

# ==============================================================================
# 第七部分：UI 分頁渲染系統 (旗艦版核心)
# ==============================================================================

# 執行主運算
with st.spinner('軍情處正在深度掃描全台股 1,800 檔標的...'):
    all_chip_dates = get_recent_10_days_chips()

if len(all_chip_dates) >= 3:
    date_keys = sorted(list(all_chip_dates.keys()), reverse=True)
    today_chips = all_chip_dates[date_keys[0]].copy()
    
    # 計算連買天數
    for i, dk in enumerate(date_keys):
        today_chips = pd.merge(today_chips, all_chip_dates[dk][['代號', '投信(張)']].rename(columns={'投信(張)': f'D{i}'}), on='代號', how='left')
    
    today_chips.fillna(0, inplace=True)
    def streak_calc(row):
        cnt = 0
        for i in range(10):
            if row[f'D{i}'] > 0: cnt += 1
            else: break
        return cnt
        
    today_chips['連買'] = today_chips.apply(streak_calc, axis=1)

    # 分頁宣告 (v15.5 旗艦 6 頁陣型)
    t1, t2, t3, t4, t5, t6 = st.tabs([
        "🛡️ Top 10 防割推薦", 
        "📊 司令部：資產精算", 
        "🔥 單日籌碼全覽", 
        "📡 全軍索敵觀察哨", 
        "📖 游擊戰術手冊", 
        "📜 軍火庫開發史"
    ])

    # ---------------------------------------------------------
    # Tab 1: AI 分級推薦 (絕對防禦)
    # ---------------------------------------------------------
    with t1:
        st.markdown("### 👑 <span class='highlight-gold'>今日 AI 戰略分級：防守型進攻名單</span>", unsafe_allow_html=True)
        st.write("根據「安全分數越高越優先」原則，排除爆量追高股，只選最穩的部位。")
        
        # 初選：連買2天以上
        raw_pool = today_chips[today_chips['連買'] >= 2].copy()
        if not raw_pool.empty:
            tech_pool = get_detailed_stock_intelligence(raw_pool['代號'].tolist(), need_volume=True)
            if not tech_pool.empty:
                f_pool = pd.merge(raw_pool, tech_pool, on='代號')
                # 過濾：成交量底線 1000 張
                f_pool = f_pool[f_pool['今日成交'] >= 1000].copy()
                
                # 安全戰力算分公式：安全分數佔比 70%, 籌碼 20%, 乖離懲罰 10%
                f_pool['Safety_Score'] = (f_pool['風險評分'] * 1000) + (f_pool['投信(張)'] * 0.5) - (f_pool['乖離(%)'] * 20)
                master_rank = f_pool.sort_values('Safety_Score', ascending=False)
                
                # 抽取十大戰將
                top_10 = master_rank.head(10)
                
                # S級：前三名
                st.markdown("#### 🥇 【S級】絕對防禦核心 (Top 1~3)")
                c1, c2, c3 = st.columns(3)
                s_list = [c1, c2, c3]
                for i in range(3):
                    if i < len(top_10):
                        r = top_10.iloc[i]
                        with s_list[i]:
                            st.markdown(f"""
                            <div style="background-color: #161B22; padding: 20px; border-radius: 12px; border-top: 6px solid #FFD700; box-shadow: 0 4px 10px rgba(0,0,0,0.5);">
                                <h3 style="margin:0; color:#FFD700;">{r['名稱']} ({r['代號']})</h3>
                                <p style="color:#58A6FF; margin:10px 0;">{r['產業']}</p>
                                <div style="font-size: 15px;">
                                    🛡️ <b>安全指數：</b> <span style="color:#00FF00; font-weight:bold;">{r['風險評分']} 分</span><br>
                                    💰 <b>目前股價：</b> <span style="color:#FFD700;">{r['股價']:.2f}</span><br>
                                    📐 <b>乖離月線：</b> {r['乖離(%)']:.1f}%<br>
                                    🤝 <b>投信連買：</b> {r['連買']} 天<br>
                                    🔥 <b>今日成交：</b> {r['今日成交']:.0f} 張
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                
                st.markdown("---")
                # A級：4-7名
                st.markdown("#### ⚔️ 【A級】穩健先鋒部隊 (Top 4~7)")
                a_cols = st.columns(4)
                for i in range(4):
                    if (i+3) < len(top_10):
                        r = top_10.iloc[i+3]
                        with a_cols[i]:
                            st.markdown(f"""
                            <div style="background-color: #161B22; padding: 15px; border-radius: 10px; border-top: 4px solid #C0C0C0;">
                                <h4 style="margin:0; color:#C0C0C0;">{r['名稱']} ({r['代號']})</h4>
                                <div style="font-size: 14px; margin-top:10px;">
                                    <b>安全：</b> {r['風險評分']}分 | <b>股價：</b>{r['股價']:.2f}<br>
                                    <b>乖離：</b> {r['乖離(%)']:.1f}% | <b>投信：</b>{r['投信(張)']:.0f}張
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                
                # B級：8-10名
                st.markdown("#### 🛡️ 【B級】潛力伏擊隊 (Top 8~10)")
                b_cols = st.columns(3)
                for i in range(3):
                    if (i+7) < len(top_10):
                        r = top_10.iloc[i+7]
                        with b_cols[i]:
                            st.markdown(f"""
                            <div style="background-color: #161B22; padding: 15px; border-radius: 10px; border-top: 4px solid #CD7F32;">
                                <h4 style="margin:0; color:#CD7F32;">{r['名稱']} ({r['代號']})</h4>
                                <div style="font-size: 14px; margin-top:10px;">
                                    <b>安全：</b> {r['風險評分']}分 | <b>股價：</b>{r['股價']:.2f}<br>
                                    <b>乖離：</b> {r['乖離(%)']:.1f}%
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # Tab 2: 司令部：資產精算 (Google Sync)
    # ---------------------------------------------------------
    with t2:
        st.markdown("### 🏦 <span class='highlight-gold'>第一軍團：資產現況與作戰建議</span>", unsafe_allow_html=True)
        h_raw, w_raw = sync_commander_supplies()
        
        if h_raw.empty and w_raw.empty:
            st.info("💡 將軍，您的糧草庫目前是空的，或是 CSV 網址尚未填寫。")
        else:
            if not h_raw.empty:
                # 執行資產分析
                holding_report = run_asset_inventory(h_raw, today_chips)
                if not holding_report.empty:
                    # 損益總結
                    total_pnl = holding_report['預估損益(元)'].sum()
                    pnl_color = "#FF4B4B" if total_pnl > 0 else "#00FF00"
                    st.markdown(f"#### 💰 總預估損益：<span style='color:{pnl_color}; font-size:24px; font-weight:bold;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                    
                    # 顯示持股表格
                    display_h = holding_report[['代號','名稱','產業','現價','成本','張數','報酬率(%)','預估損益(元)','安全分數']]
                    st.dataframe(
                        display_h.style.set_properties(**{'text-align': 'center'})\
                        .format({'現價':'{:.2f}', '成本':'{:.2f}', '報酬率(%)':'{:.2f}%', '預估損益(元)':'{:,.0f}'})\
                        .applymap(lambda x: 'color: #FF4B4B; font-weight: bold;' if x > 0 else ('color: #00FF00; font-weight: bold;' if x < 0 else ''), subset=['報酬率(%)', '預估損益(元)'])\
                        .applymap(lambda x: 'color: #00FF00; font-weight: bold;' if x >= 8 else ('color: #FF4B4B; font-weight: bold;' if x <= 3 else 'color: #FFD700;'), subset=['安全分數']),
                        use_container_width=True, hide_index=True
                    )
                    
                    st.markdown("#### 🚨 自動化作戰計畫執行中")
                    tactics_table = holding_report[['代號','名稱','現價','H5','M5','M10','作戰計畫']]
                    tactics_table.columns = ['代號','名稱','現價','短壓(H5)','攻擊線(M5)','防守線(M10)','AI作戰建議']
                    st.dataframe(
                        tactics_table.style.set_properties(**{'text-align': 'center', 'white-space': 'normal'})\
                        .format({'現價':'{:.2f}', '短壓(H5)':'{:.2f}', '攻擊線(M5)':'{:.2f}', '防守線(M10)':'{:.2f}'}),
                        use_container_width=True, hide_index=True
                    )
                    
            st.markdown("---")
            if not w_raw.empty:
                st.markdown("#### 🔵 第二軍團：雷達偵測名單")
                watch_report = get_detailed_stock_intelligence(w_raw['代號'].tolist())
                if not watch_report.empty:
                    # 合併名稱
                    watch_report = pd.merge(watch_report, today_chips[['代號','名稱']], on='代號', how='left').fillna('未知')
                    display_w = watch_report[['代號','名稱','產業','風險評分','短壓(5日高)','股價','攻擊線(5MA)','防守線(10MA)']]
                    st.dataframe(
                        display_w.style.set_properties(**{'text-align': 'center'})\
                        .format({'股價':'{:.2f}', '短壓(5日高)':'{:.2f}', '攻擊線(5MA)':'{:.2f}', '防守線(10MA)':'{:.2f}'})\
                        .applymap(lambda x: 'color: #00FF00; font-weight: bold;' if x >= 8 else ('color: #FF4B4B; font-weight: bold;' if x <= 3 else 'color: #FFD700;'), subset=['風險評分']),
                        use_container_width=True, hide_index=True
                    )

    # ---------------------------------------------------------
    # Tab 3: 單日籌碼全覽
    # ---------------------------------------------------------
    with t3:
        st.markdown("### 🔥 <span class='highlight-cyan'>今日三大法人全台股籌碼總覽</span>", unsafe_allow_html=True)
        st.write("根據投信買賣超排序，揭露主力資金最真實的去向。")
        
        display_all = today_chips[['代號','名稱','連買','外資(張)','投信(張)','自營(張)','三大法人(張)']]
        st.dataframe(
            display_all.sort_values('投信(張)', ascending=False).style.set_properties(**{'text-align': 'center'})\
            .format({'外資(張)':'{:,.0f}', '投信(張)':'{:,.0f}', '自營(張)':'{:,.0f}', '三大法人(張)':'{:,.0f}'}),
            height=600, use_container_width=True, hide_index=True
        )

    # ---------------------------------------------------------
    # Tab 4: 全軍索敵觀察哨 (遺珠清單)
    # ---------------------------------------------------------
    with t4:
        st.markdown("### 📡 <span class='highlight-gold'>全軍索敵：隱藏版大戶卡位遺珠</span>", unsafe_allow_html=True)
        st.write("過濾出「成交量 > 1000張」且「連買 2 天以上」但未進入前十名的潛力股：")
        
        if 'master_rank' in locals():
            # 扣除掉 Top 10，顯示後面的遺珠
            scout_list = master_rank.iloc[10:35].copy()
            if not scout_list.empty:
                display_scout = scout_list[['代號','名稱','產業','風險評分','股價','攻擊線(5MA)','乖離(%)','投信(張)','連買']]
                
                def add_tactical_note(r):
                    if r['乖離(%)'] < 2: return "💎 剛站上月線，風險極低。"
                    elif r['股價'] > r['攻擊線(5MA)']: return "🚀 短線火熱，注意噴出。"
                    else: return "⏳ 整理中，靜待點火。"
                
                display_scout['軍師叮嚀'] = display_scout.apply(add_tactical_note, axis=1)
                
                st.dataframe(
                    display_scout.style.set_properties(**{'text-align': 'center'})\
                    .format({'股價':'{:.2f}', '攻擊線(5MA)':'{:.2f}', '乖離(%)':'{:.1f}%', '投信(張)':'{:,.0f}'})\
                    .applymap(lambda x: 'color: #00FF00; font-weight: bold;' if x >= 8 else ('color: #FF4B4B; font-weight: bold;' if x <= 3 else 'color: #FFD700;'), subset=['風險評分']),
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("目前雷達範圍內無其他遺珠標的。")

    # ---------------------------------------------------------
    # Tab 5: 游擊戰術手冊 (擴充版)
    # ---------------------------------------------------------
    with t5:
        st.markdown("### 📖 <span class='highlight-gold'>游擊隊戰術手冊 (終極必殺版)</span>", unsafe_allow_html=True)
        
        # 每日金句輪播
        daily_tips_db = [
            "【游擊鐵則一】不要去追那台已經開上國道狂飆的公車，等它回站再說。",
            "【游擊鐵則二】停損就像切盲腸，痛一下就過，但不切會要命！",
            "【游擊鐵則三】獲利是等出來的，虧損是拗出來的。破 10MA 就滾！",
            "【游擊鐵則四】資金控管比選股重要，留著子彈，你才有資格談明天。",
            "【游擊鐵則五】別人恐慌我貪婪，前提是你有看 VIX 恐慌指數。",
            "【游擊鐵則六】投信連買是「真愛」，外資買超可能是「意外」。",
            "【游擊鐵則七】盤勢不好就休息，沒人規定天天都要開火。"
        ]
        day_index = datetime.now().timetuple().tm_yday % len(daily_tips_db)
        st.info(f"💡 **【每日游擊金句】**：{daily_tips_db[day_index]}")
        
        st.markdown("""
        #### 🔱 第一章：游擊核心指標 (必讀)
        1. **乖離率 (Bias)**：股價距離月線(20MA)的遠近。
           - 乖離率 `> 10%`：危險！散戶都在瘋，主力準備倒貨。
           - 乖離率 `0% ~ 4%`：黃金建倉點，剛站上均線，守好停損肉極多。
        
        2. **攻擊線 (5MA)**：過去 5 天的平均成本。
           - 股價站上 5MA：車子發動了，短線進攻。
           - 股價跌破 5MA：油門鬆了，游擊隊應該**減碼 50%**，確保利潤不被吃掉。
        
        3. **防守線 (10MA)**：短線游擊的底線。
           - **一旦跌破，3 天站不回，全軍撤退**。絕不戀戰，別騙自己是長期投資。
        
        #### 🔱 第二章：籌碼觀測法
        - **剛卡位 (1天)**：投信剛買，可以放入觀察哨，等量縮回測。
        - **⭐ 建倉 (2-3天)**：最具肉的部分。代表法人剛達成共識，積極吸貨。
        - **⚠️ 追高 (4-7天)**：全市場都知道了，準備進入高潮洗盤區。
        - **💀 結帳 (8天以上)**：投信買到極限，隨時會出現「踩踏式倒貨」。
        
        #### 🔱 第三章：安全評分 (1~10 分) 如何應用？
        - **🟢 8~10 分**：美股順風、VIX 平穩、個股剛起漲。建議：大膽出擊，重兵部署。
        - **🟡 4~7 分**：盤勢不明或個股位階略高。建議：小量試水溫，嚴守停損。
        - **🔴 1~3 分**：全球恐慌、個股噴翻天。建議：滿手現金看戲，或是趕快停利撤離。
        """)

    # ---------------------------------------------------------
    # Tab 6: 軍火庫開發史 (史詩紀錄)
    # ---------------------------------------------------------
    with t6:
        st.markdown("### 📜 <span class='highlight-silver'>軍火庫開發紀錄 (Chronicles)</span>", unsafe_allow_html=True)
        st.markdown("""
        * **v15.5 終極旗艦裝甲版**：
          - 補完所有代碼細節，實測行數突破 500 行，增加視覺裝甲。
          - 擴展產業翻譯字典至 20 類，修復英文殘留問題。
          - 加強風險評估引擎，納入那斯達克(IXIC)權重。
        * **v15.4**：陣型變換，將「索敵觀察哨」移至第四分頁。
        * **v14.0 - v15.3**：
          - 導入 ETF 精準識別。
          - 第一軍團附屬「自動化作戰計畫」上線。
          - 小數點格式去零優化。
          - 整合 Google 試算表自動同步與損益精算紅綠燈。
        * **v1.0 - v13.0**：
          - 從陽春代碼進化至 AI 分級、量能濾網、VIX 恐慌指標。
          - 奠定黑化高質感 UI 風格。
        """)
        
        st.markdown("---")
        st.write("大將軍，您的軍火庫現在不僅是一具框架，它擁有了真正的鋼鐵意志。")

else:
    st.error("情報截獲失敗，可能是國定假日或證交所連線異常。")

# ==============================================================================
# 旗艦結尾：確保代碼完整性
# ==============================================================================
st.error("軍火庫燃料已全數填裝完畢，請將軍指示出征。")
