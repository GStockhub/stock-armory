import streamlit as st
import pandas as pd
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

st.title("⚔️ 游擊隊專屬軍火庫 (v3.0 終極防割版)")
st.write("大將軍，我們已啟用「時光機」與「月線探測器」，專抓投信剛剛上車的潛伏股！")

# 1. 建立時光機：往前尋找最近的 3 個交易日
@st.cache_data(ttl=3600)
def get_last_3_trading_days_data():
    dates_to_try = [(datetime.now() - timedelta(days=i)) for i in range(10)]
    valid_data = {}
    
    for d in dates_to_try:
        if len(valid_data) >= 3: # 找到 3 天就停止
            break
        if d.weekday() >= 5: # 跳過六日
            continue
            
        date_str = d.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALLBUT0999&response=json"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        try:
            res = requests.get(url, headers=headers, timeout=5, verify=False)
            data = res.json()
            if data['stat'] == 'OK':
                df = pd.DataFrame(data['data'], columns=data['fields'])
                # 提取代號和投信買賣超
                col_code = [c for c in df.columns if '代號' in c][0]
                col_trust = [c for c in df.columns if '投信' in c and '買賣超' in c][0]
                df = df[[col_code, col_trust]]
                df.columns = ['股票代號', f'投信買賣_{date_str}']
                df[f'投信買賣_{date_str}'] = pd.to_numeric(df[f'投信買賣_{date_str}'].str.replace(',', ''), errors='coerce').fillna(0)
                valid_data[date_str] = df
                time.sleep(0.5) # 遵守不塞車規矩
        except:
            pass
            
    return valid_data

# 2. 啟動月線探測器
def get_price_and_ma(stock_list):
    results = []
    for code in stock_list:
        try:
            # 透過 yfinance 抓取台灣股票 (代號後面要加 .TW)
            ticker = yf.Ticker(f"{code}.TW")
            hist = ticker.history(period="2mo") # 抓兩個月資料算月線
            if len(hist) >= 20:
                current_price = hist['Close'].iloc[-1]
                ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                # 計算乖離率：(現在價格 - 月線) / 月線 * 100
                bias = ((current_price - ma20) / ma20) * 100
                results.append({'股票代號': code, '目前股價': current_price, '月線(20MA)': ma20, '乖離率(%)': bias})
        except:
            pass
    return pd.DataFrame(results)

# ================= 戰情室介面 =================
st.divider()

with st.spinner('情報兵已搭乘時光機，正在比對過去三天的籌碼，並測量月線距離...（約需 10-20 秒）'):
    historical_data = get_last_3_trading_days_data()

if len(historical_data) >= 3:
    # 按照日期由新到舊排序
    sorted_dates = sorted(list(historical_data.keys()), reverse=True)
    day1_date, day2_date, day3_date = sorted_dates[0], sorted_dates[1], sorted_dates[2]
    
    df1, df2, df3 = historical_data[day1_date], historical_data[day2_date], historical_data[day3_date]
    
    # 把三天的資料合併在一起
    merged_df = pd.merge(df1, df2, on='股票代號', how='outer')
    merged_df = pd.merge(merged_df, df3, on='股票代號', how='outer').fillna(0)
    
    # 建立兩個專欄 (分頁)
    tab1, tab2 = st.tabs(["🛡️ 防割韭菜：投信初建倉 (將軍嚴選)", "🔥 單日無腦排行榜 (舊版)"])
    
    with tab1:
        st.subheader("🎯 將軍的 3 層黃金濾網過濾結果")
        st.markdown(f"**分析區間：** 最新日({day1_date})、昨日({day2_date})、前日({day3_date})")
        
        # 濾網 1：投信連續買超 (最新兩天都要買)
        condition_buy = (merged_df[f'投信買賣_{day1_date}'] > 0) & (merged_df[f'投信買賣_{day2_date}'] > 0)
        potential_stocks = merged_df[condition_buy].copy()
        
        # 判定連買天數
        def check_streak(row):
            if row[f'投信買賣_{day3_date}'] > 0: return "連買 3 天以上"
            else: return "剛連買 2 天 (極新鮮)"
        potential_stocks['建倉狀態'] = potential_stocks.apply(check_streak, axis=1)
        
        if not potential_stocks.empty:
            # 濾網 2 & 3：抓取股價與月線距離
            stock_codes = potential_stocks['股票代號'].tolist()
            ma_df = get_price_and_ma(stock_codes)
            
            if not ma_df.empty:
                final_df = pd.merge(potential_stocks, ma_df, on='股票代號')
                
                # 過濾出「距離月線不遠 (乖離率小於 10%)」的股票防追高
                safe_df = final_df[final_df['乖離率(%)'] < 10].copy()
                
                # 整理最終表格外觀
                safe_df = safe_df[['股票代號', '建倉狀態', f'投信買賣_{day1_date}', f'投信買賣_{day2_date}', '目前股價', '月線(20MA)', '乖離率(%)']]
                safe_df.columns = ['股票代號', '建倉狀態', '最新日買超(股)', '昨日買超(股)', '目前股價', '月線(20MA)', '乖離率(%)']
                safe_df = safe_df.sort_values(by='乖離率(%)', ascending=True) # 乖離率越小(越靠近月線)排越前面
                
                st.success("🎉 過濾完成！這些股票【投信剛剛進場】，且【股價靠近月線】，受傷機率極低！")
                st.dataframe(
                    safe_df.style.format({"最新日買超(股)": "{:,.0f}", "昨日買超(股)": "{:,.0f}", "目前股價": "{:.2f}", "月線(20MA)": "{:.2f}", "乖離率(%)": "{:.2f}%"}),
                    height=500, use_container_width=True
                )
            else:
                st.warning("月線探測器暫時無法取得報價資料。")
        else:
            st.info("報告將軍，今日沒有符合「剛剛連續買超 2 天」的標的。投信大哥都在休息！")

    with tab2:
        st.subheader("單日排行榜 (僅供參考，小心追高！)")
        df1_display = df1[df1[f'投信買賣_{day1_date}'] > 0].sort_values(by=f'投信買賣_{day1_date}', ascending=False)
        st.dataframe(df1_display.style.format({f'投信買賣_{day1_date}': "{:,.0f}"}), height=400)

else:
    st.error("情報截獲失敗，可能是國定假日或證交所連線異常。")
