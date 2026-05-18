"""active_etf_source_registry.py

V37.10 全主動 ETF 官方來源 Registry
----------------------------------
用途：
- 集中管理「主動 ETF → 投信 → 候選官方來源」mapping。
- Streamlit 前端不直接使用；GitHub Actions / ETL / Scout 使用。
- 來源以 PCF / Excel / CSV / JSON 優先；HTML table 次之；Playwright 只標記需求，不在前端執行。

注意：
這份 registry 是資料源地圖，不代表每個來源都已打通。
真正是否可用由 active_etf_source_scout.py / active_etf_etl.py 的完整度檢查決定。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class SourceCandidate:
    etf_code: str
    etf_name: str
    issuer: str
    url: str
    source_type: str = "official"
    note: str = ""
    priority: int = 100
    enabled: bool = True
    needs_playwright: bool = False
    skip_pdf: bool = True


# 全主動 ETF 母清單。若未來新增 ETF，只要在這裡補 mapping，不要散落在 parser 裡。
ACTIVE_ETF_META: Dict[str, Dict[str, str]] = {
    "00981A": {"名稱": "主動統一台股增長", "投信": "統一投信"},
    "00403A": {"名稱": "主動統一升級50", "投信": "統一投信"},
    "00992A": {"名稱": "主動群益科技創新", "投信": "群益投信"},
    "00982A": {"名稱": "主動群益台灣強棒", "投信": "群益投信"},
    "00991A": {"名稱": "主動復華未來50", "投信": "復華投信"},
    "00988A": {"名稱": "主動統一全球創新", "投信": "統一投信"},
    "00990A": {"名稱": "主動元大AI新經濟", "投信": "元大投信"},
    "00400A": {"名稱": "主動國泰動能高息", "投信": "國泰投信"},
    "00980A": {"名稱": "主動野村臺灣優選", "投信": "野村投信"},
    "00999A": {"名稱": "主動野村臺灣高息", "投信": "野村投信"},
    "00997A": {"名稱": "主動群益美國增長", "投信": "群益投信"},
    "00993A": {"名稱": "主動安聯台灣", "投信": "安聯投信"},
    "00985A": {"名稱": "主動野村台灣50", "投信": "野村投信"},
    "00984A": {"名稱": "主動安聯台灣高息", "投信": "安聯投信"},
    "00994A": {"名稱": "主動第一金台股優", "投信": "第一金投信"},
    "00995A": {"名稱": "主動中信台灣卓越", "投信": "中信投信"},
    "00996A": {"名稱": "主動兆豐台灣豐收", "投信": "兆豐投信"},
    "00401A": {"名稱": "主動摩根台灣鑫收", "投信": "摩根投信"},
    "00987A": {"名稱": "主動台新優勢成長", "投信": "台新投信"},
    "00998A": {"名稱": "主動復華金融股息", "投信": "復華投信"},
    "00983A": {"名稱": "主動中信ARK創新", "投信": "中信投信"},
    "00989A": {"名稱": "主動摩根美國科技", "投信": "摩根投信"},
    "00986A": {"名稱": "主動台新龍頭成長", "投信": "台新投信"},
}


def _src(code: str, url: str, note: str, priority: int = 100, source_type: str = "official", needs_playwright: bool = False) -> SourceCandidate:
    meta = ACTIVE_ETF_META.get(code, {})
    return SourceCandidate(
        etf_code=code,
        etf_name=meta.get("名稱", code),
        issuer=meta.get("投信", ""),
        url=url,
        source_type=source_type,
        note=note,
        priority=priority,
        needs_playwright=needs_playwright,
    )


ACTIVE_ETF_SOURCE_REGISTRY: Dict[str, List[SourceCandidate]] = {
    # 統一投信：PCF / Excel / API 候選優先，HTML 頁籤次之。
    "00981A": [
        _src("00981A", "https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW", "PCF Excel候選", 10),
        _src("00981A", "https://www.ezmoney.com.tw/ETF/Transaction/GetPCF?fundCode=49YTW", "PCF API候選", 20),
        _src("00981A", "https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode=49YTW", "PCF", 30, needs_playwright=True),
        _src("00981A", "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW#asset", "基金投資組合頁籤", 40, needs_playwright=True),
    ],
    "00403A": [
        # 00403A 是新主動 ETF；目前先同時保留可能 fundCode，讓 scout 用完整度決定採用誰。
        _src("00403A", "https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=63YTW", "PCF Excel候選 63YTW", 10),
        _src("00403A", "https://www.ezmoney.com.tw/ETF/Transaction/GetPCF?fundCode=63YTW", "PCF API候選 63YTW", 20),
        _src("00403A", "https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode=63YTW", "PCF 63YTW", 30, needs_playwright=True),
        _src("00403A", "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=63YTW#asset", "基金投資組合頁籤 63YTW", 40, needs_playwright=True),
        _src("00403A", "https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=50YTW", "PCF Excel候選 50YTW", 50),
        _src("00403A", "https://www.ezmoney.com.tw/ETF/Transaction/GetPCF?fundCode=50YTW", "PCF API候選 50YTW", 60),
        _src("00403A", "https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode=50YTW", "PCF 50YTW", 70, needs_playwright=True),
    ],
    "00988A": [
        _src("00988A", "https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=61YTW", "PCF Excel候選", 10),
        _src("00988A", "https://www.ezmoney.com.tw/ETF/Transaction/GetPCF?fundCode=61YTW", "PCF API候選", 20),
        _src("00988A", "https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode=61YTW", "PCF", 30, needs_playwright=True),
        _src("00988A", "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=61YTW#asset", "基金投資組合頁籤", 40, needs_playwright=True),
    ],

    # 群益投信：buyback 頁目前可直接解析。
    "00982A": [_src("00982A", "https://www.capitalfund.com.tw/etf/product/detail/399/buyback", "PCF", 10)],
    "00992A": [_src("00992A", "https://www.capitalfund.com.tw/etf/product/detail/500/buyback", "PCF", 10)],
    "00997A": [_src("00997A", "https://www.capitalfund.com.tw/etf/product/detail/502/buyback", "PCF", 10)],

    # 其他投信先列官方入口；scout 會標明未打通/需 Playwright/需另找 PCF。
    "00980A": [_src("00980A", "https://www.nomurafunds.com.tw/ETFWEB/pcf", "PCF入口", 50, needs_playwright=True)],
    "00999A": [_src("00999A", "https://www.nomurafunds.com.tw/ETFWEB/pcf", "PCF入口", 50, needs_playwright=True)],
    "00985A": [_src("00985A", "https://www.nomurafunds.com.tw/ETFWEB/pcf", "PCF入口", 50, needs_playwright=True)],
    "00400A": [
        _src("00400A", "https://www.cathaysite.com.tw/ETF/detail/EEA?tab=etf3", "ETF持股/投資組合頁籤", 50, needs_playwright=True),
        _src("00400A", "https://www.cathaysite.com.tw/ETF/purchase?code=EA", "PCF申購買回清單", 60, needs_playwright=True),
    ],
    "00991A": [_src("00991A", "https://www.fhtrust.com.tw/ETF/etf_detail/ETF24#nav", "ETF明細", 60, needs_playwright=True)],
    "00998A": [_src("00998A", "https://www.fhtrust.com.tw/ETF", "ETF入口", 90, needs_playwright=True)],
    "00990A": [_src("00990A", "https://www.yuantaetfs.com/", "ETF入口", 90, needs_playwright=True)],
    "00993A": [_src("00993A", "https://tw.allianzgi.com/zh-tw/etf", "ETF入口", 90, needs_playwright=True)],
    "00984A": [_src("00984A", "https://tw.allianzgi.com/zh-tw/etf", "ETF入口", 90, needs_playwright=True)],
    "00994A": [_src("00994A", "https://www.fsitc.com.tw/Fund/ETF", "ETF入口", 90, needs_playwright=True)],
    "00995A": [_src("00995A", "https://www.ctbcinvestments.com/", "ETF入口", 90, needs_playwright=True)],
    "00983A": [_src("00983A", "https://www.ctbcinvestments.com/", "ETF入口", 90, needs_playwright=True)],
    "00996A": [_src("00996A", "https://www.megafunds.com.tw/", "ETF入口", 90, needs_playwright=True)],
    "00401A": [_src("00401A", "https://www.jpmrich.com.tw/", "ETF入口", 90, needs_playwright=True)],
    "00989A": [_src("00989A", "https://www.jpmrich.com.tw/", "ETF入口", 90, needs_playwright=True)],
    "00987A": [_src("00987A", "https://www.tsit.com.tw/", "ETF入口", 90, needs_playwright=True)],
    "00986A": [_src("00986A", "https://www.tsit.com.tw/", "ETF入口", 90, needs_playwright=True)],
}


def iter_registry(etf_codes: Iterable[str] | None = None) -> List[Dict[str, object]]:
    allowed = {str(c).upper() for c in etf_codes} if etf_codes else None
    rows: List[Dict[str, object]] = []
    for code, meta in ACTIVE_ETF_META.items():
        if allowed and code not in allowed:
            continue
        sources = sorted(ACTIVE_ETF_SOURCE_REGISTRY.get(code, []), key=lambda s: s.priority)
        if not sources:
            rows.append({"ETF代號": code, "ETF名稱": meta.get("名稱", code), "投信": meta.get("投信", ""), "來源": "", "來源類型": "none", "備註": "未設定官方來源", "優先序": 999, "需要Playwright": False})
            continue
        for s in sources:
            rows.append({
                "ETF代號": s.etf_code,
                "ETF名稱": s.etf_name,
                "投信": s.issuer,
                "來源": s.url,
                "來源類型": s.source_type,
                "備註": s.note,
                "優先序": s.priority,
                "需要Playwright": bool(s.needs_playwright),
                "啟用": bool(s.enabled),
            })
    return rows


def get_sources_for_etf(etf_code: str) -> List[SourceCandidate]:
    code = str(etf_code or "").upper().strip()
    return sorted([s for s in ACTIVE_ETF_SOURCE_REGISTRY.get(code, []) if s.enabled], key=lambda s: s.priority)


def get_etf_meta(etf_code: str) -> Dict[str, str]:
    code = str(etf_code or "").upper().strip()
    return ACTIVE_ETF_META.get(code, {"名稱": code, "投信": ""})


def build_official_source_registry(official_source_cls):
    """提供 active_etf_official_sources.py 使用，避免兩份 mapping 不同步。"""
    out: Dict[str, List[object]] = {}
    for code in ACTIVE_ETF_META:
        rows = []
        for s in get_sources_for_etf(code):
            rows.append(official_source_cls(s.etf_code, s.issuer, s.url, s.note))
        out[code] = rows
    return out
