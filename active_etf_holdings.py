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
    from active_etf_official_sources import fetch_official_holding_one, source_quality
except Exception:
    fetch_official_holding_one = None
    source_quality = None

try:
    import streamlit as st
except Exception:  # 允許單元測試或命令列環境不載入 Streamlit
    st = None


DEFAULT_ACTIVE_ETFS: Dict[str, Dict[str, str]] = {
    # V37.4.1：依主動式 ETF 清單擴充，不再只追蹤少數幾檔。
    # key 順序以目前規模/熱門度概念排列；動能表若有資料仍會優先重排。
    "00981A": {"名稱": "主動統一台股增長", "投信": "統一投信"},
    "00403A": {"名稱": "主動統一升級50", "投信": "統一投信"},
    "00992A": {"名稱": "主動群益科技創新", "投信": "群益投信"},
    "00982A": {"名稱": "主動群益台灣強棒", "投信": "群益投信"},
    "00991A": {"名稱": "主動復華未來50", "投信": "復華投信"},
    "00988A": {"名稱": "主動統一全球創新", "投信": "統一投信"},
    "00990A": {"名稱": "主動元大AI新經濟", "投信": "元大投信"},
    "00400A": {"名稱": "主動國泰動能高息", "投信": "國泰投信"},
    "00980A": {"名稱": "主動野村臺灣優選", "投信": "野村投信"},
    "00999A": {"名稱": "主動野村臺灣高息", "投信": "野村投信"},
    "00997A": {"名稱": "主動群益美國增長", "投信": "群益投信"},
    "00993A": {"名稱": "主動安聯台灣", "投信": "安聯投信"},
    "00985A": {"名稱": "主動野村台灣50", "投信": "野村投信"},
    "00984A": {"名稱": "主動安聯台灣高息", "投信": "安聯投信"},
    "00994A": {"名稱": "主動第一金台股優", "投信": "第一金投信"},
    "00995A": {"名稱": "主動中信台灣卓越", "投信": "中信投信"},
    "00996A": {"名稱": "主動兆豐台灣豐收", "投信": "兆豐投信"},
    "00401A": {"名稱": "主動摩根台灣鑫收", "投信": "摩根投信"},
    "00987A": {"名稱": "主動台新優勢成長", "投信": "台新投信"},
    "00998A": {"名稱": "主動復華金融股息", "投信": "復華投信"},
    "00983A": {"名稱": "主動中信ARK創新", "投信": "中信投信"},
    "00989A": {"名稱": "主動摩根美國科技", "投信": "摩根投信"},
    "00986A": {"名稱": "主動台新龍頭成長", "投信": "台新投信"},
}

# Generic sources. 這些網頁格式可能變動，所以 fetch 會自動 fail-soft。

# V37.12：平日 daily 專攻熱門 Top10；冷門 ETF 交給週末 full 補抓。
# 固定核心優先，避免重要 ETF 因暫時抓不到完整資料而被擠出 daily 名單。
PREFERRED_DAILY_ACTIVE_ETFS = [
    "00981A", "00982A", "00992A", "00991A", "00980A",
    "00400A", "00990A", "00999A", "00993A", "00985A",
]

GENERIC_SOURCE_TEMPLATES = [
    # V37.10：官方失敗後的備援來源，MoneyDJ 持股頁優先。
    "https://www.moneydj.com/etf/x/basic/basic0007.xdjhtm?etfid={code}.tw",
    "https://www.cmoney.tw/etf/tw/{code}/fundholding",
    "https://www.pocket.tw/etf//tw/{code}/fundholding",
]

CACHE_FILE = "active_etf_holdings_history.csv"
ALT_CACHE_FILE = "/tmp/active_etf_holdings_history.csv"
SESSION_HISTORY_KEY = "_active_etf_holdings_history_df"
GITHUB_DIAG_KEY = "_active_etf_github_diag"

# V37.7 主動 ETF 經理人雷達瘦身版
# - 明細快照保留 60 天
# - 主畫面判讀 20 天
# - 事件表看近 30 天
# - 股數變化優先；沒有股數時退回權重變化
# - 自動來源完整度防呆：抓到太少持股不寫入 history、不參與共同動作
HOLDINGS_KEEP_DAYS = 60
MAIN_LOOKBACK_DAYS = 20
EVENT_LOOKBACK_DAYS = 30
ACTIVE_ETF_TOP_N = 10
SIGNIFICANT_SHARE_RATIO = 0.03
SIGNIFICANT_WEIGHT_PP = 0.3
MIN_COMPLETE_HOLDINGS = 10
MIN_COMPLETE_WEIGHT_SUM = 20.0
# V37.11.4：有些新主動 ETF 目前只能拿到前 8~9 大持股。
# 這種資料不適合當「完整官方資料」，但足夠看經理人大方向，列為可參考快照。
MIN_REFERENCE_HOLDINGS = 8
MIN_REFERENCE_WEIGHT_SUM = 35.0


def _holding_quality(df: pd.DataFrame, industry_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """檢查每檔 ETF 的持股快照是否足夠完整。

    抓到 1~2 筆不等於成功；這種資料會污染產業占比與共同動作。
    """
    cols = ["ETF代號", "ETF名稱", "持股數", "權重合計", "產業數", "資料狀態", "資料備註"]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    tmp = df.copy()
    if "權重" not in tmp.columns:
        tmp["權重"] = 0
    tmp["權重"] = tmp["權重"].map(_to_float)
    if industry_map is not None and "產業" not in tmp.columns:
        tmp["產業"] = tmp["成分股代號"].map(lambda x: _industry_of(x, industry_map))
    elif "產業" not in tmp.columns:
        tmp["產業"] = ""

    q = tmp.groupby(["ETF代號", "ETF名稱"], dropna=False).agg(
        持股數=("成分股代號", "nunique"),
        權重合計=("權重", "sum"),
        產業數=("產業", "nunique"),
    ).reset_index()

    def _status(r):
        cnt = int(r.get("持股數", 0) or 0)
        wsum = float(r.get("權重合計", 0) or 0)
        ind_cnt = int(r.get("產業數", 0) or 0)

        # 完整快照：可以納入共同動作與主要統計。
        if cnt >= MIN_COMPLETE_HOLDINGS and wsum >= MIN_COMPLETE_WEIGHT_SUM:
            return "✅ 完整", "可納入分析"

        # 可參考快照：通常是前 8~9 大持股，足以看大方向，但不當成高信任共識。
        if cnt >= MIN_REFERENCE_HOLDINGS and wsum >= MIN_REFERENCE_WEIGHT_SUM:
            return "🟡 可參考", f"約80~90%持股方向；持股數{cnt}、權重合計{wsum:.1f}%"

        reasons = []
        if cnt < MIN_REFERENCE_HOLDINGS:
            reasons.append(f"持股數<{MIN_REFERENCE_HOLDINGS}")
        if wsum < MIN_REFERENCE_WEIGHT_SUM:
            reasons.append(f"權重合計<{MIN_REFERENCE_WEIGHT_SUM:.0f}%")
        if ind_cnt <= 1 and cnt < MIN_COMPLETE_HOLDINGS:
            reasons.append("產業過少")
        return "⚠️ 不完整", "、".join(reasons) if reasons else "資料不足"

    pairs = q.apply(_status, axis=1)
    q["資料狀態"] = [x[0] for x in pairs]
    q["資料備註"] = [x[1] for x in pairs]
    return q[cols]


def _filter_complete_holdings(df: pd.DataFrame, industry_map: Optional[Dict[str, str]] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    quality = _holding_quality(df, industry_map=industry_map)
    if df is None or df.empty or quality.empty:
        return pd.DataFrame(), quality
    good = set(quality[quality["資料狀態"].astype(str).str.match(r"^[✅🟡]", na=False)]["ETF代號"].astype(str))
    if not good:
        return pd.DataFrame(), quality
    return df[df["ETF代號"].astype(str).isin(good)].copy(), quality


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

def get_active_etf_candidates(momentum_df: Optional[pd.DataFrame] = None, top_n: int = 30) -> List[Dict[str, str]]:
    """主動 ETF 觀察清單。

    V37.4：不再只看 ETF 綜合動能 Top 10 內出現的主動 ETF。
    先依動能表排序，再把 DEFAULT_ACTIVE_ETFS 全部補齊；主動 ETF 不多，直接全追蹤比較適合。
    """
    rows: List[Dict[str, str]] = []
    if momentum_df is not None and not momentum_df.empty:
        df = momentum_df.copy()
        if "類型" in df.columns:
            df = df[df["類型"].astype(str).str.contains("主動", na=False)]
        if "動能分數" in df.columns:
            df["_score"] = pd.to_numeric(df["動能分數"], errors="coerce").fillna(0)
            df = df.sort_values("_score", ascending=False)
        for _, r in df.iterrows():
            code = _clean_code(r.get("代號", ""))
            if not code:
                continue
            rows.append({"ETF代號": code, "ETF名稱": str(r.get("名稱", DEFAULT_ACTIVE_ETFS.get(code, {}).get("名稱", code)))})

    # 動能表沒出現也要追蹤，避免只剩 00981A / 00982A。
    for code, meta in DEFAULT_ACTIVE_ETFS.items():
        rows.append({"ETF代號": code, "ETF名稱": meta.get("名稱", code)})

    seen = set()
    out = []
    for r in rows:
        code = r["ETF代號"]
        if code not in seen:
            seen.add(code)
            out.append(r)
    return out[:min(len(out), max(1, int(top_n)))]


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

    # V37.9：官方公告優先。這裡只作為前端 fallback；正式每日更新仍建議由 GitHub Actions ETL 跑。
    if fetch_official_holding_one is not None:
        try:
            official_df, _official_report = fetch_official_holding_one(code, name)
            ok = False
            if source_quality is not None:
                ok = bool(source_quality(official_df)[0])
            elif official_df is not None and not official_df.empty:
                ok = True
            if ok:
                return official_df
        except Exception:
            pass

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

def fetch_active_etf_holding_one_with_report(
    etf_code: str,
    etf_name: str = "",
    custom_sources: Optional[Dict[str, str]] = None,
    name_map: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
    """第三方備援抓取，帶每個 URL 的結果報告。ETL 用；前端不即時呼叫。"""
    code = _clean_code(etf_code)
    name = etf_name or DEFAULT_ACTIVE_ETFS.get(code, {}).get("名稱", code)
    reports: List[Dict[str, object]] = []
    best = pd.DataFrame()

    for url in _source_urls_for(code, custom_sources):
        html_text = _fetch_html(url)
        local_best = pd.DataFrame()

        for t in _read_html_tables_from_text(html_text):
            std = _standardize_holding_table(t, code, name, name_map=name_map, source_url=url)
            if std.empty:
                continue
            if len(std) > len(local_best):
                local_best = std

        if local_best.empty:
            local_best = _parse_moneydj_text(html_text, code, name, name_map=name_map, source_url=url)

        q = _holding_quality(local_best, industry_map=None)
        cnt = int(q["持股數"].iloc[0]) if not q.empty else 0
        wsum = float(q["權重合計"].iloc[0]) if not q.empty else 0.0
        status = str(q["資料狀態"].iloc[0]) if not q.empty else "⚠️ 不完整"
        note = str(q["資料備註"].iloc[0]) if not q.empty else "empty"
        adopted = bool(str(status).startswith(("✅", "🟡")))

        reports.append({
            "ETF代號": code,
            "ETF名稱": name,
            "投信": DEFAULT_ACTIVE_ETFS.get(code, {}).get("投信", ""),
            "來源類別": "備援",
            "來源": url,
            "類型": "MoneyDJ/CMoney/Pocket",
            "抓到筆數": cnt,
            "權重合計": round(wsum, 4),
            "狀態": status if adopted else f"⚠️ {note}",
            "採用": adopted,
        })

        if len(local_best) > len(best):
            best = local_best
        if adopted:
            return local_best, reports
        time.sleep(0.25)

    return best, reports


def fetch_active_etf_holdings_with_report(
    candidates: Tuple[Tuple[str, str], ...],
    custom_sources: Optional[Dict[str, str]] = None,
    name_map: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """批次備援抓取，並回傳 URL 級報告。"""
    frames = []
    all_reports: List[Dict[str, object]] = []
    for code, name in candidates:
        df, reports = fetch_active_etf_holding_one_with_report(code, name, custom_sources=custom_sources, name_map=name_map)
        all_reports.extend(reports)
        if df is not None and not df.empty:
            frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return out, pd.DataFrame(all_reports)


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


def _to_ts(x):
    try:
        return pd.Timestamp(x)
    except Exception:
        return pd.NaT


def _weighted_hot_candidates(
    latest_df: pd.DataFrame,
    momentum_df: Optional[pd.DataFrame],
    top_n: int = ACTIVE_ETF_TOP_N,
) -> pd.DataFrame:
    """每週熱門主動 ETF Top N。

    先用最新持股快照裡真的有資料的 ETF，再用：
    - 規模 / 權重合計概念 50%
    - 動能分數 30%
    - 新上市關注 20%
    做排序。若缺欄位，會自動退回持股數與內建順序。
    """
    if latest_df is None or latest_df.empty:
        return pd.DataFrame()

    rank = latest_df.groupby(["ETF代號", "ETF名稱"], dropna=False).agg(
        權重合計=("權重", "sum"),
        持股數=("成分股代號", "count"),
    ).reset_index()

    # 動能表只拿來加分 / 排序，不再限制候選池。
    if momentum_df is not None and not momentum_df.empty and "代號" in momentum_df.columns:
        mom = momentum_df.copy()
        mom["ETF代號"] = mom["代號"].map(_clean_code)
        if "動能分數" in mom.columns:
            mom["動能分數"] = pd.to_numeric(mom["動能分數"], errors="coerce").fillna(0)
        else:
            mom["動能分數"] = 0
        rank = pd.merge(rank, mom[["ETF代號", "動能分數"]].drop_duplicates("ETF代號"), on="ETF代號", how="left")
    else:
        rank["動能分數"] = 0

    rank["動能分數"] = pd.to_numeric(rank["動能分數"], errors="coerce").fillna(0)
    rank["_規模分"] = pd.to_numeric(rank["權重合計"], errors="coerce").fillna(0).rank(pct=True)
    rank["_動能分"] = rank["動能分數"].rank(pct=True)

    # 新 ETF / 近期熱門 ETF 若沒有足夠動能資料，也不能完全被吃掉：用內建清單前段給一點關注分。
    order = {code: i for i, code in enumerate(DEFAULT_ACTIVE_ETFS.keys())}
    rank["_內建序"] = rank["ETF代號"].map(order).fillna(len(order) + 99)
    rank["_新關注"] = (1 - (rank["_內建序"] / max(1, len(order)))).clip(lower=0, upper=1)

    rank["熱門分數"] = rank["_規模分"] * 50 + rank["_動能分"] * 30 + rank["_新關注"] * 20
    rank = rank.sort_values(["熱門分數", "權重合計", "持股數"], ascending=[False, False, False]).head(int(top_n)).copy()
    rank["熱門名次"] = range(1, len(rank) + 1)
    return rank


def summarize_holdings(
    holdings_df: pd.DataFrame,
    industry_map: Dict[str, str],
    name_map: Dict[str, str],
    top_n: int = ACTIVE_ETF_TOP_N,
    lookback_days: int = MAIN_LOOKBACK_DAYS,
    momentum_df: Optional[pd.DataFrame] = None,
    event_days: int = EVENT_LOOKBACK_DAYS,
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
        "hot_etfs": pd.DataFrame(),
        "quality": pd.DataFrame(),
        "incomplete_holdings": pd.DataFrame(),
        "meta": pd.DataFrame(),
    }
    if holdings_df is None or holdings_df.empty:
        return empty

    df = holdings_df.copy()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    df["權重"] = df["權重"].map(_to_float)
    if "持有股數" not in df.columns:
        df["持有股數"] = 0
    df["持有股數"] = df["持有股數"].map(_to_float)
    df = df.dropna(subset=["日期"])
    if df.empty:
        return empty

    # V37.7.1：清掉歷史庫中已污染的「單筆持股假快照」。
    # 完整度必須以「日期 + ETF」為單位判斷，避免多天零碎資料累加後被誤判完整。
    df["_產業_tmp"] = df["成分股代號"].map(lambda x: _industry_of(x, industry_map))
    q = df.groupby(["日期", "ETF代號", "ETF名稱"], dropna=False).agg(
        持股數=("成分股代號", "nunique"),
        權重合計=("權重", "sum"),
        產業數=("_產業_tmp", "nunique"),
    ).reset_index()
    q_cnt = pd.to_numeric(q["持股數"], errors="coerce").fillna(0)
    q_wsum = pd.to_numeric(q["權重合計"], errors="coerce").fillna(0)
    full_mask = (q_cnt >= MIN_COMPLETE_HOLDINGS) & (q_wsum >= MIN_COMPLETE_WEIGHT_SUM)
    ref_mask = (q_cnt >= MIN_REFERENCE_HOLDINGS) & (q_wsum >= MIN_REFERENCE_WEIGHT_SUM)
    good_groups = q[full_mask | ref_mask][["日期", "ETF代號"]]
    if good_groups.empty:
        return empty
    df = pd.merge(df.drop(columns=["_產業_tmp"], errors="ignore"), good_groups, on=["日期", "ETF代號"], how="inner")
    if df.empty:
        return empty

    latest = df["日期"].max()
    latest_df = df[df["日期"] == latest].copy()
    if latest_df.empty:
        return empty

    latest_df["產業"] = latest_df["成分股代號"].map(lambda x: _industry_of(x, industry_map))
    quality = _holding_quality(latest_df, industry_map=industry_map)
    incomplete_holdings = quality[~quality["資料狀態"].astype(str).str.match(r"^[✅🟡]", na=False)].copy() if not quality.empty else pd.DataFrame()

    hot_etfs = _weighted_hot_candidates(latest_df, momentum_df, top_n=top_n)
    focus = hot_etfs["ETF代號"].astype(str).tolist() if not hot_etfs.empty else latest_df["ETF代號"].astype(str).drop_duplicates().head(top_n).tolist()

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
            "熱門名次": int(hot_etfs.loc[hot_etfs["ETF代號"].astype(str).eq(str(etf_code)), "熱門名次"].iloc[0]) if not hot_etfs.empty and hot_etfs["ETF代號"].astype(str).eq(str(etf_code)).any() else "-",
            "前十大產業": "、".join([f"{k} {v:.1f}%" for k, v in ind_top.items()]),
            "前十大個股": "、".join([f"{r['成分股名稱']}({r['成分股代號']}) {r['權重']:.1f}%" for _, r in stock_top.iterrows()]),
            "持股數": len(sub),
            "前十集中度": round(float(stock_top["權重"].sum()), 2),
        })
    snapshot = pd.DataFrame(snap_rows)

    industries = latest_focus.groupby(["ETF代號", "產業"], dropna=False)["權重"].sum().reset_index().sort_values(["ETF代號", "權重"], ascending=[True, False])
    stocks = latest_focus[["ETF代號", "成分股代號", "成分股名稱", "產業", "權重", "持有股數"]].sort_values(["ETF代號", "權重"], ascending=[True, False])

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

        new_cols = ["ETF代號", "ETF名稱", "成分股代號", "成分股名稱", "權重", "持有股數"]
        old_cols = ["ETF代號", "成分股代號", "權重", "持有股數"]
        new_key = new_df[[c for c in new_cols if c in new_df.columns]].copy() if not new_df.empty else pd.DataFrame(columns=new_cols)
        old_key = old_df[[c for c in old_cols if c in old_df.columns]].copy() if not old_df.empty else pd.DataFrame(columns=old_cols)

        merged = pd.merge(new_key, old_key, on=["ETF代號", "成分股代號"], how="outer", suffixes=("_新", "_舊"))
        for c in ["權重_新", "權重_舊", "持有股數_新", "持有股數_舊"]:
            if c not in merged.columns:
                merged[c] = 0
            merged[c] = merged[c].fillna(0).map(_to_float)

        merged["變化"] = merged["權重_新"] - merged["權重_舊"]
        merged["股數變化"] = merged["持有股數_新"] - merged["持有股數_舊"]
        merged["股數變化率"] = np.where(merged["持有股數_舊"] > 0, merged["股數變化"] / merged["持有股數_舊"], np.nan)
        merged["最大權重"] = merged[["權重_新", "權重_舊"]].max(axis=1)

        has_share_data = (merged["持有股數_新"].abs().sum() + merged["持有股數_舊"].abs().sum()) > 0
        if has_share_data:
            significant = (
                ((merged["股數變化率"].abs() >= SIGNIFICANT_SHARE_RATIO) | ((merged["持有股數_舊"] == 0) & (merged["持有股數_新"] > 0)) | ((merged["持有股數_舊"] > 0) & (merged["持有股數_新"] == 0)))
                & (merged["最大權重"] >= SIGNIFICANT_WEIGHT_PP)
            )
            mode = "股數變化"
        else:
            significant = (merged["變化"].abs() >= SIGNIFICANT_WEIGHT_PP) & (merged["最大權重"] >= SIGNIFICANT_WEIGHT_PP)
            mode = "權重變化"

        merged["狀態"] = np.where((merged["權重_舊"] == 0) & (merged["權重_新"] > 0), "新增",
                              np.where((merged["權重_舊"] > 0) & (merged["權重_新"] == 0), "刪除",
                              np.where(merged["股數變化"] > 0 if has_share_data else merged["變化"] > 0, "加碼",
                              np.where(merged["股數變化"] < 0 if has_share_data else merged["變化"] < 0, "減碼", "持平"))))

        merged = merged[merged["狀態"].isin(["新增", "刪除", "加碼", "減碼"]) & significant].copy()
        if merged.empty:
            return merged

        merged["成分股名稱"] = merged.apply(lambda r: (name_map or {}).get(str(r["成分股代號"]), str(r.get("成分股名稱", r["成分股代號"]))), axis=1)
        merged["產業"] = merged.apply(lambda r: _industry_of(r["成分股代號"], industry_map), axis=1)
        merged["比較基準"] = f"{pd.Timestamp(prev_day).strftime('%Y-%m-%d')} → {pd.Timestamp(new_day).strftime('%Y-%m-%d')}"
        merged["事件日期"] = pd.Timestamp(new_day).strftime("%Y-%m-%d")
        merged["資料模式"] = mode
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
        # 事件表只保留近 30 天；主畫面再從其中抓最新一個事件日。
        cutoff_event = latest - pd.Timedelta(days=int(event_days))
        daily_events["_事件日_ts"] = pd.to_datetime(daily_events["事件日期"], errors="coerce")
        daily_events = daily_events[daily_events["_事件日_ts"] >= cutoff_event].drop(columns=["_事件日_ts"], errors="ignore")
        latest_event_day = str(daily_events["事件日期"].max()) if not daily_events.empty else ""
        changes = daily_events[daily_events["事件日期"].astype(str).eq(latest_event_day)].copy() if latest_event_day else pd.DataFrame()
    else:
        changes = pd.DataFrame()

    event_scope = daily_events if daily_events is not None and not daily_events.empty else changes

    if event_scope is not None and not event_scope.empty:
        # 產業變化看近 30 天事件總和，不只看最新一天，避免共同減碼被吃掉。
        industry_changes = event_scope.groupby("產業", dropna=False)["變化"].sum().reset_index().sort_values("變化", ascending=False)

        agg_map = {
            "ETF數": ("ETF代號", "nunique"),
            "涉及ETF": ("ETF代號", lambda x: "、".join(sorted(set(map(str, x))))),
            "事件數": ("ETF代號", "count"),
            "合計變化": ("變化", "sum"),
        }
        if "股數變化" in event_scope.columns:
            agg_map["合計股數變化"] = ("股數變化", "sum")
        if "資料模式" in event_scope.columns:
            agg_map["資料模式"] = ("資料模式", lambda x: "、".join(sorted(set(map(str, x)))))

        shared_actions = event_scope.groupby(["成分股代號", "成分股名稱", "產業", "狀態"], dropna=False).agg(**agg_map).reset_index()
        shared_actions = shared_actions[shared_actions["ETF數"] >= 2].copy()
        if not shared_actions.empty:
            shared_actions["_排序變化"] = shared_actions["合計變化"].abs()
            shared_actions = shared_actions.sort_values(["ETF數", "事件數", "_排序變化"], ascending=[False, False, False]).drop(columns=["_排序變化"], errors="ignore")
    else:
        shared_actions = pd.DataFrame()

    if changes is not None and not changes.empty:
        changes = changes.sort_values(["狀態", "變化"], ascending=[True, False])

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
        "hot_etfs": hot_etfs,
        "quality": quality,
        "incomplete_holdings": incomplete_holdings,
        "meta": pd.DataFrame([{
            "資料意義": "主動 ETF 經理人持股變化，不代表全市場資金流",
            "事件門檻": "|Δshares/prev_shares|≥3% 且 最大權重≥0.3pp；無股數資料時改用 |Δweight|≥0.3pp",
            "完整度門檻": f"完整：持股數≥{MIN_COMPLETE_HOLDINGS} 且 權重≥{MIN_COMPLETE_WEIGHT_SUM:.0f}%；可參考：持股數≥{MIN_REFERENCE_HOLDINGS} 且 權重≥{MIN_REFERENCE_WEIGHT_SUM:.0f}%",
            "快照保留": f"{HOLDINGS_KEEP_DAYS}天",
            "主畫面判讀": f"{lookback_days}天",
            "事件明細": f"{event_days}天",
            "追蹤ETF數": len(focus),
        }]),
    }


def build_active_etf_manager_radar(
    momentum_df: Optional[pd.DataFrame],
    industry_map: Dict[str, str],
    name_map: Dict[str, str],
    top_n: int = ACTIVE_ETF_TOP_N,
    lookback_days: int = MAIN_LOOKBACK_DAYS,
    custom_sources: Optional[Dict[str, str]] = None,
    cache_path: str = CACHE_FILE,
) -> Dict[str, object]:
    """主入口：追蹤主動 ETF 清單 → 抓持股 → 併歷史 → 產出分析。"""
    candidates = get_active_etf_candidates(momentum_df, top_n=top_n)
    cand_tuple = tuple((c["ETF代號"], c["ETF名稱"]) for c in candidates)
    latest_raw = fetch_active_etf_holdings_auto(cand_tuple, custom_sources=custom_sources, name_map=name_map)
    latest, latest_quality = _filter_complete_holdings(latest_raw, industry_map=industry_map)
    incomplete_count = 0 if latest_quality is None or latest_quality.empty else int((~latest_quality["資料狀態"].astype(str).str.match(r"^[✅🟡]", na=False)).sum())
    if latest.empty:
        hist = merge_holdings_history(pd.DataFrame(), cache_path=cache_path, max_days=HOLDINGS_KEEP_DAYS)
        summary = summarize_holdings(hist, industry_map, name_map, top_n=top_n, lookback_days=lookback_days, momentum_df=momentum_df, event_days=EVENT_LOOKBACK_DAYS)
        history_status = get_history_status(hist, lookback_days=lookback_days)
        if hist is not None and not hist.empty and summary.get("snapshot", pd.DataFrame()).empty is False:
            return {
                "ok": True,
                "message": f"今日自動來源未取得完整快照；已沿用 GitHub / 本機最近成功快照。自動來源不完整 {incomplete_count} 檔。",
                "candidates": pd.DataFrame(candidates),
                "holdings": hist,
                "summary": summary,
                "history_status": history_status,
            }
        return {
            "ok": False,
            "message": f"自動持股來源目前沒有完整資料，且沒有可沿用的歷史快照；請使用 CSV 備援。自動來源不完整 {incomplete_count} 檔。",
            "candidates": pd.DataFrame(candidates),
            "holdings": pd.DataFrame(),
            "summary": summarize_holdings(pd.DataFrame(), industry_map, name_map, top_n=top_n, lookback_days=lookback_days, momentum_df=momentum_df, event_days=EVENT_LOOKBACK_DAYS),
            "history_status": history_status,
        }
    hist = merge_holdings_history(latest, cache_path=cache_path, max_days=HOLDINGS_KEEP_DAYS)
    summary = summarize_holdings(hist, industry_map, name_map, top_n=top_n, lookback_days=lookback_days, momentum_df=momentum_df, event_days=EVENT_LOOKBACK_DAYS)
    history_status = get_history_status(hist, lookback_days=lookback_days)
    return {
        "ok": True,
        "message": f"已自動更新 {latest['ETF代號'].nunique()} 檔完整主動 ETF 持股；不完整 {incomplete_count} 檔已排除，不寫入歷史庫。",
        "candidates": pd.DataFrame(candidates),
        "holdings": hist,
        "summary": summary,
        "history_status": history_status,
    }
