import streamlit as st
import pandas as pd
import requests

# 設定網站基本外觀
st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

st.title("⚔️ 游擊隊專屬軍火庫 - 籌碼雷達 (v1.0)")
st.write("大將軍，歡迎來到您的專屬指揮中心！這裡的情報絕對沒有主力假新聞。")

# 建立免費的證交所情報截獲機器人
@st.cache_data(ttl=3600) # 快取一小時，避免被證交所封鎖
def load_twse_data():
    # 證交所免費 API：三大法人買賣超日報
    url = "https://openapi.twse.com.tw/v1/fund/T86_ALL"
    try:
        res = requests.get(url)
        data = res.json()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        return pd.DataFrame()

st.divider()
st.subheader("🕵️‍♂️ 戰報：最新台股三大法人籌碼動向 (上市)")

with st.spinner('正在從證交所前線截獲情報...'):
    df = load_twse_data()

if not df.empty:
    # 把英文欄位翻譯成我們的戰場術語，並轉換數字格式
    df = df[['Code', 'Name', 'ForeignInvestorBuyAmount', 'InvestmentTrustBuyAmount']]
    df.columns = ['股票代號', '股票名稱', '外資買賣超(股)', '投信買賣超(股)']
    
    # 確保數字欄位可以排序
    df['外資買賣超(股)'] = pd.to_numeric(df['外資買賣超(股)'].str.replace(',', ''), errors='coerce')
    df['投信買賣超(股)'] = pd.to_numeric(df['投信買賣超(股)'].str.replace(',', ''), errors='coerce')
    
    # 篩選出「投信有買進」的股票，並由大到小排序
    df_trust_buy = df[df['投信買賣超(股)'] > 0].sort_values(by='投信買賣超(股)', ascending=False)
    
    st.success("情報截獲成功！以下是投信大哥最新佈局的軍火名單：")
    
    # 在網站上顯示漂亮的表格
    st.dataframe(
        df_trust_buy.style.format({"外資買賣超(股)": "{:,.0f}", "投信買賣超(股)": "{:,.0f}"}),
        height=600,
        use_container_width=True
    )
else:
    st.error("報告將軍，目前無法取得情報，可能證交所伺服器正在維護，請稍後再試。")
