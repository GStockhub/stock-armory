"""active_etf_etl.py

V37.8 主動 ETF 自動 ETL
----------------------
用途：
- 由 GitHub Actions 每天自動執行
- 抓取主動 ETF 持股快照
- 檢查完整度，不完整資料不覆蓋歷史
- 合併既有 active_etf_holdings_history.csv
- 只保留近 60 天快照

輸出欄位：
日期, ETF代號, ETF名稱, 成分股代號, 成分股名稱, 權重, 持有股數, 收盤價, 產業, 來源

注意：
這是 ETFedge-lite 的 CSV 資料層，不把 Streamlit 本體變成大型爬蟲。
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

try:
    import yfinance as yf
except Exception:  # yfinance 失敗不阻斷 ETL，收盤價欄可留 0
    yf = None

from active_etf_holdings import (
    ACTIVE_ETF_TOP_N,
    DEFAULT_ACTIVE_ETFS,
    HOLDINGS_KEEP_DAYS,
    _filter_complete_holdings,
    fetch_active_etf_holdings_auto,
    get_active_etf_candidates,
)
from github_history_store import normalize_history_df

OUTPUT_COLUMNS = ["日期", "ETF代號", "ETF名稱", "成分股代號", "成分股名稱", "權重", "持有股數", "收盤價", "產業", "來源"]


def load_industry_map(path: str = "industry_map.csv") -> Tuple[Dict[str, str], Dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return {}, {}
    df = pd.read_csv(p, dtype=str, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    for c in ["代號", "名稱", "產業"]:
        if c not in df.columns:
            df[c] = ""
    df["代號"] = df["代號"].astype(str).str.strip().str.upper()
    return dict(zip(df["代號"], df["產業"].astype(str).str.strip())), dict(zip(df["代號"], df["名稱"].astype(str).str.strip()))


def _clean_code(code: str) -> str:
    return str(code or "").strip().upper()


def fetch_latest_close_prices(stock_codes) -> Dict[str, float]:
    """抓最新收盤價。失敗時回傳空 dict，不阻斷持股快照。"""
    if yf is None:
        return {}
    codes = sorted({_clean_code(c) for c in stock_codes if _clean_code(c)})
    if not codes:
        return {}
    out: Dict[str, float] = {}
    tickers = []
    rev = {}
    for code in codes:
        # 台股普通股大多 .TW；上櫃會失敗但不阻斷。這裡只是輔助欄位。
        tk = f"{code}.TW"
        tickers.append(tk)
        rev[tk] = code
    try:
        data = yf.download(tickers, period="7d", interval="1d", group_by="ticker", threads=False, progress=False)
        if data is None or getattr(data, "empty", True):
            return out
        if len(tickers) == 1:
            s = pd.to_numeric(data.get("Close"), errors="coerce").dropna()
            if not s.empty:
                out[rev[tickers[0]]] = float(s.iloc[-1])
            return out
        for tk in tickers:
            try:
                if tk in data.columns.get_level_values(0):
                    s = pd.to_numeric(data[tk]["Close"], errors="coerce").dropna()
                    if not s.empty:
                        out[rev[tk]] = float(s.iloc[-1])
            except Exception:
                continue
    except Exception as exc:
        print(f"[WARN] 收盤價抓取失敗：{type(exc).__name__}: {exc}")
    return out


def standardize_latest(df: pd.DataFrame, industry_map: Dict[str, str], with_prices: bool = True) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    out = df.copy()
    for c in ["日期", "ETF代號", "ETF名稱", "成分股代號", "成分股名稱", "權重", "持有股數", "來源"]:
        if c not in out.columns:
            out[c] = "" if c not in ["權重", "持有股數"] else 0
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["ETF代號"] = out["ETF代號"].astype(str).str.strip().str.upper()
    out["成分股代號"] = out["成分股代號"].astype(str).str.strip().str.upper()
    out["權重"] = pd.to_numeric(out["權重"].astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
    out["持有股數"] = pd.to_numeric(out["持有股數"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
    out["產業"] = out["成分股代號"].map(lambda x: industry_map.get(str(x).strip(), "未分類"))
    out["收盤價"] = 0.0
    if with_prices:
        price_map = fetch_latest_close_prices(out["成分股代號"].unique())
        if price_map:
            out["收盤價"] = out["成分股代號"].map(lambda x: float(price_map.get(str(x).strip(), 0.0)))
    out = out[(out["日期"].astype(str) != "NaT") & (out["ETF代號"] != "") & (out["成分股代號"] != "")].copy()
    return out[OUTPUT_COLUMNS].drop_duplicates(["日期", "ETF代號", "成分股代號"], keep="last")


def merge_with_history(latest: pd.DataFrame, output_path: str, keep_days: int = HOLDINGS_KEEP_DAYS) -> pd.DataFrame:
    frames = []
    p = Path(output_path)
    if p.exists():
        try:
            old = pd.read_csv(p, dtype=str, encoding="utf-8-sig")
            if old is not None and not old.empty:
                frames.append(old)
        except Exception as exc:
            print(f"[WARN] 舊歷史讀取失敗：{exc}")
    if latest is not None and not latest.empty:
        frames.append(latest)
    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    merged = pd.concat(frames, ignore_index=True)
    norm = normalize_history_df(merged, max_days=keep_days)
    for c in OUTPUT_COLUMNS:
        if c not in norm.columns:
            norm[c] = 0 if c in ["權重", "持有股數", "收盤價"] else ""
    return norm[OUTPUT_COLUMNS]


def run_etl(output_path: str, report_path: str, top_n: int, keep_days: int, no_prices: bool = False) -> int:
    industry_map, name_map = load_industry_map()
    candidates = get_active_etf_candidates(None, top_n=top_n)
    cand_tuple = tuple((c["ETF代號"], c["ETF名稱"]) for c in candidates)
    print(f"[INFO] 開始抓取主動 ETF：{len(cand_tuple)} 檔")

    raw = fetch_active_etf_holdings_auto(cand_tuple, name_map=name_map)
    complete_raw, quality = _filter_complete_holdings(raw, industry_map=industry_map)
    latest = standardize_latest(complete_raw, industry_map=industry_map, with_prices=not no_prices)
    merged = merge_with_history(latest, output_path, keep_days=keep_days)

    outp = Path(output_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    if not merged.empty:
        merged.to_csv(outp, index=False, encoding="utf-8-sig", lineterminator="\n")
        print(f"[INFO] 已寫入 {outp}：{len(merged):,} 筆，{pd.to_datetime(merged['日期'], errors='coerce').nunique()} 日")
    else:
        print("[WARN] 沒有完整快照，也沒有可沿用歷史；不產生有效歷史資料。")

    report = {
        "run_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "output_path": str(outp),
        "top_n": top_n,
        "keep_days": keep_days,
        "raw_rows": 0 if raw is None else int(len(raw)),
        "complete_rows": int(len(latest)) if latest is not None else 0,
        "history_rows": int(len(merged)) if merged is not None else 0,
        "complete_etfs": [] if latest is None or latest.empty else sorted(latest["ETF代號"].dropna().astype(str).unique().tolist()),
        "quality": [] if quality is None or quality.empty else quality.to_dict(orient="records"),
    }
    rp = Path(report_path)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] ETL 報告：{rp}")
    # 抓不到完整資料不視為 Action 失敗；避免每天紅燈，但會在 report 記錄。
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Active ETF holdings ETL")
    ap.add_argument("--output", default=os.environ.get("ACTIVE_ETF_HISTORY_PATH", "data/active_etf_holdings_history.csv"))
    ap.add_argument("--report", default=os.environ.get("ACTIVE_ETF_REPORT_PATH", "data/active_etf_etl_report.json"))
    ap.add_argument("--top-n", type=int, default=int(os.environ.get("ACTIVE_ETF_TOP_N", ACTIVE_ETF_TOP_N)))
    ap.add_argument("--keep-days", type=int, default=int(os.environ.get("ACTIVE_ETF_KEEP_DAYS", HOLDINGS_KEEP_DAYS)))
    ap.add_argument("--no-prices", action="store_true", help="不抓個股收盤價，只更新持股與權重")
    args = ap.parse_args()
    return run_etl(args.output, args.report, args.top_n, args.keep_days, no_prices=args.no_prices)


if __name__ == "__main__":
    raise SystemExit(main())
