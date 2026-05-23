# -*- coding: utf-8 -*-
"""
V38 Daily Intel Engine
- GitHub Actions / local CLI: fetch news, classify topics, cross-check with ETF / signal outputs, write JSON/CSV.
- Streamlit front-end: render the generated JSON only. No live crawling in app.py.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
import time
import html
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import pandas as pd
import requests

TW_TZ = timezone(timedelta(hours=8))
DEFAULT_OUT = Path("data/intel_daily.json")
DEFAULT_RAW = Path("data/intel_news_raw.csv")

TOPICS: Dict[str, List[str]] = {
    "AI伺服器": ["AI伺服器", "AI server", "GB200", "GB300", "Blackwell", "CoWoS", "輝達", "NVIDIA", "散熱", "液冷"],
    "半導體": ["半導體", "台積電", "TSMC", "晶圓", "先進製程", "封測", "IC設計", "ASIC"],
    "PCB/ABF": ["PCB", "ABF", "載板", "欣興", "南電", "華通", "臻鼎", "金像電", "高階板"],
    "記憶體": ["記憶體", "DRAM", "NAND", "HBM", "華邦電", "南亞科", "群聯", "威剛"],
    "金融": ["金融股", "銀行", "壽險", "金控", "殖利率", "股息", "配息"],
    "高息/主動ETF": ["主動式ETF", "主動 ETF", "高息ETF", "009", "ETF", "經理人", "持股"],
    "台股大盤": ["台股", "加權指數", "台北股市", "外資", "投信", "融資", "台幣", "匯率"],
    "美股科技": ["Nasdaq", "那斯達克", "費半", "SOX", "美股", "科技股", "Apple", "Microsoft", "Meta", "AMD"],
    "利率/總經": ["Fed", "聯準會", "降息", "升息", "通膨", "CPI", "PCE", "美債", "利率", "美元"],
}

POS_WORDS = ["上修", "成長", "創高", "優於", "看好", "需求強", "擴產", "加碼", "買超", "利多", "突破", "回補", "大漲", "strong", "beat", "upgrade", "growth", "record"]
NEG_WORDS = ["下修", "衰退", "不如", "賣超", "利空", "跌破", "大跌", "庫存", "警訊", "裁員", "制裁", "延後", "overheat", "miss", "downgrade", "weak", "risk"]

NEWS_QUERIES = {
    "台股大盤": "台股 OR 加權指數 OR 外資 投信",
    "AI伺服器": "AI伺服器 OR NVIDIA OR GB200 OR CoWoS OR 散熱",
    "半導體": "台積電 OR 半導體 OR 晶圓 OR IC設計",
    "PCB/ABF": "PCB OR ABF OR 載板 OR 南電 OR 欣興",
    "記憶體": "記憶體 OR DRAM OR HBM OR NAND",
    "主動ETF": "主動式ETF OR 主動 ETF OR ETF 持股",
    "美股科技": "那斯達克 OR 費半 OR NVIDIA OR 美股科技",
    "總經": "Fed OR 聯準會 OR 降息 OR 通膨 OR 美債",
}


def _now_tw() -> datetime:
    return datetime.now(TW_TZ)


def _clean_text(s: Any) -> str:
    s = html.unescape(str(s or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _article_key(title: str, url: str) -> str:
    t = re.sub(r"\W+", "", title.lower())[:60]
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
    return f"{host}:{t}"


def _request_json(url: str, timeout: int = 15) -> Dict[str, Any]:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 StockArmoryIntel/1.0"})
    r.raise_for_status()
    return r.json()


def _request_text(url: str, timeout: int = 15) -> str:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 StockArmoryIntel/1.0"})
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def fetch_gdelt(query: str, max_records: int = 25, timespan: str = "24h") -> List[Dict[str, Any]]:
    q = quote_plus(query)
    url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist&maxrecords={max_records}&format=json&sort=hybridrel&timespan={timespan}"
    try:
        data = _request_json(url)
        rows = data.get("articles", []) if isinstance(data, dict) else []
    except Exception as e:
        return [{"source_engine": "GDELT", "error": str(e), "query": query}]
    out = []
    for a in rows:
        title = _clean_text(a.get("title"))
        if not title:
            continue
        out.append({
            "source_engine": "GDELT",
            "query": query,
            "title": title,
            "url": a.get("url", ""),
            "source": a.get("sourceCommonName") or a.get("domain") or "",
            "published": a.get("seendate") or a.get("publishedDate") or "",
            "snippet": _clean_text(a.get("snippet", "")),
        })
    return out


def fetch_google_rss(query: str, max_records: int = 20) -> List[Dict[str, Any]]:
    q = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        text = _request_text(url)
        root = ET.fromstring(text)
    except Exception as e:
        return [{"source_engine": "GoogleNewsRSS", "error": str(e), "query": query}]
    items = []
    for item in root.findall(".//item")[:max_records]:
        title = _clean_text(item.findtext("title"))
        link = _clean_text(item.findtext("link"))
        pub = _clean_text(item.findtext("pubDate"))
        desc = _clean_text(item.findtext("description"))
        if title:
            items.append({
                "source_engine": "GoogleNewsRSS",
                "query": query,
                "title": title,
                "url": link,
                "source": "Google News",
                "published": pub,
                "snippet": desc,
            })
    return items


def collect_news(max_per_query: int = 20) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for topic, query in NEWS_QUERIES.items():
        batch = fetch_gdelt(query, max_records=max_per_query)
        # GDELT occasionally has thin Chinese coverage; RSS is a fallback and de-duplicated.
        batch += fetch_google_rss(query, max_records=max(8, max_per_query // 2))
        for r in batch:
            if r.get("error"):
                rows.append({**r, "seed_topic": topic})
                continue
            key = _article_key(r.get("title", ""), r.get("url", ""))
            if key in seen:
                continue
            seen.add(key)
            rows.append({**r, "seed_topic": topic})
        time.sleep(0.25)
    return rows


def classify_article(row: Dict[str, Any]) -> Tuple[List[str], int, str]:
    text = f"{row.get('title','')} {row.get('snippet','')} {row.get('query','')}"
    hit_topics = []
    for topic, kws in TOPICS.items():
        if any(k.lower() in text.lower() for k in kws):
            hit_topics.append(topic)
    if not hit_topics and row.get("seed_topic"):
        hit_topics = [str(row.get("seed_topic"))]
    pos = sum(1 for w in POS_WORDS if w.lower() in text.lower())
    neg = sum(1 for w in NEG_WORDS if w.lower() in text.lower())
    score = pos - neg
    tone = "偏多" if score > 0 else ("偏空" if score < 0 else "中性")
    return hit_topics[:4], score, tone


def _load_json(path: str | Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _read_csv_safe(path: str | Path) -> pd.DataFrame:
    try:
        p = Path(path)
        if p.exists():
            return pd.read_csv(p)
    except Exception:
        pass
    return pd.DataFrame()


def _topic_from_industry_name(name: str) -> str:
    s = str(name or "")
    if any(k in s for k in ["半導體", "電子", "電腦", "其他電子", "通信", "資訊"]):
        return "半導體"
    if any(k in s for k in ["零組件", "PCB", "載板"]):
        return "PCB/ABF"
    if any(k in s for k in ["金融", "銀行", "保險"]):
        return "金融"
    return s or "未知"


def build_intel(news_rows: List[Dict[str, Any]], etf_report_path="data/active_etf_etl_report.json", signal_path="data/signal_history.csv") -> Dict[str, Any]:
    topic_stats: Dict[str, Dict[str, Any]] = {}
    clean_rows = []
    for r in news_rows:
        if r.get("error"):
            continue
        topics, score, tone = classify_article(r)
        if not topics:
            continue
        rr = dict(r)
        rr["topics"] = topics
        rr["tone_score"] = score
        rr["tone"] = tone
        clean_rows.append(rr)
        for topic in topics:
            stat = topic_stats.setdefault(topic, {"topic": topic, "news_count": 0, "tone_sum": 0, "examples": []})
            stat["news_count"] += 1
            stat["tone_sum"] += score
            if len(stat["examples"]) < 3:
                stat["examples"].append({"title": rr.get("title", ""), "source": rr.get("source", ""), "url": rr.get("url", ""), "tone": tone})

    # ETF direction cross-check: parse latest ETL quality if available.
    etf_report = _load_json(etf_report_path)
    etf_quality = etf_report.get("quality", []) if isinstance(etf_report, dict) else []
    complete = set(map(str, etf_report.get("complete_etfs", []))) if isinstance(etf_report, dict) else set()
    usable_count = len(complete)
    candidate_count = int(etf_report.get("candidate_count", 0) or max(usable_count, 1)) if isinstance(etf_report, dict) else max(usable_count, 1)

    industry_votes: Dict[str, float] = {}
    for q in etf_quality:
        # Current quality only has 產業數, not actual industries; keep coverage signal only.
        pass

    # Signal history cross-check: use latest day S/A/B industries as simple盤面驗證.
    sig = _read_csv_safe(signal_path)
    market_topics: Dict[str, int] = {}
    if not sig.empty:
        try:
            date_col = "日期" if "日期" in sig.columns else ("date" if "date" in sig.columns else None)
            latest = sig[date_col].max() if date_col else None
            ss = sig[sig[date_col].eq(latest)].copy() if latest is not None else sig.tail(100).copy()
            grade_col = "評級" if "評級" in ss.columns else ("grade" if "grade" in ss.columns else None)
            if grade_col:
                ss = ss[ss[grade_col].astype(str).isin(["S", "A", "B", "特殊關注"])]
            ind_col = "產業" if "產業" in ss.columns else None
            if ind_col:
                for x in ss[ind_col].astype(str).head(100):
                    topic = _topic_from_industry_name(x)
                    market_topics[topic] = market_topics.get(topic, 0) + 1
        except Exception:
            market_topics = {}

    topic_list = []
    for topic, stat in topic_stats.items():
        heat = int(stat["news_count"])
        tone_sum = int(stat["tone_sum"])
        market_hits = int(market_topics.get(topic, 0))
        etf_verified = usable_count >= max(8, candidate_count * 0.5)
        if heat >= 8 and market_hits >= 2 and etf_verified:
            trust = "A"
            trust_label = "A級｜新聞＋盤面＋ETF覆蓋同向"
        elif heat >= 5 and (market_hits >= 1 or etf_verified):
            trust = "B"
            trust_label = "B級｜新聞主線有盤面/ETF部分驗證"
        elif heat >= 3:
            trust = "C"
            trust_label = "C級｜只有新聞熱度，先看不追"
        else:
            trust = "D"
            trust_label = "D級｜雜訊偏多"
        topic_list.append({
            "topic": topic,
            "news_count": heat,
            "tone_score": tone_sum,
            "tone": "偏多" if tone_sum > 0 else ("偏空" if tone_sum < 0 else "中性"),
            "market_hits": market_hits,
            "trust": trust,
            "trust_label": trust_label,
            "examples": stat.get("examples", []),
        })
    topic_list.sort(key=lambda x: (x["trust"] in ["A", "B"], x["news_count"], abs(x["tone_score"])), reverse=True)

    top_topics = topic_list[:5]
    top_names = "、".join([t["topic"] for t in top_topics[:3]]) if top_topics else "暫無明顯新聞主線"
    coverage = usable_count / candidate_count * 100 if candidate_count else 0
    if top_topics:
        main_tone = top_topics[0]["tone"]
        summary_1 = f"今日新聞主線集中在 {top_names}，整體語氣偏{main_tone.replace('偏','')}。"
    else:
        summary_1 = "今日新聞主線不明顯，情報局以盤面與持股風控為主。"
    summary_2 = f"主動ETF資料覆蓋 {usable_count}/{candidate_count} 檔，約 {coverage:.0f}%，可用來判斷經理人大方向。"
    if any(t["trust"] in ["A", "B"] for t in top_topics):
        summary_3 = "新聞若與ETF重倉、法人籌碼、S/A/B族群同向，可視為主線被盤面承認；仍不直接當買進訊號。"
    else:
        summary_3 = "目前偏新聞熱度，盤面驗證不足；適合當背景，不適合追價。"

    risks = []
    if any(t["tone"] == "偏多" and t["news_count"] >= 10 for t in top_topics):
        risks.append("熱門新聞過熱時，若強股跌破開盤價，容易變成獲利了結。")
    if coverage < 70:
        risks.append("ETF資料覆蓋未滿 70%，主動ETF方向只能看大概，不能當精準調倉證據。")
    if not risks:
        risks.append("新聞只解釋背景；實際進出仍以沙盤推演、開盤價戰法與持股風控為準。")

    return {
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "local_date": _now_tw().strftime("%Y-%m-%d"),
        "summary": [summary_1, summary_2, summary_3],
        "topics": topic_list,
        "risks": risks,
        "market_validation": {
            "signal_topics": market_topics,
            "active_etf_coverage": {"usable": usable_count, "candidate_count": candidate_count, "coverage_pct": round(coverage, 1)},
        },
        "representative_news": clean_rows[:60],
        "source_note": "GDELT + Google News RSS；前端只讀 data/intel_daily.json，不即時抓新聞。",
    }


def write_outputs(intel: Dict[str, Any], news_rows: List[Dict[str, Any]], out_path: str | Path = DEFAULT_OUT, raw_path: str | Path = DEFAULT_RAW) -> None:
    out = Path(out_path)
    raw = Path(raw_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(intel, f, ensure_ascii=False, indent=2)
    cols = ["source_engine", "seed_topic", "title", "source", "published", "url", "snippet", "query"]
    with raw.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in news_rows:
            w.writerow(r)


def generate_daily_intel(out_path: str | Path = DEFAULT_OUT, raw_path: str | Path = DEFAULT_RAW) -> Dict[str, Any]:
    news = collect_news()
    intel = build_intel(news)
    write_outputs(intel, news, out_path, raw_path)
    return intel


def load_daily_intel(path: str | Path = DEFAULT_OUT) -> Dict[str, Any]:
    return _load_json(path)


def _safe(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


def render_daily_intel_panel(st, COLORS: Dict[str, str], table_style: Dict[str, Any] | None = None, path: str = "data/intel_daily.json") -> None:
    table_style = table_style or {"text-align": "center"}
    intel = load_daily_intel(path)
    st.markdown("#### 📡 今日新聞情報總結")
    if not intel:
        st.info("尚未產生每日新聞情報。請先讓 GitHub Actions 執行 Update Daily Intel；前端不即時抓新聞，避免拖慢戰情室。")
        with st.expander("建議設定", expanded=False):
            st.code("Actions → Update Daily Intel → Run workflow\n或等待台股收盤後自動更新 data/intel_daily.json", language="text")
        return
    summary = intel.get("summary", []) or []
    risks = intel.get("risks", []) or []
    topics = intel.get("topics", []) or []
    coverage = ((intel.get("market_validation") or {}).get("active_etf_coverage") or {})
    cov_txt = f"ETF覆蓋 {coverage.get('usable','-')}/{coverage.get('candidate_count','-')}｜{coverage.get('coverage_pct','-')}%"

    lines = "".join([f"<div style='margin:3px 0;'>・{_safe(x)}</div>" for x in summary[:3]])
    risk_line = "；".join(map(str, risks[:2])) if risks else "新聞只作背景，沙盤才是決策。"
    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['primary']}; border-radius:12px; padding:13px 15px; margin:8px 0 14px 0;">
        <div style="font-size:16px; font-weight:900; color:{COLORS['text']}; margin-bottom:6px;">🧭 情報局三句話</div>
        <div style="font-size:13.5px; color:{COLORS['text']}; line-height:1.6;">{lines}</div>
        <div style="font-size:12.5px; color:{COLORS['subtext']}; margin-top:8px; line-height:1.45;">{_safe(cov_txt)}｜{_safe(risk_line)}</div>
    </div>
    """, unsafe_allow_html=True)

    if topics:
        cols = st.columns(min(3, len(topics)))
        for col, t in zip(cols, topics[:3]):
            trust = str(t.get("trust", "C"))
            color = COLORS.get("green") if trust == "A" else (COLORS.get("primary") if trust == "B" else COLORS.get("accent"))
            with col:
                st.markdown(f"""
                <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-top:4px solid {color}; border-radius:12px; padding:12px 14px; min-height:155px;">
                    <div style="font-size:18px; font-weight:900; color:{color};">{_safe(t.get('topic',''))}</div>
                    <div style="font-size:13px; color:{COLORS['text']}; line-height:1.6; margin-top:6px;">
                        新聞 {t.get('news_count',0)} 則｜語氣 {t.get('tone','中性')}<br>
                        盤面命中 {t.get('market_hits',0)}｜可信 {trust}級
                    </div>
                    <div style="font-size:12px; color:{COLORS['subtext']}; line-height:1.45; margin-top:6px;">{_safe(t.get('trust_label',''))}</div>
                </div>
                """, unsafe_allow_html=True)

    with st.expander("📰 代表新聞與主題分級", expanded=False):
        rows = []
        for t in topics[:8]:
            examples = t.get("examples", []) or []
            rows.append({
                "主題": t.get("topic", ""),
                "可信度": t.get("trust_label", ""),
                "新聞數": t.get("news_count", 0),
                "語氣": t.get("tone", ""),
                "代表新聞": "；".join([e.get("title", "")[:42] for e in examples[:2]]),
            })
        if rows:
            st.dataframe(pd.DataFrame(rows).style.set_properties(**table_style), use_container_width=True, hide_index=True, height=260)
        else:
            st.caption("今日沒有足夠代表新聞。")


if __name__ == "__main__":
    try:
        out = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_OUT)
        raw = sys.argv[2] if len(sys.argv) > 2 else str(DEFAULT_RAW)
        intel = generate_daily_intel(out, raw)
        print(json.dumps({"ok": True, "out": out, "topics": [t.get("topic") for t in intel.get("topics", [])[:5]]}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        raise
