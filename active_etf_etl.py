"""active_etf_etl.py

V37.12.2 指定官方頁籤 Top10 Adapter 分層 ETL
------------------------------
用途：
- 由 GitHub Actions 每天自動執行
- 優先追蹤投信官網每日 PCF / 投資組合明細
- 抓不到官方完整資料時才退回第三方備援
- 檢查完整度，不完整資料不覆蓋歷史
- 合併既有 active_etf_holdings_history.csv
- 只保留近 60 天快照

輸出欄位：
日期, ETF代號, ETF名稱, 成分股代號, 成分股名稱, 權重, 持有股數, 收盤價, 產業, 來源

注意：
這是 ETFedge-lite 的 CSV 資料層，不把 Streamlit 本體變成大型爬蟲。
V37.8.1：ETL 預設不抓個股收盤價，避免對每個成分股逐一打 Yahoo；收盤價只在明確指定 --with-prices 時補值。
V37.10.1：新增分層抓取：
- daily：每日只抓熱門前 15 檔
- full：每週或手動全抓所有主動 ETF
- auto：依執行日自動決定，週六日 full，其餘 daily
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
    PREFERRED_DAILY_ACTIVE_ETFS,
    HOLDINGS_KEEP_DAYS,
    _filter_complete_holdings,
    fetch_active_etf_holdings_auto,
    fetch_active_etf_holdings_with_report,
    get_active_etf_candidates,
)
from github_history_store import normalize_history_df
from active_etf_official_sources import fetch_official_holdings_auto

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



def _read_latest_history_etf_order(output_path: str) -> list:
    """從現有 history 裡推估較熱門/較常用的 ETF 排序，讓 daily 模式有延續性。"""
    p = Path(output_path)
    if not p.exists():
        return []
    try:
        old = pd.read_csv(p, dtype=str, encoding="utf-8-sig")
        if old is None or old.empty or "ETF代號" not in old.columns:
            return []
        if "日期" in old.columns:
            old["_d"] = pd.to_datetime(old["日期"], errors="coerce")
            latest = old["_d"].max()
            if pd.notna(latest):
                old = old[old["_d"].eq(latest)]
        if "權重" in old.columns:
            old["_w"] = pd.to_numeric(old["權重"], errors="coerce").fillna(0)
        else:
            old["_w"] = 0
        rank = old.groupby("ETF代號").agg(權重合計=("_w", "sum"), 持股數=("ETF代號", "count")).reset_index()
        rank = rank.sort_values(["權重合計", "持股數"], ascending=[False, False])
        return rank["ETF代號"].astype(str).str.upper().tolist()
    except Exception:
        return []


def select_etf_candidates(mode: str, top_n: int, output_path: str):
    """V37.12.1 分層抓取候選清單。

    daily：強制熱門核心 Top10，不受 history 排序影響。
    full：全部母清單。
    auto：週末 full，其餘 daily。
    """
    mode = str(mode or "daily").lower().strip()
    if mode not in {"daily", "full", "auto"}:
        mode = "daily"
    if mode == "auto":
        mode = "full" if datetime.utcnow().weekday() >= 5 else "daily"

    all_candidates = get_active_etf_candidates(None, top_n=999)
    by_code = {c["ETF代號"]: c for c in all_candidates}

    if mode == "full":
        return all_candidates, mode, "full：全抓內建全部主動 ETF"

    top_n = max(1, int(top_n or 10))
    forced_order = list(PREFERRED_DAILY_ACTIVE_ETFS)

    # preferred 不足才補位，但不能讓 history 排序覆蓋核心名單。
    for code in DEFAULT_ACTIVE_ETFS.keys():
        code = str(code).upper()
        if code not in forced_order:
            forced_order.append(code)

    selected = [by_code[c] for c in forced_order if c in by_code][:top_n]
    if not selected:
        selected = all_candidates[:top_n]

    return selected, "daily", f"daily：強制熱門核心 Top {top_n}；其餘交給每週 full 補抓"


def run_etl(output_path: str, report_path: str, top_n: int, keep_days: int, no_prices: bool = True, mode: str = 'daily') -> int:
    industry_map, name_map = load_industry_map()
    candidates, resolved_mode, mode_note = select_etf_candidates(mode, top_n, output_path)
    cand_tuple = tuple((c["ETF代號"], c["ETF名稱"]) for c in candidates)
    print(f"[INFO] ETL 模式：{resolved_mode}｜{mode_note}")
    print(f"[INFO] 開始抓取主動 ETF：{len(cand_tuple)} 檔")

    # V37.10：官方優先、全主動 ETF 抓取；官方不完整才逐檔轉備援。
    official_raw, official_report = fetch_official_holdings_auto(cand_tuple)
    official_codes = set()
    if official_raw is not None and not official_raw.empty and "ETF代號" in official_raw.columns:
        official_codes = set(official_raw["ETF代號"].dropna().astype(str).str.upper())

    missing_tuple = tuple((c, n) for c, n in cand_tuple if str(c).upper() not in official_codes)
    print(f"[INFO] 官方來源完整 ETF：{len(official_codes)} 檔；需第三方備援：{len(missing_tuple)} 檔")

    fallback_raw = pd.DataFrame()
    fallback_report = pd.DataFrame()
    if missing_tuple:
        fallback_raw, fallback_report = fetch_active_etf_holdings_with_report(missing_tuple, name_map=name_map)

    raw_frames = []
    if official_raw is not None and not official_raw.empty:
        raw_frames.append(official_raw)
    if fallback_raw is not None and not fallback_raw.empty:
        # 若官方已完整，備援資料不得覆蓋；缺漏 ETF 才補。
        fallback_raw = fallback_raw[~fallback_raw["ETF代號"].astype(str).str.upper().isin(official_codes)].copy()
        if not fallback_raw.empty:
            raw_frames.append(fallback_raw)
    raw = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()

    source_reports = []
    if official_report is not None and not official_report.empty:
        source_reports.extend(official_report.to_dict(orient="records"))
    if fallback_report is not None and not fallback_report.empty:
        source_reports.extend(fallback_report.to_dict(orient="records"))

    adopted_source = {}
    for r in source_reports:
        if bool(r.get("採用", False)):
            adopted_source.setdefault(str(r.get("ETF代號", "")).upper(), f"{r.get('來源類別','')}: {r.get('來源','')}")

    complete_raw, quality = _filter_complete_holdings(raw, industry_map=industry_map)
    if no_prices:
        print("[INFO] 跳過個股收盤價補值：收盤價欄保留 0，避免逐檔訪問 Yahoo。")
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
        "mode": resolved_mode,
        "mode_note": mode_note,
        "candidate_count": len(cand_tuple),
        "candidate_etfs": [c for c, _n in cand_tuple],
        "top_n": top_n,
        "keep_days": keep_days,
        "raw_rows": 0 if raw is None else int(len(raw)),
        "complete_rows": int(len(latest)) if latest is not None else 0,
        "history_rows": int(len(merged)) if merged is not None else 0,
        "source_mode": "force_top10_official_tab_urls_weekly_full",
        "official_source_report": [] if official_report is None or official_report.empty else official_report.to_dict(orient="records"),
        "fallback_source_report": [] if fallback_report is None or fallback_report.empty else fallback_report.to_dict(orient="records"),
        "source_report": source_reports,
        "adopted_source": adopted_source,
        "price_mode": "skipped" if no_prices else "fetched",
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
    ap.add_argument("--mode", choices=["daily", "full", "auto"], default=os.environ.get("ACTIVE_ETF_ETL_MODE", "daily"), help="daily=每日熱門前N；full=全主動ETF；auto=依日期自動判斷")
    ap.add_argument("--top-n", type=int, default=int(os.environ.get("ACTIVE_ETF_TOP_N", 10)))
    ap.add_argument("--keep-days", type=int, default=int(os.environ.get("ACTIVE_ETF_KEEP_DAYS", HOLDINGS_KEEP_DAYS)))
    ap.add_argument("--with-prices", action="store_true", help="補抓個股收盤價；預設關閉，避免逐檔訪問 Yahoo")
    args = ap.parse_args()
    return run_etl(args.output, args.report, args.top_n, args.keep_days, no_prices=not args.with_prices, mode=args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
