"""active_etf_playwright_probe.py

V37.11 主動 ETF 官方來源 Playwright 攻堅器
---------------------------------------
只給 GitHub Actions / 本機 ETL 使用；Streamlit 前端不會呼叫。

用途：
- 對 registry 標記 needs_playwright 的官方頁做 headless browser 渲染。
- 收集渲染後 HTML 與同網域 XHR/JSON/HTML response。
- 交回 active_etf_official_sources.py 用既有 parser 判斷是否完整。

啟用方式：
- 設定環境變數 ACTIVE_ETF_ENABLE_PLAYWRIGHT=1
- GitHub Actions 需先執行：pip install playwright && python -m playwright install chromium
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Iterable, List
from urllib.parse import urlparse


DATA_KEYWORDS = [
    "pcf", "purchase", "buyback", "tradeinfo", "api", "download", "etf_detail",
    "holding", "holdings", "portfolio", "constituent", "component", "basket",
    "csv", "xlsx", "xls", "json", "funddetail", "fundhold", "fundholding",
    "GetPCF", "PCFInfo", "PCFExcel", "fundCode", "FundCode",
    "申購", "買回", "清單", "投資組合", "持股", "成分", "權重",
]

BAD_EXT_RE = re.compile(r"\.(css|ico|jpg|jpeg|png|gif|svg|webp|woff2?|ttf|eot|map|mp4|mp3)(\?|$)", re.I)
BINARY_CT_RE = re.compile(r"(image/|font/|video/|audio/|pdf|octet-stream)", re.I)
CLICK_TEXTS = [
    "投資組合", "基金投資組合", "持股", "成分", "申購買回", "PCF", "買回清單", "投組",
    "投資明細", "持股明細", "基金資料", "產品資料", "申購", "買回", "下載",
]


def _extract_interesting_links(page, base_url: str, etf_code: str = "", limit: int = 10) -> list[str]:
    """從渲染頁面擷取可能的 ETF/PCF/持股連結，再由 browser 逐一打開。

    這用來處理只給投信入口頁的來源，例如安聯/中信/台新/摩根等。
    """
    try:
        links = page.locator("a").evaluate_all(
            "els => els.map(a => ({href: a.href || '', text: (a.innerText || a.textContent || '')})).filter(x => x.href)"
        )
    except Exception:
        return []
    out = []
    seen = set()
    code = str(etf_code or "").lower()
    for item in links or []:
        href = str(item.get("href", "") or "")
        text = str(item.get("text", "") or "")
        blob = (href + " " + text).lower()
        if href in seen:
            continue
        if not _same_domain(base_url, href):
            continue
        if BAD_EXT_RE.search(href):
            continue
        hit = False
        if code and code in blob:
            hit = True
        if any(k.lower() in blob for k in DATA_KEYWORDS):
            hit = True
        if any(k in text for k in ["主動", "ETF", "申購", "買回", "持股", "投資組合", "成分", "PCF"]):
            hit = True
        if not hit:
            continue
        seen.add(href)
        out.append(href)
        if len(out) >= limit:
            break
    return out


@dataclass(frozen=True)
class RenderedCandidate:
    url: str
    kind: str
    content_type: str
    text: str


def is_enabled() -> bool:
    return str(os.environ.get("ACTIVE_ETF_ENABLE_PLAYWRIGHT", "")).strip().lower() in {"1", "true", "yes", "on"}


def _same_domain(base_url: str, url: str) -> bool:
    try:
        b = urlparse(base_url).netloc.lower()
        u = urlparse(url).netloc.lower()
        if not b or not u:
            return False
        return ".".join(b.split(".")[-2:]) == ".".join(u.split(".")[-2:])
    except Exception:
        return False


def _looks_like_data_url(base_url: str, url: str, etf_code: str = "") -> bool:
    if not url or BAD_EXT_RE.search(url):
        return False
    if not _same_domain(base_url, url):
        return False
    low = url.lower()
    code = str(etf_code or "").lower()
    if code and code in low:
        return True
    return any(k.lower() in low for k in DATA_KEYWORDS)


def _safe_response_text(resp, max_chars: int) -> tuple[str, str]:
    try:
        ct = str(resp.headers.get("content-type", "") or "")
    except Exception:
        ct = ""
    if BINARY_CT_RE.search(ct):
        return "", ct
    try:
        text = resp.text()
    except Exception:
        return "", ct
    if not text:
        return "", ct
    text = text[:max_chars]
    return text, ct


def render_and_capture(
    urls: Iterable[str],
    etf_code: str = "",
    wait_ms: int = 5500,
    max_responses: int = 60,
    max_chars: int = 900_000,
) -> List[RenderedCandidate]:
    """渲染官方頁並收集候選 response。

    備註：這裡只做資料收集，不判定成功。成功與否交給 parser + source_quality。
    """
    if not is_enabled():
        return []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"[WARN] Playwright 未安裝或無法載入：{type(exc).__name__}: {exc}")
        return []

    out: List[RenderedCandidate] = []
    seen = set()

    def add(url: str, kind: str, content_type: str, text: str):
        if not text or not url:
            return
        key = (url, kind)
        if key in seen:
            return
        seen.add(key)
        out.append(RenderedCandidate(url=url, kind=kind, content_type=content_type or "text/html", text=text[:max_chars]))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7"},
        )

        try:
            for base_url in urls:
                if not base_url:
                    continue
                captured = 0
                page = context.new_page()

                def on_response(resp, base_url=base_url):
                    nonlocal captured
                    if captured >= max_responses:
                        return
                    u = getattr(resp, "url", "")
                    if not _looks_like_data_url(base_url, u, etf_code=etf_code):
                        return
                    text, ct = _safe_response_text(resp, max_chars=max_chars)
                    if not text:
                        return
                    captured += 1
                    add(u, "playwright-response", ct, text)

                page.on("response", on_response)
                try:
                    page.goto(base_url, wait_until="domcontentloaded", timeout=45_000)
                    page.wait_for_timeout(wait_ms)
                    # 嘗試點擊可能觸發 XHR 的頁籤或按鈕。失敗就跳過，不阻斷。
                    for label in CLICK_TEXTS:
                        try:
                            loc = page.get_by_text(label, exact=False)
                            if loc.count() > 0:
                                loc.first.click(timeout=1500)
                                page.wait_for_timeout(1200)
                        except Exception:
                            continue
                    try:
                        page.wait_for_load_state("networkidle", timeout=6000)
                    except Exception:
                        pass
                    add(base_url, "playwright-rendered-page", "text/html", page.content())

                    # 入口頁攻堅：若 registry 只給投信首頁/ETF入口，嘗試開啟頁面中
                    # 跟 ETF/PCF/持股有關的連結，讓 XHR 監聽器抓到真正 API。
                    for href in _extract_interesting_links(page, base_url, etf_code=etf_code, limit=10):
                        if captured >= max_responses:
                            break
                        try:
                            page.goto(href, wait_until="domcontentloaded", timeout=25_000)
                            page.wait_for_timeout(max(1800, wait_ms // 2))
                            for label in CLICK_TEXTS:
                                try:
                                    loc = page.get_by_text(label, exact=False)
                                    if loc.count() > 0:
                                        loc.first.click(timeout=1200)
                                        page.wait_for_timeout(900)
                                except Exception:
                                    continue
                            try:
                                page.wait_for_load_state("networkidle", timeout=3500)
                            except Exception:
                                pass
                            add(href, "playwright-linked-page", "text/html", page.content())
                        except Exception:
                            continue
                except Exception as exc:
                    print(f"[WARN] Playwright 渲染失敗 {base_url}: {type(exc).__name__}: {exc}")
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
                    time.sleep(0.25)
        finally:
            try:
                context.close()
            except Exception:
                pass
            browser.close()
    return out
