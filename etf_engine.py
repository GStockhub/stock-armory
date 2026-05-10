import io
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from data_center import read_remote_csv, safe_download


DEFAULT_ETF_UNIVERSE = {
    "00400A": {"名稱": "主動國泰動能高息", "類型": "主動ETF"},
    "0050": {"名稱": "元大台灣50", "類型": "被動ETF"},
    "0051": {"名稱": "元大中型100", "類型": "被動ETF"},
    "0052": {"名稱": "富邦科技", "類型": "被動ETF"},
    "0053": {"名稱": "元大電子", "類型": "被動ETF"},
    "0056": {"名稱": "元大高股息", "類型": "被動ETF"},
    "006208": {"名稱": "富邦台50", "類型": "被動ETF"},
    "00631L": {"名稱": "元大台灣50正2", "類型": "被動ETF"},
    "00878": {"名稱": "國泰永續高股息", "類型": "被動ETF"},
    "00919": {"名稱": "群益台灣精選高息", "類型": "被動ETF"},
    "00929": {"名稱": "復華台灣科技優息", "類型": "被動ETF"},
    "00940": {"名稱": "元大台灣價值高息", "類型": "被動ETF"},
    "00946": {"名稱": "群益科技高息成長", "類型": "被動ETF"},
    "00952": {"名稱": "凱基台灣AI50", "類型": "被動ETF"},
    "00981A": {"名稱": "00981A", "類型": "主動ETF"},
    "00982A": {"名稱": "00982A", "類型": "主動ETF"},
    "00980A": {"名稱": "00980A", "類型": "主動ETF"},
    "00983A": {"名稱": "00983A", "類型": "主動ETF"},
    "00999A": {"名稱": "00999A", "類型": "主動ETF"},
}


def _to_float(v, default=0.0):
    try:
        if pd.isna(v):
            return default
        return float(str(v).replace(',', '').replace('%', '').strip())
    except Exception:
        return default


def _pct(series: pd.Series, bars: int) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) <= bars:
        return 0.0
    base = float(s.iloc[-bars - 1])
    now = float(s.iloc[-1])
    if base <= 0:
        return 0.0
    return (now / base - 1) * 100


def _prepare_price_df(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Close"])
    if df.empty:
        return df
    df["Volume"] = df["Volume"].replace(0, np.nan).ffill().fillna(1000)
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA10"] = df["Close"].rolling(10).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["VolMA5"] = df["Volume"].rolling(5).mean()
    return df


def _etf_next_action(row: dict) -> Tuple[str, str]:
    score = _to_float(row.get("動能分數", 0))
    bias = _to_float(row.get("乖離(%)", 0))
    price = _to_float(row.get("現價", 0))
    ma5 = _to_float(row.get("M5", price))
    ma10 = _to_float(row.get("M10", price))
    if price <= 0:
        return "⚪ 資料不足", "資料不足，暫不判斷"
    if price < ma10:
        return "🔴 轉弱", "跌破 M10，不主動加碼"
    if price < ma5:
        return "🟡 等站回", "站回 M5 才恢復觀察"
    if bias >= 8:
        return "🟠 過熱不追", "乖離偏高，只續抱不追價"
    if score >= 80:
        return "🟢 可分批", "趨勢強，可小量分批，不追高"
    if score >= 65:
        return "🔵 續抱觀察", "站在 M5 上可續看"
    return "⚪ 普通觀察", "動能普通，等更明確訊號"


@st.cache_data(ttl=1800, show_spinner=False)
def run_etf_momentum_radar(fm_token: str = "", universe: Optional[Dict[str, dict]] = None, period: str = "6mo") -> pd.DataFrame:
    """ETF 主體倉動能雷達。只用價格與量能，不使用 ETF 持股資料。"""
    universe = universe or DEFAULT_ETF_UNIVERSE
    rows = []
    for code, meta in universe.items():
        try:
            raw = safe_download(code, fm_token)
            df = _prepare_price_df(raw)
            if df.empty or len(df) < 25:
                continue
            close = df["Close"]
            now = float(close.iloc[-1])
            ma5 = float(df["MA5"].iloc[-1]) if pd.notna(df["MA5"].iloc[-1]) else now
            ma10 = float(df["MA10"].iloc[-1]) if pd.notna(df["MA10"].iloc[-1]) else now
            ma20 = float(df["MA20"].iloc[-1]) if pd.notna(df["MA20"].iloc[-1]) and df["MA20"].iloc[-1] else now
            vol = float(df["Volume"].iloc[-1])
            vol5 = float(df["VolMA5"].iloc[-1]) if pd.notna(df["VolMA5"].iloc[-1]) and df["VolMA5"].iloc[-1] > 0 else vol
            r3 = _pct(close, 3)
            r5 = _pct(close, 5)
            r10 = _pct(close, 10)
            bias = (now / ma20 - 1) * 100 if ma20 > 0 else 0.0
            vol_ratio = vol / vol5 if vol5 > 0 else 1.0

            score = 50.0
            score += min(max(r5 * 4.2, -18), 26)
            score += min(max(r3 * 2.2, -10), 14)
            score += min(max(r10 * 1.6, -12), 18)
            if now > ma5: score += 8
            if now > ma10: score += 7
            if ma5 > ma10 > ma20: score += 8
            score += min(max((vol_ratio - 1) * 8, -5), 10)
            if bias > 8: score -= (bias - 8) * 3.0
            if bias < -3: score -= 6
            score = max(1, min(100, round(score, 1)))

            row = {
                "代號": code,
                "名稱": meta.get("名稱", code),
                "類型": meta.get("類型", "ETF"),
                "現價": round(now, 2),
                "M5": round(ma5, 2),
                "M10": round(ma10, 2),
                "M20": round(ma20, 2),
                "3日漲幅(%)": round(r3, 2),
                "5日漲幅(%)": round(r5, 2),
                "10日漲幅(%)": round(r10, 2),
                "乖離(%)": round(bias, 2),
                "量能比": round(vol_ratio, 2),
                "動能分數": score,
            }
            label, action = _etf_next_action(row)
            row["狀態"] = label
            row["下一步"] = action
            rows.append(row)
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("動能分數", ascending=False).reset_index(drop=True)


def _standardize_holding_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work.columns = work.columns.str.replace("\ufeff", "", regex=False).str.strip()
    col_map = {}
    for c in work.columns:
        cs = str(c).strip()
        if cs in ["日期", "資料日期", "持股日期", "date"]:
            col_map[c] = "日期"
        elif cs in ["ETF代號", "ETF", "基金代號", "etf_code", "代號"]:
            col_map[c] = "ETF代號"
        elif cs in ["ETF名稱", "基金名稱", "etf_name"]:
            col_map[c] = "ETF名稱"
        elif cs in ["成分股代號", "股票代號", "證券代號", "持股代號", "stock_id"]:
            col_map[c] = "成分股代號"
        elif cs in ["成分股名稱", "股票名稱", "證券名稱", "持股名稱", "stock_name"]:
            col_map[c] = "成分股名稱"
        elif cs in ["權重", "持股權重", "比重", "weight", "持股比例"]:
            col_map[c] = "權重"
    work = work.rename(columns=col_map)
    required = ["日期", "ETF代號", "成分股代號"]
    if any(c not in work.columns for c in required):
        return pd.DataFrame()
    if "權重" not in work.columns:
        work["權重"] = 0.0
    if "ETF名稱" not in work.columns:
        work["ETF名稱"] = work["ETF代號"].astype(str)
    if "成分股名稱" not in work.columns:
        work["成分股名稱"] = work["成分股代號"].astype(str)
    work["日期"] = pd.to_datetime(work["日期"], errors="coerce")
    work["ETF代號"] = work["ETF代號"].astype(str).str.strip()
    work["成分股代號"] = work["成分股代號"].astype(str).str.strip()
    work["權重"] = work["權重"].apply(_to_float)
    work = work.dropna(subset=["日期"])
    return work


@st.cache_data(ttl=1800, show_spinner=False)
def load_active_etf_holdings(holdings_csv_url: str) -> pd.DataFrame:
    if not holdings_csv_url:
        return pd.DataFrame()
    df = read_remote_csv(holdings_csv_url, dtype=str)
    return _standardize_holding_columns(df)


def _industry_of(code: str, industry_map: Dict[str, str]) -> str:
    return industry_map.get(str(code).strip(), "未分類")


def summarize_active_etf_holdings(holdings_df: pd.DataFrame, industry_map: Dict[str, str], name_map: Dict[str, str], top_n: int = 3, lookback_days: int = 5) -> Dict[str, pd.DataFrame]:
    """主動 ETF 持股快照與變化。需要使用者提供每日持股 CSV。"""
    empty = {
        "snapshot": pd.DataFrame(),
        "industries": pd.DataFrame(),
        "stocks": pd.DataFrame(),
        "common_holdings": pd.DataFrame(),
        "changes": pd.DataFrame(),
        "industry_changes": pd.DataFrame(),
    }
    if holdings_df is None or holdings_df.empty:
        return empty
    df = holdings_df.copy()
    latest = df["日期"].max()
    if pd.isna(latest):
        return empty
    latest_df = df[df["日期"] == latest].copy()
    if latest_df.empty:
        return empty

    # 以最新日總權重最高的主動 ETF 作 Top N 快照
    etf_rank = latest_df.groupby(["ETF代號", "ETF名稱"], dropna=False)["權重"].sum().reset_index().sort_values("權重", ascending=False).head(top_n)
    focus = etf_rank["ETF代號"].astype(str).tolist()
    latest_focus = latest_df[latest_df["ETF代號"].isin(focus)].copy()
    latest_focus["產業"] = latest_focus["成分股代號"].map(lambda x: _industry_of(x, industry_map))
    latest_focus["成分股名稱"] = latest_focus.apply(lambda r: name_map.get(str(r["成分股代號"]), str(r.get("成分股名稱", r["成分股代號"]))), axis=1)

    snap_rows = []
    for etf_code, sub in latest_focus.groupby("ETF代號"):
        etf_name = sub["ETF名稱"].iloc[0] if "ETF名稱" in sub else etf_code
        ind_top = sub.groupby("產業")["權重"].sum().sort_values(ascending=False).head(10)
        stock_top = sub.sort_values("權重", ascending=False).head(10)
        snap_rows.append({
            "ETF": etf_code,
            "名稱": etf_name,
            "前十大產業": "、".join([f"{k} {v:.1f}%" for k, v in ind_top.items()]),
            "前十大個股": "、".join([f"{r['成分股名稱']}({r['成分股代號']}) {r['權重']:.1f}%" for _, r in stock_top.iterrows()]),
            "持股數": len(sub),
            "前十集中度": round(float(stock_top["權重"].sum()), 2),
        })
    snapshot = pd.DataFrame(snap_rows)

    industries = latest_focus.groupby(["ETF代號", "產業"], dropna=False)["權重"].sum().reset_index().sort_values(["ETF代號", "權重"], ascending=[True, False])
    stocks = latest_focus[["ETF代號", "成分股代號", "成分股名稱", "產業", "權重"]].sort_values(["ETF代號", "權重"], ascending=[True, False])

    common = latest_focus.groupby(["成分股代號", "成分股名稱", "產業"], dropna=False).agg(
        出現ETF數=("ETF代號", "nunique"),
        合計權重=("權重", "sum"),
        持有ETF=("ETF代號", lambda x: "、".join(sorted(set(map(str, x)))))
    ).reset_index()
    common_holdings = common[common["出現ETF數"] >= 2].sort_values(["出現ETF數", "合計權重"], ascending=[False, False]).head(20)

    # 近 N 日變化：找 latest 前的最近一個日期，或 lookback_days 以前最接近日期
    dates = sorted(df["日期"].dropna().unique())
    prev_dates = [d for d in dates if d < latest]
    changes = pd.DataFrame()
    industry_changes = pd.DataFrame()
    if prev_dates:
        target_min = latest - pd.Timedelta(days=max(1, int(lookback_days) + 2))
        candidates = [d for d in prev_dates if d >= target_min]
        prev = candidates[0] if candidates else prev_dates[-1]
        # 用區間內最早日期，較貼近「近5日變化」；若資料只有昨日，就自然變成昨日比較
        if candidates:
            prev = min(candidates)
        prev_df = df[(df["日期"] == prev) & (df["ETF代號"].isin(focus))].copy()
        prev_df["產業"] = prev_df["成分股代號"].map(lambda x: _industry_of(x, industry_map))
        latest_key = latest_focus[["ETF代號", "成分股代號", "成分股名稱", "產業", "權重"]].copy()
        prev_key = prev_df[["ETF代號", "成分股代號", "權重"]].copy() if not prev_df.empty else pd.DataFrame(columns=["ETF代號", "成分股代號", "權重"])
        merged = pd.merge(latest_key, prev_key, on=["ETF代號", "成分股代號"], how="outer", suffixes=("_新", "_舊"))
        merged["權重_新"] = merged["權重_新"].fillna(0)
        merged["權重_舊"] = merged["權重_舊"].fillna(0)
        merged["變化"] = merged["權重_新"] - merged["權重_舊"]
        merged["狀態"] = np.where((merged["權重_舊"] == 0) & (merged["權重_新"] > 0), "新增",
                              np.where((merged["權重_舊"] > 0) & (merged["權重_新"] == 0), "刪除",
                              np.where(merged["變化"] > 0, "加碼", np.where(merged["變化"] < 0, "減碼", "持平"))))
        merged["成分股名稱"] = merged.apply(lambda r: name_map.get(str(r["成分股代號"]), str(r.get("成分股名稱", r["成分股代號"]))), axis=1)
        merged["產業"] = merged.apply(lambda r: _industry_of(r["成分股代號"], industry_map), axis=1)
        changes = merged[merged["狀態"].isin(["新增", "刪除", "加碼", "減碼"])].sort_values("變化", ascending=False)
        industry_changes = changes.groupby("產業", dropna=False)["變化"].sum().reset_index().sort_values("變化", ascending=False)
        changes["比較基準"] = f"{pd.Timestamp(prev).strftime('%Y-%m-%d')} → {pd.Timestamp(latest).strftime('%Y-%m-%d')}"

    return {
        "snapshot": snapshot,
        "industries": industries,
        "stocks": stocks,
        "common_holdings": common_holdings,
        "changes": changes,
        "industry_changes": industry_changes,
    }
