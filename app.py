import streamlit as st
import pandas as pd
import requests
import urllib3

# 關閉安全警告，避免破門時引發警報器大響
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="游擊隊專屬軍火庫", page_icon="⚔️", layout="wide")

st.title("⚔️ 游擊隊專屬軍火庫 - 籌碼雷達 (v2.1 終極破門版)")
st.write("大將軍，官方大門依然有憑證盤查，我們直接上破甲彈強攻！")

@st.cache_data(ttl=3600)
def load_twse_data():
    # 使用大將軍夥伴提供的最新官方主線路 (RWD API)
    url = "https://www.twse.com.tw/rwd/zh/fund/T86?selectType=ALLBUT0999&response=json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        # 【裝填破甲彈】：加回 verify=False，無視官方大門的 SSL 憑證盤查！
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        res.raise_for_status() 
        data = res.json()
        
        # 官方 API 的資料結構會分開給 'fields'(欄位名) 和 'data'(數據)
        if data['stat'] == 'OK':
            df = pd.DataFrame(data['data'], columns=data['fields'])
            return df
        else:
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"🛑 情報兵遭攔截！敵軍火力代碼：{e}") 
        return pd.DataFrame()

st.divider()
st.subheader("🕵️‍♂️ 戰報：最新台股三大法人籌碼動向 (上市)")

with st.spinner('裝填破甲彈，強行突破證交所主機大門中...'):
    df = load_twse_data()

if not df.empty:
    try:
        # 動態抓取欄位名稱 (防範證交所偷偷改名)
        col_code = [c for c in df.columns if '代號' in c][0]
        col_name = [c for c in df.columns if '名稱' in c][0]
        col_foreign = [c for c in df.columns if '外' in c and '買賣超' in c][0]
        col_trust = [c for c in df.columns if '投信' in c and '買賣超' in c][0]
        
        # 提取我們需要的精華情報
        df = df[[col_code, col_name, col_foreign, col_trust]]
        df.columns = ['股票代號', '股票名稱', '外資買賣超(股)', '投信買賣超(股)']
        
        # 清除千分位逗號，並轉換為可計算的數字
        df['外資買賣超(股)'] = pd.to_numeric(df['外資買賣超(股)'].str.replace(',', ''), errors='coerce')
        df['投信買賣超(股)'] = pd.to_numeric(df['投信買賣超(股)'].str.replace(',', ''), errors='coerce')
        
        # 兵法核心：只抓出「投信大哥有買進」的股票，由大到小排列
        df_trust_buy = df[df['投信買賣超(股)'] > 0].sort_values(by='投信買賣超(股)', ascending=False)
        
        st.success("情報截獲成功！以下是投信大哥最新佈局的軍火名單：")
        
        # 顯示為華麗的戰情報表
        st.dataframe(
            df_trust_buy.style.format({"外資買賣超(股)": "{:,.0f}", "投信買賣超(股)": "{:,.0f}"}),
            height=600,
            use_container_width=True
        )
    except Exception as e:
        st.error(f"資料解析失敗，可能是證交所更換了陣型：{e}")
else:
    st.warning("報告將軍！目前無資料，可能是今日剛開盤數據尚未結算，或遇到國定假日！")
