"""active_etf_holdings.py

主動 ETF 經理人風向雷達（自動來源 + CSV 備援用）
--------------------------------------------------
用途：
1. 依 ETF 動能排行挑出主動 ETF 前 N 名。
2. 嘗試自動抓取主動 ETF 最新持股。
3. 以 industry_map.csv 做產業聚合，產生：
   - Top 主動 ETF 持股快照
   - 前十大產業
   - 前十大個股
   - 共同重倉股
   - 近 5 日加碼 / 減碼 / 新增 / 刪除

設計原則：
- 這區只看「產業風向」，不是照抄成分股買進。
- 自動來源若抓不到，回傳空資料，前端可改用 CSV 備援。
- 不額外依賴 bs4，只用 requests + pandas.read_html，降低 requirements 負擔。
"""

from __future__ import annotations

import html as html_lib
import io
import os
import re
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from github_history_store import (
    normalize_history_df,
    sync_history_with_github,
    diagnose_github_history_connection,
)

try:
    import streamlit as st
except Exception:  # 允許單元測試或命令列環境不載入 Streamlit
    st = None


DEFAULT_ACTIVE_ETFS: Dict[str, Dict[str, str]] = {
    "00400A": {"名稱": "主動國泰動能高息"},
    "00981A": {"名稱": "主動統一台股增長"},
    "00982A": {"名稱": "主動群益台灣強棒"},
    "00980A": {"名稱": "主動野村臺灣優選"},
    "00983A": {"名稱": "主動中信ARK創新"},
    "00992A": {"名稱": "主動群益科技創新"},
    "00999A": {"名稱": "主動復華未來50"},
}

# Generic sources. 這些網頁格式可能變動，所以 fetch 會自動 fail-soft。
GENERIC_SOURCE_TEMPLATES = [
    "https://www.moneydj.com/etf/x/basic/basic0007.xdjhtm?etfid={code}.tw",
    "https://www.pocket.tw/etf//tw/{code}/fundholding",
]

CACHE_FILE = "active_etf_holdings_history.csv"
ALT_CACHE_FILE = "/tmp/active_etf_holdings_history.csv"
SESSION_HISTORY_KEY = "_active_etf_holdings_history_df"
GITHUB_DIAG_KEY = "_active_etf_github_diag"


# -----------------------------
# 基礎工具
# -----------------------------

def _maybe_cache_data(ttl=1800, show_spinner=False):
    def deco(fn):
        if st is not None:
            return st.cache_data(ttl=ttl, show_spinner=show_spinner)(fn)
        return fn
    return deco


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


def _to_float(v, default=0.0) -> float:
    try:
        if pd.isna(v):
            return default
        s = str(v).replace("％", "%").replace("%", "").replace(",", "").strip()
        m = re.search(r"-?\d+\.?\d*", s)
        return float(m.group(0)) if m else default
    except Exception:
        return default


def _clean_code(v) -> str:
    s = str(v or "").strip().upper()
    s = re.sub(r"[^0-9A-Z]", "", s)
    # 台股代碼常見：四碼、五碼、含 A 的 ETF。成分股代碼通常四碼。
    return s


def _norm_col(c: object) -> str:
    return str(c).replace("\ufeff", "").replace("\n", "").strip()


def _pick_col(cols: Iterable[str], keys: List[str], exclude: Optional[List[str]] = None) -> Optional[str]:
    exclude = exclude or []
    cols = [_norm_col(c) for c in cols]
    for c in cols:
        if any(x in c for x in exclude):
            continue
        if c in keys:
            return c
    for c in cols:
        if any(x in c for x in exclude):
            continue
        if any(k in c for k in keys):
            return c
    return None


def _name_reverse_map(name_map: Dict[str, str]) -> Dict[str, str]:
    rev = {}
    for code, name in (name_map or {}).items():
        n = str(name).strip()
        if n:
            rev[n] = str(code).strip()
    return rev


# -----------------------------
# ETF 名單與自動來源
# -----------------------------

def get_active_etf_candidates(momentum_df: Optional[pd.DataFrame] = None, top_n: int = 10) -> List[Dict[str, str]]:
    """從 ETF 動能排行抓主動 ETF 前 N 名；若沒有動能表，就用預設主動 ETF 清單。"""
    rows: List[Dict[str, str]] = []
    if momentum_df is not None and not momentum_df.empty:
        df = momentum_df.copy()
        if "類型" in df.columns:
            df = df[df["類型"].astype(str).str.contains("主動", na=False)]
        if "動能分數" in df.columns:
            df["_score"] = pd.to_numeric(df["動能分數"], errors="coerce").fillna(0)
            df = df.sort_values("_score", ascending=False)
        for _, r in df.head(top_n).iterrows():
            code = _clean_code(r.get("代號", ""))
            if not code:
                continue
            rows.append({"ETF代號": code, "ETF名稱": str(r.get("名稱", DEFAULT_ACTIVE_ETFS.get(code, {}).get("名稱", code)))} )
    if not rows:
        for code, meta in list(DEFAULT_ACTIVE_ETFS.items())[:top_n]:
            rows.append({"ETF代號": code, "ETF名稱": meta.get("名稱", code)})
    # 去重保序
    seen = set()
    out = []
    for r in rows:
        code = r["ETF代號"]
        if code not in seen:
            seen.add(code)
            out.append(r)
    return out[:top_n]


def _source_urls_for(code: str, custom_sources: Optional[Dict[str, str]] = None) -> List[str]:
    custom_sources = custom_sources or {}
    urls = []
    if code in custom_sources and str(custom_sources[code]).strip():
        urls.append(str(custom_sources[code]).strip())
    urls.extend([tpl.format(code=code) for tpl in GENERIC_SOURCE_TEMPLATES])
    return urls


def _fetch_html(url: str, timeout: int = 18) -> str:
    try:
        resp = _session().get(url, timeout=timeout, verify=False)
        resp.raise_for_status()
        text = resp.text or ""
        return text if len(text) >= 100 else ""
    except Exception:
        return ""


def _read_html_tables_from_text(html_text: str) -> List[pd.DataFrame]:
    if not html_text:
        return []
    try:
        return pd.read_html(io.StringIO(html_text))
    except Exception:
        return []


def _strip_html_to_text(html_text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html_text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[\t\r\f\v]+", " ", text)
    text = re.sub(r" +", " ", text)
    return text


def _parse_moneydj_text(html_text: str, etf_code: str, etf_name: str, name_map: Optional[Dict[str, str]], source_url: str) -> pd.DataFrame:
    """MoneyDJ / 類似頁面文字備援解析。

    有些網站表格不是 pandas.read_html 可解析的真正 table，
    但頁面文字會出現：台積電(2330.TW) 8.99 10,039,000 這類格式。
    """
    if not html_text:
        return pd.DataFrame()
    text = _strip_html_to_text(html_text)
    pos = text.find("持股明細")
    segment = text[pos: pos + 8000] if pos >= 0 else text[:10000]

    date = pd.Timestamp(datetime.now().date())
    date_matches = re.findall(r"資料日期[:：]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})", segment)
    if date_matches:
        y, m, d = date_matches[-1]
        try:
            date = pd.Timestamp(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")
        except Exception:
            pass

    patterns = [
        re.compile(r"([\u4e00-\u9fffA-Za-z0-9*\-]+)\((\d{4}[A-Z]?)\.TW\)\s*([0-9]+(?:\.[0-9]+)?)\s+([0-9,]+(?:\.[0-9]+)?)"),
        re.compile(r"(\d{4}[A-Z]?)\s+([\u4e00-\u9fffA-Za-z0-9*\-]+)\s+([0-9]+(?:\.[0-9]+)?)%?"),
    ]
    rows = []
    seen = set()
    for idx, pattern in enumerate(patterns):
        for m in pattern.findall(segment):
            if idx == 0:
                name, code, weight, shares = m
            else:
                code, name, weight = m
                shares = 0
            code = _clean_code(code)
            if not code or code in seen:
                continue
            w = _to_float(weight)
            if w <= 0 or w > 100:
                continue
            seen.add(code)
            rows.append({
                "日期": date,
                "ETF代號": _clean_code(etf_code),
                "ETF名稱": etf_name or etf_code,
                "成分股代號": code,
                "成分股名稱": (name_map or {}).get(code, str(name).strip()),
                "權重": w,
                "持有股數": _to_float(shares),
                "來源": source_url,
            })
        if rows:
            break
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _standardize_holding_table(
    raw: pd.DataFrame,
    etf_code: str,
    etf_name: str,
    name_map: Optional[Dict[str, str]] = None,
    source_url: str = "",
) -> pd.DataFrame:
    """把不同網站表格標準化為：日期 / ETF代號 / ETF名稱 / 成分股代號 / 成分股名稱 / 權重 / 來源。"""
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    df.columns = [_norm_col(c) for c in df.columns]

    code_col = _pick_col(df.columns, ["成分股代號", "股票代號", "證券代號", "持股代號", "代號", "股票代碼", "Code"])
    name_col = _pick_col(df.columns, ["成分股名稱", "股票名稱", "證券名稱", "持股名稱", "個股名稱", "名稱", "Name"])
    weight_col = _pick_col(df.columns, ["權重", "持股權重", "持股比例", "比重", "比例%", "投資比例(%)", "投資比例", "Weight"])

    # 沒有權重但有持有股數時，仍可作為持股快照，但共同重倉權重會較弱。
    share_col = _pick_col(df.columns, ["持有股數", "股數", "持股股數", "持股數", "Shares"])

    if name_col is None and code_col is None:
        return pd.DataFrame()
    if weight_col is None and share_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["成分股代號"] = df[code_col].map(_clean_code) if code_col else ""
    out["成分股名稱"] = df[name_col].astype(str).str.strip() if name_col else out["成分股代號"]

    if code_col is None or out["成分股代號"].eq("").all():
        rev = _name_reverse_map(name_map or {})
        out["成分股代號"] = out["成分股名稱"].map(lambda x: rev.get(str(x).strip(), ""))

    out["權重"] = df[weight_col].map(_to_float) if weight_col else 0.0
    if share_col:
        out["持有股數"] = df[share_col].map(_to_float)
    else:
        out["持有股數"] = 0.0

    out["日期"] = pd.Timestamp(datetime.now().date())
    out["ETF代號"] = etf_code
    out["ETF名稱"] = etf_name or etf_code
    out["來源"] = source_url

    # 過濾合計列 / 空列 / 非台股代碼且無名稱列
    bad_name = out["成分股名稱"].astype(str).str.contains("合計|小計|現金|期貨|基金|ETF|預估|項目", na=False)
    out = out[~bad_name].copy()
    out = out[(out["成分股名稱"].astype(str).str.strip() != "") | (out["成分股代號"].astype(str).str.strip() != "")]

    # 權重全 0 的表格，多半不是持股比例表；除非有股數。
    if out.empty:
        return out
    if out["權重"].sum() <= 0 and out["持有股數"].sum() <= 0:
        return pd.DataFrame()
    return out.reset_index(drop=True)


@_maybe_cache_data(ttl=3600, show_spinner=False)
def fetch_active_etf_holding_one(
    etf_code: str,
    etf_name: str = "",
    custom_sources: Optional[Dict[str, str]] = None,
    name_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """嘗試自動抓取單檔主動 ETF 持股。抓不到就回空表。"""
    code = _clean_code(etf_code)
    name = etf_name or DEFAULT_ACTIVE_ETFS.get(code, {}).get("名稱", code)
    for url in _source_urls_for(code, custom_sources):
        html_text = _fetch_html(url)
        best = pd.DataFrame()

        for t in _read_html_tables_from_text(html_text):
            std = _standardize_holding_table(t, code, name, name_map=name_map, source_url=url)
            if std.empty:
                continue
            if len(std) > len(best):
                best = std

        # MoneyDJ / JS 文字備援：read_html 抓不到時仍可解析持股文字。
        if best.empty:
            best = _parse_moneydj_text(html_text, code, name, name_map=name_map, source_url=url)

        if not best.empty:
            return best
        time.sleep(0.25)
    return pd.DataFrame()


@_maybe_cache_data(ttl=3600, show_spinner=False)
def fetch_active_etf_holdings_auto(
    candidates: Tuple[Tuple[str, str], ...],
    custom_sources: Optional[Dict[str, str]] = None,
    name_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    frames = []
    for code, name in candidates:
        df = fetch_active_etf_holding_one(code, name, custom_sources=custom_sources, name_map=name_map)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# -----------------------------
# 歷史快取與分析
# -----------------------------

def merge_holdings_history(latest_df: pd.DataFrame, cache_path: str = CACHE_FILE, max_days: int = 20) -> pd.DataFrame:
    """把今日快照併入歷史庫。

    順序：今日快照 + session + 本機 CSV + /tmp CSV + GitHub CSV → 去重 → 寫回本機與 GitHub。
    GitHub 若失敗，不影響前端分析；診斷資訊會放在 st.session_state。
    """
    frames = []
    if latest_df is not None and not latest_df.empty:
        frames.append(latest_df.copy())

    if st is not None:
        try:
            sess_df = st.session_state.get(SESSION_HISTORY_KEY)
            if isinstance(sess_df, pd.DataFrame) and not sess_df.empty:
                frames.append(sess_df.copy())
        except Exception:
            pass

    for p in [cache_path, ALT_CACHE_FILE]:
        try:
            if p and os.path.exists(p):
                old = pd.read_csv(p, dtype=str)
                if old is not None and not old.empty:
                    frames.append(old)
        except Exception:
            pass

    if not frames:
        try:
            gh_hist, gh_diag = sync_history_with_github(pd.DataFrame(), max_days=max_days)
            if st is not None:
                st.session_state[GITHUB_DIAG_KEY] = gh_diag
            if gh_hist is not None and not gh_hist.empty:
                return normalize_history_df(gh_hist, max_days=max_days).reset_index(drop=True)
        except Exception as e:
            if st is not None:
                st.session_state[GITHUB_DIAG_KEY] = {"ok": False, "message": f"GitHub 讀取例外：{type(e).__name__}: {e}"}
        return pd.DataFrame()

    local_hist = normalize_history_df(pd.concat(frames, ignore_index=True), max_days=max_days)

    # 優先同步 GitHub；失敗時仍沿用本機/session 歷史。
    try:
        gh_hist, gh_diag = sync_history_with_github(local_hist, max_days=max_days)
        if st is not None:
            st.session_state[GITHUB_DIAG_KEY] = gh_diag
        hist = gh_hist if gh_hist is not None and not gh_hist.empty else local_hist
    except Exception as e:
        if st is not None:
            st.session_state[GITHUB_DIAG_KEY] = {"ok": False, "message": f"GitHub 同步例外：{type(e).__name__}: {e}"}
        hist = local_hist

    hist = normalize_history_df(hist, max_days=max_days)

    # 寫回本機與 /tmp；失敗就略過，不能影響主流程。
    for p in [cache_path, ALT_CACHE_FILE]:
        try:
            if p:
                os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
                hist.to_csv(p, index=False, encoding="utf-8-sig")
        except Exception:
            pass

    if st is not None:
        try:
            st.session_state[SESSION_HISTORY_KEY] = hist.copy()
        except Exception:
            pass

    # summarize_holdings 期待日期可轉換，這裡保留字串也可以，後續會 pd.to_datetime。
    return hist.reset_index(drop=True)


def get_history_status(holdings_df: pd.DataFrame, lookback_days: int = 5) -> Dict[str, object]:
    if holdings_df is None or holdings_df.empty or "日期" not in holdings_df.columns:
        base = {"days": 0, "latest": "-", "message": "尚無歷史快照。", "github": {}}
    else:
        dates = pd.to_datetime(holdings_df["日期"], errors="coerce").dropna()
        days = int(dates.dt.normalize().nunique()) if not dates.empty else 0
        latest = dates.max().strftime("%Y-%m-%d") if not dates.empty else "-"
        if days >= max(2, int(lookback_days)):
            msg = f"歷史快照已有 {days} 個交易日，可觀察近 {lookback_days} 日變化。"
        elif days >= 2:
            msg = f"歷史快照目前 {days} 個交易日，可先看區間變化；累積到 {lookback_days} 日會更穩。"
        elif days == 1:
            msg = "目前只有單日快照，需等後續交易日累積。"
        else:
            msg = "尚無有效快照。"
        base = {"days": days, "latest": latest, "message": msg, "github": {}}
    if st is not None:
        try:
            gh = st.session_state.get(GITHUB_DIAG_KEY, {}) or {}
            if gh:
                base["github"] = gh
                gh_msg = gh.get("message") or gh.get("write", {}).get("message") or gh.get("read", {}).get("message")
                if gh_msg:
                    base["message"] = f"{base['message']}｜{gh_msg}"
        except Exception:
            pass
    return base


def get_github_history_diagnostics() -> Dict[str, object]:
    """給前端顯示用的 GitHub 連線診斷，不包含 token。"""
    return diagnose_github_history_connection()


def _industry_of(code: str, industry_map: Dict[str, str]) -> str:
    return (industry_map or {}).get(str(code).strip(), "未分類")


def summarize_holdings(
    holdings_df: pd.DataFrame,
    industry_map: Dict[str, str],
    name_map: Dict[str, str],
    top_n: int = 5,
    lookback_days: int = 5,
) -> Dict[str, pd.DataFrame]:
    empty = {
        "snapshot": pd.DataFrame(),
        "industries": pd.DataFrame(),
        "stocks": pd.DataFrame(),
        "common_holdings": pd.DataFrame(),
        "changes": pd.DataFrame(),
        "industry_changes": pd.DataFrame(),
        "daily_events": pd.DataFrame(),
        "shared_actions": pd.DataFrame(),
        "manager_profiles": pd.DataFrame(),
    }
    if holdings_df is None or holdings_df.empty:
        return empty

    df = holdings_df.copy()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    df["權重"] = df["權重"].map(_to_float)
    df = df.dropna(subset=["日期"])
    if df.empty:
        return empty

    latest = df["日期"].max()
    latest_df = df[df["日期"] == latest].copy()
    if latest_df.empty:
        return empty

    # 如果最新日 ETF 數 > top_n，用總權重較高者或資料列較多者做 focus。
    etf_rank = latest_df.groupby(["ETF代號", "ETF名稱"], dropna=False).agg(
        權重合計=("權重", "sum"),
        持股數=("成分股代號", "count"),
    ).reset_index().sort_values(["權重合計", "持股數"], ascending=[False, False]).head(top_n)
    focus = etf_rank["ETF代號"].astype(str).tolist()

    latest_focus = latest_df[latest_df["ETF代號"].isin(focus)].copy()
    latest_focus["產業"] = latest_focus["成分股代號"].map(lambda x: _industry_of(x, industry_map))
    latest_focus["成分股名稱"] = latest_focus.apply(
        lambda r: (name_map or {}).get(str(r["成分股代號"]), str(r.get("成分股名稱", r["成分股代號"]))), axis=1
    )

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

    profile_rows = []
    for etf_code, sub in latest_focus.groupby("ETF代號"):
        etf_name = sub["ETF名稱"].iloc[0] if "ETF名稱" in sub else etf_code
        ind_top = sub.groupby("產業")["權重"].sum().sort_values(ascending=False).head(5)
        stock_top = sub.sort_values("權重", ascending=False).head(8)
        profile_rows.append({
            "ETF代號": etf_code,
            "ETF名稱": etf_name,
            "持股數": int(len(sub)),
            "集中度": round(float(stock_top["權重"].sum()), 2),
            "主要產業": "、".join([f"{k} {v:.1f}%" for k, v in ind_top.items()]),
            "重點持股": "、".join([f"{r['成分股名稱']}({r['成分股代號']}) {r['權重']:.1f}%" for _, r in stock_top.iterrows()]),
        })
    manager_profiles = pd.DataFrame(profile_rows)

    common = latest_focus.groupby(["成分股代號", "成分股名稱", "產業"], dropna=False).agg(
        出現ETF數=("ETF代號", "nunique"),
        合計權重=("權重", "sum"),
        持有ETF=("ETF代號", lambda x: "、".join(sorted(set(map(str, x)))))
    ).reset_index()
    common_holdings = common[common["出現ETF數"] >= 2].sort_values(["出現ETF數", "合計權重"], ascending=[False, False]).head(30)

    changes = pd.DataFrame()
    daily_events = pd.DataFrame()
    shared_actions = pd.DataFrame()
    industry_changes = pd.DataFrame()
    dates = sorted(df["日期"].dropna().unique())

    def _compare_pair(prev_day, new_day):
        new_df = df[(df["日期"] == new_day) & (df["ETF代號"].isin(focus))].copy()
        old_df = df[(df["日期"] == prev_day) & (df["ETF代號"].isin(focus))].copy()
        if new_df.empty and old_df.empty:
            return pd.DataFrame()
        new_key = new_df[["ETF代號", "成分股代號", "成分股名稱", "權重"]].copy() if not new_df.empty else pd.DataFrame(columns=["ETF代號", "成分股代號", "成分股名稱", "權重"])
        old_key = old_df[["ETF代號", "成分股代號", "權重"]].copy() if not old_df.empty else pd.DataFrame(columns=["ETF代號", "成分股代號", "權重"])
        merged = pd.merge(new_key, old_key, on=["ETF代號", "成分股代號"], how="outer", suffixes=("_新", "_舊"))
        merged["權重_新"] = merged["權重_新"].fillna(0).map(_to_float)
        merged["權重_舊"] = merged["權重_舊"].fillna(0).map(_to_float)
        merged["變化"] = merged["權重_新"] - merged["權重_舊"]
        merged["狀態"] = np.where((merged["權重_舊"] == 0) & (merged["權重_新"] > 0), "新增",
                              np.where((merged["權重_舊"] > 0) & (merged["權重_新"] == 0), "刪除",
                              np.where(merged["變化"] > 0, "加碼", np.where(merged["變化"] < 0, "減碼", "持平"))))
        merged = merged[merged["狀態"].isin(["新增", "刪除", "加碼", "減碼"])].copy()
        if merged.empty:
            return merged
        merged["成分股名稱"] = merged.apply(lambda r: (name_map or {}).get(str(r["成分股代號"]), str(r.get("成分股名稱", r["成分股代號"]))), axis=1)
        merged["產業"] = merged.apply(lambda r: _industry_of(r["成分股代號"], industry_map), axis=1)
        merged["比較基準"] = f"{pd.Timestamp(prev_day).strftime('%Y-%m-%d')} → {pd.Timestamp(new_day).strftime('%Y-%m-%d')}"
        merged["事件日期"] = pd.Timestamp(new_day).strftime("%Y-%m-%d")
        return merged

    # 逐日事件：看每一天相對前一個有效快照，避免「一直顯示同一段區間」。
    daily_parts = []
    if len(dates) >= 2:
        for prev_day, new_day in zip(dates[:-1], dates[1:]):
            part = _compare_pair(prev_day, new_day)
            if part is not None and not part.empty:
                daily_parts.append(part)
    if daily_parts:
        daily_events = pd.concat(daily_parts, ignore_index=True)
        latest_event_day = str(daily_events["事件日期"].max())
        changes = daily_events[daily_events["事件日期"].astype(str).eq(latest_event_day)].copy()
    else:
        changes = pd.DataFrame()

    if changes is not None and not changes.empty:
        changes = changes.sort_values(["狀態", "變化"], ascending=[True, False])
        industry_changes = changes.groupby("產業", dropna=False)["變化"].sum().reset_index().sort_values("變化", ascending=False)
        shared_actions = changes.groupby(["成分股代號", "成分股名稱", "產業", "狀態"], dropna=False).agg(
            ETF數=("ETF代號", "nunique"),
            涉及ETF=("ETF代號", lambda x: "、".join(sorted(set(map(str, x))))),
            合計變化=("變化", "sum"),
        ).reset_index().sort_values(["ETF數", "合計變化"], ascending=[False, False])
    else:
        shared_actions = pd.DataFrame()

    return {
        "snapshot": snapshot,
        "industries": industries,
        "stocks": stocks,
        "common_holdings": common_holdings,
        "changes": changes,
        "industry_changes": industry_changes,
        "daily_events": daily_events,
        "shared_actions": shared_actions,
        "manager_profiles": manager_profiles,
    }


def build_active_etf_manager_radar(
    momentum_df: Optional[pd.DataFrame],
    industry_map: Dict[str, str],
    name_map: Dict[str, str],
    top_n: int = 5,
    lookback_days: int = 5,
    custom_sources: Optional[Dict[str, str]] = None,
    cache_path: str = CACHE_FILE,
) -> Dict[str, object]:
    """主入口：自動挑主動 ETF Top N → 抓持股 → 併歷史 → 產出分析。"""
    candidates = get_active_etf_candidates(momentum_df, top_n=top_n)
    cand_tuple = tuple((c["ETF代號"], c["ETF名稱"]) for c in candidates)
    latest = fetch_active_etf_holdings_auto(cand_tuple, custom_sources=custom_sources, name_map=name_map)
    if latest.empty:
        hist = merge_holdings_history(pd.DataFrame(), cache_path=cache_path, max_days=max(20, lookback_days + 10))
        summary = summarize_holdings(hist, industry_map, name_map, top_n=top_n, lookback_days=lookback_days)
        history_status = get_history_status(hist, lookback_days=lookback_days)
        if hist is not None and not hist.empty and summary.get("snapshot", pd.DataFrame()).empty is False:
            return {
                "ok": True,
                "message": "今日自動持股來源抓不到；已沿用 GitHub / 本機最近成功快照。",
                "candidates": pd.DataFrame(candidates),
                "holdings": hist,
                "summary": summary,
                "history_status": history_status,
            }
        return {
            "ok": False,
            "message": "自動持股來源目前抓不到資料，且沒有可沿用的歷史快照；請使用 CSV 備援。",
            "candidates": pd.DataFrame(candidates),
            "holdings": pd.DataFrame(),
            "summary": summarize_holdings(pd.DataFrame(), industry_map, name_map, top_n=top_n, lookback_days=lookback_days),
            "history_status": history_status,
        }
    hist = merge_holdings_history(latest, cache_path=cache_path, max_days=max(20, lookback_days + 10))
    summary = summarize_holdings(hist, industry_map, name_map, top_n=top_n, lookback_days=lookback_days)
    history_status = get_history_status(hist, lookback_days=lookback_days)
    return {
        "ok": True,
        "message": f"已自動更新 {latest['ETF代號'].nunique()} 檔主動 ETF 持股；歷史庫會自動同步，若 GitHub 失敗則先用本機快取。",
        "candidates": pd.DataFrame(candidates),
        "holdings": hist,
        "summary": summary,
        "history_status": history_status,
    }
