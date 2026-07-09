"""fundamental_engine.py

沙盤推演用基本面背景燈。
- 不參與 S/A/B 分數。
- 只在單檔沙盤查詢時補充月營收背景。
- 抓不到資料時 fail-soft，不阻斷沙盤。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict

import pandas as pd
import requests

try:
    import streamlit as st
except Exception:
    st = None


from net_utils import maybe_cache_data as _maybe_cache_data


def _is_etf_like(sid: str) -> bool:
    return str(sid or "").strip().upper().startswith("00")


def _to_float(v, default=0.0):
    try:
        if pd.isna(v):
            return default
        return float(str(v).replace(",", "").replace("%", "").strip())
    except Exception:
        return default


def _fetch_finmind_month_revenue(sid: str, token: str = "") -> pd.DataFrame:
    sid = str(sid).strip().upper()
    if not sid:
        return pd.DataFrame()
    start_date = (datetime.now() - timedelta(days=760)).strftime("%Y-%m-%d")
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": sid,
        "start_date": start_date,
    }
    if token:
        params["token"] = token
    try:
        resp = requests.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        if not data or data.get("status") not in [200, "200"]:
            return pd.DataFrame()
        df = pd.DataFrame(data.get("data", []))
        if df.empty:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


def _normalize_month_revenue(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    # FinMind 常見欄位：date, stock_id, country, revenue, revenue_month, revenue_year
    if "date" not in out.columns:
        return pd.DataFrame()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).sort_values("date")
    rev_col = None
    for c in ["revenue", "monthly_revenue", "當月營收"]:
        if c in out.columns:
            rev_col = c
            break
    if rev_col is None:
        return pd.DataFrame()
    out["revenue_num"] = pd.to_numeric(out[rev_col], errors="coerce")
    out = out.dropna(subset=["revenue_num"])
    if out.empty:
        return pd.DataFrame()
    out["ym"] = out["date"].dt.strftime("%Y-%m")
    return out


@_maybe_cache_data(ttl=21600, show_spinner=False)
def get_fundamental_badge(sid: str, name: str = "", token: str = "") -> Dict[str, str]:
    """回傳沙盤用基本面背景燈。"""
    sid = str(sid or "").strip().upper()
    if not sid:
        return {"level": "neutral", "title": "⚪ 基本面背景：資料不足", "detail": "未取得有效代號。", "action": "不影響沙盤技術判斷。"}

    if _is_etf_like(sid):
        return {
            "level": "etf",
            "title": "📦 基本面背景：ETF 標的",
            "detail": "ETF 不用單看 EPS / 月營收；重點看成分股主題、ETF 動能、乖離與大盤風險。",
            "action": "用 ETF 主體倉雷達與 M5/M10 管理，不把它當單一公司基本面判斷。",
        }

    raw = _fetch_finmind_month_revenue(sid, token)
    df = _normalize_month_revenue(raw)
    if df.empty or len(df) < 3:
        return {
            "level": "unknown",
            "title": "⚪ 基本面背景：暫無穩定資料",
            "detail": "月營收資料不足或資料源暫時無法取得。",
            "action": "本次仍以價格結構、量能、法人與風控為主；不要因基本面空白而加碼。",
        }

    latest = df.iloc[-1]
    latest_date = latest["date"]
    latest_rev = _to_float(latest["revenue_num"])
    prev_rev = _to_float(df.iloc[-2]["revenue_num"]) if len(df) >= 2 else 0

    yoy = None
    try:
        target_ym = (latest_date - pd.DateOffset(years=1)).strftime("%Y-%m")
        same = df[df["ym"].eq(target_ym)]
        if not same.empty:
            base = _to_float(same.iloc[-1]["revenue_num"])
            if base > 0:
                yoy = (latest_rev / base - 1) * 100
    except Exception:
        yoy = None

    mom = (latest_rev / prev_rev - 1) * 100 if prev_rev > 0 else None
    yoy_txt = f"YoY {yoy:+.1f}%" if yoy is not None else "YoY -"
    mom_txt = f"MoM {mom:+.1f}%" if mom is not None else "MoM -"
    month_txt = latest_date.strftime("%Y-%m")

    if yoy is not None and yoy >= 15 and (mom is None or mom >= -5):
        return {
            "level": "good",
            "title": "🎖️ 基本面背景：營收順風",
            "detail": f"最新月營收 {month_txt}｜{yoy_txt}｜{mom_txt}。營收動能偏正向。",
            "action": "可作為波段信心加分，但仍以 M5/M10 與停損線執行，不因基本面好就凹單。",
        }
    if yoy is not None and yoy <= -10:
        return {
            "level": "bad",
            "title": "⚠️ 基本面背景：營收逆風",
            "detail": f"最新月營收 {month_txt}｜{yoy_txt}｜{mom_txt}。基本面背景偏弱。",
            "action": "短線若有動能可以游擊，但不能放寬停損；破線要更快處理。",
        }
    if mom is not None and mom <= -15:
        return {
            "level": "warn",
            "title": "🟠 基本面背景：月營收轉弱",
            "detail": f"最新月營收 {month_txt}｜{yoy_txt}｜{mom_txt}。單月動能明顯降溫。",
            "action": "可打短線，但不適合越跌越補；若開高轉弱，優先保護本金。",
        }
    return {
        "level": "neutral",
        "title": "⚪ 基本面背景：普通 / 中性",
        "detail": f"最新月營收 {month_txt}｜{yoy_txt}｜{mom_txt}。未見明顯順風或逆風。",
        "action": "不加分也不扣分，仍以沙盤技術線、量能、法人與風控執行。",
    }
