import streamlit as st
import pandas as pd
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

# ================= UI 視覺優化 (淺灰質感底色與字體) =================
st.markdown("""
    <style>
    /* 設定全站淺灰背景 */
    .stApp {
        background-color: #F0F2F6;
    }
    /* 設定字體顏色為深鐵灰色，增加閱讀舒適度 */
    h1, h2, h3, h4, h5, h6, p, div, span, label {
        color: #2C3E50 !important;
    }
    /* 調整表格字體顏色 */
    .dataframe {
        color: #2C3E50 !important;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("⚔️ 游擊隊專屬軍火庫 (v4.0 統帥全覽版)")
st.write("大將軍，您的基地已全面升級！包含三大法人全貌、張數轉換、產業類別，以及專屬價位分析！")

# ================= 戰場情報獲取模組 =================

# 獲取「上市產業別與名稱」字典 (直接從證交所開放資料抓取，保證中文)
@st.cache_data(ttl=86400)
def get_stock_info_map():
    info_map = {}
    try:
        res = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False, timeout=10)
        for item in res.json():
            info_map[item['公司代號']] = {'名稱': item['公司名稱'], '產業': item['產業類別']}
    except:
        pass
    return info_map

stock_info_dict = get_stock_info_map()

# 獲取單日三大法人資料
def fetch_twse_t86(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALLBUT0999&response=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        data = res.json()
        if data['stat'] == 'OK':
            df = pd.DataFrame(data['data'], columns=data['fields'])
            
            # 動態找尋欄位
            col_code = [c for c in df.columns if '代號' in c][0]
            col_name = [c for c in df.columns if '名稱' in c][0]
            
            # 尋找三大法人欄位
            foreign_cols = [c for c in df.columns if '外' in c and '買賣超' in c and '不含' in c]
            col_foreign = foreign_cols[0] if foreign_cols else [c for c in df.columns if '外' in c and '買賣超' in c][0]
            col_trust = [c for c in df.columns if '投信' in c and '買賣超' in c][0]
            dealer_cols = [c for c in df.columns if '自營商' in c and '買賣超' in c]
            col_dealer = min(dealer_cols, key=len) if dealer_cols else None # 取名稱最短的通常是總和
            
            # 萃取所需欄位並轉換單位 (股 -> 張，除以1000)
            res_df = df[[col_code, col_name]].copy()
            res_df.columns = ['股票代號', '股票名稱']
            
            # 加入產業別
            res_df['產業類別'] = res_df['股票代號'].apply(lambda x: stock_info_dict.get(x, {}).get('產業', '未知'))
            
            res_df['外資買賣超(張)'] = pd.to_numeric(df[col_foreign].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            res_df['投信買賣超(張)'] = pd.to_numeric(df[col_trust].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            if col_dealer:
                res_df['自營商買賣超(張)'] = pd.to_numeric(df[col_dealer].str.replace(',', ''), errors='coerce').fillna(0) / 1000
            else:
                res_df['自營商買賣超(張)'] = 0
                
            return res_df
    except:
        pass
    return pd.DataFrame()

# 建立時光機：往前尋找最近的 3 個交易日
@st.cache_data(ttl=3600)
def get_last_3_trading_days_data():
    dates_to_try = [(datetime.now() - timedelta(days=i)) for i in range(10)]
    valid_data = {}
    
    for d in dates_to_try:
        if len(valid_data) >= 3: break
        if d.weekday() >= 5: continue
            
        date_str = d.strftime("%Y%m%d")
        df = fetch_twse_t86(date_str)
        if not df.empty:
            valid_data[date_str] = df
            time.sleep(0.5) 
            
    return valid_data

# 啟動月線與價位探測器 (使用 yfinance)
def get_price_and_levels(stock_list):
    results = []
    for code in stock_list:
        code = str(code).strip()
        if not code: continue
        try:
            ticker = yf.Ticker(f"{code}.TW")
            hist = ticker.history(period="3mo") # 抓三個月資料算技術線
            if len(hist) >= 20:
                current_price = hist['Close'].iloc[-1]
                ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                high20 = hist['High'].rolling(window=20).max().iloc[-1]
                low20 = hist['Low'].rolling(window=20).min().iloc[-1]
                
                bias = ((current_price - ma20) / ma20) * 100
                results.append({
                    '股票代號': code, 
                    '目前股價': current_price, 
                    '壓力價(近20日高)': high20,
                    '支撐價(月線20MA)': ma20,
                    '底線價(近20日低)': low20,
                    '乖離率(%)': bias
                })
        except:
            pass
    return pd.DataFrame(results)

# ================= 戰情室介面 (三大分頁) =================
st.divider()

with st.spinner('情報兵正在為將軍繪製最新戰場地圖...'):
    historical_data = get_last_3_trading_days_data()

if len(historical_data) >= 3:
    sorted_dates = sorted(list(historical_data.keys()), reverse=True)
    day1_date, day2_date, day3_date = sorted_dates[0], sorted_dates[1], sorted_dates[2]
    
    # 取得最新一天的完整資料 (包含三大法人)
    df_latest = historical_data[day1_date].copy()
    
    # 取出前兩天的投信資料來做連續買超比對
    df_yesterday = historical_data[day2_date][['股票代號', '投信買賣超(張)']].rename(columns={'投信買賣超(張)': '昨日投信買超(張)'})
    df_daybefore = historical_data[day3_date][['股票代號', '投信買賣超(張)']].rename(columns={'投信買賣超(張)': '前日投信買超(張)'})
    
    # 合併三天資料
    merged_df = pd.merge(df_latest, df_yesterday, on='股票代號', how='left').fillna(0)
    merged_df = pd.merge(merged_df, df_daybefore, on='股票代號', how='left').fillna(0)
    
    # 建立三大分頁
    tab1, tab2, tab3 = st.tabs(["🛡️ 防割韭菜 (初建倉名單)", "🔥 單日三大法人全覽", "📈 持股與觀察名單 (三段價位)"])
    
    # ---------------- 分頁 1: 防割韭菜 ----------------
    with tab1:
        st.subheader("🎯 將軍嚴選：投信剛上車 + 股價位階安全")
        st.markdown(f"**分析區間：** 最新日({day1_date})、昨日({day2_date})、前日({day3_date}) | 單位：張")
        
        # 條件：最新日與昨日投信皆為買超
        condition_buy = (merged_df['投信買賣超(張)'] > 0) & (merged_df['昨日投信買超(張)'] > 0)
        potential_stocks = merged_df[condition_buy].copy()
        
        def check_streak(row):
            if row['前日投信買超(張)'] > 0: return "連買 3 天以上"
            else: return "剛連買 2 天 (極新鮮⭐)"
        
        if not potential_stocks.empty:
            potential_stocks['建倉狀態'] = potential_stocks.apply(check_streak, axis=1)
            
            # 抓取股價與月線距離
            stock_codes = potential_stocks['股票代號'].tolist()
            ma_df = get_price_and_levels(stock_codes)
            
            if not ma_df.empty:
                final_df = pd.merge(potential_stocks, ma_df, on='股票代號')
                
                # 防追高：只顯示距離月線小於 10% 的股票
                safe_df = final_df[final_df['乖離率(%)'] < 10].copy()
                
                # 重新排列直觀的欄位
                safe_df = safe_df[['股票代號', '股票名稱', '產業類別', '建倉狀態', 
                                   '投信買賣超(張)', '昨日投信買超(張)', '外資買賣超(張)', '自營商買賣超(張)', 
                                   '目前股價', '支撐價(月線20MA)', '乖離率(%)']]
                
                safe_df = safe_df.sort_values(by='乖離率(%)', ascending=True)
                
                st.success("🎉 報告將軍！以下是投信【剛建倉】且【位階安全】的名單，並附上外資動向供您確認是否有土洋合買！")
                st.dataframe(
                    safe_df.style.format({
                        "投信買賣超(張)": "{:,.0f}", "昨日投信買超(張)": "{:,.0f}", 
                        "外資買賣超(張)": "{:,.0f}", "自營商買賣超(張)": "{:,.0f}",
                        "目前股價": "{:.2f}", "支撐價(月線20MA)": "{:.2f}", "乖離率(%)": "{:.2f}%"
                    }),
                    height=500, use_container_width=True
                )
            else:
                st.warning("暫時無法取得報價資料。")
        else:
            st.info("今日沒有符合「剛剛連買 2 天」的標的。")

    # ---------------- 分頁 2: 單日全覽 ----------------
    with tab2:
        st.subheader("🔥 舊版保留：單日三大法人籌碼總覽 (全市場)")
        st.markdown(f"**日期：** {day1_date} | 單位：張")
        
        # 只顯示投信或外資有買賣的，並按照投信買超排序
        df_all = df_latest.sort_values(by='投信買賣超(張)', ascending=False)
        st.dataframe(
            df_all.style.format({
                "外資買賣超(張)": "{:,.0f}", 
                "投信買賣超(張)": "{:,.0f}", 
                "自營商買賣超(張)": "{:,.0f}"
            }),
            height=600, use_container_width=True
        )

    # ---------------- 分頁 3: 觀察名單與三段價位 ----------------
    with tab3:
        st.subheader("📈 大將軍專屬：持股與觀察名單戰略版")
        st.write("輸入您目前持有的股票代號或觀察名單（用逗號隔開，例如：3189, 4958, 2313）")
        
        user_input = st.text_input("📝 輸入股票代號：", value="3189, 4958, 2313")
        
        if st.button("🚀 執行價位分析"):
            with st.spinner("正在為您計算三段價位..."):
                code_list = [c.strip() for c in user_input.split(',')]
                levels_df = get_price_and_levels(code_list)
                
                if not levels_df.empty:
                    # 補上名稱與產業
                    levels_df['股票名稱'] = levels_df['股票代號'].apply(lambda x: stock_info_dict.get(x, {}).get('名稱', '未知'))
                    levels_df['產業類別'] = levels_df['股票代號'].apply(lambda x: stock_info_dict.
