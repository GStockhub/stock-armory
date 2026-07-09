"""active_etf_official_sources.py

V37.9 主動 ETF 官方持股公告來源層
----------------------------------
目的：
- 優先追蹤投信官網每日揭露的 PCF / 投資組合明細。
- 將各投信不同格式統一成 active_etf_holdings_history.csv 欄位。
- 只在 ETL / GitHub Actions 使用；Streamlit 主畫面不需要每次即時爬官方站。

設計：
- 每檔 ETF 可設定多個官方 URL。
- 解析器採「表格優先、文字序列備援」。
- 只接受 >=10 檔、權重合計 >=20% 的完整快照，避免假資料污染歷史。
"""

from __future__ import annotations

import html as html_lib
import io
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests

try:
    from active_etf_source_probe import probe_official_urls, fetch_url as probe_fetch_url
except Exception:
    probe_official_urls = None
    probe_fetch_url = None

try:
    from active_etf_source_registry import get_sources_for_etf
except Exception:
    get_sources_for_etf = None

try:
    from active_etf_playwright_probe import is_enabled as playwright_enabled, render_and_capture
except Exception:
    playwright_enabled = None
    render_and_capture = None

try:
    from bs4 import BeautifulSoup
except Exception:  # bs4 若不可用，仍可退回簡易 HTML strip
    BeautifulSoup = None


@dataclass(frozen=True)
class OfficialSource:
    etf_code: str
    issuer: str
    url: str
    note: str = ""


# 已確認能從公開搜尋結果看到 PCF / 投資組合內容的官方頁。
# 其他投信先保留 generic/fallback，不在這裡硬塞未知 URL，避免抓錯基金。
# V37.10：完整主動 ETF 官方來源母清單。
# 原則：
# 1. 投信官網 / PCF / 申購買回清單優先。
# 2. 未確認可直接解析的官方頁，也先放官方候選；解析不到不寫入。
# 3. 官方失敗後由 active_etf_etl.py 接第三方備援，不在這裡硬判定成功。
OFFICIAL_SOURCE_REGISTRY: Dict[str, List[OfficialSource]] = {
    # 統一投信 ezmoney
    "00981A": [
        OfficialSource("00981A", "統一投信", "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW#asset", "資產/投資組合頁籤"),
        OfficialSource("00981A", "統一投信", "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW", "基金投資組合"),
        OfficialSource("00981A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode=49YTW", "PCF"),
        OfficialSource("00981A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/GetPCF?fundCode=49YTW", "PCF API候選"),
        OfficialSource("00981A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=49YTW", "PCF Excel候選"),
    ],
    "00403A": [
        OfficialSource("00403A", "統一投信", "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=63YTW&tabName=basic#asset", "資產/投資組合頁籤"),
        OfficialSource("00403A", "統一投信", "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=63YTW", "基金投資組合"),
        OfficialSource("00403A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode=63YTW", "PCF"),
        OfficialSource("00403A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/GetPCF?fundCode=63YTW", "PCF API候選"),
        OfficialSource("00403A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=63YTW", "PCF Excel候選"),
    ],
    "00988A": [
        OfficialSource("00988A", "統一投信", "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=61YTW", "基金投資組合"),
        OfficialSource("00988A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode=61YTW", "PCF"),
        OfficialSource("00988A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/GetPCF?fundCode=61YTW", "PCF API候選"),
        OfficialSource("00988A", "統一投信", "https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI?fundCode=61YTW", "PCF Excel候選"),
    ],

    # 群益投信：product/detail/{id}/buyback 頁目前可直接解析 PCF。
    "00982A": [OfficialSource("00982A", "群益投信", "https://www.capitalfund.com.tw/etf/product/detail/399/buyback", "PCF")],
    "00992A": [OfficialSource("00992A", "群益投信", "https://www.capitalfund.com.tw/etf/product/detail/500/buyback", "PCF")],
    "00997A": [OfficialSource("00997A", "群益投信", "https://www.capitalfund.com.tw/etf/product/detail/502/buyback", "PCF")],

    # 野村投信：官方 PCF 入口為動態頁；先列入口，若解析不到交給備援。
    "00980A": [OfficialSource("00980A", "野村投信", "https://www.nomurafunds.com.tw/ETFWEB/pcf", "PCF入口")],
    "00999A": [OfficialSource("00999A", "野村投信", "https://www.nomurafunds.com.tw/ETFWEB/pcf", "PCF入口")],
    "00985A": [OfficialSource("00985A", "野村投信", "https://www.nomurafunds.com.tw/ETFWEB/pcf", "PCF入口")],

    # 國泰投信
    "00400A": [
        OfficialSource("00400A", "國泰投信", "https://www.cathaysite.com.tw/ETF/detail/EEA?tab=etf3", "ETF持股/投資組合頁籤"),
        OfficialSource("00400A", "國泰投信", "https://www.cathaysite.com.tw/ETF/purchase?code=EA&name=%E5%9C%8B%E6%B3%B0%E5%8F%B0%E8%82%A1%E5%8B%95%E8%83%BD%E9%AB%98%E6%81%AF%E4%B8%BB%E5%8B%95%E5%BC%8FETF%E5%9F%BA%E9%87%91", "PCF申購買回清單"),
        OfficialSource("00400A", "國泰投信", "https://www.cathaysite.com.tw/ETF/detail/EEA", "ETF詳情"),
    ],

    # 復華投信
    "00991A": [
        OfficialSource("00991A", "復華投信", "https://www.fhtrust.com.tw/ETF/etf_detail/ETF24#nav", "ETF明細"),
        OfficialSource("00991A", "復華投信", "https://www.fhtrust.com.tw/ETF", "ETF入口"),
    ],
    "00998A": [
        OfficialSource("00998A", "復華投信", "https://www.fhtrust.com.tw/ETF", "ETF入口"),
    ],

    # 元大 / 安聯 / 第一金 / 中信 / 兆豐 / 摩根 / 台新
    # 這些官網 URL 格式可能改版，先列投信 ETF 入口；抓不到完整時用備援。
    "00990A": [OfficialSource("00990A", "元大投信", "https://www.yuantaetfs.com/", "ETF入口")],
    "00993A": [OfficialSource("00993A", "安聯投信", "https://tw.allianzgi.com/zh-tw/etf", "ETF入口")],
    "00984A": [OfficialSource("00984A", "安聯投信", "https://tw.allianzgi.com/zh-tw/etf", "ETF入口")],
    "00994A": [OfficialSource("00994A", "第一金投信", "https://www.fsitc.com.tw/Fund/ETF", "ETF入口")],
    "00995A": [OfficialSource("00995A", "中信投信", "https://www.ctbcinvestments.com/", "ETF入口")],
    "00983A": [OfficialSource("00983A", "中信投信", "https://www.ctbcinvestments.com/", "ETF入口")],
    "00996A": [OfficialSource("00996A", "兆豐投信", "https://www.megafunds.com.tw/", "ETF入口")],
    "00401A": [OfficialSource("00401A", "摩根投信", "https://www.jpmrich.com.tw/", "ETF入口")],
    "00989A": [OfficialSource("00989A", "摩根投信", "https://www.jpmrich.com.tw/", "ETF入口")],
    "00987A": [OfficialSource("00987A", "台新投信", "https://www.tsit.com.tw/", "ETF入口")],
    "00986A": [OfficialSource("00986A", "台新投信", "https://www.tsit.com.tw/", "ETF入口")],
}



# V37.10：以 active_etf_source_registry.py 作為單一來源地圖。
# 保留上方舊表只是為了回溯相容；實際執行時用 registry 覆蓋，避免多處 mapping 不同步。
try:
    from active_etf_source_registry import build_official_source_registry
    OFFICIAL_SOURCE_REGISTRY = build_official_source_registry(OfficialSource)
except Exception:
    pass

OUTPUT_COLUMNS = ["日期", "ETF代號", "ETF名稱", "成分股代號", "成分股名稱", "權重", "持有股數", "來源"]


from net_utils import build_session, smart_get


def _session() -> requests.Session:
    return build_session(with_retry=True)


def _fetch_html(url: str, timeout: int = 25) -> str:
    try:
        resp = smart_get(url, session=_session(), timeout=timeout)
        resp.raise_for_status()
        text = resp.text or ""
        return text if len(text) >= 80 else ""
    except Exception:
        return ""


def _clean_code(v) -> str:
    s = str(v or "").strip().upper()
    s = re.sub(r"[^0-9A-Z]", "", s)
    return s


def _split_name_code(v) -> tuple[str, str]:
    """從 MoneyDJ / 第三方常見的「台積電(2330.TW)」格式拆出名稱與代號。"""
    raw = str(v or "").strip()
    # 台股：台積電(2330.TW)、旺矽(6223.TW)；海外：NVDA(或 NVDA.US) 也盡量保留。
    m = re.search(r"(.+?)[（(]\s*([0-9A-Z]{1,8})(?:\.(?:TW|TWO|US|O|N|K|HK))?\s*[)）]", raw, flags=re.I)
    if m:
        return m.group(1).strip(), _clean_code(m.group(2))
    m = re.search(r"\b(\d{4}[A-Z]?)\.(?:TW|TWO)\b", raw, flags=re.I)
    if m:
        name = re.sub(r"[（(]?\s*" + re.escape(m.group(0)) + r"\s*[)）]?", "", raw, flags=re.I).strip()
        return name or raw, _clean_code(m.group(1))
    return raw, ""


def _to_float(v, default=0.0) -> float:
    try:
        if pd.isna(v):
            return default
        s = str(v).replace("％", "%").replace("%", "").replace(",", "").strip()
        m = re.search(r"-?\d+\.?\d*", s)
        return float(m.group(0)) if m else default
    except Exception:
        return default


def _parse_date(text: str) -> pd.Timestamp:
    today = pd.Timestamp(datetime.now().date())
    if not text:
        return today
    dates: List[pd.Timestamp] = []
    for y, m, d in re.findall(r"(?<!\d)(\d{3,4})[./\-年](\d{1,2})[./\-月](\d{1,2})", text):
        try:
            yi = int(y)
            if 100 <= yi < 200:  # 民國年
                yi += 1911
            ts = pd.Timestamp(f"{yi:04d}-{int(m):02d}-{int(d):02d}")
            if pd.Timestamp("2020-01-01") <= ts <= today + pd.Timedelta(days=5):
                dates.append(ts)
        except Exception:
            continue
    return max(dates) if dates else today


def _text_from_html(html_text: str) -> str:
    if not html_text:
        return ""
    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text("\n")
        except Exception:
            text = html_text
    else:
        text = re.sub(r"<script[\s\S]*?</script>", " ", html_text, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[\t\r\f\v]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text


def _norm_col(c: object) -> str:
    return str(c).replace("\ufeff", "").replace("\n", "").strip()


def _pick_col(cols: Iterable[str], keys: List[str], exclude: Optional[List[str]] = None) -> Optional[str]:
    """寬鬆欄位對應。

    各投信/第三方 API 常混用中文、英文、駝峰與大小寫；這裡用大小寫不敏感與
    去空白比對，降低「抓到 JSON 但欄位對不上」的失敗率。
    """
    exclude = exclude or []
    cols = [_norm_col(c) for c in cols]
    key_norm = [str(k).replace(" ", "").replace("_", "").lower() for k in keys]
    exc_norm = [str(x).replace(" ", "").replace("_", "").lower() for x in exclude]

    def _canon(v: str) -> str:
        return str(v).replace(" ", "").replace("_", "").lower()

    for c in cols:
        cc = _canon(c)
        if any(x and x in cc for x in exc_norm):
            continue
        if cc in key_norm or c in keys:
            return c
    for c in cols:
        cc = _canon(c)
        if any(x and x in cc for x in exc_norm):
            continue
        if any(k and k in cc for k in key_norm) or any(k in c for k in keys):
            return c
    return None


def _standardize_table(raw: pd.DataFrame, etf_code: str, etf_name: str, date: pd.Timestamp, source_url: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["".join([str(x) for x in tup if str(x) != "nan"]) for tup in df.columns]
    df.columns = [_norm_col(c) for c in df.columns]
    code_col = _pick_col(df.columns, [
        "股票代號", "證券代號", "成分股代號", "代號", "股票代碼", "Code",
        "stock_code", "stockCode", "stockNo", "StockNo", "symbol", "ticker",
        "securityCode", "SecurityCode", "holdingCode", "fundStockCode", "FundStockCode",
    ])
    name_col = _pick_col(df.columns, [
        "股票名稱", "證券名稱", "成分股名稱", "個股名稱", "持股名稱", "名稱", "Name",
        "stock_name", "stockName", "StockName", "securityName", "SecurityName",
        "symbolName", "tickerName", "holdingName", "fundStockName", "FundStockName",
    ])
    weight_col = _pick_col(df.columns, [
        "持股權重(%)", "持股權重", "權重", "比重", "比例", "投資比例", "投資比例(%)", "投資比率", "Weight",
        "weight", "weight_pct", "weightPct", "WeightPct", "stockWeight", "StockWeight",
        "ratio", "Ratio", "percent", "percentage", "Percentage", "holdingRatio", "HoldingRatio",
        "valueRatio", "ValueRatio", "marketValueRatio", "MarketValueRatio",
    ])
    share_col = _pick_col(df.columns, [
        "股數", "持有股數", "持股股數", "持股數", "持有股數", "Shares",
        "shares", "share_count", "shareCount", "ShareCount", "numberOfShares", "NumberOfShares",
        "qty", "quantity", "Quantity", "volume", "Volume", "unit", "units",
    ])
    if name_col is None or (weight_col is None and share_col is None):
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    if code_col is not None:
        codes = df[code_col].map(_clean_code)
        names = df[name_col].astype(str).str.strip()
    else:
        # MoneyDJ 等第三方持股表常把代號放在名稱欄：台積電(2330.TW)
        split = df[name_col].map(_split_name_code)
        names = split.map(lambda x: x[0])
        codes = split.map(lambda x: x[1])

    out = pd.DataFrame({
        "日期": date,
        "ETF代號": _clean_code(etf_code),
        "ETF名稱": etf_name or etf_code,
        "成分股代號": codes,
        "成分股名稱": names,
        "權重": df[weight_col].map(_to_float) if weight_col else 0.0,
        "持有股數": df[share_col].map(_to_float) if share_col else 0.0,
        "來源": source_url,
    })
    return _clean_rows(out, etf_code)


def _tokenize(text: str) -> List[str]:
    # 先拿掉日期，避免 2026/05/12 被拆成 2026 這種假股票代碼。
    text = re.sub(r"(?<!\d)\d{3,4}[./\-年]\d{1,2}[./\-月]\d{1,2}(?:日)?", " ", text)
    text = re.sub(r"([0-9]+(?:,[0-9]{3})+(?:\.\d+)?|\d+\.\d+%?|\d+%?)", r" \1 ", text)
    # 不移除 ASCII comma，保留 1,728,000 這類股數。
    text = re.sub(r"[｜|()（）【】\[\]{};；，]", " ", text)
    return [t.strip() for t in re.split(r"\s+", text) if t.strip()]


def _looks_number(tok: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:,\d{3})*(?:\.\d+)?%?", str(tok).strip()))


FOREIGN_HOLDING_ETFS = {"00988A", "00997A", "00983A", "00989A"}
_BAD_TICKER_WORDS = {
    "ETF", "PCF", "NAV", "TWD", "USD", "API", "HTML", "JSON", "NULL", "TRUE", "FALSE",
    "TOP", "BUY", "SELL", "DATE", "NAME", "CODE", "SHARE", "SHARES", "WEIGHT",
}


def _is_stock_code(tok: str, etf_code: str) -> bool:
    s = _clean_code(tok)
    code = _clean_code(etf_code)
    if not s or s == code:
        return False
    # 台股官方 PCF 多為 4 碼；部分新金融商品/特別股允許 4 碼 + 字母。
    if re.fullmatch(r"\d{4}[A-Z]?", s):
        return True
    # 海外型主動 ETF 會出現 NVDA/MSFT/TSLA/BRKB 等英文 ticker；只對海外 ETF 開放，
    # 避免把 PCF、ETF、NAV 之類文字誤判為成分股。
    if code in FOREIGN_HOLDING_ETFS and re.fullmatch(r"[A-Z]{1,5}[A-Z0-9]?", s) and s not in _BAD_TICKER_WORDS:
        return True
    return False


def _parse_text_rows(html_text: str, etf_code: str, etf_name: str, source_url: str) -> pd.DataFrame:
    text = _text_from_html(html_text)
    if not text:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    date = _parse_date(text)
    # 優先從股票/投資組合區塊開始，降低抓到頁首基金清單的機率。
    anchors = ["股票代號", "基金投資組合", "投資組合", "股票"]
    start = min([text.find(a) for a in anchors if text.find(a) >= 0] or [0])
    tail = text[start:start + 40000]
    # 避免附買回債券、其他資產、備註被吃進來。
    stop_pos = len(tail)
    for stop in ["附買回債券", "其他資產", "備註", "買回總價金", "基金經理公司"]:
        p = tail.find(stop)
        if p > 0:
            stop_pos = min(stop_pos, p)
    segment = tail[:stop_pos]
    tokens = _tokenize(segment)
    rows = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not _is_stock_code(tok, etf_code):
            i += 1
            continue
        code = _clean_code(tok)
        j = i + 1
        name_parts = []
        # 名稱可能有 *、英文縮寫；收集到第一個數字為止。
        while j < len(tokens) and not _is_stock_code(tokens[j], etf_code):
            if _looks_number(tokens[j]):
                # 例如「元大台灣50 10,871,000 1.46%」：50 是名稱的一部分，不是權重。
                if (name_parts and "%" not in tokens[j] and _to_float(tokens[j]) <= 100
                        and j + 1 < len(tokens) and _looks_number(tokens[j + 1]) and _to_float(tokens[j + 1]) > 100):
                    name_parts.append(tokens[j])
                    j += 1
                    continue
                break
            name_parts.append(tokens[j])
            j += 1
        nums = []
        k = j
        while k < len(tokens) and len(nums) < 2:
            if _looks_number(tokens[k]):
                nums.append(tokens[k])
                k += 1
                continue
            break
        if not name_parts or not nums:
            i += 1
            continue
        name = "".join(name_parts).strip()
        vals = [_to_float(x) for x in nums]
        weight = 0.0
        shares = 0.0
        # 常見兩種：code name weight shares（群益），或 code name shares weight（統一投資組合）。
        if len(vals) >= 2:
            a, b = vals[0], vals[1]
            if a <= 100 and ("%" in nums[0] or b > 100):
                weight, shares = a, b
            elif b <= 100:
                shares, weight = a, b
            elif a <= 100:
                weight = a
            else:
                shares = a
        elif vals[0] <= 100:
            weight = vals[0]
        else:
            shares = vals[0]
        if weight <= 0 or weight > 100:
            i += 1
            continue
        rows.append({
            "日期": date,
            "ETF代號": _clean_code(etf_code),
            "ETF名稱": etf_name or etf_code,
            "成分股代號": code,
            "成分股名稱": name,
            "權重": weight,
            "持有股數": shares,
            "來源": source_url,
        })
        i = max(k, i + 1)
    out = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    return _clean_rows(out, etf_code)


def _clean_rows(df: pd.DataFrame, etf_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    out = df.copy()
    for c in OUTPUT_COLUMNS:
        if c not in out.columns:
            out[c] = 0 if c in ["權重", "持有股數"] else ""
    out["成分股代號"] = out["成分股代號"].map(_clean_code)
    out["ETF代號"] = out["ETF代號"].map(_clean_code)
    out["權重"] = pd.to_numeric(out["權重"], errors="coerce").fillna(0.0)
    out["持有股數"] = pd.to_numeric(out["持有股數"], errors="coerce").fillna(0.0)
    bad_name = out["成分股名稱"].astype(str).str.contains(
        "合計|小計|現金|期貨|備註|申購|買回|債券|保證金|應收|應付|基金淨資產|ETF首頁|"
        "收益|費用|總價金|差額|預收|付款|幣別|交易日|基準日|淨值|單位數",
        na=False,
    )
    bad_code = out["成分股代號"].astype(str).str.contains(
        "ETF|PCF|NAV|TWD|USD|DATE|TOTAL|AMOUNT|CASH|PRICE|VALUE",
        na=False,
    )
    out = out[~bad_name & ~bad_code]
    out = out[(out["成分股代號"] != "") & (out["成分股代號"] != _clean_code(etf_code)) & (out["權重"] > 0) & (out["權重"] <= 100)]
    if out.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    # 同頁常有桌機/手機兩份重複資料；同一代號保留股數較完整的一筆。
    out["_rank"] = out["持有股數"].fillna(0)
    out = out.sort_values(["成分股代號", "_rank"], ascending=[True, False]).drop_duplicates("成分股代號", keep="first")
    out = out.drop(columns=["_rank"], errors="ignore")
    return out[OUTPUT_COLUMNS].reset_index(drop=True)



def _flatten_json_records(obj):
    """從未知 JSON 結構中找 list[dict] 候選。"""
    records = []
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            records.append(obj)
        for x in obj:
            records.extend(_flatten_json_records(x))
    elif isinstance(obj, dict):
        for v in obj.values():
            records.extend(_flatten_json_records(v))
    return records


def parse_official_response(text: str, etf_code: str, etf_name: str, source_url: str, content_type: str = "") -> pd.DataFrame:
    """解析 HTML / JSON response。Excel/PDF 目前只記錄候選，不解析 binary。"""
    if not text:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    ct = str(content_type or "").lower()
    if "json" in ct or text.strip().startswith(("{", "[")):
        try:
            obj = json.loads(text)
            best = pd.DataFrame(columns=OUTPUT_COLUMNS)
            date = _parse_date(text)
            for recs in _flatten_json_records(obj):
                try:
                    raw = pd.DataFrame(recs)
                    std = _standardize_table(raw, etf_code, etf_name, date, source_url)
                    if len(std) > len(best):
                        best = std
                except Exception:
                    continue
            if not best.empty:
                return best
        except Exception:
            pass
    return parse_official_holdings_html(text, etf_code, etf_name, source_url)



def _parse_moneydj_text(text: str, etf_code: str, etf_name: str, source_url: str) -> pd.DataFrame:
    """解析 MoneyDJ 持股頁常見的：台積電(2330.TW)4.54 138,000.00。"""
    if "moneydj.com" not in str(source_url).lower():
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    plain = _text_from_html(text)
    date = _parse_date(plain)
    rows = []
    # 先鎖定持股區之後，避免基本資料/配息表誤入。
    start = plain.find("個股名稱")
    if start < 0:
        start = plain.find("持股名稱")
    seg = plain[start if start >= 0 else 0:]
    # 台股/海外 ticker 都支援；權重後面常接持有股數。
    pat = re.compile(
        r"([^\n\r()（）]{1,30})[（(]\s*([0-9A-Z]{1,8})(?:\.(?:TW|TWO|US|O|N|K|HK))?\s*[)）]\s*"
        r"(-?\d+(?:\.\d+)?)\s*(?:%|％)?\s+([0-9,]+(?:\.\d+)?)",
        flags=re.I,
    )
    for name, code, weight, shares in pat.findall(seg):
        code = _clean_code(code)
        if not code or code == _clean_code(etf_code):
            continue
        rows.append({
            "日期": date,
            "ETF代號": _clean_code(etf_code),
            "ETF名稱": etf_name or etf_code,
            "成分股代號": code,
            "成分股名稱": str(name).strip(),
            "權重": _to_float(weight),
            "持有股數": _to_float(shares),
            "來源": source_url,
        })
    return _clean_rows(pd.DataFrame(rows, columns=OUTPUT_COLUMNS), etf_code)


def parse_official_holdings_html(html_text: str, etf_code: str, etf_name: str, source_url: str) -> pd.DataFrame:
    if not html_text:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    text = _text_from_html(html_text)
    date = _parse_date(text)
    best = pd.DataFrame(columns=OUTPUT_COLUMNS)
    # 1) 先試真正 HTML table。
    try:
        tables = pd.read_html(io.StringIO(html_text))
    except Exception:
        tables = []
    for t in tables:
        std = _standardize_table(t, etf_code, etf_name, date, source_url)
        if len(std) > len(best):
            best = std
    # 2) MoneyDJ 備援頁名稱欄常含代號，另外用專門 regex 補強。
    mdj_df = _parse_moneydj_text(html_text, etf_code, etf_name, source_url)
    if len(mdj_df) > len(best):
        best = mdj_df
    # 3) 官方頁常是 div/span 排版，不一定有 table；用文字序列解析。
    txt_df = _parse_text_rows(html_text, etf_code, etf_name, source_url)
    if len(txt_df) > len(best):
        best = txt_df
    return best


def source_quality(
    df: pd.DataFrame,
    min_rows: int = 10,
    min_weight_sum: float = 20.0,
    max_weight_sum: float = 110.0,
    reference_min_rows: int = 8,
    reference_min_weight_sum: float = 35.0,
) -> Tuple[bool, str, int, float]:
    """來源品質門檻。

    V37.11.1：把上限從 105% 放寬到 110%。統一 PCF/投資組合頁有時會
    把現金或四捨五入後的總和推到 105% 左右；這不應直接視為污染。真正混表
    通常會超過 120% 甚至 200%。
    """
    if df is None or df.empty:
        return False, "empty", 0, 0.0
    cnt = int(df["成分股代號"].nunique()) if "成分股代號" in df.columns else int(len(df))
    wsum = float(pd.to_numeric(df.get("權重", 0), errors="coerce").fillna(0).sum())
    if wsum > max_weight_sum:
        return False, f"權重合計>{max_weight_sum:.0f}%疑似重複/污染", cnt, wsum
    if cnt >= min_rows and wsum >= min_weight_sum:
        return True, "完整", cnt, wsum
    if cnt >= reference_min_rows and wsum >= reference_min_weight_sum:
        return True, "可參考", cnt, wsum

    reasons = []
    if cnt < reference_min_rows:
        reasons.append(f"持股數<{reference_min_rows}")
    if wsum < reference_min_weight_sum:
        reasons.append(f"權重合計<{reference_min_weight_sum:.0f}%")
    return False, "、".join(reasons), cnt, wsum




def _is_rejected_holding_source(url: str) -> bool:
    """V37.12.1：硬性排除非 holdings 頁，避免 interest/news/dividend 誤採用。"""
    s = str(url or "").lower()
    bad = [
        "interest", "news", "service", "dividend", "networth",
        "performance", "selection", "download-app", "fund-calendar"
    ]
    return any(x in s for x in bad)


def _short_url_for_report(url: str, max_len: int = 220) -> str:
    s = str(url or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "...[truncated]"



def _source_needs_playwright(etf_code: str, url: str) -> bool:
    if get_sources_for_etf is None:
        return False
    try:
        for s in get_sources_for_etf(etf_code):
            if str(getattr(s, "url", "")).strip() == str(url).strip():
                return bool(getattr(s, "needs_playwright", False))
    except Exception:
        return False
    return False


def _source_category_label(url: str, note: str = "") -> str:
    text = f"{url or ''} {note or ''}".lower()
    if "moneydj.com" in text or "cmoney" in text or "pocket" in text or "備援" in str(note):
        return "第三方備援"
    return "官方"


def _ok_status_for_source(url: str, note: str = "", default: str = "官方完整", quality_note: str = "完整") -> str:
    cat = _source_category_label(url, note)
    is_ref = "可參考" in str(quality_note)
    if cat == "第三方備援":
        return "🟡 第三方備援可參考" if is_ref else "✅ 第三方備援完整"
    if "Playwright" in str(default):
        return "🟡 Playwright可參考" if is_ref else "✅ Playwright完整"
    return f"🟡 {default}可參考" if is_ref else f"✅ {default}"

def _playwright_is_enabled() -> bool:
    if playwright_enabled is None or render_and_capture is None:
        return False
    try:
        return bool(playwright_enabled())
    except Exception:
        return False


def fetch_official_holding_one(etf_code: str, etf_name: str = "") -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
    """官方來源單檔抓取。

    V37.11：
    1. 先跑 registry 固定官方 URL。
    2. 若沒有完整資料，對官方入口做 probe，掃描 deeper API / download / JSON / PCF 候選。
    3. 權重合計過高視為疑似污染，不採用。
    """
    code = _clean_code(etf_code)
    sources = OFFICIAL_SOURCE_REGISTRY.get(code, [])
    reports: List[Dict[str, object]] = []
    best = pd.DataFrame(columns=OUTPUT_COLUMNS)

    for src in sources:
        html_text = _fetch_html(src.url)
        df = parse_official_response(html_text, code, etf_name or code, src.url, "text/html")
        ok, reason, cnt, wsum = source_quality(df)
        if _is_rejected_holding_source(src.url):
            ok = False
            reason = "疑似非持股來源頁"
        reports.append({
            "ETF代號": code,
            "ETF名稱": etf_name or code,
            "投信": src.issuer,
            "來源類別": _source_category_label(src.url, src.note),
            "來源": src.url,
            "類型": src.note,
            "抓到筆數": cnt,
            "權重合計": round(wsum, 4),
            "狀態": _ok_status_for_source(src.url, src.note, "官方完整", reason) if ok else f"⚠️ {reason}",
            "採用": bool(ok),
            "需要Playwright": bool(_source_needs_playwright(code, src.url)),
        })
        if len(df) > len(best):
            best = df
        if ok:
            return df, reports
        time.sleep(0.35)

    if sources and probe_official_urls is not None and probe_fetch_url is not None:
        try:
            candidates = probe_official_urls([s.url for s in sources], etf_code=code, max_candidates_per_source=25)
        except Exception:
            candidates = []

        seen = {r.get("來源") for r in reports}
        for cand in candidates:
            if cand.url in seen:
                continue

            if re.search(r"\\.(pdf|xlsx?|zip)(\\?|$)", cand.url, re.I):
                reports.append({
                    "ETF代號": code,
                    "ETF名稱": etf_name or code,
                    "投信": sources[0].issuer if sources else "",
                    "來源類別": "官方偵察",
                    "來源": _short_url_for_report(cand.url),
                    "類型": f"{cand.kind}:{cand.source_hint}",
                    "抓到筆數": 0,
                    "權重合計": 0.0,
                    "狀態": "⚠️ binary_candidate_not_parsed",
                    "採用": False,
                })
                continue

            text, ct = probe_fetch_url(cand.url)
            if any(x in str(ct).lower() for x in ["pdf", "excel", "spreadsheet"]):
                reports.append({
                    "ETF代號": code,
                    "ETF名稱": etf_name or code,
                    "投信": sources[0].issuer if sources else "",
                    "來源類別": "官方偵察",
                    "來源": _short_url_for_report(cand.url),
                    "類型": f"{cand.kind}:{cand.source_hint}",
                    "抓到筆數": 0,
                    "權重合計": 0.0,
                    "狀態": "⚠️ binary_candidate_not_parsed",
                    "採用": False,
                })
                continue

            df = parse_official_response(text, code, etf_name or code, cand.url, ct)
            ok, reason, cnt, wsum = source_quality(df)
            if _is_rejected_holding_source(cand.url):
                ok = False
                reason = "疑似非持股來源頁"
            reports.append({
                "ETF代號": code,
                "ETF名稱": etf_name or code,
                "投信": sources[0].issuer if sources else "",
                "來源類別": "官方偵察",
                "來源": _short_url_for_report(cand.url),
                "類型": f"{cand.kind}:{cand.source_hint}",
                "抓到筆數": cnt,
                "權重合計": round(wsum, 4),
                "狀態": _ok_status_for_source(cand.url, f"{cand.kind}:{cand.source_hint}", "官方偵察完整", reason) if ok else f"⚠️ {reason}",
                "採用": bool(ok),
            })
            if len(df) > len(best):
                best = df
            if ok:
                return df, reports
            time.sleep(0.25)



    # V37.11：一般 requests / probe 都失敗後，才啟用 Playwright 攻堅。
    # 只在 GitHub Actions / 本機 ETL 設定 ACTIVE_ETF_ENABLE_PLAYWRIGHT=1 時執行；Streamlit 前端不會跑。
    if sources and _playwright_is_enabled():
        pw_urls = [src.url for src in sources if _source_needs_playwright(code, src.url)]
        # 如果 registry 只有入口但沒標記，仍允許對來源做一次保守渲染。
        if not pw_urls:
            pw_urls = [src.url for src in sources[:2]]
        try:
            rendered_items = render_and_capture(pw_urls, etf_code=code)
        except Exception as exc:
            rendered_items = []
            reports.append({
                "ETF代號": code,
                "ETF名稱": etf_name or code,
                "投信": sources[0].issuer if sources else "",
                "來源類別": "官方Playwright",
                "來源": " / ".join(pw_urls[:3]),
                "類型": "playwright-error",
                "抓到筆數": 0,
                "權重合計": 0.0,
                "狀態": f"⚠️ playwright_failed:{type(exc).__name__}",
                "採用": False,
                "需要Playwright": True,
            })

        for item in rendered_items:
            df = parse_official_response(item.text, code, etf_name or code, item.url, item.content_type)
            ok, reason, cnt, wsum = source_quality(df)
            if _is_rejected_holding_source(item.url):
                ok = False
                reason = "疑似非持股來源頁"
            reports.append({
                "ETF代號": code,
                "ETF名稱": etf_name or code,
                "投信": sources[0].issuer if sources else "",
                "來源類別": "官方Playwright",
                "來源": _short_url_for_report(item.url),
                "類型": item.kind,
                "抓到筆數": cnt,
                "權重合計": round(wsum, 4),
                "狀態": _ok_status_for_source(item.url, item.kind, "Playwright", reason) if ok else f"⚠️ {reason}",
                "採用": bool(ok),
                "需要Playwright": True,
            })
            if len(df) > len(best):
                best = df
            if ok:
                return df, reports
            time.sleep(0.15)

    if not sources:
        reports.append({
            "ETF代號": code,
            "ETF名稱": etf_name or code,
            "投信": "",
            "來源類別": "官方",
            "來源": "",
            "類型": "未設定官方來源",
            "抓到筆數": 0,
            "權重合計": 0.0,
            "狀態": "⚠️ no_official_source",
            "採用": False,
        })
    return best, reports


def fetch_official_holdings_auto(candidates: Tuple[Tuple[str, str], ...]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    frames = []
    all_reports: List[Dict[str, object]] = []
    for code, name in candidates:
        df, reports = fetch_official_holding_one(code, name)
        all_reports.extend(reports)
        ok, _, _, _ = source_quality(df)
        if ok:
            frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
    report = pd.DataFrame(all_reports)
    return out, report
