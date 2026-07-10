"""signal_tracker.py

V37 訊號追蹤室
---------------
目的：
- 取代原本較少使用的回測室。
- 第一階段只保存系統實際產出的 S/A/B 候選，不再混入產業輪動、主動 ETF 或手動觀察。
- 保存當下自動補一份沙盤體檢結果，檢查「原始訊號 + 沙盤通過」的命中率。
- 後續用隔日 / 3 日 / 5 日結果檢查最近訊號品質。
- 採「滾動保存」：明細預設只留 180 天，避免 CSV 與 GitHub 變肥。
"""
from __future__ import annotations

import base64
import io
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st

from data_center import safe_download
from quant_engine import run_sandbox_sim


SIGNAL_COLUMNS = [
    "日期", "類型", "代號", "名稱", "評級", "分數", "產業", "狀態", "來源摘要",
    "基準價",
    "沙盤狀態", "沙盤等級", "沙盤建議", "沙盤現價", "沙盤M5", "沙盤M10", "沙盤乖離", "沙盤勝率", "沙盤停損價", "沙盤檢查時間",
    "樣本代號", "隔日漲跌%", "3日最高漲幅%", "5日最高漲幅%",
    "是否達標", "是否失敗", "模式", "大盤分數", "更新時間",
]

TRACKED_SIGNAL_TYPES = ["S級", "A級", "B級"]

DEFAULT_SIGNAL_PATH = "data/signal_history.csv"
LOCAL_SIGNAL_PATH = "signal_history.csv"
TMP_SIGNAL_PATH = "/tmp/stock_armory_signal_history.csv"


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_code(v) -> str:
    return "".join(ch for ch in str(v or "").strip().upper() if ch.isalnum())


def _to_float(v, default=0.0) -> float:
    try:
        if pd.isna(v):
            return default
        s = str(v).replace(",", "").replace("%", "").strip()
        return float(s) if s not in ["", "nan", "None"] else default
    except Exception:
        return default


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(columns=SIGNAL_COLUMNS)


def normalize_signal_history(df: pd.DataFrame, keep_days: int = 180) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_history()
    out = df.copy()
    out.columns = [str(c).replace("\ufeff", "").strip() for c in out.columns]
    for c in SIGNAL_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out = out[SIGNAL_COLUMNS].copy()
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out[out["日期"].notna() & (out["日期"] != "NaT")].copy()
    if keep_days:
        cutoff = (datetime.now() - timedelta(days=int(keep_days))).strftime("%Y-%m-%d")
        out = out[out["日期"] >= cutoff].copy()
    for c in ["分數", "基準價", "沙盤現價", "沙盤M5", "沙盤M10", "沙盤乖離", "沙盤勝率", "沙盤停損價", "隔日漲跌%", "3日最高漲幅%", "5日最高漲幅%", "大盤分數"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    # 資料瘦身：去除 float32 精度雜訊（63.70000076...），CSV 更小、git diff 更乾淨。
    for c in ["基準價", "沙盤現價", "沙盤M5", "沙盤M10", "沙盤停損價"]:
        out[c] = out[c].round(2)
    for c in ["分數", "沙盤乖離", "沙盤勝率", "隔日漲跌%", "3日最高漲幅%", "5日最高漲幅%", "大盤分數"]:
        out[c] = out[c].round(2)
    for c in ["類型", "代號", "名稱", "評級", "產業", "狀態", "來源摘要", "沙盤狀態", "沙盤等級", "沙盤建議", "沙盤檢查時間", "樣本代號", "是否達標", "是否失敗", "模式", "更新時間"]:
        out[c] = out[c].astype(str).replace("nan", "")
    out["代號"] = out["代號"].map(_clean_code)
    out = out.drop_duplicates(subset=["日期", "類型", "代號", "名稱"], keep="last")
    return out.sort_values(["日期", "類型", "分數"], ascending=[False, True, False], na_position="last").reset_index(drop=True)


def _github_cfg() -> Dict[str, str]:
    try:
        return {
            "token": str(st.secrets.get("github_token", "")).strip(),
            "repo": str(st.secrets.get("github_repo", "")).strip(),
            "branch": str(st.secrets.get("github_branch", "main")).strip() or "main",
            "path": str(st.secrets.get("github_signal_history_path", DEFAULT_SIGNAL_PATH)).strip() or DEFAULT_SIGNAL_PATH,
        }
    except Exception:
        return {"token": "", "repo": "", "branch": "main", "path": DEFAULT_SIGNAL_PATH}


def _gh_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "stock-armory-signal-tracker",
    }


def _read_from_github() -> Tuple[pd.DataFrame, str]:
    cfg = _github_cfg()
    if not (cfg["token"] and cfg["repo"] and cfg["path"]):
        return _empty_history(), "GitHub 未設定，使用本機 / session 紀錄。"
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{cfg['path']}"
    try:
        resp = requests.get(url, headers=_gh_headers(cfg["token"]), params={"ref": cfg["branch"]}, timeout=15)
        if resp.status_code == 404:
            return _empty_history(), "GitHub 尚無 signal_history.csv，第一次儲存會建立。"
        resp.raise_for_status()
        data = resp.json()
        raw = base64.b64decode(data.get("content", "")).decode("utf-8-sig")
        return normalize_signal_history(pd.read_csv(io.StringIO(raw))), f"已讀取 GitHub：{cfg['path']}"
    except Exception as e:
        return _empty_history(), f"GitHub 讀取失敗，改用本機紀錄：{e}"


def _save_to_github(df: pd.DataFrame) -> str:
    cfg = _github_cfg()
    if not (cfg["token"] and cfg["repo"] and cfg["path"]):
        return "GitHub 未設定，已只保存本機 / session。"
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{cfg['path']}"
    headers = _gh_headers(cfg["token"])
    content = df.to_csv(index=False, encoding="utf-8-sig")
    encoded = base64.b64encode(content.encode("utf-8-sig")).decode("utf-8")
    sha = None
    try:
        get_resp = requests.get(url, headers=headers, params={"ref": cfg["branch"]}, timeout=15)
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")
        elif get_resp.status_code != 404:
            get_resp.raise_for_status()
        payload = {
            "message": f"Update signal history {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": encoded,
            "branch": cfg["branch"],
        }
        if sha:
            payload["sha"] = sha
        put_resp = requests.put(url, headers=headers, json=payload, timeout=20)
        put_resp.raise_for_status()
        return f"GitHub 已同步：{cfg['path']}"
    except Exception as e:
        return f"GitHub 同步失敗，已保留本機 / session：{e}"


def load_signal_history() -> Tuple[pd.DataFrame, str]:
    if "_signal_history_df" in st.session_state:
        return normalize_signal_history(st.session_state["_signal_history_df"]), "已讀取 session 訊號紀錄。"
    gh_df, msg = _read_from_github()
    if not gh_df.empty:
        st.session_state["_signal_history_df"] = gh_df.copy()
        return gh_df, msg
    for path in [LOCAL_SIGNAL_PATH, TMP_SIGNAL_PATH]:
        try:
            if os.path.exists(path):
                df = normalize_signal_history(pd.read_csv(path))
                st.session_state["_signal_history_df"] = df.copy()
                return df, f"已讀取本機：{path}"
        except Exception:
            pass
    return _empty_history(), msg


def save_signal_history(df: pd.DataFrame) -> str:
    df = normalize_signal_history(df)
    st.session_state["_signal_history_df"] = df.copy()
    msgs = []
    for path in [LOCAL_SIGNAL_PATH, TMP_SIGNAL_PATH]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
            df.to_csv(path, index=False, encoding="utf-8-sig")
            msgs.append(f"本機已保存：{path}")
        except Exception:
            pass
    msgs.append(_save_to_github(df))
    return "；".join(msgs)


def _pick(row: pd.Series, keys: List[str], default=""):
    for k in keys:
        if k in row.index:
            v = row.get(k)
            if pd.notna(v) and str(v).strip() != "":
                return v
    return default


def _rows_from_signal_df(df: pd.DataFrame, signal_type: str, limit: int) -> List[Dict]:
    rows = []
    if df is None or df.empty or "代號" not in df.columns:
        return rows
    src = df.head(limit).copy()
    for _, r in src.iterrows():
        code = _clean_code(_pick(r, ["代號", "股票代號"]))
        if not code:
            continue
        grade = str(_pick(r, ["評級", "等級"], signal_type)).replace("級", "")
        score = _to_float(_pick(r, ["Quant_Score", "安全指數", "分數"], np.nan), np.nan)
        price = _to_float(_pick(r, ["現價", "市價", "Close"], np.nan), np.nan)
        rows.append({
            "日期": _today_str(),
            "類型": signal_type,
            "代號": code,
            "名稱": str(_pick(r, ["名稱", "股票名稱"], "")),
            "評級": grade,
            "分數": score,
            "產業": str(_pick(r, ["產業"], "")),
            "狀態": str(_pick(r, ["生命週期", "決策標籤", "狀態"], "")),
            "來源摘要": str(_pick(r, ["戰術型態", "建議", "法人狀態"], ""))[:120],
            "基準價": price,
            "樣本代號": "",
            "隔日漲跌%": np.nan,
            "3日最高漲幅%": np.nan,
            "5日最高漲幅%": np.nan,
            "是否達標": "",
            "是否失敗": "",
            "更新時間": _now_str(),
        })
    return rows


def _sandbox_assessment(res: Optional[dict]) -> Dict[str, object]:
    """把沙盤結果壓成可追蹤欄位。這不是交易紀錄，只是系統候選的第二道體檢。"""
    if not res:
        return {
            "沙盤狀態": "未取得",
            "沙盤等級": "資料不足",
            "沙盤建議": "沙盤資料不足，暫不納入通過樣本。",
            "沙盤現價": np.nan,
            "沙盤M5": np.nan,
            "沙盤M10": np.nan,
            "沙盤乖離": np.nan,
            "沙盤勝率": np.nan,
            "沙盤停損價": np.nan,
            "沙盤檢查時間": _now_str(),
        }
    p_now = _to_float(res.get("現價", np.nan), np.nan)
    m5 = _to_float(res.get("M5", np.nan), np.nan)
    m10 = _to_float(res.get("M10", np.nan), np.nan)
    bias = _to_float(res.get("乖離", np.nan), np.nan)
    win_rate = _to_float(res.get("勝率", np.nan), np.nan)
    stop_price = _to_float(res.get("停損價", np.nan), np.nan)

    if pd.isna(p_now) or pd.isna(m5) or pd.isna(m10):
        status, level, advice = "未取得", "資料不足", "沙盤資料不足，暫不納入通過樣本。"
    elif p_now < m10:
        status, level, advice = "不通過", "跌破M10", "短線結構轉弱；系統候選先觀察，不列入沙盤通過。"
    elif p_now < m5:
        status, level, advice = "觀察", "等站回M5", "未站回 M5，等 13:00 後或隔日站回再看。"
    elif pd.notna(bias) and bias > 7:
        status, level, advice = "觀察", "乖離偏高", "結構偏強但追高風險高；等回踩 M5 或隔日不跳空。"
    elif pd.notna(win_rate) and win_rate >= 50:
        status, level, advice = "通過", "結構合格", "S/A/B 候選通過沙盤第二道體檢，可納入後續命中率追蹤。"
    else:
        status, level, advice = "觀察", "勝率普通", "站上均線但歷史勝率普通；可追蹤，不視為高把握通過。"

    return {
        "沙盤狀態": status,
        "沙盤等級": level,
        "沙盤建議": advice,
        "沙盤現價": p_now,
        "沙盤M5": m5,
        "沙盤M10": m10,
        "沙盤乖離": bias,
        "沙盤勝率": win_rate,
        "沙盤停損價": stop_price,
        "沙盤檢查時間": _now_str(),
    }


def _attach_sandbox_to_rows(rows: List[Dict], twse_name_map: Optional[Dict[str, str]], fm_token: str) -> List[Dict]:
    twse_name_map = twse_name_map or {}
    enriched = []
    for row in rows:
        code = _clean_code(row.get("代號", ""))
        res = None
        if code:
            try:
                res = run_sandbox_sim(code, twse_name_map, fm_token)
            except Exception:
                res = None
        row.update(_sandbox_assessment(res))
        enriched.append(row)
    return enriched


def _current_signal_rows(twse_ind_map: Dict[str, str], twse_name_map: Optional[Dict[str, str]], fm_token: str, macro_score, overheat_flag, operation_mode) -> pd.DataFrame:
    rows = []

    # 第一階段只追蹤系統自動產出的 S/A/B 候選。
    # 不再把產業輪動、主動 ETF、特殊關注、手動觀察混進同一張命中率表，避免樣本污染。
    master = st.session_state.get("eod_master_list", pd.DataFrame())
    if isinstance(master, pd.DataFrame) and not master.empty and "評級" in master.columns:
        for grade in ["S", "A", "B"]:
            part = master[master["評級"].astype(str).str.replace("級", "", regex=False).eq(grade)].copy()
            rows.extend(_rows_from_signal_df(part, f"{grade}級", 10))

    rows = _attach_sandbox_to_rows(rows, twse_name_map, fm_token)
    out = pd.DataFrame(rows)
    if not out.empty:
        out["模式"] = str(operation_mode or "")
        try:
            out["大盤分數"] = float(macro_score)
        except Exception:
            out["大盤分數"] = np.nan
    return normalize_signal_history(out, keep_days=9999)

def _calc_returns_for_code(code: str, base_date: str, base_price: float, fm_token: str) -> Tuple[float, float, float]:
    code = _clean_code(code)
    base_price = _to_float(base_price, np.nan)
    if not code or pd.isna(base_price) or base_price <= 0:
        return np.nan, np.nan, np.nan
    df = safe_download(code, fm_token=fm_token, period="45d", min_bars=5)
    if df is None or df.empty or "Close" not in df.columns:
        return np.nan, np.nan, np.nan
    px = df.copy()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    px = px.sort_index()
    d0 = pd.to_datetime(base_date)
    future = px[px.index > d0].copy()
    if future.empty:
        return np.nan, np.nan, np.nan
    close = pd.to_numeric(future["Close"], errors="coerce").dropna()
    high = pd.to_numeric(future["High"], errors="coerce").dropna() if "High" in future.columns else close
    if close.empty:
        return np.nan, np.nan, np.nan
    day1 = (float(close.iloc[0]) / base_price - 1) * 100 if len(close) >= 1 else np.nan
    high3 = (float(high.head(3).max()) / base_price - 1) * 100 if len(high) >= 1 else np.nan
    high5 = (float(high.head(5).max()) / base_price - 1) * 100 if len(high) >= 1 else np.nan
    return round(day1, 2), round(high3, 2), round(high5, 2)


def _calc_returns_for_industry(codes_text: str, base_date: str, fm_token: str) -> Tuple[float, float, float]:
    codes = [_clean_code(x) for x in str(codes_text or "").split(",") if _clean_code(x)]
    vals = []
    for code in codes[:10]:
        df = safe_download(code, fm_token=fm_token, period="45d", min_bars=5)
        if df is None or df.empty or "Close" not in df.columns:
            continue
        px = df.copy()
        px.index = pd.to_datetime(px.index).tz_localize(None)
        px = px.sort_index()
        d0 = pd.to_datetime(base_date)
        hist = px[px.index <= d0]
        future = px[px.index > d0]
        if hist.empty or future.empty:
            continue
        base = _to_float(hist["Close"].iloc[-1], np.nan)
        if pd.isna(base) or base <= 0:
            continue
        close = pd.to_numeric(future["Close"], errors="coerce").dropna()
        high = pd.to_numeric(future["High"], errors="coerce").dropna() if "High" in future.columns else close
        if close.empty:
            continue
        vals.append((
            (float(close.iloc[0]) / base - 1) * 100,
            (float(high.head(3).max()) / base - 1) * 100,
            (float(high.head(5).max()) / base - 1) * 100,
        ))
    if not vals:
        return np.nan, np.nan, np.nan
    arr = np.array(vals, dtype=float)
    return tuple(np.round(np.nanmean(arr, axis=0), 2))


def update_signal_outcomes(history: pd.DataFrame, fm_token: str) -> pd.DataFrame:
    if history is None or history.empty:
        return _empty_history()
    out = normalize_signal_history(history)
    for idx, r in out.iterrows():
        # 已有 5 日結果就不重算，減少 API 壓力。
        if pd.notna(r.get("5日最高漲幅%")):
            continue
        base_date = str(r.get("日期", ""))
        if not base_date:
            continue
        d1, h3, h5 = _calc_returns_for_code(r.get("代號", ""), base_date, r.get("基準價", np.nan), fm_token)
        if pd.notna(d1):
            out.at[idx, "隔日漲跌%"] = d1
        if pd.notna(h3):
            out.at[idx, "3日最高漲幅%"] = h3
        if pd.notna(h5):
            out.at[idx, "5日最高漲幅%"] = h5
        best = np.nanmax([x for x in [h3, h5] if pd.notna(x)]) if any(pd.notna(x) for x in [h3, h5]) else np.nan
        if pd.notna(best):
            out.at[idx, "是否達標"] = "Y" if best >= 3 else "N"
            out.at[idx, "是否失敗"] = "Y" if (pd.notna(d1) and d1 <= -2) else "N"
            out.at[idx, "更新時間"] = _now_str()
    return normalize_signal_history(out)


def append_today_snapshot(history: pd.DataFrame, twse_ind_map: Dict[str, str], twse_name_map: Optional[Dict[str, str]], fm_token: str, macro_score, overheat_flag, operation_mode) -> pd.DataFrame:
    today = _current_signal_rows(twse_ind_map, twse_name_map, fm_token, macro_score, overheat_flag, operation_mode)
    if today.empty:
        return normalize_signal_history(history)
    old = normalize_signal_history(history)
    merged = pd.concat([old, today], ignore_index=True)
    return normalize_signal_history(merged)


def _summary_stats(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work = work[work["類型"].isin(TRACKED_SIGNAL_TYPES)].copy()
    if work.empty:
        return pd.DataFrame()
    rows = []
    for typ, g in work.groupby("類型"):
        g2 = g[pd.notna(g["隔日漲跌%"]) | pd.notna(g["3日最高漲幅%"]) | pd.notna(g["5日最高漲幅%"])].copy()
        if g2.empty:
            rows.append({"類型": typ, "已驗證筆數": 0, "隔日勝率%": np.nan, "3日達標率%": np.nan, "5日達標率%": np.nan, "平均5日高點%": np.nan})
            continue
        rows.append({
            "類型": typ,
            "已驗證筆數": len(g2),
            "隔日勝率%": round((pd.to_numeric(g2["隔日漲跌%"], errors="coerce") > 0).mean() * 100, 1),
            "3日達標率%": round((pd.to_numeric(g2["3日最高漲幅%"], errors="coerce") >= 3).mean() * 100, 1),
            "5日達標率%": round((pd.to_numeric(g2["5日最高漲幅%"], errors="coerce") >= 3).mean() * 100, 1),
            "平均5日高點%": round(pd.to_numeric(g2["5日最高漲幅%"], errors="coerce").mean(), 2),
        })
    return pd.DataFrame(rows).sort_values("類型")


def _fragment_deco(fn):
    """Streamlit >=1.37 fragment：面板內互動只重跑本面板，不重跑整個 app。舊版自動退回原行為。"""
    frag = getattr(st, "fragment", None)
    if callable(frag):
        try:
            return frag(fn)
        except Exception:
            return fn
    return fn

@_fragment_deco
def render_signal_tracker_tab(COLORS, table_style, fm_token, twse_ind_map, twse_name_map=None, macro_score=None, overheat_flag=False, operation_mode="標準模式"):
    st.markdown("### 🧪 <span class='highlight-primary'>訊號追蹤室 V37.2</span>", unsafe_allow_html=True)
    st.caption("第一階段：只追蹤系統自動產生的 S/A/B 候選，保存時自動補沙盤體檢；不混入產業輪動、ETF、特殊關注或手動觀察。")

    history, msg = load_signal_history()
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        save_btn = st.button("📌 保存今日作戰快照", type="primary", use_container_width=True)
    with c2:
        update_btn = st.button("🔄 更新命中結果", use_container_width=True)
    with c3:
        st.caption(msg)

    if save_btn:
        history = append_today_snapshot(history, twse_ind_map, twse_name_map, fm_token, macro_score, overheat_flag, operation_mode)
        save_msg = save_signal_history(history)
        st.success(f"今日快照已保存。{save_msg}")

    if update_btn:
        with st.spinner("正在用最新日 K 更新隔日 / 3 日 / 5 日結果..."):
            history = update_signal_outcomes(history, fm_token)
            save_msg = save_signal_history(history)
        st.success(f"命中結果已更新。{save_msg}")

    history = normalize_signal_history(st.session_state.get("_signal_history_df", history))
    if history.empty:
        st.info("尚無訊號紀錄。請先在個股游擊完成掃描，再按「保存今日作戰快照」。")
        return

    recent_all = history[history["類型"].isin(TRACKED_SIGNAL_TYPES)].copy()
    recent = recent_all.head(300).copy()
    if recent.empty:
        st.info("目前紀錄裡沒有 S/A/B 候選樣本。請先在個股游擊完成掃描，再按「保存今日作戰快照」。")
        return
    stats = _summary_stats(recent)
    if not stats.empty:
        m1, m2, m3, m4 = st.columns(4)
        total = int(len(recent))
        verified = int((pd.notna(recent["隔日漲跌%"]) | pd.notna(recent["3日最高漲幅%"]) | pd.notna(recent["5日最高漲幅%"])).sum())
        best_type = "-"
        if stats["已驗證筆數"].max() > 0:
            best = stats.sort_values(["5日達標率%", "平均5日高點%"], ascending=False).iloc[0]
            best_type = f"{best['類型']}｜5日達標 {best['5日達標率%']:.1f}%"
        cards = [
            ("紀錄筆數", f"{total}", COLORS["primary"]),
            ("已驗證", f"{verified}", COLORS["green"] if verified else COLORS["accent"]),
            ("目前最佳", best_type, COLORS["green"]),
            ("保存規則", "只存 S/A/B + 沙盤", COLORS["accent"]),
        ]
        for col, (title, value, color) in zip([m1, m2, m3, m4], cards):
            with col:
                st.markdown(f"""
                <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {color}; border-radius:10px; padding:11px 13px; min-height:76px;">
                    <div style="font-size:13px; color:{COLORS['subtext']};">{title}</div>
                    <div style="font-size:18px; font-weight:900; color:{COLORS['text']}; line-height:1.35;">{value}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("#### 📊 近期命中率")
        st.dataframe(
            stats.style.format({
                "隔日勝率%": "{:.1f}%",
                "3日達標率%": "{:.1f}%",
                "5日達標率%": "{:.1f}%",
                "平均5日高點%": "{:.2f}%",
            }, na_rep="-").set_properties(**table_style),
            use_container_width=True,
            hide_index=True,
            height=245,
        )

    st.markdown("#### 📜 訊號明細")
    show_cols = ["日期", "類型", "代號", "名稱", "評級", "分數", "產業", "狀態", "基準價", "沙盤狀態", "沙盤等級", "沙盤現價", "沙盤M5", "沙盤M10", "沙盤乖離", "沙盤勝率", "隔日漲跌%", "3日最高漲幅%", "5日最高漲幅%", "是否達標", "是否失敗", "來源摘要"]
    view = recent[[c for c in show_cols if c in recent.columns]].copy()
    st.dataframe(
        view.style.format({
            "分數": "{:.1f}",
            "基準價": "{:.2f}",
            "沙盤現價": "{:.2f}",
            "沙盤M5": "{:.2f}",
            "沙盤M10": "{:.2f}",
            "沙盤乖離": "{:+.1f}%",
            "沙盤勝率": "{:.0f}%",
            "隔日漲跌%": "{:+.2f}%",
            "3日最高漲幅%": "{:+.2f}%",
            "5日最高漲幅%": "{:+.2f}%",
        }, na_rep="-").set_properties(**table_style),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    st.markdown("<hr style='margin: 18px 0; border-color: " + COLORS.get("border", "#444") + ";'>", unsafe_allow_html=True)
    import signal_quality
    signal_quality.render_quality_dashboard(history, COLORS, table_style, operation_mode=operation_mode)

    with st.expander("🧾 CSV 保存設計", expanded=False):
        st.markdown("""
        * 第一階段只存 S/A/B 候選，不存產業輪動、ETF、特殊關注或手動觀察，避免樣本污染。
        * 保存時會自動補沙盤體檢欄位，用來比較「原始 S/A/B」與「S/A/B + 沙盤通過」。
        * `signal_history.csv` 預設只保留最近 180 天。
        * 若設定 `github_token` / `github_repo`，會同步到 `data/signal_history.csv`。
        * 可用 `github_signal_history_path` 自訂路徑。
        """)
