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
from net_utils import smart_get
from chips_provider import safe_fetch_chips
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# 新掛牌主動 ETF 常常不在本機 industry_map.csv 內；先補靜態名稱，避免持股卡片顯示「未知」。
ACTIVE_ETF_NAME_MAP = {
    "00980A": "主動野村臺灣優選",
    "00981A": "主動統一台股增長",
    "00982A": "主動群益台灣強棒",
    "00985A": "主動野村臺灣優選",
    "00988A": "主動統一全球創新",
    "00991A": "主動復華未來50",
    "00992A": "主動群益科技創新",
    "00999A": "主動野村臺灣高息",
    "00400A": "主動國泰動能高息",
    "00403A": "主動統一升級50",
}

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

@st.cache_data(ttl=180, show_spinner=False)
def read_remote_csv(url: str, dtype=str) -> pd.DataFrame:
    """讀取遠端或本機 CSV。

    V37.10.1：ETF 經理人風向會讀 GitHub Actions 產出的
    data/active_etf_holdings_history.csv。這是 repo 內的本機檔案，
    不能用 requests.get() 當網址讀，否則會回空表，導致前端誤判
    「目前沒有可用的主動 ETF history」。
    """
    url = str(url or "").strip()
    if not url:
        return pd.DataFrame()

    # 本機 / repo 內 CSV：給 Streamlit 直接讀 data/*.csv 使用。
    try:
        if os.path.exists(url):
            return pd.read_csv(url, dtype=dtype, encoding="utf-8-sig")
    except Exception as e:
        print(f"Read Local CSV Error: {e}")
        return pd.DataFrame()

    url = convert_gsheet_url(url)
    if not url:
        return pd.DataFrame()
    session = get_retry_session()
    try:
        resp = smart_get(url, session=session, timeout=20)
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

        # V37.9.1：補上新掛牌主動 ETF。官方產業地圖更新會慢於 ETF 上市，
        # 若不補，持股風控會顯示「未知（00403A）」甚至被當成普通個股。
        for code, name in ACTIVE_ETF_NAME_MAP.items():
            name_map.setdefault(code, name)
            ind_map.setdefault(code, "主動ETF")
        return ind_map, name_map
    except Exception as e:
        print(f"❌ 讀取自建產業地圖失敗: {e}")
        # 地圖失敗時仍保留新主動 ETF 名稱，避免持股卡片變未知。
        return {code: "主動ETF" for code in ACTIVE_ETF_NAME_MAP}, ACTIVE_ETF_NAME_MAP.copy()

@st.cache_data(ttl=1800, show_spinner=False)
def get_macro_dashboard():
    indices = {"^TWII": "台股加權", "^IXIC": "那斯達克", "^GSPC": "標普500", "^VIX": "恐慌指數", "USDTWD=X": "美元/台幣"}
    results = []
    score = 0
    macro_df = pd.DataFrame()
    overheat_flag = False

    try:
        from price_provider import _YF_LOCK
        with _YF_LOCK:
            data = yf.download(list(indices.keys()), period="60d", threads=False, progress=False, auto_adjust=False)
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


def fetch_single_stock_batch_diag(sid, fm_token=None, period="60d"):
    """批次技術掃描專用：回傳價格資料 + 可讀診斷。

    S/A/B 掃描最常見的失敗不是候選池空，而是某檔價格資料暫時抓不到、
    新掛牌 K 棒不足，或 Yahoo/FinMind 被限流。這個函式保留原本 safe_download
    的多來源邏輯，但額外做一次較低門檻補抓，讓前端能說清楚是哪一檔卡住。
    """
    sid = str(sid).strip().upper()
    min_primary = 1 if _is_etf_like_code(sid) else 20
    min_rescue = 1 if _is_etf_like_code(sid) else 10

    diag = {
        "代號": sid,
        "價格狀態": "待檢查",
        "K線筆數": 0,
        "價格來源": "",
        "最後日期": "",
        "失敗原因": "",
    }

    df = None
    try:
        df = safe_download(sid, fm_token=fm_token, period=period, min_bars=min_primary)
    except Exception as e:
        diag["失敗原因"] = f"主抓取例外：{e}"
        df = None

    if df is not None and not df.empty:
        diag.update({
            "價格狀態": "✅ 正常",
            "K線筆數": len(df),
            "價格來源": str(getattr(df, "attrs", {}).get("source", "")),
            "最後日期": str(getattr(df, "attrs", {}).get("data_date", "")),
        })
        return sid, df, diag

    # 第二段：新掛牌或暫時少資料時，允許 10 根以上先進技術掃描，均線在 quant_engine 會降級處理。
    try:
        rescue = safe_download(sid, fm_token=fm_token, period=period, min_bars=min_rescue)
    except Exception as e:
        rescue = None
        if not diag.get("失敗原因"):
            diag["失敗原因"] = f"補抓例外：{e}"

    if rescue is not None and not rescue.empty:
        diag.update({
            "價格狀態": "🟡 K線較少但可掃描",
            "K線筆數": len(rescue),
            "價格來源": str(getattr(rescue, "attrs", {}).get("source", "")),
            "最後日期": str(getattr(rescue, "attrs", {}).get("data_date", "")),
            "失敗原因": f"未滿{min_primary}根，已降級用{len(rescue)}根計算",
        })
        return sid, rescue, diag

    diag.update({
        "價格狀態": "🔴 無有效K線",
        "失敗原因": diag.get("失敗原因") or "TW/TWO、FinMind、官方與快取都沒有可用 Close",
    })
    return sid, pd.DataFrame(), diag

def _is_etf_like_code(sid):
    """台股 ETF/主動 ETF 多為 00 開頭，部分新 ETF 交易天數不足 20 根。"""
    s = str(sid).strip().upper()
    return s.startswith("00")


def safe_download(sid, fm_token=None, period="60d", min_bars=None):
    """多層價格備援下載：Yahoo(.TW/.TWO) → FinMind → TWSE官方 → 最近成功快取。

    ETF/新掛牌標的允許較少 K 棒也回傳，避免持股風控與沙盤只因未滿 20 日就顯示「抓取中」。
    排名/回測需要的長週期指標會在 quant_engine 內再自行降級處理。
    """
    sid_clean = str(sid).strip().upper()
    if min_bars is None:
        # 新掛牌 ETF 可能只有 1~3 根 K 棒；持股風控至少要先能取到現價。
        min_bars = 1 if _is_etf_like_code(sid_clean) else 20
    try:
        df = safe_download_price(sid_clean, fm_token=fm_token, period=period, min_bars=int(min_bars))
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"safe_download_price failed {sid}: {e}")
    return None
