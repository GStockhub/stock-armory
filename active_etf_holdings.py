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

import io
import os
import re
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

try:
    import streamlit as st
except Exception:  # 允許單元測試或命令列環境不載入 Streamlit
    st = None


DEFAULT_ACTIVE_ETFS: Dict[str, Dict[str, str]] = {
    "00981A": {"名稱": "主動統一台股增長"},
    "00982A": {"名稱": "主動群益台灣強棒"},
    "00980A": {"名稱": "主動野村臺灣優選"},
    "00983A": {"名稱": "主動中信ARK創新"},
    "00992A": {"名稱": "主動群益科技創新"},
    "00999A": {"名稱": "主動復華未來50"},
}

# Generic sources. 這些網頁格式可能變動，所以 fetch 會自動 fail-soft。
# MoneyDJ 目前可直接在持股頁看到「持股明細」與「投資比例」，
# Pocket / Yahoo 作為備援來源；若網站改版，前端仍會回到 CSV 備援。
GENERIC_SOURCE_TEMPLATES = [
    "https://www.moneydj.com/etf/x/basic/basic0007.xdjhtm?etfid={code_l}.tw",
    "https://www.moneydj.com/ETF/X/Basic/Basic0007.xdjhtm?etfid={code_l}.tw&topc=",
    "https://tw.stock.yahoo.com/quote/{code}.TW/holding",
    "https://www.pocket.tw/etf//tw/{code}",
    "https://www.pocket.tw/etf//tw/{code}/fundholding",
]

CACHE_FILE = "active_etf_holdings_history.csv"


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


def _strip_html_to_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_unescape(text)
    text = re.sub(r"[\t\r\f\v]+", " ", text)
    text = re.sub(r" +", " ", text)
    return text


def html_unescape(text: str) -> str:
    # 避免額外 import html 與既有 html 變數撞名。
    try:
        import html as _html
        return _html.unescape(text)
    except Exception:
        return text


def _parse_holdings_from_moneydj_text(html: str, etf_code: str, etf_name: str, name_map: Optional[Dict[str, str]], source_url: str) -> pd.DataFrame:
    """MoneyDJ 持股明細文字備援解析。

    MoneyDJ 頁面常可直接看到：
    台積電(2330.TW) 8.99 10,039,000.00
    若 read_html 解析不到規格化表格，就用此法抓前十大持股。
    """
    if not html:
        return pd.DataFrame()
    text = _strip_html_to_text(html)
    # 優先抓「持股明細」後面的區段，避免誤抓相關 ETF 或新聞文字。
    pos = text.find("持股明細")
    if pos >= 0:
        segment = text[pos: pos + 6000]
    else:
        segment = text[:8000]

    # 日期：取持股明細後最接近的資料日期。
    date = pd.Timestamp(datetime.now().date())
    date_matches = re.findall(r"資料日期[:：]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})", segment)
    if date_matches:
        y, m, d = date_matches[-1]
        try:
            date = pd.Timestamp(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")
        except Exception:
            pass

    # 主要格式：名稱(2330.TW) 8.99 10,039,000.00
    pattern = re.compile(r"([\u4e00-\u9fffA-Za-z0-9*\-]+)\((\d{4}[A-Z]?)\.TW\)\s*([0-9]+(?:\.[0-9]+)?)\s+([0-9,]+(?:\.[0-9]+)?)")
    rows = []
    seen = set()
    for name, code, weight, shares in pattern.findall(segment):
        code = _clean_code(code)
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append({
            "日期": date,
            "ETF代號": _clean_code(etf_code),
            "ETF名稱": etf_name or etf_code,
            "成分股代號": code,
            "成分股名稱": (name_map or {}).get(code, str(name).strip()),
            "權重": _to_float(weight),
            "持有股數": _to_float(shares),
            "來源": source_url,
        })
    if rows:
        return pd.DataFrame(rows)

    # Yahoo 等來源常只有「台積電 9.57%」沒有代號；能用 name_map 反查就保留。
    rev = _name_reverse_map(name_map or {})
    loose = re.findall(r"([\u4e00-\u9fffA-Za-z0-9*\-]{2,20})\s+([0-9]+(?:\.[0-9]+)?)%", segment)
    for name, weight in loose:
        code = rev.get(str(name).strip(), "")
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append({
            "日期": date,
            "ETF代號": _clean_code(etf_code),
            "ETF名稱": etf_name or etf_code,
            "成分股代號": code,
            "成分股名稱": str(name).strip(),
            "權重": _to_float(weight),
            "持有股數": 0.0,
            "來源": source_url,
        })
    return pd.DataFrame(rows)


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
    code = _clean_code(code)
    urls = []
    if code in custom_sources and str(custom_sources[code]).strip():
        urls.append(str(custom_sources[code]).strip())
    for tpl in GENERIC_SOURCE_TEMPLATES:
        try:
            urls.append(tpl.format(code=code, code_l=code.lower()))
        except Exception:
            continue
    # 去重保序
    out, seen = [], set()
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _fetch_html(url: str, timeout: int = 18) -> str:
    try:
        resp = _session().get(url, timeout=timeout, verify=False)
        resp.raise_for_status()
        # MoneyDJ 常見 Big5 / cp950；apparent_encoding 可避免中文欄位變亂碼。
        enc = getattr(resp, "apparent_encoding", None) or resp.encoding or "utf-8"
        resp.encoding = enc
        html = resp.text
        return html if html and len(html) > 100 else ""
    except Exception:
        return ""


def _read_html_tables(url: str, timeout: int = 18) -> List[pd.DataFrame]:
    html = _fetch_html(url, timeout=timeout)
    if not html:
        return []
    try:
        return pd.read_html(io.StringIO(html))
    except Exception:
        return []


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
        html = _fetch_html(url)
        best = pd.DataFrame()
        if html:
            try:
                tables = pd.read_html(io.StringIO(html))
            except Exception:
                tables = []
            for t in tables:
                std = _standardize_holding_table(t, code, name, name_map=name_map, source_url=url)
                if std.empty:
                    continue
                if len(std) > len(best):
                    best = std
            # MoneyDJ / Yahoo 文字備援：read_html 抓不到時仍可解析「持股明細」文字。
            if best.empty:
                best = _parse_holdings_from_moneydj_text(html, code, name, name_map=name_map, source_url=url)
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
    """把今日快照併入本地 CSV 歷史。Streamlit Cloud 若檔案系統不可寫，會自動只回今日資料。"""
    if latest_df is None or latest_df.empty:
        return pd.DataFrame()
    latest = latest_df.copy()
    latest["日期"] = pd.to_datetime(latest["日期"], errors="coerce")
    frames = [latest]
    try:
        if cache_path and os.path.exists(cache_path):
            old = pd.read_csv(cache_path, dtype=str)
            if not old.empty:
                old["日期"] = pd.to_datetime(old["日期"], errors="coerce")
                frames.append(old)
        hist = pd.concat(frames, ignore_index=True)
        hist["日期"] = pd.to_datetime(hist["日期"], errors="coerce")
        hist = hist.dropna(subset=["日期", "ETF代號", "成分股代號"])
        hist["權重"] = hist["權重"].map(_to_float)
        hist = hist.drop_duplicates(subset=["日期", "ETF代號", "成分股代號"], keep="last")
        keep_dates = sorted(hist["日期"].dropna().unique())[-max_days:]
        hist = hist[hist["日期"].isin(keep_dates)].copy()
        try:
            hist.to_csv(cache_path, index=False, encoding="utf-8-sig")
        except Exception:
            pass
        return hist.reset_index(drop=True)
    except Exception:
        return latest.reset_index(drop=True)


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

    common = latest_focus.groupby(["成分股代號", "成分股名稱", "產業"], dropna=False).agg(
        出現ETF數=("ETF代號", "nunique"),
        合計權重=("權重", "sum"),
        持有ETF=("ETF代號", lambda x: "、".join(sorted(set(map(str, x)))))
    ).reset_index()
    common_holdings = common[common["出現ETF數"] >= 2].sort_values(["出現ETF數", "合計權重"], ascending=[False, False]).head(30)

    changes = pd.DataFrame()
    industry_changes = pd.DataFrame()
    dates = sorted(df["日期"].dropna().unique())
    prev_dates = [d for d in dates if d < latest]
    if prev_dates:
        target_min = latest - pd.Timedelta(days=max(1, int(lookback_days) + 2))
        candidates = [d for d in prev_dates if d >= target_min]
        prev = min(candidates) if candidates else prev_dates[-1]
        prev_df = df[(df["日期"] == prev) & (df["ETF代號"].isin(focus))].copy()
        prev_df["產業"] = prev_df["成分股代號"].map(lambda x: _industry_of(x, industry_map))

        latest_key = latest_focus[["ETF代號", "成分股代號", "成分股名稱", "產業", "權重"]].copy()
        prev_key = prev_df[["ETF代號", "成分股代號", "權重"]].copy() if not prev_df.empty else pd.DataFrame(columns=["ETF代號", "成分股代號", "權重"])
        merged = pd.merge(latest_key, prev_key, on=["ETF代號", "成分股代號"], how="outer", suffixes=("_新", "_舊"))
        merged["權重_新"] = merged["權重_新"].fillna(0).map(_to_float)
        merged["權重_舊"] = merged["權重_舊"].fillna(0).map(_to_float)
        merged["變化"] = merged["權重_新"] - merged["權重_舊"]
        merged["狀態"] = np.where((merged["權重_舊"] == 0) & (merged["權重_新"] > 0), "新增",
                              np.where((merged["權重_舊"] > 0) & (merged["權重_新"] == 0), "刪除",
                              np.where(merged["變化"] > 0, "加碼", np.where(merged["變化"] < 0, "減碼", "持平"))))
        merged["成分股名稱"] = merged.apply(lambda r: (name_map or {}).get(str(r["成分股代號"]), str(r.get("成分股名稱", r["成分股代號"]))), axis=1)
        merged["產業"] = merged.apply(lambda r: _industry_of(r["成分股代號"], industry_map), axis=1)
        changes = merged[merged["狀態"].isin(["新增", "刪除", "加碼", "減碼"])].sort_values("變化", ascending=False)
        changes["比較基準"] = f"{pd.Timestamp(prev).strftime('%Y-%m-%d')} → {pd.Timestamp(latest).strftime('%Y-%m-%d')}"
        industry_changes = changes.groupby("產業", dropna=False)["變化"].sum().reset_index().sort_values("變化", ascending=False)

    return {
        "snapshot": snapshot,
        "industries": industries,
        "stocks": stocks,
        "common_holdings": common_holdings,
        "changes": changes,
        "industry_changes": industry_changes,
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
        return {
            "ok": False,
            "message": "自動來源未成功解析：MoneyDJ / Yahoo / Pocket 皆未取得持股表，請暫用 CSV 備援。",
            "candidates": pd.DataFrame(candidates),
            "holdings": pd.DataFrame(),
            "summary": summarize_holdings(pd.DataFrame(), industry_map, name_map, top_n=top_n, lookback_days=lookback_days),
        }
    hist = merge_holdings_history(latest, cache_path=cache_path, max_days=max(20, lookback_days + 10))
    summary = summarize_holdings(hist, industry_map, name_map, top_n=top_n, lookback_days=lookback_days)
    return {
        "ok": True,
        "message": f"已自動更新 {latest['ETF代號'].nunique()} 檔主動 ETF 持股；若只有單日資料，近 5 日變化會等累積後顯示。",
        "candidates": pd.DataFrame(candidates),
        "holdings": hist,
        "summary": summary,
    }
