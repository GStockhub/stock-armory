"""signal_tracker.py

V37 訊號追蹤室
---------------
目的：
- 取代原本較少使用的回測室。
- 每日保存系統實際產出的 S/A/B、特殊關注、產業輪動、主動 ETF 前五訊號。
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
from etf_engine import run_etf_momentum_radar
import rotation_radar


SIGNAL_COLUMNS = [
    "日期", "類型", "代號", "名稱", "評級", "分數", "產業", "狀態", "來源摘要",
    "基準價", "樣本代號", "隔日漲跌%", "3日最高漲幅%", "5日最高漲幅%",
    "是否達標", "是否失敗", "更新時間",
]

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
    for c in ["分數", "基準價", "隔日漲跌%", "3日最高漲幅%", "5日最高漲幅%"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    for c in ["類型", "代號", "名稱", "評級", "產業", "狀態", "來源摘要", "樣本代號", "是否達標", "是否失敗", "更新時間"]:
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


def _current_signal_rows(twse_ind_map: Dict[str, str], fm_token: str, macro_score, overheat_flag, operation_mode) -> pd.DataFrame:
    rows = []

    master = st.session_state.get("eod_master_list", pd.DataFrame())
    if isinstance(master, pd.DataFrame) and not master.empty:
        for grade in ["S", "A", "B"]:
            part = master[master.get("評級", "").astype(str).str.replace("級", "", regex=False).eq(grade)].copy() if "評級" in master.columns else pd.DataFrame()
            rows.extend(_rows_from_signal_df(part, f"{grade}級", 10))
    else:
        # V37.1：若主清單剛好為空，仍從 rank_sorted 補一份保守 B 級觀察紀錄，
        # 避免當日完全沒有訊號可追蹤。
        ranked = st.session_state.get("eod_rank_sorted", pd.DataFrame())
        if isinstance(ranked, pd.DataFrame) and not ranked.empty and "代號" in ranked.columns:
            fallback = ranked.head(10).copy()
            fallback["評級"] = "B"
            rows.extend(_rows_from_signal_df(fallback, "B級", 10))

    special = st.session_state.get("eod_special_watch", pd.DataFrame())
    if isinstance(special, pd.DataFrame) and not special.empty:
        rows.extend(_rows_from_signal_df(special, "特殊關注", 5))

    # 產業輪動：融合第一/第二/第四優先。只保存主戰場、升溫、退潮，並帶樣本代碼方便後續驗證。
    frames = []
    for key in ["eod_master_list", "eod_special_watch", "eod_rank_sorted"]:
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            frames.append(df.copy())
    if frames:
        pool = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["代號"], keep="first")
        if "產業" not in pool.columns:
            pool["產業"] = pool["代號"].astype(str).map(lambda x: twse_ind_map.get(str(x), "未分類"))
        rot = rotation_radar.build_industry_rotation_table(pool, None)
        if isinstance(rot, pd.DataFrame) and not rot.empty:
            keep = rot[rot["輪動狀態"].isin(["🔥 主戰場", "🟠 資金升溫", "⚠️ 退潮警戒"])].head(8)
            for _, r in keep.iterrows():
                ind = str(r.get("產業", ""))
                members = pool[pool["產業"].astype(str).eq(ind)]["代號"].astype(str).map(_clean_code).dropna().head(10).tolist()
                rows.append({
                    "日期": _today_str(),
                    "類型": "產業輪動",
                    "代號": f"IND_{ind}",
                    "名稱": ind,
                    "評級": str(r.get("輪動狀態", "")),
                    "分數": _to_float(r.get("今日熱度", np.nan), np.nan),
                    "產業": ind,
                    "狀態": str(r.get("輪動狀態", "")),
                    "來源摘要": f"可信度 {r.get('可信度','')}｜樣本 {r.get('樣本數','')}｜{r.get('操作建議','')}",
                    "基準價": np.nan,
                    "樣本代號": ",".join(members),
                    "隔日漲跌%": np.nan,
                    "3日最高漲幅%": np.nan,
                    "5日最高漲幅%": np.nan,
                    "是否達標": "",
                    "是否失敗": "",
                    "更新時間": _now_str(),
                })

    # 主動 ETF 前五：不管有沒有進綜合 Top 10 都保存。
    try:
        radar = run_etf_momentum_radar(fm_token)
        if isinstance(radar, pd.DataFrame) and not radar.empty and "類型" in radar.columns:
            active = radar[radar["類型"].eq("主動ETF")].head(5).copy()
            for _, r in active.iterrows():
                rows.append({
                    "日期": _today_str(),
                    "類型": "主動ETF",
                    "代號": _clean_code(r.get("代號", "")),
                    "名稱": str(r.get("名稱", "")),
                    "評級": str(r.get("狀態", "")),
                    "分數": _to_float(r.get("動能分數", np.nan), np.nan),
                    "產業": "ETF",
                    "狀態": str(r.get("狀態", "")),
                    "來源摘要": str(r.get("下一步", ""))[:120],
                    "基準價": _to_float(r.get("現價", np.nan), np.nan),
                    "樣本代號": "",
                    "隔日漲跌%": np.nan,
                    "3日最高漲幅%": np.nan,
                    "5日最高漲幅%": np.nan,
                    "是否達標": "",
                    "是否失敗": "",
                    "更新時間": _now_str(),
                })
    except Exception:
        pass

    out = pd.DataFrame(rows)
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
        if str(r.get("類型", "")) == "產業輪動":
            d1, h3, h5 = _calc_returns_for_industry(r.get("樣本代號", ""), base_date, fm_token)
        else:
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


def append_today_snapshot(history: pd.DataFrame, twse_ind_map: Dict[str, str], fm_token: str, macro_score, overheat_flag, operation_mode) -> pd.DataFrame:
    today = _current_signal_rows(twse_ind_map, fm_token, macro_score, overheat_flag, operation_mode)
    if today.empty:
        return normalize_signal_history(history)
    old = normalize_signal_history(history)
    merged = pd.concat([old, today], ignore_index=True)
    return normalize_signal_history(merged)


def _summary_stats(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work = work[work["類型"].isin(["S級", "A級", "B級", "特殊關注", "產業輪動", "主動ETF"])].copy()
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




def _verified_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    return out[pd.notna(out["隔日漲跌%"] ) | pd.notna(out["3日最高漲幅%"] ) | pd.notna(out["5日最高漲幅%"] )].copy()


def _recent_window_stats(df: pd.DataFrame, windows=(5, 10, 20)) -> pd.DataFrame:
    """最近 N 筆已驗證訊號的真實命中率摘要，避免只看長期平均誤判。"""
    ver = _verified_rows(df)
    if ver.empty:
        return pd.DataFrame()
    ver = ver.sort_values(["日期", "更新時間"], ascending=[False, False])
    rows = []
    for n in windows:
        g = ver.head(int(n)).copy()
        if g.empty:
            continue
        hit = (g["是否達標"].astype(str).str.upper().eq("Y")).mean() * 100
        fail = (g["是否失敗"].astype(str).str.upper().eq("Y")).mean() * 100
        h5 = pd.to_numeric(g["5日最高漲幅%"], errors="coerce")
        d1 = pd.to_numeric(g["隔日漲跌%"], errors="coerce")
        rows.append({
            "視窗": f"最近{len(g)}筆",
            "達標率%": round(hit, 1),
            "失敗率%": round(fail, 1),
            "隔日勝率%": round((d1 > 0).mean() * 100, 1),
            "平均5日高點%": round(h5.mean(), 2),
        })
    return pd.DataFrame(rows)


def _type_power_rank(df: pd.DataFrame, min_samples: int = 5) -> pd.DataFrame:
    ver = _verified_rows(df)
    if ver.empty:
        return pd.DataFrame()
    rows = []
    for typ, g in ver.groupby("類型"):
        if len(g) < min_samples:
            continue
        hit = (g["是否達標"].astype(str).str.upper().eq("Y")).mean() * 100
        fail = (g["是否失敗"].astype(str).str.upper().eq("Y")).mean() * 100
        h5 = pd.to_numeric(g["5日最高漲幅%"], errors="coerce")
        score = hit + max(0, float(h5.mean() or 0)) * 5 - fail * 0.6
        rows.append({
            "訊號類型": typ,
            "樣本數": int(len(g)),
            "達標率%": round(hit, 1),
            "失敗率%": round(fail, 1),
            "平均5日高點%": round(h5.mean(), 2),
            "目前權重建議": "升權" if len(g) >= 10 and hit >= 55 and fail <= 25 else ("保留" if hit >= 40 else "降權觀察"),
            "_score": round(score, 2),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["_score", "樣本數"], ascending=[False, False]).drop(columns=["_score"])


def render_signal_quality_brief(history: pd.DataFrame, COLORS: Dict[str, str], table_style: Dict[str, str]) -> None:
    """96分版：用真實樣本告訴使用者哪些訊號該升權/保守。"""
    if history is None or history.empty:
        return
    recent = normalize_signal_history(history, keep_days=60).head(300)
    verified = _verified_rows(recent)
    if verified.empty:
        st.info("🧪 訊號追蹤：已有紀錄，但尚未回填足夠績效；暫不調整任何訊號權重。")
        return

    total = len(recent)
    vcnt = len(verified)
    hit_rate = (verified["是否達標"].astype(str).str.upper().eq("Y")).mean() * 100
    fail_rate = (verified["是否失敗"].astype(str).str.upper().eq("Y")).mean() * 100
    rank = _type_power_rank(recent, min_samples=5)
    top = "樣本不足，暫不升權"
    if not rank.empty:
        top_row = rank.iloc[0]
        top = f"{top_row['訊號類型']}｜{top_row['目前權重建議']}｜達標 {top_row['達標率%']:.1f}%"

    st.markdown("#### 🧭 訊號追蹤結論")
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        ("追蹤筆數", f"{total}", COLORS.get("primary", "#A67C52")),
        ("已驗證樣本", f"{vcnt}", COLORS.get("green", "#3D8D5A")),
        ("整體達標率", f"{hit_rate:.1f}%", COLORS.get("green", "#3D8D5A") if hit_rate >= 45 else COLORS.get("accent", "#C47A3A")),
        ("目前最有效", top, COLORS.get("primary", "#A67C52")),
    ]
    for col, (title, value, color) in zip([c1, c2, c3, c4], cards):
        with col:
            st.markdown(f"""
            <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {color}; border-radius:10px; padding:10px 12px; min-height:78px;">
                <div style="font-size:12.5px; color:{COLORS['subtext']};">{title}</div>
                <div style="font-size:16px; font-weight:900; color:{COLORS['text']}; line-height:1.35;">{value}</div>
            </div>
            """, unsafe_allow_html=True)

    note = "樣本已可初步參考，但仍以最近 20 筆與分型樣本數一起看。" if vcnt >= 30 else "樣本仍偏少，暫時只當方向參考，不自動放大部位。"
    st.caption(f"{note}｜整體失敗率 {fail_rate:.1f}%")

    win = _recent_window_stats(recent)
    if not win.empty:
        with st.expander("📏 最近 5 / 10 / 20 筆樣本", expanded=False):
            st.dataframe(
                win.style.format({"達標率%": "{:.1f}%", "失敗率%": "{:.1f}%", "隔日勝率%": "{:.1f}%", "平均5日高點%": "{:.2f}%"}).set_properties(**table_style),
                use_container_width=True,
                hide_index=True,
                height=145,
            )
    if not rank.empty:
        with st.expander("🏷️ 訊號類型升降權建議", expanded=False):
            st.dataframe(
                rank.style.format({"達標率%": "{:.1f}%", "失敗率%": "{:.1f}%", "平均5日高點%": "{:.2f}%"}).set_properties(**table_style),
                use_container_width=True,
                hide_index=True,
                height=min(260, 45 + 36 * len(rank)),
            )

def render_signal_tracker_tab(COLORS, table_style, fm_token, twse_ind_map, macro_score, overheat_flag, operation_mode):
    st.markdown("### 🧪 <span class='highlight-primary'>訊號追蹤室 V37</span>", unsafe_allow_html=True)
    st.caption("取代原回測室：每天保存 S/A/B、特殊關注、產業輪動、主動 ETF 前五，之後檢查隔日 / 3 日 / 5 日命中率。")

    history, msg = load_signal_history()
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        save_btn = st.button("📌 保存今日作戰快照", type="primary", use_container_width=True)
    with c2:
        update_btn = st.button("🔄 更新命中結果", use_container_width=True)
    with c3:
        st.caption(msg)

    if save_btn:
        history = append_today_snapshot(history, twse_ind_map, fm_token, macro_score, overheat_flag, operation_mode)
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

    render_signal_quality_brief(history, COLORS, table_style)

    recent = history.head(300).copy()
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
            ("保存規則", "明細滾動 180 天", COLORS["accent"]),
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
    show_cols = ["日期", "類型", "代號", "名稱", "評級", "分數", "產業", "狀態", "基準價", "隔日漲跌%", "3日最高漲幅%", "5日最高漲幅%", "是否達標", "是否失敗", "來源摘要"]
    view = recent[[c for c in show_cols if c in recent.columns]].copy()
    st.dataframe(
        view.style.format({
            "分數": "{:.1f}",
            "基準價": "{:.2f}",
            "隔日漲跌%": "{:+.2f}%",
            "3日最高漲幅%": "{:+.2f}%",
            "5日最高漲幅%": "{:+.2f}%",
        }, na_rep="-").set_properties(**table_style),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    with st.expander("🧾 CSV 保存設計", expanded=False):
        st.markdown("""
        * 只存入選訊號，不存全市場，避免 CSV 變肥。
        * `signal_history.csv` 預設只保留最近 180 天。
        * 若設定 `github_token` / `github_repo`，會同步到 `data/signal_history.csv`。
        * 可用 `github_signal_history_path` 自訂路徑。
        """)
