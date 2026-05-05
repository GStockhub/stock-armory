import io
import os
import time
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf
from price_provider import safe_download_price
from chips_provider import safe_fetch_chips
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    return session

def convert_gsheet_url(url: str) -> str:
    url = str(url).strip()
    if not url: return url
    # 🚀 救星：強制將 Web 網頁連結轉為 CSV 下載連結
    if "pubhtml" in url: url = url.replace("pubhtml", "pub?output=csv")
    if "/pub" in url or "export" in url or "output=csv" in url: return url
    if "/edit" in url or "/view" in url:
        import re
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
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

@st.cache_data(ttl=86400, show_spinner=False)
def load_industry_map():
    try:
        # 🚀 救星：強制使用 utf-8-sig 讀取，徹底消滅 BOM 亂碼，名字絕對出得來！
        with open("industry_map.csv", "r", encoding="utf-8-sig") as f:
            df = pd.read_csv(f, dtype=str)
        df.columns = df.columns.str.strip()
        df["代號"] = df["代號"].astype(str).str.strip()
        df["產業"] = df["產業"].astype(str).str.strip()
        df["名稱"] = df["名稱"].astype(str).str.strip()
        
        ind_map = dict(zip(df["代號"], df["產業"]))
        name_map = dict(zip(df["代號"], df["名稱"]))
        return ind_map, name_map
    except Exception as e:
        print(f"❌ 讀取自建產業地圖失敗: {e}")
        return {}, {}

@st.cache_data(ttl=1800, show_spinner=False)
def get_macro_dashboard():
    indices = {"^TWII": "台股加權", "^IXIC": "那斯達克", "^GSPC": "標普500", "^VIX": "恐慌指數", "USDTWD=X": "美元/台幣"}
    results = []
    score = 0
    macro_df = pd.DataFrame()
    overheat_flag = False

    try:
        data = yf.download(list(indices.keys()), period="60d", threads=False, progress=False)
        if data.empty or "Close" not in data.columns:
            return 5, pd.DataFrame([{"名稱": "系統", "現價": "0", "月線(M20)": "0", "乖離(%)": "0", "狀態": "⚠️ Yahoo資料中斷"}]), False

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

            # 🚀 救星：物理閹割大盤小數點
            results.append({"名稱": name, "現價": f"{p_now:.2f}", "月線(M20)": f"{m20:.2f}", "乖離(%)": f"{bias:.2f}%", "狀態": status})

        macro_df = pd.DataFrame(results)
    except Exception as e:
        return 5, pd.DataFrame([{"名稱": "系統", "現價": "0", "月線(M20)": "0", "乖離(%)": "0", "狀態": f"⚠️ {e}"}]), False
        
    return max(0, min(10, int(score))), macro_df, overheat_flag


def _chips_cache_paths():
    return [
        os.path.join(".chips_cache", "chip_db.pkl"),
        os.path.join("/tmp", "stock_armory_chip_db.pkl"),
    ]


def _save_chips_cache(chip_dict):
    if not chip_dict:
        return
    for p in _chips_cache_paths():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            pd.to_pickle(chip_dict, p)
        except Exception:
            pass


def _load_chips_cache():
    for p in _chips_cache_paths():
        try:
            if os.path.exists(p):
                obj = pd.read_pickle(p)
                if isinstance(obj, dict) and len(obj) > 0:
                    return obj
        except Exception:
            continue
    return {}

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_chips_data(fm_token=None):
    """法人籌碼多來源防斷線：TWSE T86 → FinMind → TPEX → GitHub/本機快取。

    回傳 dict[YYYYMMDD] = DataFrame，欄位：代號、名稱、外資(張)、投信(張)、自營(張)、三大法人合計。
    若所有來源與快取都失敗，回傳空 dict；前端可改用技術面備援，不阻斷沙盤/ETF/持股風控。
    """
    try:
        return safe_fetch_chips(fm_token=fm_token, days=5, max_lookback_days=35)
    except Exception as e:
        print(f"safe_fetch_chips failed: {e}")
        cached = _load_chips_cache()
        return cached if cached else {}

def fetch_single_stock_batch(sid, fm_token=None, period="60d"):
    sid = str(sid).strip()
    df = safe_download(sid, fm_token, period=period)
    return sid, df

def safe_download(sid, fm_token=None, period="60d"):
    """多層價格備援下載：Yahoo(.TW/.TWO) → FinMind → TWSE官方 → 最近成功快取。

    回傳前會做 OHLCV 清洗與最後一列有效檢查；若所有來源都失敗，回傳 None。
    """
    try:
        df = safe_download_price(str(sid).strip(), fm_token=fm_token, period=period, min_bars=20)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"safe_download_price failed {sid}: {e}")
    return None
