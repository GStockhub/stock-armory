"""active_etf_source_probe.py

V37.11.1 官方來源精準偵察器
--------------------------
只偵察「像資料源」的官方 URL，避免 CSS / 圖檔 / 活動頁 / 超長 HTML 片段洗爆 report。
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


DATA_KEYWORDS = [
    "pcf", "purchase", "buyback", "tradeinfo", "api", "download", "etf_detail",
    "holding", "holdings", "portfolio", "constituent", "component", "basket",
    "csv", "xlsx", "xls", "json", "funddetail", "fundhold", "fundholding",
    "申購", "買回", "清單", "投資組合", "持股", "成分", "權重",
]

BAD_EXT = re.compile(r"\.(css|ico|jpg|jpeg|png|gif|svg|webp|woff2?|ttf|eot|map|mp4|mp3)(\?|$)", re.I)
BAD_TEXT = re.compile(r"(<|>|\\u003c|\\u003e|\{|\}|data:image|base64|microsoft\.com|edge\?|download10|font-weight|background:|text-align|@media|svg\+xml)", re.I)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    })
    return s


def fetch_url(url: str, timeout: int = 25) -> tuple[str, str]:
    try:
        resp = _session().get(url, timeout=timeout, verify=False)
        resp.raise_for_status()
        return resp.text or "", resp.headers.get("content-type", "")
    except Exception:
        return "", ""


def _abs(base_url: str, href: str) -> str:
    href = html_lib.unescape(str(href or "").strip())
    if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
        return ""
    return urljoin(base_url, href)


def _same_official_domain(base_url: str, candidate_url: str) -> bool:
    try:
        base_host = urlparse(base_url).netloc.lower()
        cand_host = urlparse(candidate_url).netloc.lower()
        if not base_host or not cand_host:
            return False
        base_root = ".".join(base_host.split(".")[-2:])
        cand_root = ".".join(cand_host.split(".")[-2:])
        return base_root == cand_root
    except Exception:
        return False


def _is_clean_candidate(base_url: str, url: str, etf_code: str = "") -> bool:
    if not url:
        return False
    u = html_lib.unescape(str(url).strip())
    if len(u) > 280:
        return False
    if BAD_EXT.search(u) or BAD_TEXT.search(u):
        return False
    if not _same_official_domain(base_url, u):
        return False
    low = u.lower()
    code = str(etf_code or "").lower()
    if code and code in low and any(k in low for k in ["etf", "pcf", "purchase", "detail", "download"]):
        return True
    return any(k.lower() in low for k in DATA_KEYWORDS)


def _dedupe(urls: Iterable[ProbeCandidate], limit: int = 25) -> List[ProbeCandidate]:
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
    if not html_text:
        return []
    candidates: List[ProbeCandidate] = []

    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup.find_all(["a", "script", "iframe", "form"]):
                for attr in ["href", "src", "action"]:
                    u = _abs(base_url, tag.get(attr))
                    if u and _is_clean_candidate(base_url, u, etf_code):
                        kind = "form" if attr == "action" else ("script" if tag.name == "script" else "link")
                        candidates.append(ProbeCandidate(u, kind, attr))
        except Exception:
            pass

    quoted_pattern = r"""["']((?:https?:)?//[^"'<>\s\\]+|/[A-Za-z0-9_./?=&%:-]{3,180})["']"""
    for m in re.findall(quoted_pattern, html_text, flags=re.I):
        u = _abs(base_url, m)
        if u and _is_clean_candidate(base_url, u, etf_code):
            candidates.append(ProbeCandidate(u, "script-url", "regex"))

    code = str(etf_code or "").upper()
    if code:
        try:
            pr = urlparse(base_url)
            existing = dict(parse_qsl(pr.query, keep_blank_values=True))
            for k in ["etfCode", "stockNo", "fundCode", "code"]:
                q = existing.copy()
                q[k] = code
                u = urlunparse((pr.scheme, pr.netloc, pr.path, pr.params, urlencode(q), pr.fragment))
                if _is_clean_candidate(base_url, u, code):
                    candidates.append(ProbeCandidate(u, "query-variant", k))
        except Exception:
            pass

    def score(c: ProbeCandidate):
        s = c.url.lower()
        val = 100
        scoring = [
            (45, [".xlsx", ".xls", ".csv", ".json"]),
            (35, ["api"]),
            (30, ["pcf", "purchase", "buyback"]),
            (20, ["etf_detail", "holding", "portfolio"]),
            (10, [str(etf_code).lower()]),
        ]
        for bonus, keys in scoring:
            if any(k and k in s for k in keys):
                val -= bonus
        return val

    return _dedupe(sorted(candidates, key=score), limit=25)


def probe_official_urls(source_urls: Iterable[str], etf_code: str = "", max_candidates_per_source: int = 8) -> List[ProbeCandidate]:
    all_candidates: List[ProbeCandidate] = []
    for url in source_urls:
        html_text, _ct = fetch_url(url)
        if not html_text:
            continue
        cands = extract_probe_candidates(url, html_text, etf_code=etf_code)
        all_candidates.extend(cands[:max_candidates_per_source])
        time.sleep(0.2)
    return _dedupe(all_candidates, limit=20)
