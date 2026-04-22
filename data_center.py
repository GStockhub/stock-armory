import pandas as pd
import numpy as np
import yfinance as yf
import requests
import urllib3
import time
from datetime import datetime, timedelta
import streamlit as st

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🚀 V26.95: 終極網址轉換器，破解 Google 表單 HTML 陷阱！
def convert_gsheet_url(url):
    url = str(url).strip()
    if "docs.google.com/spreadsheets/d/" in url and "export?format=csv" not in url:
        import re
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        if match:
            doc_id = match.group(1)
            gid = "0"
            if "gid=" in url:
                gid = url.split("gid=")[1].split("&")[0]
            return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"
    return url

@st.cache_data(ttl=86400, show_spinner=False)
def load_industry_map():
    ind_map, name_map = {}, {}
    try:
        df = pd.read_csv("industry_map.csv", dtype=str)
        for _, row in df.iterrows():
            cid = str(row['代號']).strip()
            ind_map[cid] = str(row['產業']).strip()
            name_map[cid] = str(row['名稱']).strip()
    except: pass 
    return ind_map, name_map

def safe_download(sid, fm_token=None, retries=2):
    for suffix in [".TW", ".TWO"]:
        for _ in range(retries):
            try:
                sym = f"{sid}{suffix}"
                df = yf.Ticker(sym).history(period="3mo")
                if not df.empty and len(df) > 5: return df
            except: time.sleep(0.5 + np.random.rand())
            
    if fm_token and fm_token.strip() != "":
        try:
            start_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={sid}&start_date={start_date}&token={fm_token}"
            res = requests.get(url, timeout=5, verify=False).json()
            if res.get('msg') == 'success' and len(res['data']) > 0:
                df = pd.DataFrame(res['data'])
                df.rename(columns={'date': 'Date', 'open': 'Open', 'max': 'High', 'min': 'Low', 'close': 'Close', 'Trading_Volume': 'Volume'}, inplace=True)
                df['Date'] = pd.to_datetime(df['Date'])
                df.set_index('Date', inplace=True)
                if len(df) > 20: return df
        except: pass
        
    return pd.DataFrame()

def fetch_single_stock_batch(sid, fm_token=None):
    df = safe_download(sid, fm_token)
    if not df.empty: return sid, df
    return sid, None

@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_dashboard():
    score = 5.0
    macro_data = []
    OVERHEAT_FLAG = False 
    
    indices = {
        "^TWII": ("台股加權", "2330.TW"), 
        "^PHLX_SO": ("美費半導體", "SOXX"), 
        "^IXIC": ("那斯達克", "QQQ"), 
        "^VIX": ("恐慌指數", "VIXY"),
        "TWD=X": ("美元/台幣(匯率)", "TWD=X")
    }
    
    for main_sym, (base_name, fallback_sym) in indices.items():
        display_name = base_name
        hist = safe_download(main_sym.replace('^','')) 
        if hist.empty:
            hist = yf.Ticker(fallback_sym).history(period="3mo")
            if not hist.empty: display_name = f"{base_name} (備援)"
        
        if hist.empty:
            macro_data.append({"戰區": display_name, "現值": "抓取失敗", "月線": "-", "狀態": "⚪ 斷線"})
            continue
            
        try:
            close_s = hist['Close']
            last_p = float(close_s.iloc[-1])
            ma20 = float(close_s.rolling(20).mean().iloc[-1])
            bias = ((last_p - ma20) / ma20) * 100 
            
            status = "🟢 多頭" if last_p > ma20 else "🔴 空頭"
            
            if "恐慌指數" in base_name:
                status = "🔴 恐慌" if last_p > 25 else ("🟡 警戒" if last_p > 18 else "🟢 安定")
                if last_p > 25: score -= 2
                elif last_p < 18: score += 1
            elif "匯率" in base_name:
                if last_p > ma20: 
                    status = "🔴 貶值(資金外逃)"
                    score -= 1.5 
                else: 
                    status = "🟢 升值(熱錢湧入)"
                    score += 1.5 
            else:
                if last_p > ma20: score += 1
                else: score -= 1
                if "台股加權" in base_name and bias > 5.0:
                    OVERHEAT_FLAG = True
                    score -= 3 
                    status = "🔥 高檔過熱"
                
            macro_data.append({"戰區": display_name, "現值": f"{last_p:.2f}", "月線": f"{ma20:.2f}", "狀態": status})
        except: 
            macro_data.append({"戰區": display_name, "現值": "計算失敗", "月線": "-", "狀態": "⚪ 斷線"})
            continue
            
    return max(1, min(10, int(score))), pd.DataFrame(macro_data), OVERHEAT_FLAG

@st.cache_data(ttl=14400, show_spinner=False)
def fetch_chips_data(fm_token=None):
    chip_dict = {}
    date_ptr = datetime.now()
    attempts = 0
    while len(chip_dict) < 10 and attempts < 20:
        if date_ptr.weekday() < 5:
            d_str = date_ptr.strftime("%Y%m%d")
            fm_d_str = date_ptr.strftime("%Y-%m-%d") 
            success = False
            url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={d_str}&selectType=ALLBUT0999&response=json"
            try:
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5, verify=False)
                if r.status_code == 200:
                    res = r.json()
                    if res.get('stat') == 'OK':
                        df = pd.DataFrame(res['data'], columns=res['fields'])
                        tru_cols = [c for c in df.columns if '投信' in c and '買賣超' in c]
                        for_cols = [c for c in df.columns if '外資' in c and '買賣超' in c]
                        self_cols = [c for c in df.columns if '自營' in c and '買賣超' in c]
                        def parse_col(col_name): return pd.to_numeric(df[col_name].astype(str).str.replace(',', ''), errors='coerce').fillna(0) / 1000
                        clean = pd.DataFrame()
                        clean['代號'] = df[[c for c in df.columns if '代號' in c][0]]
                        clean['名稱'] = df[[c for c in df.columns if '名稱' in c][0]]
                        clean['投信(張)'] = parse_col(tru_cols[0]) if tru_cols else 0
                        clean['外資(張)'] = sum(parse_col(c) for c in for_cols)
                        clean['自營(張)'] = sum(parse_col(c) for c in self_cols)
                        clean['三大法人合計'] = clean['投信(張)'] + clean['外資(張)'] + clean['自營(張)']
                        chip_dict[d_str] = clean
                        success = True
            except: pass
            
            if not success and fm_token and fm_token.strip() != "":
                try:
                    fm_url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&start_date={fm_d_str}&end_date={fm_d_str}&token={fm_token}"
                    r_fm = requests.get(fm_url, timeout=5, verify=False)
                    if r_fm.status_code == 200:
                        res_fm = r_fm.json()
                        if res_fm.get('msg') == 'success' and len(res_fm.get('data', [])) > 0:
                            df_fm = pd.DataFrame(res_fm['data'])
                            df_fm['net'] = (df_fm['buy'] - df_fm['sell']) / 1000
                            pivot_df = df_fm.pivot_table(index='stock_id', columns='name', values='net', aggfunc='sum').fillna(0)
                            
                            clean = pd.DataFrame()
                            clean['代號'] = pivot_df.index
                            trust_cols = [c for c in pivot_df.columns if '投信' in c]
                            for_cols = [c for c in pivot_df.columns if '外資' in c]
                            deal_cols = [c for c in pivot_df.columns if '自營' in c]
                            
                            clean['投信(張)'] = pivot_df[trust_cols].sum(axis=1).values if trust_cols else 0
                            clean['外資(張)'] = pivot_df[for_cols].sum(axis=1).values if for_cols else 0
                            clean['自營(張)'] = pivot_df[deal_cols].sum(axis=1).values if deal_cols else 0
                            clean['三大法人合計'] = clean['投信(張)'] + clean['外資(張)'] + clean['自營(張)']
                            chip_dict[d_str] = clean
                            success = True
                except: pass
                
            if success: time.sleep(0.2)
                
        date_ptr -= timedelta(days=1)
        attempts += 1
        
    return chip_dict

@st.cache_data(ttl=3600, show_spinner=False)
def get_holding_intel(id_tuple, TWSE_IND_MAP, fm_token=None):
    id_list = list(id_tuple)
    intel_results = []
    if not id_list: return pd.DataFrame()
    
    bulk_data = {}
    # 🛡️ 拆除多執行緒，改為安靜的循序下載防封鎖
    for sid in id_list:
        sid_str = str(sid).strip()
        df = fetch_single_stock_batch(sid_str, fm_token)[1]
        if df is not None and not df.empty: 
            bulk_data[sid_str] = df
        time.sleep(0.1) # 降速防擋
                
    for sid in id_list:
        try:
            df_stock = bulk_data.get(str(sid).strip())
            if df_stock is None or df_stock.empty: continue
            close_s = df_stock['Close']
            if len(close_s) < 20: continue
            
            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            
            df_stock['PrevClose'] = df_stock['Close'].shift(1)
            df_stock['TR'] = np.maximum(df_stock['High'] - df_stock['Low'], np.maximum(abs(df_stock['High'] - df_stock['PrevClose']), abs(df_stock['Low'] - df_stock['PrevClose'])))
            df_stock['ATR'] = df_stock['TR'].rolling(14).mean()
            atr_now = float(df_stock['ATR'].iloc[-1])
            if pd.isna(atr_now) or atr_now == 0: atr_now = p_now * 0.03
            
            ind = TWSE_IND_MAP.get(str(sid).strip()) or "其他"
            if str(sid).strip().startswith('00'): ind = "ETF"
            
            intel_results.append({
                '代號': str(sid).strip(), '產業': ind, '現價': p_now,
                'M5': m5, 'M10': m10, 'M20': m20, 'ATR': atr_now,
                '停損價': p_now - 1.5 * atr_now
            })
        except: continue
    return pd.DataFrame(intel_results)
