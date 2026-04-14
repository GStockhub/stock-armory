import streamlit as st
import pandas as pd
import requests
import urllib3
from datetime import datetime, timedelta
import time
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR8WTv-KY303bD4qPlhoyZaAhlJujrfD5fxLpCNjyKvxk5NOxYMsMUAigsvmMV6q-A8HI4hlBk3V4bB/pub?output=csv"

# ================= 偵錯面板 =================
with st.sidebar:
    st.header("🛠️ 調試面板")

    if st.button("🔄 強制重新整理資料"):
        st.cache_data.clear()
        st.success("已清除快取")

    st.write("CSV網址檢查：")
    if GOOGLE_SHEET_CSV_URL.startswith("http"):
        st.success("✅ URL格式正確")
    else:
        st.error("❌ URL錯誤")

    st.code(GOOGLE_SHEET_CSV_URL)

# ================= UI =================
st.markdown("""
<style>
.stApp { background-color: #1E1E1E; }
h1, h2, h3, h4, p, div { color: #E0E0E0 !important; }
</style>
""", unsafe_allow_html=True)

st.title("⚔️ 游擊隊專屬軍火庫（穩定版）")

# ================= 產業資料 =================
@st.cache_data(ttl=86400)
def get_twse_industry_map():
    try:
        res = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False)
        data = res.json()
        return {str(i['公司代號']): i['產業類別'] for i in data}
    except Exception as e:
        st.error(f"產業讀取失敗: {e}")
        return {}

industry_map = get_twse_industry_map()

# ================= 大盤風險 =================
@st.cache_data(ttl=3600)
def get_macro():
    score = 5
    try:
        twii = yf.Ticker("^TWII").history(period="1mo")
        if twii['Close'].iloc[-1] > twii['Close'].rolling(20).mean().iloc[-1]:
            score += 1
        else:
            score -= 1
    except Exception as e:
        st.warning(f"大盤抓取失敗: {e}")
    return score

macro_score = get_macro()

# ================= Google Sheet =================
def load_sheet():
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV_URL)
        df.columns = df.columns.str.strip()

        hold = df[df['分類'] == '持股']
        watch = df[df['分類'] == '觀察']

        return hold, watch

    except Exception as e:
        st.error(f"❌ Google Sheet 讀取失敗: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ================= 股價資料 =================
def get_stock_data(codes):
    result = []
    for code in codes:
        try:
            ticker = yf.Ticker(f"{code}.TW")
            hist = ticker.history(period="3mo")

            if len(hist) < 20:
                continue

            price = hist['Close'].iloc[-1]
            ma5 = hist['Close'].rolling(5).mean().iloc[-1]
            ma10 = hist['Close'].rolling(10).mean().iloc[-1]
            ma20 = hist['Close'].rolling(20).mean().iloc[-1]

            risk = macro_score
            if price > ma5: risk += 1
            if price > ma20: risk += 1
            else: risk -= 2

            result.append({
                "代號": code,
                "股價": price,
                "5MA": ma5,
                "10MA": ma10,
                "20MA": ma20,
                "風險": max(1, min(10, risk))
            })

        except Exception as e:
            st.warning(f"{code} 讀取失敗: {e}")

    return pd.DataFrame(result)

# ================= 主流程 =================
st.divider()

hold_df, watch_df = load_sheet()

# 👉 顯示原始資料（重點）
st.subheader("📦 原始資料")
st.dataframe(hold_df)

st.subheader("👀 觀察資料")
st.dataframe(watch_df)

# ================= 持股 =================
if not hold_df.empty:
    st.subheader("💰 持股分析")

    codes = hold_df['代號'].dropna().tolist()
    stock_df = get_stock_data(codes)

    merged = pd.merge(hold_df, stock_df, on="代號", how="left")

    st.dataframe(merged)

    # 👉 自動策略
    def strategy(row):
        if row['股價'] < row['10MA']:
            return "❌ 跌破10MA 出場"
        elif row['股價'] < row['5MA']:
            return "⚠️ 跌破5MA 減碼"
        else:
            return "✅ 持有"

    merged['建議'] = merged.apply(strategy, axis=1)

    st.subheader("📊 作戰建議")
    st.dataframe(merged[['代號','股價','5MA','10MA','建議']])

else:
    st.warning("沒有持股資料")

# ================= 觀察 =================
if not watch_df.empty:
    st.subheader("🎯 觀察清單")

    codes = watch_df['代號'].dropna().tolist()
    stock_df = get_stock_data(codes)

    st.dataframe(stock_df)

else:
    st.info("沒有觀察清單")

# ================= 收尾 =================
st.divider()

st.write("📈 大盤風險分數:", macro_score)
