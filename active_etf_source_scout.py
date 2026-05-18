"""active_etf_source_scout.py

V37.10 全主動 ETF 官方來源 Scout
-------------------------------
用途：
- 只在 GitHub Actions / 本機執行，不在 Streamlit 前端即時執行。
- 依 registry 偵察 PCF / JSON / HTML / hidden endpoint。
- PDF / binary 候選只記錄，不硬解析。
- 輸出 data/active_etf_source_scout.json，讓前端與 ETL 知道哪裡成功、哪裡需要 Playwright、哪裡需要另找來源。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

from active_etf_source_registry import ACTIVE_ETF_META, get_sources_for_etf, iter_registry
from active_etf_source_probe import fetch_url, probe_official_urls
from active_etf_official_sources import parse_official_response, source_quality


def _short(s: str, n: int = 240) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[:n] + "...[truncated]"


def _is_binary_url(url: str) -> bool:
    return bool(re.search(r"\.(pdf|xlsx?|xlsm|zip)(\?|$)", str(url or ""), re.I))


def _binary_note(url: str) -> str:
    low = str(url or "").lower()
    if ".pdf" in low:
        return "PDF候選已跳過；PDF表格解析不穩，建議改用PCF/CSV/JSON/第三方備援"
    if any(x in low for x in [".xls", ".xlsx", ".xlsm"]):
        return "Excel候選；目前 scout 只記錄，正式 parser 後續再接 openpyxl/read_excel"
    if ".zip" in low:
        return "ZIP候選已跳過"
    return "binary_candidate_not_parsed"


def scout_one(etf_code: str, etf_name: str = "", max_probe: int = 12) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
    code = str(etf_code or "").upper().strip()
    meta = ACTIVE_ETF_META.get(code, {})
    name = etf_name or meta.get("名稱", code)
    issuer = meta.get("投信", "")
    sources = get_sources_for_etf(code)
    reports: List[Dict[str, object]] = []
    best = pd.DataFrame()

    def add_report(source_url: str, source_type: str, note: str, rows: int, wsum: float, status: str, adopted: bool, needs_playwright: bool = False, extra: str = ""):
        reports.append({
            "ETF代號": code,
            "ETF名稱": name,
            "投信": issuer,
            "來源類別": source_type,
            "來源": _short(source_url),
            "類型": note,
            "抓到筆數": int(rows or 0),
            "權重合計": round(float(wsum or 0.0), 4),
            "狀態": status,
            "採用": bool(adopted),
            "需要Playwright": bool(needs_playwright),
            "補充": extra,
        })

    base_urls = []
    for s in sources:
        base_urls.append(s.url)
        if _is_binary_url(s.url):
            add_report(s.url, "registry", s.note, 0, 0.0, f"⚠️ {_binary_note(s.url)}", False, s.needs_playwright)
            continue
        text, ct = fetch_url(s.url)
        if any(x in str(ct).lower() for x in ["pdf", "spreadsheet", "excel"]):
            add_report(s.url, "registry", s.note, 0, 0.0, f"⚠️ {_binary_note(s.url)}", False, s.needs_playwright)
            continue
        df = parse_official_response(text, code, name, s.url, ct)
        ok, reason, cnt, wsum = source_quality(df)
        if len(df) > len(best):
            best = df
        add_report(s.url, "registry", s.note, cnt, wsum, "✅ 可用" if ok else f"⚠️ {reason}", ok, s.needs_playwright)
        if ok:
            return df, reports
        time.sleep(0.25)

    # 對已知官方入口做 deeper scout；這一步不碰 Playwright，只找同網域的資料候選。
    try:
        candidates = probe_official_urls(base_urls, etf_code=code, max_candidates_per_source=max_probe)
    except Exception as exc:
        candidates = []
        add_report("", "probe", "probe_error", 0, 0.0, f"⚠️ probe_error: {type(exc).__name__}", False)

    seen = {r.get("來源") for r in reports}
    for cand in candidates:
        if cand.url in seen:
            continue
        if _is_binary_url(cand.url):
            add_report(cand.url, "probe", f"{cand.kind}:{cand.source_hint}", 0, 0.0, f"⚠️ {_binary_note(cand.url)}", False)
            continue
        text, ct = fetch_url(cand.url)
        if any(x in str(ct).lower() for x in ["pdf", "spreadsheet", "excel"]):
            add_report(cand.url, "probe", f"{cand.kind}:{cand.source_hint}", 0, 0.0, f"⚠️ {_binary_note(cand.url)}", False)
            continue
        df = parse_official_response(text, code, name, cand.url, ct)
        ok, reason, cnt, wsum = source_quality(df)
        if len(df) > len(best):
            best = df
        add_report(cand.url, "probe", f"{cand.kind}:{cand.source_hint}", cnt, wsum, "✅ 可用" if ok else f"⚠️ {reason}", ok)
        if ok:
            return df, reports
        time.sleep(0.2)

    if not sources:
        add_report("", "registry", "未設定官方來源", 0, 0.0, "⚠️ no_source", False)

    return best, reports


def scout_many(etf_codes: Iterable[str] | None = None, max_probe: int = 12) -> Dict[str, object]:
    codes = [str(c).upper().strip() for c in etf_codes] if etf_codes else list(ACTIVE_ETF_META.keys())
    all_reports: List[Dict[str, object]] = []
    adopted = []
    needs_playwright = []
    for code in codes:
        meta = ACTIVE_ETF_META.get(code, {})
        _df, reports = scout_one(code, meta.get("名稱", code), max_probe=max_probe)
        all_reports.extend(reports)
        ok = any(bool(r.get("採用")) for r in reports)
        if ok:
            adopted.append(code)
        elif any(bool(r.get("需要Playwright")) for r in reports):
            needs_playwright.append(code)
    return {
        "run_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "registry_count": len(ACTIVE_ETF_META),
        "scanned_count": len(codes),
        "adopted_etfs": sorted(set(adopted)),
        "needs_playwright_etfs": sorted(set(needs_playwright)),
        "registry": iter_registry(codes),
        "source_report": all_reports,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Active ETF source scout")
    ap.add_argument("--output", default="data/active_etf_source_scout.json")
    ap.add_argument("--codes", default="", help="逗號分隔 ETF 代號；空白代表全掃")
    ap.add_argument("--max-probe", type=int, default=12)
    args = ap.parse_args()
    codes = [x.strip().upper() for x in args.codes.split(",") if x.strip()] if args.codes else None
    report = scout_many(codes, max_probe=args.max_probe)
    p = Path(args.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Scout report: {p}｜adopted={len(report.get('adopted_etfs', []))}｜needs_playwright={len(report.get('needs_playwright_etfs', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
