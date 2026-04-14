import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

st.title("⚔️ 游擊隊專屬軍火庫 - 籌碼雷達 (v1.1 偽裝版)")
st.write("大將軍，歡迎來到您的專屬指揮中心！這裡的情報絕對沒有主力假新聞。")

@st.cache_data(ttl=3600)
def load_twse_data():
    url = "https://openapi.twse.com.tw/v1/fund/T86_ALL"
    # 【新增特種裝備】：穿上偽裝網，讓證交所以為我們是正常的 Chrome 瀏覽器
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status() # 檢查是否被狙擊 (HTTP 錯誤)
        data = res.json()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        # 如果還是被擋，把敵人的子彈(錯誤代碼)印出來給大將軍看
        st.error(f"🛑 情報兵遭攔截！敵軍火力代碼：{e}") 
        return pd.DataFrame()

st.divider()
st.subheader("🕵️‍♂️ 戰報：最新台股三大法人籌碼動向 (上市)")

with st.spinner('情報兵已穿上偽裝網，正在潛入證交所...'):
    df = load_twse_data()

if not df.empty:
    df = df[['Code', 'Name', 'ForeignInvestorBuyAmount', 'InvestmentTrustBuyAmount']]
    df.columns = ['股票代號', '股票名稱', '外資買賣超(股)', '投信買賣超(股)']
    
    df['外資買賣超(股)'] = pd.to_numeric(df['外資買賣超(股)'].str.replace(',', ''), errors='coerce')
    df['投信買賣超(股)'] = pd.to_numeric(df['投信買賣超(股)'].str.replace(',', ''), errors='coerce')
    
    # 篩選投信有買，並由大到小排序
    df_trust_buy = df[df['投信買賣超(股)'] > 0].sort_values(by='投信買賣超(股)', ascending=False)
    
    st.success("情報截獲成功！以下是投信大哥最新佈局的軍火名單：")
    
    st.dataframe(
        df_trust_buy.style.format({"外資買賣超(股)": "{:,.0f}", "投信買賣超(股)": "{:,.0f}"}),
        height=600,
        use_container_width=True
    )
else:
    st.warning("報告將軍！證交所的國外 IP 防火牆太厚，偽裝網被識破了。若持續失敗，臣將啟動『B 計畫』改用地下的 FinMind 情報網！")
