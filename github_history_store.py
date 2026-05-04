"""github_history_store.py

GitHub CSV 持久化工具
----------------------
用途：把主動 ETF 每日持股快照保存到 GitHub repo 內的 CSV，
讓 Streamlit Cloud 重新啟動後仍能讀回近 5 日歷史。

需要在 Streamlit Secrets 設定：
    github_token = "github_pat_xxx"
    github_repo = "你的帳號/你的repo"
    github_branch = "main"
    github_etf_history_path = "data/active_etf_holdings_history.csv"

設計：
- 不額外依賴 PyGithub，只用 requests。
- 若 secrets 未設定或 GitHub API 失敗，會 fail-soft，不影響主系統。
- 寫入前會比對內容，完全相同就不 commit，避免每次 rerun 都產生 commit。
"""

from __future__ import annotations

import base64
import io
from datetime import datetime
from typing import Dict, Optional, Tuple

import pandas as pd
import requests

try:
    import streamlit as st
except Exception:
    st = None

STATUS_KEY = "_github_etf_history_store_status"
DEFAULT_STATUS = {
    "configured": False,
    "ok": False,
    "read_ok": False,
    "write_ok": False,
    "skipped": False,
    "message": "GitHub 歷史庫未設定",
}


# -----------------------------
# Secrets / config
# -----------------------------

def _secret(name: str, default: str = "") -> str:
    try:
        if st is not None:
            return str(st.secrets.get(name, default) or "").strip()
    except Exception:
        pass
    return default


def get_github_config() -> Dict[str, str]:
    token = _secret("github_token")
    repo = _secret("github_repo")
    branch = _secret("github_branch", "main") or "main"
    path = _secret("github_etf_history_path", "data/active_etf_holdings_history.csv") or "data/active_etf_holdings_history.csv"
    return {"token": token, "repo": repo, "branch": branch, "path": path}


def is_configured() -> bool:
    cfg = get_github_config()
    return bool(cfg["token"] and cfg["repo"] and cfg["path"])


def _set_status(**kwargs) -> Dict[str, object]:
    status = dict(DEFAULT_STATUS)
    status.update(kwargs)
    try:
        if st is not None:
            st.session_state[STATUS_KEY] = status
    except Exception:
        pass
    return status


def get_github_store_status() -> Dict[str, object]:
    try:
        if st is not None and STATUS_KEY in st.session_state:
            return dict(st.session_state[STATUS_KEY])
    except Exception:
        pass
    if is_configured():
        return {**DEFAULT_STATUS, "configured": True, "message": "GitHub 歷史庫已設定，尚未讀寫"}
    return dict(DEFAULT_STATUS)


# -----------------------------
# GitHub API helpers
# -----------------------------

def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "streamlit-etf-history-writer",
    }


def _contents_url(repo: str, path: str) -> str:
    path = str(path).strip().lstrip("/")
    return f"https://api.github.com/repos/{repo}/contents/{path}"


def _get_file_payload(cfg: Dict[str, str]) -> Tuple[Optional[Dict], str]:
    url = _contents_url(cfg["repo"], cfg["path"])
    try:
        resp = requests.get(
            url,
            headers=_headers(cfg["token"]),
            params={"ref": cfg["branch"]},
            timeout=20,
        )
        if resp.status_code == 404:
            return None, "not_found"
        resp.raise_for_status()
        return resp.json(), "ok"
    except Exception as e:
        return None, f"read_error: {e}"


def _decode_content(payload: Dict) -> str:
    raw = str(payload.get("content", "")).replace("\n", "")
    if not raw:
        return ""
    return base64.b64decode(raw).decode("utf-8-sig")


# -----------------------------
# Public API
# -----------------------------

def read_history_csv_from_github() -> pd.DataFrame:
    """讀取 GitHub 上的歷史 CSV；未設定或失敗則回傳空 DataFrame。"""
    cfg = get_github_config()
    if not is_configured():
        _set_status(configured=False, ok=False, message="GitHub 歷史庫未設定，使用本機 / session 快取")
        return pd.DataFrame()

    payload, state = _get_file_payload(cfg)
    if state == "not_found":
        _set_status(configured=True, ok=True, read_ok=False, message="GitHub 歷史 CSV 尚不存在，首次更新會建立")
        return pd.DataFrame()
    if state != "ok" or payload is None:
        _set_status(configured=True, ok=False, read_ok=False, message=f"GitHub 歷史庫讀取失敗：{state}")
        return pd.DataFrame()

    try:
        content = _decode_content(payload)
        if not content.strip():
            _set_status(configured=True, ok=True, read_ok=True, message="GitHub 歷史 CSV 為空，等待首次寫入")
            return pd.DataFrame()
        df = pd.read_csv(io.StringIO(content), dtype=str)
        _set_status(configured=True, ok=True, read_ok=True, message="已讀取 GitHub 歷史 CSV")
        return df
    except Exception as e:
        _set_status(configured=True, ok=False, read_ok=False, message=f"GitHub CSV 解析失敗：{e}")
        return pd.DataFrame()


def _df_to_csv_content(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        # 保留標準表頭，讓首次建立檔案時可讀。
        cols = ["日期", "ETF代號", "ETF名稱", "成分股代號", "成分股名稱", "權重", "持有股數", "產業", "來源"]
        return pd.DataFrame(columns=cols).to_csv(index=False, encoding="utf-8-sig")

    work = df.copy()
    if "日期" in work.columns:
        dates = pd.to_datetime(work["日期"], errors="coerce")
        work["日期"] = dates.dt.strftime("%Y-%m-%d").fillna(work["日期"].astype(str))
    # 欄位順序優先固定，其他欄位放後面。
    preferred = ["日期", "ETF代號", "ETF名稱", "成分股代號", "成分股名稱", "權重", "持有股數", "產業", "來源"]
    cols = [c for c in preferred if c in work.columns] + [c for c in work.columns if c not in preferred]
    work = work[cols]
    return work.to_csv(index=False, encoding="utf-8-sig")


def write_history_csv_to_github(df: pd.DataFrame, commit_message: Optional[str] = None) -> bool:
    """把歷史 DataFrame 寫回 GitHub CSV。成功 / 內容相同略過回傳 True。"""
    cfg = get_github_config()
    if not is_configured():
        _set_status(configured=False, ok=False, write_ok=False, message="GitHub 歷史庫未設定，未寫入遠端")
        return False

    new_content = _df_to_csv_content(df)
    payload, state = _get_file_payload(cfg)
    sha = None
    old_content = ""
    if state == "ok" and payload is not None:
        sha = payload.get("sha")
        try:
            old_content = _decode_content(payload)
        except Exception:
            old_content = ""
    elif state not in ["not_found", "ok"]:
        _set_status(configured=True, ok=False, write_ok=False, message=f"GitHub 寫入前讀取失敗：{state}")
        return False

    # 內容相同就不要 commit，避免每次 rerun 都增加 commit。
    if old_content.strip() == new_content.strip():
        _set_status(configured=True, ok=True, read_ok=True, write_ok=True, skipped=True, message="GitHub 歷史 CSV 已是最新，未重複提交")
        return True

    url = _contents_url(cfg["repo"], cfg["path"])
    msg = commit_message or f"Update active ETF history {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    body = {
        "message": msg,
        "content": base64.b64encode(new_content.encode("utf-8-sig")).decode("ascii"),
        "branch": cfg["branch"],
    }
    if sha:
        body["sha"] = sha

    try:
        resp = requests.put(url, headers=_headers(cfg["token"]), json=body, timeout=25)
        resp.raise_for_status()
        _set_status(configured=True, ok=True, read_ok=True, write_ok=True, skipped=False, message="已寫入 GitHub 歷史 CSV")
        return True
    except Exception as e:
        _set_status(configured=True, ok=False, write_ok=False, message=f"GitHub 歷史 CSV 寫入失敗：{e}")
        return False
