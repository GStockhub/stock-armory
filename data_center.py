import io
import time
from datetime import datetime, timedelta
import concurrent.futures
import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 🚀 建立帶有重試機制的 Requests Session ---
def get_retry_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5, 
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7"
    })
    return session

def convert_gsheet_url(url: str) -> str:
    url = str(url).strip()
    if not url: return url
    if "/pub" in url or "export" in url or "output=csv" in url: return url
    if "/edit" in url or "/view" in url:
        import re
        match = re.search(r'/d/([a-zA-Z0-9-_]{40,})', url)
        if match:
            doc_id = match.group(1)
            gid = "0"
            if "gid=" in url: gid = url.split("gid=")[1].split("&")[0]
            return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"
    return url

def read_remote_csv(url: str, dtype=str) -> pd.DataFrame:
    url = convert_gsheet_url(url)
    if not url: return pd.DataFrame()

    session = get_retry_session()
    try:
        resp = session.get(url, timeout=20, verify=False)
        resp.raise_for_status()
        content = resp.content.decode('utf-8-sig')
        return pd.read_csv(io.StringIO(content), dtype=dtype)
    except Exception as e:
        print(f"Read CSV Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def load_industry_map():
    url = "https://raw.githubusercontent.com/FinMind/FinMind/master/data/TaiwanStockInfo.csv"
    try:
        df = pd.read_csv(url)
        df["stock_id"] = df["stock_id"].astype(str)
        return dict(zip(df["stock_id"], df["industry_category"])), dict(zip(df["stock_id"], df["stock_name"]))
    except Exception:
        return {}, {}

@st.cache_data(ttl=1800, show_spinner=False)
def get_macro_dashboard():
    session = get_retry_session()
    indices = {"^TWII": "台股加權", "^IXIC": "那斯達克", "^GSPC": "標普500", "^VIX": "恐慌指數", "USDTWD=X": "美元/台幣"}
    results = []
    score = 0
    macro_df = pd.DataFrame()
    overheat_flag = False

    try:
        data = yf.download(list(indices.keys()), period="60d", session=session, threads=False, progress=False)
        
        if data.empty or "Close" not in data.columns:
            return 5, pd.DataFrame([{"名稱": "系統", "現價": 0, "月線(M20)": 0, "乖離(%)": 0, "狀態": "⚠️ Yahoo資料中斷"}]), False

        for tk, name in indices.items():
            if tk not in data["Close"].columns: continue
            s = data["Close"][tk].dropna()
            if len(s) < 20: continue

            p_now = float(s.iloc[-1])
            m20 = float(s.rolling(20).mean().iloc[-1])
            bias = ((p_now - m20) / m20) * 100

            if tk in ["^VIX", "USDTWD=X"]:
                status = "🔴 恐慌升高 (在月線上)" if p_now > m20 else "🟢 安定 (在月線下)"
                if tk == "USDTWD=X":
                    status = "🔴 台幣貶值 (資金外逃)" if p_now > m20 else "🟢 台幣升值 (資金流入)"
                    if p_now > m20: score -= 1.5
                else:
                    if p_now < m20: score += 2
            else:
                status = "🟢 多頭 (在月線上)" if p_now > m20 else "🔴 空頭 (跌破月線)"
                if p_now > m20:
                    score += 2 if tk == "^TWII" else 1.5
                if tk == "^TWII" and bias > 5:
                    overheat_flag = True
                    status += " 🔥過熱"

            results.append({"名稱": name, "現價": round(p_now, 2), "月線(M20)": round(m20, 2), "乖離(%)": round(bias, 2), "狀態": status})

        macro_df = pd.DataFrame(results)
    except Exception as e:
        print(f"Macro Error: {e}")
        return 5, pd.DataFrame([{"名稱": "系統", "現價": 0, "月線(M20)": 0, "乖離(%)": 0, "狀態": f"⚠️ {e}"}]), False
        
    return max(0, min(10, int(score))), macro_df, overheat_flag

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_chips_data(fm_token=None):
    session = get_retry_session()
    now = datetime.now()
    dates_to_try = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(10)]
    valid_dates, raw_data, chip_db = [], {}, {}
    url = "https://api.finmindtrade.com/api/v4/data"

    for d in dates_to_try:
        if len(valid_dates) >= 4: break
        payload = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "start_date": d, "end_date": d}
        if fm_token: payload["token"] = fm_token
        try:
            resp = session.get(url, params=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("msg") == "success" and data.get("data"):
                    df = pd.DataFrame(data["data"])
                    raw_data[d] = df
                    valid_dates.append(d)
        except Exception as e:
            print(f"Chip Error {d}: {e}")
            continue

    if not valid_dates: return {}

    for d in valid_dates:
        try:
            df = raw_data[d].copy()
            
            # 🛡️ 終極防呆：如果 FinMind 給的資料是空的，或是漏給了最重要的 'name' 欄位，直接跳過這天的資料，不要崩潰！
            if df.empty or "name" not in df.columns or "stock_id" not in df.columns:
                print(f"[{d}] FinMind 資料異常，缺少必要欄位！跳過此日。")
                continue

            df["buy"] = pd.to_numeric(df["buy"], errors="coerce").fillna(0)
            df["sell"] = pd.to_numeric(df["sell"], errors="coerce").fillna(0)
            df["net"] = (df["buy"] - df["sell"]) / 1000
            
            pivoted = df.pivot_table(index="stock_id", columns="name", values="net", aggfunc="sum").fillna(0)
            
            # 確保欄位存在，避免 KeyError
            for col in ["Foreign_Investor", "Investment_Trust", "Dealer_self"]:
                if col not in pivoted.columns:
                    pivoted[col] = 0

            pivoted["三大法人合計"] = pivoted["Foreign_Investor"] + pivoted["Investment_Trust"] + pivoted["Dealer_self"]
            
            pivoted = pivoted.rename(columns={
                "Foreign_Investor": "外資(張)", 
                "Investment_Trust": "投信(張)", 
                "Dealer_self": "自營(張)"
            }).reset_index().rename(columns={"stock_id": "代號"})
            
            pivoted["代號"] = pivoted["代號"].astype(str)
            chip_db[d] = pivoted
        except Exception as e:
            print(f"Pivot Error {d}: {e}")
            continue

    return chip_db

def fetch_single_stock_batch(sid, fm_token=None):
    sid = str(sid).strip()
    df = safe_download(sid, fm_token)
    return sid, df

def safe_download(sid, fm_token=None):
    try:
        session = get_retry_session()
        ticker = f"{sid}.TW"
        df = yf.download(ticker, period="60d", session=session, threads=False, progress=False)
        if df is not None and not df.empty and "Close" in df.columns:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if len(df.dropna(subset=['Close'])) > 10:
                return df
    except Exception as e:
        print(f"Yahoo download failed for {sid}: {e}")

    try:
        session = get_retry_session()
        url = "https://api.finmindtrade.com/api/v4/data"
        start_d = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        payload = {"dataset": "TaiwanStockPrice", "data_id": sid, "start_date": start_d}
        if fm_token: payload["token"] = fm_token
        
        resp = session.get(url, params=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("msg") == "success" and data.get("data"):
                fm_df = pd.DataFrame(data["data"])
                fm_df["date"] = pd.to_datetime(fm_df["date"])
                fm_df = fm_df.set_index("date").rename(columns={
                    "open": "Open", "max": "High", "min": "Low", "close": "Close", "Trading_Volume": "Volume"
                })
                if not fm_df.empty and len(fm_df) > 10:
                    return fm_df
        else:
            print(f"FinMind API Error for {sid}: Status Code {resp.status_code}")
    except Exception as e:
         print(f"FinMind backup failed for {sid}: {e}")
         
    return None

@st.cache_data(ttl=900, show_spinner=False)
def get_holding_intel(id_tuple, TWSE_IND_MAP, fm_token=None):
    id_list = [str(x).strip() for x in list(id_tuple) if str(x).strip()]
    if not id_list: return pd.DataFrame()

    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_single_stock_batch, sid, fm_token): sid for sid in id_list}
        for future in concurrent.futures.as_completed(futures):
            sid, df = future.result()
            if df is not None and not df.empty:
                bulk_data[sid] = df

    if len(bulk_data) == 0: return pd.DataFrame()

    results = []
    for sid in id_list:
        try:
            df = bulk_data.get(sid)
            if df is None or df.empty: continue
            
            df = df[~df.index.duplicated(keep="last")].copy()
            close_s = pd.to_numeric(df["Close"], errors="coerce")
            
            if close_s.isna().all() or len(close_s.dropna()) < 10: continue

            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])

            try:
                high_s = pd.to_numeric(df["High"], errors="coerce")
                low_s = pd.to_numeric(df["Low"], errors="coerce")
                tmp = pd.DataFrame({"Close": close_s, "High": high_s, "Low": low_s}).dropna()
                tmp["PrevClose"] = tmp["Close"].shift(1)
                tr1 = tmp["High"] - tmp["Low"]
                tr2 = (tmp["High"] - tmp["PrevClose"]).abs()
                tr3 = (tmp["Low"] - tmp["PrevClose"]).abs()
                tmp["TR"] = np.maximum(tr1, np.maximum(tr2, tr3))
                tmp["ATR"] = tmp["TR"].rolling(14).mean()
                atr_now = float(tmp["ATR"].iloc[-1])
                if pd.isna(atr_now) or atr_now <= 0: atr_now = p_now * 0.03
            except Exception: atr_now = p_now * 0.03

            ind = TWSE_IND_MAP.get(sid, "未知")
            results.append({"代號": sid, "產業": ind, "現價": round(p_now, 2), "M5": round(m5, 2), "M10": round(m10, 2), "ATR": round(atr_now, 2)})
        except Exception as e:
            print(f"Holding intel error for {sid}: {e}")
            continue

    return pd.DataFrame(results)
