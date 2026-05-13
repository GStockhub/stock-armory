"""active_etf_source_probe.py

V37.11 官方來源偵察器
--------------------
用途：
- 針對投信官方入口頁，掃描可能的 deeper data endpoint：
  JSON / CSV / XLS / XLSX / API / PCF / download links / form actions / script URLs。
- 不直接相信入口頁；逐一測試候選 URL，交給 active_etf_official_sources 的 parser 驗證。
- 僅在 ETL / GitHub Actions 執行，不在 Streamlit 前端即時呼叫。

限制：
- 這不是瀏覽器，不會執行大型 JS SPA。
- 若資料必須靠瀏覽器運行 JS 或 CAPTCHA，仍需後續手動補 registry。
"""

from __future__ import annotations

import html as html_lib
import re
import time
from dataclasses import dataclass
from typing import Iterable, List
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None


@dataclass(frozen=True)
class ProbeCandidate:
    url: str
    kind: str
    source_hint: str = ""


KEYWORDS = [
    "pcf", "holding", "holdings", "portfolio", "constituent", "component",
    "fund", "etf", "basket", "download", "csv", "xlsx", "xls", "json",
    "申購", "買回", "清單", "投資組合", "持股", "成分", "權重",
]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    })
    return s


def fetch_url(url: str, timeout: int = 25) -> tuple[str, str]:
    """Return (text, content_type). Binary excel/pdf is not parsed here; caller may skip."""
    try:
        resp = _session().get(url, timeout=timeout, verify=False)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        text = resp.text or ""
        return text, ct
    except Exception:
        return "", ""


def _abs(base_url: str, href: str) -> str:
    href = html_lib.unescape(str(href or "").strip())
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return ""
    return urljoin(base_url, href)


def _looks_relevant(url: str, etf_code: str = "") -> bool:
    s = str(url or "").lower()
    code = str(etf_code or "").lower()
    if code and code in s:
        return True
    return any(k.lower() in s for k in KEYWORDS)


def _dedupe(urls: Iterable[ProbeCandidate], limit: int = 60) -> List[ProbeCandidate]:
    seen = set()
    out = []
    for c in urls:
        if not c.url:
            continue
        u = c.url.strip()
        try:
            pr = urlparse(u)
            q = [(k, v) for k, v in parse_qsl(pr.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
            u = urlunparse((pr.scheme, pr.netloc, pr.path, pr.params, urlencode(q), pr.fragment))
        except Exception:
            pass
        if u in seen:
            continue
        seen.add(u)
        out.append(ProbeCandidate(u, c.kind, c.source_hint))
        if len(out) >= limit:
            break
    return out


def extract_probe_candidates(base_url: str, html_text: str, etf_code: str = "") -> List[ProbeCandidate]:
    """從 HTML 裡抓可能的 API / 下載檔 / 表單 action / script URL。"""
    if not html_text:
        return []
    candidates: List[ProbeCandidate] = []

    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup.find_all(["a", "link", "script", "iframe", "form"]):
                for attr in ["href", "src", "action"]:
                    val = tag.get(attr)
                    u = _abs(base_url, val)
                    if u and _looks_relevant(u, etf_code):
                        kind = "form" if attr == "action" else ("script" if tag.name == "script" else "link")
                        candidates.append(ProbeCandidate(u, kind, attr))
        except Exception:
            pass

    # raw URL fragments in scripts
    pattern = r"""["']([^"']+(?:api|pcf|holding|portfolio|download|csv|xlsx|xls|json|fund|etf)[^"']*)["']"""
    for m in re.findall(pattern, html_text, flags=re.I):
        u = _abs(base_url, m)
        if u and _looks_relevant(u, etf_code):
            candidates.append(ProbeCandidate(u, "script-url", "regex"))

    embedded_pattern = r"""((?:https?:)?//[^"'<>\\\s]+|/[A-Za-z0-9_./?=&%:-]*(?:api|pcf|holding|portfolio|download|csv|xlsx|xls|json|fund|etf)[^"'<>\\\s]*)"""
    for m in re.findall(embedded_pattern, html_text, flags=re.I):
        u = _abs(base_url, m)
        if u and _looks_relevant(u, etf_code):
            candidates.append(ProbeCandidate(u, "embedded-url", "regex"))

    code = str(etf_code or "").upper()
    if code:
        variants = [
            ("etfCode", code),
            ("stockNo", code),
            ("fundCode", code),
            ("code", code),
            ("id", code),
        ]
        try:
            pr = urlparse(base_url)
            existing = dict(parse_qsl(pr.query, keep_blank_values=True))
            for k, v in variants:
                q = existing.copy()
                q[k] = v
                u = urlunparse((pr.scheme, pr.netloc, pr.path, pr.params, urlencode(q), pr.fragment))
                candidates.append(ProbeCandidate(u, "query-variant", k))
        except Exception:
            pass

    def score(c: ProbeCandidate):
        s = c.url.lower()
        val = 100
        if any(x in s for x in [".xlsx", ".xls", ".csv", ".json"]):
            val -= 50
        if "api" in s:
            val -= 30
        if "pcf" in s:
            val -= 20
        if str(etf_code).lower() in s:
            val -= 10
        return val

    return _dedupe(sorted(candidates, key=score))


def probe_official_urls(source_urls: Iterable[str], etf_code: str = "", max_candidates_per_source: int = 25) -> List[ProbeCandidate]:
    """抓官方入口頁並回傳候選 deeper URL。"""
    all_candidates: List[ProbeCandidate] = []
    for url in source_urls:
        html_text, _ct = fetch_url(url)
        if not html_text:
            continue
        cands = extract_probe_candidates(url, html_text, etf_code=etf_code)
        all_candidates.extend(cands[:max_candidates_per_source])
        time.sleep(0.25)
    return _dedupe(all_candidates, limit=80)
