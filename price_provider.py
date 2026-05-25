"""price_provider.py

台股價格資料多層備援核心
------------------------
資料源順序：
1. yfinance：sid.TW / sid.TWO
2. FinMind：TaiwanStockPrice
3. TWSE 官方 STOCK_DAY：上市股票月資料
4. 最近成功快取：避免壞資料覆蓋好資料
"""

from __future__ import annotations

import os
import re
import io
import contextlib
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf

CACHE_DIR = os.environ.get("PRICE_CACHE_DIR", ".price_cache")
TMP_CACHE_DIR = os.environ.get("PRICE_TMP_CACHE_DIR", "/tmp/stock_armory_price_cache")


def _ensure_dirs():
    for d in [CACHE_DIR, TMP_CACHE_DIR]:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


def _period_to_days(period: str) -> int:
    s = str(period or "60d").lower()
    if s.endswith("d"):
        return max(30, int(re.sub(r"\D", "", s) or 60))
    if s.endswith("mo"):
        return max(60, int(re.sub(r"\D", "", s) or 3) * 31)
    if s.endswith("y"):
        return max(120, int(re.sub(r"\D", "", s) or 1) * 366)
    return 90


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """攤平 yfinance/多來源可能出現的 MultiIndex 欄位。

    yfinance 偶爾會把欄位做成 (Price, Ticker) 或 (Ticker, Price)。
    這裡優先保留 Open/High/Low/Close/Adj Close/Volume 這些價格欄，避免 Close 被攤平成股票代號。
    """
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        price_cols = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
        level_names = []
        for level in range(df.columns.nlevels):
            vals = [str(x) for x in df.columns.get_level_values(level)]
            hit = sum(v in price_cols for v in vals)
            level_names.append((hit, level))
        best_level = sorted(level_names, reverse=True)[0][1]
        df.columns = df.columns.get_level_values(best_level)
        df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]
    return df


def normalize_price_df(raw: Optional[pd.DataFrame], source: str = "unknown", min_bars: int = 20) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = _flatten_columns(raw).copy()
    # 統一欄位名稱
    rename = {
        "open": "Open", "max": "High", "min": "Low", "close": "Close",
        "Trading_Volume": "Volume", "trading_volume": "Volume", "volume": "Volume",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.set_index("date")
    try:
        df.index = pd.to_datetime(df.index).tz_localize(None)
    except Exception:
        df.index = pd.to_datetime(df.index, errors="coerce")
    df = df[~pd.isna(df.index)]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    # 若來源只有 Adj Close，就先拿來補 Close，避免 Yahoo 欄位異常時整批掃描歸零。
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df["Close"] = df["Adj Close"]
    elif "Close" in df.columns and "Adj Close" in df.columns:
        c_tmp = pd.to_numeric(df["Close"], errors="coerce")
        adj_tmp = pd.to_numeric(df["Adj Close"], errors="coerce")
        df["Close"] = c_tmp.fillna(adj_tmp)

    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c not in df.columns:
            df[c] = np.nan if c != "Volume" else 0
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Close 是絕對必要；Open/High/Low 若單列缺但 Close 有值，用 Close 補，避免最後一列 nan 外漏。
    df = df.dropna(subset=["Close"])
    for c in ["Open", "High", "Low"]:
        df[c] = df[c].fillna(df["Close"])
    df["Volume"] = df["Volume"].replace(0, np.nan).ffill().fillna(0)
    df = df[(df["Close"] > 0) & (df["Open"] > 0) & (df["High"] > 0) & (df["Low"] > 0)]
    if len(df) < min_bars:
        return pd.DataFrame()
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.attrs["source"] = source
    df.attrs["data_date"] = df.index.max().strftime("%Y-%m-%d") if not df.empty else "-"
    return df


def validate_price_df(df: Optional[pd.DataFrame], min_bars: int = 20) -> bool:
    if df is None or df.empty or len(df) < min_bars:
        return False
    need = ["Open", "High", "Low", "Close"]
    if not all(c in df.columns for c in need):
        return False
    last = df.iloc[-1]
    return all(pd.notna(last[c]) and float(last[c]) > 0 for c in need)


def _cache_paths(sid: str):
    sid = str(sid).strip().upper()
    return [os.path.join(CACHE_DIR, f"{sid}.csv"), os.path.join(TMP_CACHE_DIR, f"{sid}.csv")]


def load_last_good_cache(sid: str, min_bars: int = 20) -> pd.DataFrame:
    for p in _cache_paths(sid):
        try:
            if os.path.exists(p):
                df = pd.read_csv(p, parse_dates=["Date"], index_col="Date")
                norm = normalize_price_df(df, source="最近成功快取", min_bars=min_bars)
                if validate_price_df(norm, min_bars=min_bars):
                    return norm
        except Exception:
            continue
    return pd.DataFrame()


def save_last_good_cache(sid: str, df: pd.DataFrame) -> None:
    if not validate_price_df(df, min_bars=10):
        return
    _ensure_dirs()
    out = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    out.index.name = "Date"
    for p in _cache_paths(sid):
        try:
            out.to_csv(p, encoding="utf-8-sig")
        except Exception:
            pass


def fetch_yfinance_price(sid: str, period: str = "60d", min_bars: int = 20) -> pd.DataFrame:
    for suffix in [".TW", ".TWO"]:
        try:
            ticker = f"{sid}{suffix}"
            # yfinance 會把 404 / delisted 訊息直接吐到 stderr；這裡靜音，避免 Streamlit log 被逐檔洗版。
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                raw = yf.download(ticker, period=period, threads=False, progress=False, auto_adjust=False)
            df = normalize_price_df(raw, source=f"Yahoo{suffix}", min_bars=min_bars)
            if validate_price_df(df, min_bars=min_bars):
                return df
        except Exception:
            continue
    return pd.DataFrame()


def fetch_finmind_price(sid: str, fm_token: Optional[str] = None, period: str = "60d", min_bars: int = 20) -> pd.DataFrame:
    try:
        days = max(90, _period_to_days(period) + 30)
        start_d = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {"dataset": "TaiwanStockPrice", "data_id": str(sid).strip(), "start_date": start_d}
        if fm_token and str(fm_token).strip():
            params["token"] = str(fm_token).strip()
        r = requests.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=18)
        if r.status_code != 200:
            return pd.DataFrame()
        data = r.json()
        if data.get("msg") != "success" or not data.get("data"):
            return pd.DataFrame()
        raw = pd.DataFrame(data["data"])
        df = normalize_price_df(raw, source="FinMind", min_bars=min_bars)
        if validate_price_df(df, min_bars=min_bars):
            return df
    except Exception:
        pass
    return pd.DataFrame()


def _parse_twse_date(x: str) -> pd.Timestamp:
    s = str(x).strip().replace("/", "-")
    parts = s.split("-")
    if len(parts) == 3:
        y = int(parts[0])
        if y < 1911:
            y += 1911
        return pd.to_datetime(f"{y}-{int(parts[1]):02d}-{int(parts[2]):02d}", errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def fetch_twse_official_price(sid: str, period: str = "60d", min_bars: int = 20) -> pd.DataFrame:
    """TWSE 官方上市日線。上櫃通常會失敗，交給 FinMind / 快取。"""
    days = _period_to_days(period)
    months = max(2, min(12, int(np.ceil((days + 35) / 31))))
    frames = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    today = datetime.now().replace(day=1)
    for i in range(months):
        month = today - pd.DateOffset(months=i)
        date_str = month.strftime("%Y%m01")
        try:
            url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
            params = {"date": date_str, "stockNo": str(sid).strip(), "response": "json"}
            r = session.get(url, params=params, timeout=15)
            if r.status_code != 200:
                continue
            js = r.json()
            if js.get("stat") != "OK" or not js.get("data"):
                continue
            cols = js.get("fields", [])
            raw = pd.DataFrame(js["data"], columns=cols)
            if raw.empty:
                continue
            df = pd.DataFrame()
            date_col = cols[0]
            df["date"] = raw[date_col].map(_parse_twse_date)
            def num_col(keyword):
                col = next((c for c in raw.columns if keyword in c), None)
                if not col:
                    return np.nan
                return pd.to_numeric(raw[col].astype(str).str.replace(",", "", regex=False).str.replace("--", "", regex=False), errors="coerce")
            df["Open"] = num_col("開盤")
            df["High"] = num_col("最高")
            df["Low"] = num_col("最低")
            df["Close"] = num_col("收盤")
            df["Volume"] = num_col("成交股數")
            frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    raw_all = pd.concat(frames, ignore_index=True).dropna(subset=["date"])
    df = normalize_price_df(raw_all, source="TWSE官方", min_bars=min_bars)
    if validate_price_df(df, min_bars=min_bars):
        return df
    return pd.DataFrame()


def safe_download_price(sid: str, fm_token: Optional[str] = None, period: str = "60d", min_bars: int = 20) -> pd.DataFrame:
    sid = str(sid).strip()
    for fetcher in [
        lambda: fetch_yfinance_price(sid, period=period, min_bars=min_bars),
        lambda: fetch_finmind_price(sid, fm_token=fm_token, period=period, min_bars=min_bars),
        lambda: fetch_twse_official_price(sid, period=period, min_bars=min_bars),
    ]:
        df = fetcher()
        if validate_price_df(df, min_bars=min_bars):
            save_last_good_cache(sid, df)
            return df
    cached = load_last_good_cache(sid, min_bars=min_bars)
    if validate_price_df(cached, min_bars=min_bars):
        return cached
    return pd.DataFrame()
