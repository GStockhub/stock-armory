"""chips_provider.py

法人籌碼多來源防斷線引擎
------------------------
流程：
1. TWSE T86（上市）
2. FinMind 籌碼資料（上市櫃）
3. TPEX 櫃買中心三大法人買賣明細（上櫃）
4. GitHub / 本機最近成功快取
5. 仍失敗：回傳空 dict，前端可讓 S/A/B 技術面備援照跑

輸出格式：dict[YYYYMMDD] = DataFrame
欄位：代號、名稱、外資(張)、投信(張)、自營(張)、三大法人合計
"""
from __future__ import annotations

import base64
import io
import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import streamlit as st
except Exception:
    st = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CHIP_COLUMNS = ["日期", "代號", "名稱", "外資(張)", "投信(張)", "自營(張)", "三大法人合計"]
API_ROOT = "https://api.github.com"
DEFAULT_CHIPS_HISTORY_PATH = "data/chips_history.csv"
LOCAL_CACHE = os.environ.get("CHIPS_HISTORY_LOCAL", ".chips_cache/chips_history.csv")
TMP_CACHE = os.environ.get("CHIPS_HISTORY_TMP", "/tmp/stock_armory_chips_history.csv")
SESSION_KEY = "_stock_armory_chips_history_df"


def _maybe_cache_data(ttl=1800, show_spinner=False):
    def deco(fn):
        if st is not None:
            return st.cache_data(ttl=ttl, show_spinner=show_spinner)(fn)
        return fn
    return deco


def _get_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET", "HEAD", "OPTIONS"])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    })
    return s


def _num(s) -> pd.Series:
    return pd.to_numeric(pd.Series(s).astype(str).str.replace(",", "", regex=False).str.replace("--", "0", regex=False), errors="coerce").fillna(0)


def _clean_code(v) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(v or "").strip().upper())


def _normalize_chips_df(df: pd.DataFrame, date_str: str = "") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=CHIP_COLUMNS)
    out = df.copy()
    for c in ["代號", "名稱"]:
        if c not in out.columns:
            out[c] = ""
    for c in ["外資(張)", "投信(張)", "自營(張)", "三大法人合計"]:
        if c not in out.columns:
            out[c] = 0.0
    out["代號"] = out["代號"].map(_clean_code)
    out["名稱"] = out["名稱"].astype(str).str.strip()
    for c in ["外資(張)", "投信(張)", "自營(張)", "三大法人合計"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    if "三大法人合計" not in df.columns or out["三大法人合計"].abs().sum() == 0:
        out["三大法人合計"] = out["外資(張)"] + out["投信(張)"] + out["自營(張)"]
    out = out[(out["代號"] != "") & (~out["代號"].str.startswith("00"))].copy()
    out = out.drop_duplicates(subset=["代號"], keep="last")
    if date_str:
        out["日期"] = date_str
    elif "日期" not in out.columns:
        out["日期"] = ""
    return out[CHIP_COLUMNS].reset_index(drop=True)


def _history_to_dict(history: pd.DataFrame, max_days: int = 5) -> Dict[str, pd.DataFrame]:
    if history is None or history.empty:
        return {}
    h = normalize_chips_history(history, max_days=max_days)
    if h.empty:
        return {}
    result: Dict[str, pd.DataFrame] = {}
    for d, sub in h.groupby("日期"):
        key = pd.to_datetime(d, errors="coerce")
        if pd.isna(key):
            continue
        d_str = key.strftime("%Y%m%d")
        result[d_str] = sub[["代號", "名稱", "外資(張)", "投信(張)", "自營(張)", "三大法人合計"]].reset_index(drop=True)
    return dict(sorted(result.items(), reverse=True)[:max_days])


def normalize_chips_history(df: pd.DataFrame, max_days: int = 30) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=CHIP_COLUMNS)
    out = df.copy()
    out.columns = [str(c).replace("\ufeff", "").strip() for c in out.columns]
    for c in CHIP_COLUMNS:
        if c not in out.columns:
            out[c] = "" if c in ["日期", "代號", "名稱"] else 0.0
    out = out[CHIP_COLUMNS].copy()
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce").dt.normalize()
    out["代號"] = out["代號"].map(_clean_code)
    out["名稱"] = out["名稱"].astype(str).str.strip()
    for c in ["外資(張)", "投信(張)", "自營(張)", "三大法人合計"]:
        out[c] = pd.to_numeric(out[c].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
    out = out.dropna(subset=["日期"])
    out = out[(out["代號"] != "") & (~out["代號"].str.startswith("00"))].copy()
    out = out.drop_duplicates(subset=["日期", "代號"], keep="last")
    if out.empty:
        return pd.DataFrame(columns=CHIP_COLUMNS)
    dates = sorted(out["日期"].unique())[-max_days:]
    out = out[out["日期"].isin(dates)].sort_values(["日期", "代號"]).reset_index(drop=True)
    out["日期"] = out["日期"].dt.strftime("%Y-%m-%d")
    return out


# -----------------------------
# GitHub chips history
# -----------------------------

def _get_github_config() -> dict:
    if st is None:
        return {}
    try:
        return {
            "token": str(st.secrets.get("github_token", "")).strip(),
            "repo": str(st.secrets.get("github_repo", "")).strip(),
            "branch": str(st.secrets.get("github_branch", "main")).strip() or "main",
            "path": str(st.secrets.get("github_chips_history_path", DEFAULT_CHIPS_HISTORY_PATH)).strip() or DEFAULT_CHIPS_HISTORY_PATH,
        }
    except Exception:
        return {}


def _gh_ready(cfg: dict) -> bool:
    return bool(cfg.get("token") and cfg.get("repo") and cfg.get("branch") and cfg.get("path"))


def _gh_headers(cfg: dict) -> dict:
    return {
        "Authorization": f"Bearer {cfg.get('token','')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "stock-armory-streamlit",
    }


def _gh_url(cfg: dict) -> str:
    return f"{API_ROOT}/repos/{cfg.get('repo')}/contents/{cfg.get('path')}"


def read_github_chips_history() -> Tuple[pd.DataFrame, dict]:
    cfg = _get_github_config()
    diag = {"ok": False, "message": "GitHub chips history 未設定", "repo": cfg.get("repo"), "branch": cfg.get("branch"), "path": cfg.get("path"), "status_code": None}
    if not _gh_ready(cfg):
        return pd.DataFrame(columns=CHIP_COLUMNS), diag
    try:
        r = requests.get(_gh_url(cfg), headers=_gh_headers(cfg), params={"ref": cfg.get("branch")}, timeout=18)
        diag["status_code"] = r.status_code
        if r.status_code == 404:
            diag["message"] = "GitHub chips_history.csv 不存在；下次寫入會嘗試建立。"
            return pd.DataFrame(columns=CHIP_COLUMNS), diag
        if r.status_code >= 400:
            diag["message"] = f"GitHub chips 讀取失敗：HTTP {r.status_code} {r.text[:160]}"
            return pd.DataFrame(columns=CHIP_COLUMNS), diag
        payload = r.json()
        raw = base64.b64decode(payload.get("content", "")).decode("utf-8-sig")
        df = pd.read_csv(io.StringIO(raw), dtype=str)
        norm = normalize_chips_history(df, max_days=60)
        diag.update({"ok": True, "message": f"GitHub chips 讀取成功：{len(norm):,} 筆", "sha": payload.get("sha")})
        return norm, diag
    except Exception as e:
        diag["message"] = f"GitHub chips 讀取例外：{type(e).__name__}: {e}"
        return pd.DataFrame(columns=CHIP_COLUMNS), diag


def write_github_chips_history(df: pd.DataFrame, commit_message: Optional[str] = None) -> dict:
    cfg = _get_github_config()
    diag = {"ok": False, "message": "GitHub chips history 未設定，略過寫入", "repo": cfg.get("repo"), "branch": cfg.get("branch"), "path": cfg.get("path"), "status_code": None}
    if not _gh_ready(cfg):
        return diag
    norm = normalize_chips_history(df, max_days=60)
    if norm.empty:
        diag["message"] = "沒有可寫入的法人籌碼資料。"
        return diag
    csv_text = norm.to_csv(index=False, encoding="utf-8-sig", lineterminator="\n")
    encoded = base64.b64encode(csv_text.encode("utf-8-sig")).decode("utf-8")
    sha = None
    try:
        get_r = requests.get(_gh_url(cfg), headers=_gh_headers(cfg), params={"ref": cfg.get("branch")}, timeout=18)
        diag["status_code"] = get_r.status_code
        if get_r.status_code == 200:
            payload = get_r.json()
            sha = payload.get("sha")
            old = payload.get("content", "")
            if old:
                try:
                    old_text = base64.b64decode(old).decode("utf-8-sig")
                    if old_text.strip() == csv_text.strip():
                        diag.update({"ok": True, "message": "GitHub chips_history.csv 無變化，略過 commit。", "status_code": 200})
                        return diag
                except Exception:
                    pass
        elif get_r.status_code == 404:
            sha = None
        else:
            diag["message"] = f"GitHub chips 寫入前讀取失敗：HTTP {get_r.status_code} {get_r.text[:160]}"
            return diag
        body = {"message": commit_message or f"Update chips history {datetime.now().strftime('%Y-%m-%d %H:%M')}", "content": encoded, "branch": cfg.get("branch")}
        if sha:
            body["sha"] = sha
        put_r = requests.put(_gh_url(cfg), headers=_gh_headers(cfg), json=body, timeout=25)
        diag["status_code"] = put_r.status_code
        if put_r.status_code in (200, 201):
            diag.update({"ok": True, "message": f"GitHub chips_history.csv 已{'建立' if put_r.status_code == 201 else '更新'}：{len(norm):,} 筆"})
        else:
            diag["message"] = f"GitHub chips 寫入失敗：HTTP {put_r.status_code} {put_r.text[:220]}"
        return diag
    except Exception as e:
        diag["message"] = f"GitHub chips 寫入例外：{type(e).__name__}: {e}"
        return diag


def _read_local_history() -> pd.DataFrame:
    frames = []
    if st is not None:
        try:
            sess = st.session_state.get(SESSION_KEY)
            if isinstance(sess, pd.DataFrame) and not sess.empty:
                frames.append(sess)
        except Exception:
            pass
    for p in [LOCAL_CACHE, TMP_CACHE]:
        try:
            if os.path.exists(p):
                frames.append(pd.read_csv(p, dtype=str))
        except Exception:
            pass
    if not frames:
        return pd.DataFrame(columns=CHIP_COLUMNS)
    return normalize_chips_history(pd.concat(frames, ignore_index=True), max_days=60)


def _write_local_history(df: pd.DataFrame) -> None:
    norm = normalize_chips_history(df, max_days=60)
    if norm.empty:
        return
    if st is not None:
        try:
            st.session_state[SESSION_KEY] = norm.copy()
        except Exception:
            pass
    for p in [LOCAL_CACHE, TMP_CACHE]:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            norm.to_csv(p, index=False, encoding="utf-8-sig")
        except Exception:
            pass


def sync_chips_history(new_history: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    frames = []
    remote, rdiag = read_github_chips_history()
    local = _read_local_history()
    for f in [remote, local, new_history]:
        if f is not None and not f.empty:
            frames.append(f)
    if not frames:
        return pd.DataFrame(columns=CHIP_COLUMNS), rdiag
    merged = normalize_chips_history(pd.concat(frames, ignore_index=True), max_days=60)
    _write_local_history(merged)
    wdiag = write_github_chips_history(merged)
    diag = {"ok": bool(rdiag.get("ok") or wdiag.get("ok")), "read": rdiag, "write": wdiag, "message": wdiag.get("message") or rdiag.get("message"), "days": int(pd.to_datetime(merged["日期"], errors="coerce").nunique())}
    return merged, diag


# -----------------------------
# Sources
# -----------------------------

def fetch_twse_t86(date_yyyymmdd: str, session: Optional[requests.Session] = None) -> pd.DataFrame:
    session = session or _get_session()
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_yyyymmdd}&selectType=ALLBUT0999&response=json"
    r = session.get(url, timeout=20, verify=False)
    if r.status_code != 200:
        return pd.DataFrame()
    try:
        res = r.json()
    except Exception:
        return pd.DataFrame()
    if res.get("stat") != "OK" or not res.get("data") or not res.get("fields"):
        return pd.DataFrame()
    df = pd.DataFrame(res["data"], columns=res["fields"])
    if df.empty:
        return pd.DataFrame()
    code_col = next((c for c in df.columns if "代號" in str(c)), None)
    name_col = next((c for c in df.columns if "名稱" in str(c)), code_col)
    if not code_col:
        return pd.DataFrame()
    trust_cols = [c for c in df.columns if "投信" in str(c) and "買賣超" in str(c)]
    foreign_cols = [c for c in df.columns if "外資" in str(c) and "買賣超" in str(c)]
    dealer_cols = [c for c in df.columns if "自營" in str(c) and "買賣超" in str(c)]
    clean = pd.DataFrame()
    clean["代號"] = df[code_col].astype(str).str.strip()
    clean["名稱"] = df[name_col].astype(str).str.strip()
    clean["投信(張)"] = sum((_num(df[c]) for c in trust_cols), start=pd.Series([0]*len(df))) / 1000 if trust_cols else 0
    clean["外資(張)"] = sum((_num(df[c]) for c in foreign_cols), start=pd.Series([0]*len(df))) / 1000 if foreign_cols else 0
    clean["自營(張)"] = sum((_num(df[c]) for c in dealer_cols), start=pd.Series([0]*len(df))) / 1000 if dealer_cols else 0
    clean["三大法人合計"] = clean["投信(張)"] + clean["外資(張)"] + clean["自營(張)"]
    return _normalize_chips_df(clean, pd.to_datetime(date_yyyymmdd).strftime("%Y-%m-%d"))


def fetch_finmind_chips(date_iso: str, fm_token: Optional[str] = None, session: Optional[requests.Session] = None) -> pd.DataFrame:
    session = session or _get_session()
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "start_date": date_iso, "end_date": date_iso}
    if fm_token and str(fm_token).strip():
        params["token"] = str(fm_token).strip()
    r = session.get(url, params=params, timeout=24, verify=False)
    if r.status_code != 200:
        return pd.DataFrame()
    try:
        res = r.json()
    except Exception:
        return pd.DataFrame()
    if res.get("msg") != "success" or not res.get("data"):
        return pd.DataFrame()
    df = pd.DataFrame(res["data"])
    if df.empty or not {"stock_id", "name", "buy", "sell"}.issubset(df.columns):
        return pd.DataFrame()
    df["buy"] = pd.to_numeric(df["buy"], errors="coerce").fillna(0)
    df["sell"] = pd.to_numeric(df["sell"], errors="coerce").fillna(0)
    df["net"] = (df["buy"] - df["sell"]) / 1000
    pivot = df.pivot_table(index="stock_id", columns="name", values="net", aggfunc="sum").fillna(0)
    clean = pd.DataFrame({"代號": pivot.index.astype(str), "名稱": pivot.index.astype(str)})
    def pick(keys):
        cols = []
        for c in pivot.columns:
            cs = str(c).lower()
            if any(k.lower() in cs for k in keys):
                cols.append(c)
        return cols
    trust_cols = pick(["Investment_Trust", "投信"])
    foreign_cols = pick(["Foreign", "外資"])
    dealer_cols = pick(["Dealer", "自營"])
    clean["投信(張)"] = pivot[trust_cols].sum(axis=1).values if trust_cols else 0
    clean["外資(張)"] = pivot[foreign_cols].sum(axis=1).values if foreign_cols else 0
    clean["自營(張)"] = pivot[dealer_cols].sum(axis=1).values if dealer_cols else 0
    clean["三大法人合計"] = clean["投信(張)"] + clean["外資(張)"] + clean["自營(張)"]
    return _normalize_chips_df(clean, date_iso)


def _roc_date(dt: datetime) -> str:
    return f"{dt.year - 1911}/{dt.month:02d}/{dt.day:02d}"


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = ["".join([str(x) for x in tup if str(x) != "nan"]).replace(" ", "") for tup in out.columns]
    else:
        out.columns = [str(c).replace("\n", "").replace(" ", "") for c in out.columns]
    return out


def fetch_tpex_chips(dt: datetime, session: Optional[requests.Session] = None) -> pd.DataFrame:
    session = session or _get_session()
    roc = _roc_date(dt)
    urls = [
        f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?d={roc}&l=zh-tw&o=htm&s=0&se=EW&t=D",
        f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?d={roc}&l=zh-tw&o=csv&s=0&se=EW&t=D",
    ]
    for url in urls:
        try:
            r = session.get(url, timeout=24, verify=False)
            if r.status_code != 200 or not r.text.strip():
                continue
            tables = pd.read_html(io.StringIO(r.text))
            if not tables:
                continue
            df = _flatten_columns(tables[0])
            code_col = next((c for c in df.columns if "代號" in str(c)), None)
            name_col = next((c for c in df.columns if "名稱" in str(c)), code_col)
            if not code_col:
                continue
            clean = pd.DataFrame()
            clean["代號"] = df[code_col].astype(str).str.strip()
            clean["名稱"] = df[name_col].astype(str).str.strip()
            cols = list(df.columns)
            foreign_candidates = [c for c in cols if "外資及陸資" in str(c) and "買賣超" in str(c)]
            trust_candidates = [c for c in cols if "投信" in str(c) and "買賣超" in str(c)]
            dealer_candidates = [c for c in cols if "自營商" in str(c) and "買賣超" in str(c) and "三大法人" not in str(c)]
            total_candidates = [c for c in cols if "三大法人" in str(c) and "買賣超" in str(c)]
            clean["外資(張)"] = _num(df[foreign_candidates[-1]]) / 1000 if foreign_candidates else 0
            clean["投信(張)"] = _num(df[trust_candidates[-1]]) / 1000 if trust_candidates else 0
            clean["自營(張)"] = _num(df[dealer_candidates[-1]]) / 1000 if dealer_candidates else 0
            clean["三大法人合計"] = _num(df[total_candidates[-1]]) / 1000 if total_candidates else clean["外資(張)"] + clean["投信(張)"] + clean["自營(張)"]
            norm = _normalize_chips_df(clean, dt.strftime("%Y-%m-%d"))
            if not norm.empty:
                return norm
        except Exception:
            continue
    return pd.DataFrame()


def _merge_day_sources(frames: List[pd.DataFrame], date_iso: str) -> pd.DataFrame:
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=CHIP_COLUMNS)
    merged = pd.concat(frames, ignore_index=True)
    # 優先以後面來源補足同代號；若上市/上櫃都抓到同代號，保留最後一筆通常也可接受。
    merged = merged.drop_duplicates(subset=["日期", "代號"], keep="last")
    return _normalize_chips_df(merged, date_iso)


@_maybe_cache_data(ttl=1800, show_spinner=False)
def safe_fetch_chips(fm_token: Optional[str] = None, days: int = 5, max_lookback_days: int = 35) -> Dict[str, pd.DataFrame]:
    session = _get_session()
    fetched_days: List[pd.DataFrame] = []
    result: Dict[str, pd.DataFrame] = {}
    ptr = datetime.now()
    attempts = 0
    while len(result) < days and attempts < max_lookback_days:
        if ptr.weekday() < 5:
            date_iso = ptr.strftime("%Y-%m-%d")
            date_yyyymmdd = ptr.strftime("%Y%m%d")
            day_frames = []
            try:
                twse = fetch_twse_t86(date_yyyymmdd, session=session)
                if not twse.empty:
                    day_frames.append(twse)
            except Exception as e:
                print(f"TWSE T86 failed {date_yyyymmdd}: {e}")
            try:
                finmind = fetch_finmind_chips(date_iso, fm_token=fm_token, session=session)
                if not finmind.empty:
                    day_frames.append(finmind)
            except Exception as e:
                print(f"FinMind chips failed {date_iso}: {e}")
            try:
                tpex = fetch_tpex_chips(ptr, session=session)
                if not tpex.empty:
                    day_frames.append(tpex)
            except Exception as e:
                print(f"TPEX chips failed {date_iso}: {e}")
            day_df = _merge_day_sources(day_frames, date_iso)
            if not day_df.empty:
                result[date_yyyymmdd] = day_df[["代號", "名稱", "外資(張)", "投信(張)", "自營(張)", "三大法人合計"]].reset_index(drop=True)
                fetched_days.append(day_df)
                time.sleep(0.2)
            else:
                time.sleep(0.45)
        ptr -= timedelta(days=1)
        attempts += 1

    if fetched_days:
        new_history = normalize_chips_history(pd.concat(fetched_days, ignore_index=True), max_days=60)
        history, diag = sync_chips_history(new_history)
        if st is not None:
            try:
                st.session_state["chips_history_diag"] = diag
                st.session_state["chips_data_source"] = "即時+快取"
            except Exception:
                pass
        # 以合併後歷史回填，確保最多有 days 日。
        hist_dict = _history_to_dict(history, max_days=days)
        return hist_dict or result

    # 所有即時來源失敗，先讀 GitHub / 本機快取。
    remote, rdiag = read_github_chips_history()
    local = _read_local_history()
    frames = [f for f in [remote, local] if f is not None and not f.empty]
    if frames:
        history = normalize_chips_history(pd.concat(frames, ignore_index=True), max_days=60)
        if st is not None:
            try:
                st.session_state["chips_history_diag"] = {"ok": True, "message": "即時籌碼失敗，已沿用最近成功快取。", "read": rdiag, "days": int(pd.to_datetime(history["日期"], errors="coerce").nunique())}
                st.session_state["chips_data_source"] = "最近成功快取"
            except Exception:
                pass
        return _history_to_dict(history, max_days=days)

    if st is not None:
        try:
            st.session_state["chips_history_diag"] = {"ok": False, "message": "即時籌碼與快取皆不可用。", "read": rdiag, "days": 0}
            st.session_state["chips_data_source"] = "暫缺"
        except Exception:
            pass
    return {}
