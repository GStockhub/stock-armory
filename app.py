import streamlit as st
import pandas as pd
import requests
import urllib3

# 關閉安全警告，避免破門時引發警報器大響
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

st.title("⚔️ 游擊隊專屬軍火庫 - 籌碼雷達 (v1.2 破甲版)")
st.write("大將軍，歡迎來到您的專屬指揮中心！這裡的情報絕對沒有主力假新聞。")

@st.cache_data(ttl=3600)
def load_twse_data():
    url = "https://openapi.twse.com.tw/v1/fund/T86_ALL"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        # 【新增破甲彈】：加入 verify=False，無視證交所的 SSL 憑證盤查，強行截獲資料！
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        res.raise_for_status() 
        data = res.json()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        st.error(f"🛑 情報兵遭攔截！敵軍火力代碼：{e}") 
        return pd.DataFrame()

st.divider()
st.subheader("🕵️‍♂️ 戰報：最新台股三大法人籌碼動向 (上市)")

with st.spinner('裝備破甲彈，強制突破證交所防火牆中...'):
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
    st.warning("報告將軍！強攻失敗，請指示是否切換至地下情報網！")
