"""github_history_store.py

GitHub CSV 持久化工具
--------------------
用途：把主動 ETF 每日持股快照保存到 GitHub repo 內的 CSV，
避免 Streamlit Cloud 重啟後本機快取消失。

需要 Streamlit Secrets：
- github_token
- github_repo，例如 deki1023/stock-armory
- github_branch，例如 main
- github_etf_history_path，例如 data/active_etf_holdings_history.csv
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

import pandas as pd
import requests

try:
    import streamlit as st
except Exception:
    st = None

REQUIRED_COLUMNS = ["日期", "ETF代號", "ETF名稱", "成分股代號", "成分股名稱", "權重", "持有股數", "收盤價", "產業", "來源"]
API_ROOT = "https://api.github.com"


@dataclass
class GitHubConfig:
    token: str = ""
    repo: str = ""
    branch: str = "main"
    path: str = "data/active_etf_holdings_history.csv"

    @property
    def ready(self) -> bool:
        return bool(self.token and self.repo and self.branch and self.path)


def get_github_config() -> GitHubConfig:
    if st is None:
        return GitHubConfig()
    try:
        return GitHubConfig(
            token=str(st.secrets.get("github_token", "")).strip(),
            repo=str(st.secrets.get("github_repo", "")).strip(),
            branch=str(st.secrets.get("github_branch", "main")).strip() or "main",
            path=str(st.secrets.get("github_etf_history_path", "data/active_etf_holdings_history.csv")).strip()
            or "data/active_etf_holdings_history.csv",
        )
    except Exception:
        return GitHubConfig()


def _headers(cfg: GitHubConfig) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {cfg.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "stock-armory-streamlit",
    }


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(columns=REQUIRED_COLUMNS)


def normalize_history_df(df: pd.DataFrame, max_days: int = 60) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_history()
    out = df.copy()
    out.columns = [str(c).replace("\ufeff", "").strip() for c in out.columns]
    for c in REQUIRED_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out = out[REQUIRED_COLUMNS].copy()
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce").dt.normalize()
    out["ETF代號"] = out["ETF代號"].astype(str).str.strip().str.upper()
    out["ETF名稱"] = out["ETF名稱"].astype(str).str.strip()
    out["成分股代號"] = out["成分股代號"].astype(str).str.strip().str.upper()
    out["成分股名稱"] = out["成分股名稱"].astype(str).str.strip()
    out["產業"] = out["產業"].astype(str).str.strip()
    out["來源"] = out["來源"].astype(str).str.strip()
    out["權重"] = pd.to_numeric(out["權重"].astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
    out["持有股數"] = pd.to_numeric(out["持有股數"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
    out["收盤價"] = pd.to_numeric(out["收盤價"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
    out = out.dropna(subset=["日期"])
    out = out[(out["ETF代號"] != "") & (out["成分股代號"] != "")]
    if out.empty:
        return _empty_history()
    out = out.drop_duplicates(subset=["日期", "ETF代號", "成分股代號"], keep="last")
    dates = sorted(out["日期"].dropna().unique())[-max_days:]
    out = out[out["日期"].isin(dates)].copy()
    out = out.sort_values(["日期", "ETF代號", "權重"], ascending=[True, True, False])
    out["日期"] = out["日期"].dt.strftime("%Y-%m-%d")
    return out.reset_index(drop=True)


def _df_to_csv_text(df: pd.DataFrame) -> str:
    norm = normalize_history_df(df, max_days=9999)
    return norm.to_csv(index=False, encoding="utf-8-sig", lineterminator="\n")


def _github_url(cfg: GitHubConfig, path: Optional[str] = None) -> str:
    return f"{API_ROOT}/repos/{cfg.repo}/contents/{path or cfg.path}"


def read_github_history() -> Tuple[pd.DataFrame, Dict[str, object]]:
    cfg = get_github_config()
    diag = {
        "ok": False,
        "stage": "config",
        "message": "GitHub 歷史庫未設定。",
        "repo": cfg.repo,
        "branch": cfg.branch,
        "path": cfg.path,
        "status_code": None,
    }
    if not cfg.ready:
        missing = []
        if not cfg.token:
            missing.append("github_token")
        if not cfg.repo:
            missing.append("github_repo")
        if not cfg.branch:
            missing.append("github_branch")
        if not cfg.path:
            missing.append("github_etf_history_path")
        diag["message"] = "缺少 secrets：" + "、".join(missing)
        return _empty_history(), diag

    try:
        r = requests.get(_github_url(cfg), headers=_headers(cfg), params={"ref": cfg.branch}, timeout=18)
        diag["status_code"] = r.status_code
        diag["stage"] = "read_file"
        if r.status_code == 404:
            diag["message"] = "GitHub 找不到歷史 CSV；系統會嘗試在下次寫入時建立。"
            return _empty_history(), diag
        if r.status_code >= 400:
            diag["message"] = f"GitHub 讀取失敗：HTTP {r.status_code} {r.text[:160]}"
            return _empty_history(), diag
        payload = r.json()
        content = payload.get("content", "")
        if not content:
            diag["message"] = "GitHub CSV 內容為空。"
            return _empty_history(), diag
        raw = base64.b64decode(content).decode("utf-8-sig")
        df = pd.read_csv(io.StringIO(raw), dtype=str)
        norm = normalize_history_df(df)
        diag.update({"ok": True, "message": f"GitHub 歷史 CSV 讀取成功：{len(norm):,} 筆", "sha": payload.get("sha")})
        return norm, diag
    except Exception as e:
        diag["stage"] = "exception"
        diag["message"] = f"GitHub 讀取例外：{type(e).__name__}: {e}"
        return _empty_history(), diag


def write_github_history(df: pd.DataFrame, commit_message: Optional[str] = None) -> Dict[str, object]:
    cfg = get_github_config()
    diag = {
        "ok": False,
        "stage": "config",
        "message": "GitHub 歷史庫未設定，略過寫入。",
        "repo": cfg.repo,
        "branch": cfg.branch,
        "path": cfg.path,
        "status_code": None,
    }
    if not cfg.ready:
        return diag

    norm = normalize_history_df(df)
    if norm.empty:
        diag["message"] = "沒有可寫入的 ETF 歷史資料。"
        return diag

    new_text = _df_to_csv_text(norm)
    encoded = base64.b64encode(new_text.encode("utf-8-sig")).decode("utf-8")

    sha = None
    try:
        get_r = requests.get(_github_url(cfg), headers=_headers(cfg), params={"ref": cfg.branch}, timeout=18)
        diag["status_code"] = get_r.status_code
        if get_r.status_code == 200:
            payload = get_r.json()
            sha = payload.get("sha")
            old_content = payload.get("content", "")
            if old_content:
                try:
                    old_text = base64.b64decode(old_content).decode("utf-8-sig")
                    if old_text.strip() == new_text.strip():
                        diag.update({"ok": True, "stage": "unchanged", "message": "GitHub 歷史 CSV 無變化，略過 commit。"})
                        return diag
                except Exception:
                    pass
        elif get_r.status_code == 404:
            sha = None  # 允許建立新檔案
        else:
            diag.update({"stage": "preflight", "message": f"GitHub 寫入前讀取失敗：HTTP {get_r.status_code} {get_r.text[:160]}"})
            return diag

        body = {
            "message": commit_message or f"Update active ETF holdings history {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": encoded,
            "branch": cfg.branch,
        }
        if sha:
            body["sha"] = sha

        put_r = requests.put(_github_url(cfg), headers=_headers(cfg), json=body, timeout=25)
        diag["status_code"] = put_r.status_code
        diag["stage"] = "write_file"
        if put_r.status_code in (200, 201):
            action = "建立" if put_r.status_code == 201 else "更新"
            diag.update({"ok": True, "message": f"GitHub 歷史 CSV 已{action}：{len(norm):,} 筆"})
            return diag
        diag["message"] = f"GitHub 歷史 CSV 寫入失敗：HTTP {put_r.status_code} {put_r.text[:220]}"
        return diag
    except Exception as e:
        diag["stage"] = "exception"
        diag["message"] = f"GitHub 寫入例外：{type(e).__name__}: {e}"
        return diag


def sync_history_with_github(local_df: pd.DataFrame, max_days: int = 60) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """讀取 GitHub 歷史，與本機最新資料合併，再嘗試寫回 GitHub。"""
    remote_df, read_diag = read_github_history()
    frames = []
    if remote_df is not None and not remote_df.empty:
        frames.append(remote_df)
    if local_df is not None and not local_df.empty:
        frames.append(local_df)
    if not frames:
        return _empty_history(), read_diag
    merged = normalize_history_df(pd.concat(frames, ignore_index=True), max_days=max_days)
    write_diag = write_github_history(merged)
    final_diag = {
        "ok": bool(read_diag.get("ok") or write_diag.get("ok")),
        "read": read_diag,
        "write": write_diag,
        "message": write_diag.get("message") or read_diag.get("message"),
        "days": int(pd.to_datetime(merged["日期"], errors="coerce").nunique()) if not merged.empty else 0,
    }
    return merged, final_diag


def diagnose_github_history_connection() -> Dict[str, object]:
    """針對 repo / branch / path 做逐步診斷，不印出 token。"""
    cfg = get_github_config()
    result = {
        "ready": cfg.ready,
        "repo": cfg.repo,
        "branch": cfg.branch,
        "path": cfg.path,
        "checks": [],
        "summary": "尚未檢查",
    }
    if not cfg.ready:
        result["summary"] = "GitHub secrets 不完整。"
        return result

    def add(name, ok, status, message):
        result["checks"].append({"項目": name, "狀態": "✅" if ok else "❌", "HTTP": status or "-", "說明": message})

    try:
        repo_r = requests.get(f"{API_ROOT}/repos/{cfg.repo}", headers=_headers(cfg), timeout=15)
        add("Repo 存取", repo_r.status_code == 200, repo_r.status_code, "可存取 repo" if repo_r.status_code == 200 else repo_r.text[:120])

        branch_r = requests.get(f"{API_ROOT}/repos/{cfg.repo}/branches/{cfg.branch}", headers=_headers(cfg), timeout=15)
        add("Branch 存取", branch_r.status_code == 200, branch_r.status_code, "可存取 branch" if branch_r.status_code == 200 else branch_r.text[:120])

        file_r = requests.get(_github_url(cfg), headers=_headers(cfg), params={"ref": cfg.branch}, timeout=15)
        if file_r.status_code == 200:
            add("CSV 路徑", True, file_r.status_code, "CSV 已存在且可讀取")
        elif file_r.status_code == 404:
            add("CSV 路徑", False, file_r.status_code, "找不到 CSV；若 repo/branch 都正常，系統會嘗試建立。")
        else:
            add("CSV 路徑", False, file_r.status_code, file_r.text[:120])

        ok_count = sum(1 for c in result["checks"] if c["狀態"] == "✅")
        result["summary"] = f"GitHub 診斷完成：{ok_count}/{len(result['checks'])} 正常"
    except Exception as e:
        result["summary"] = f"GitHub 診斷例外：{type(e).__name__}: {e}"
    return result
