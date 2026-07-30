# -*- coding: utf-8 -*-
"""
market_risk_provider.py — 大盤風險燈號引擎(ETL + 計分)
--------------------------------------------------------
定位:get_macro_dashboard() 只看國際指數 vs 月線;本模組補上台股特有的
籌碼與內部結構,合成一個「該踩油門還是煞車」的 0–100 風險分數。

四維度(彼此獨立,權重 30/25/25/20):
1. 籌碼:外資台指期未平倉淨口數(期交所 futContractsDateDown)
2. 槓桿:融資餘額5日增速 − 大盤5日漲幅(TWSE MI_MARGN + FMTQIK)
3. 廣度:上市個股站上60MA比例、騰落家數(TWSE MI_INDEX,自建收盤歷史)
4. 國際:費半SOX 60MA乖離與5日報酬、台積電ADR溢價(yfinance)

方向統一:分數越高 = 風險越高。≥65 紅 / 40–65 黃 / <40 綠。
有近一年歷史採百分位計分;冷啟動期退回絕對門檻。

輸出(GitHub Actions 產出、Streamlit 唯讀,同 intel_daily 模式):
- data/market_risk_history.csv          每日一列:原始訊號 + 分數 + 燈號
- data/market_breadth_close_history.csv.gz  廣度計算用個股收盤滾動歷史(90日)

CLI:
    python market_risk_provider.py                 # 跑今天
    python market_risk_provider.py --backfill 90   # 回填廣度收盤歷史(冷啟動用,約4分鐘)

防斷線:四個維度各自 try/except;單一來源失敗該維度當日缺席,
合成分數按剩餘權重重新正規化,不會整條 ETL 掛掉。
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from net_utils import build_session, smart_get

TAIPEI_TZ = timezone(timedelta(hours=8))

RISK_HISTORY_PATH = "data/market_risk_history.csv"
BREADTH_CLOSE_PATH = "data/market_breadth_close_history.csv.gz"

WEIGHTS = {"score_chip": 0.30, "score_leverage": 0.25, "score_breadth": 0.25, "score_intl": 0.20}
RED_TH, YELLOW_TH = 65, 40
BREADTH_KEEP_DAYS = 90       # 收盤歷史只留 90 個交易日,控制檔案大小(~2MB gz)
BREADTH_MIN_DAYS = 60        # 60MA 需要的最少歷史


def _session():
    return build_session(with_retry=True)


def _num(s) -> pd.Series:
    return pd.to_numeric(
        pd.Series(s).astype(str).str.replace(",", "", regex=False).str.replace("--", "", regex=False),
        errors="coerce",
    )


def _is_stock_code(code: str) -> bool:
    """同 chips_provider:只留一般上市四碼股票,排除 ETF/ETN(00 開頭)與權證。"""
    code = re.sub(r"[^0-9A-Z]", "", str(code or "").strip().upper())
    return bool(re.fullmatch(r"\d{4}", code)) and not code.startswith("00")


# ================================================================ S1 籌碼
def fetch_taifex_foreign_oi(date) -> Optional[int]:
    """期交所三大法人期貨(TX):外資多空未平倉口數淨額。非交易日回 None。"""
    url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
    payload = {
        "firstDate": "2000/01/01 00:00",
        "queryStartDate": date.strftime("%Y/%m/%d"),
        "queryEndDate": date.strftime("%Y/%m/%d"),
        "commodityId": "TXF",
    }
    r = _session().post(url, data=payload, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.content.decode("big5", errors="replace")))
    df.columns = [str(c).strip() for c in df.columns]
    id_col = next((c for c in df.columns if "身份別" in c or "身分別" in c), None)
    oi_col = next((c for c in df.columns if "未平倉" in c and "淨額" in c and "口數" in c), None)
    if not id_col or not oi_col or df.empty:
        return None
    foreign = df[df[id_col].astype(str).str.contains("外資")]
    if foreign.empty:
        return None
    v = _num(foreign[oi_col]).iloc[0]
    return None if pd.isna(v) else int(v)


# ================================================================ S2 槓桿
def fetch_margin_and_index(date) -> Optional[dict]:
    """TWSE 融資餘額(仟元)+ 大盤收盤。非交易日回 None。"""
    d8 = date.strftime("%Y%m%d")
    s = _session()

    j = smart_get(
        f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d8}&selectType=MS&response=json",
        session=s, timeout=30,
    ).json()
    if j.get("stat") != "OK":
        return None
    margin_total = None
    for tbl in j.get("tables", []):
        for row in tbl.get("data", []):
            cells = [str(c) for c in row]
            if cells and "融資金額" in cells[0]:
                margin_total = float(_num([cells[-1]]).iloc[0])   # 最後一欄 = 今日餘額
    if margin_total is None:
        return None

    j2 = smart_get(
        f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={d8}&response=json",
        session=s, timeout=30,
    ).json()
    roc = f"{date.year - 1911}/{date.month:02d}/{date.day:02d}"
    taiex_close = None
    for row in j2.get("data", []):
        if str(row[0]).strip() == roc:
            taiex_close = float(_num([row[4]]).iloc[0])
    if taiex_close is None:
        return None
    return {"margin_balance_k": margin_total, "taiex_close": taiex_close}


# ================================================================ S3 廣度
def fetch_all_close(date) -> Optional[pd.DataFrame]:
    """TWSE MI_INDEX(每日收盤行情,type=ALLBUT0999):全上市個股收盤價。

    這個端點可以查歷史任一日,所以冷啟動可用 --backfill 直接補滿 60MA 所需歷史,
    不必等 60 個交易日或依賴 FinMind。
    """
    d8 = date.strftime("%Y%m%d")
    j = smart_get(
        f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={d8}&type=ALLBUT0999&response=json",
        session=_session(), timeout=60,
    ).json()
    if j.get("stat") != "OK":
        return None
    tbl = None
    for t in j.get("tables", []):
        if "每日收盤行情" in str(t.get("title", "")) and t.get("data"):
            tbl = t
    if tbl is None:
        return None
    fields = [str(f) for f in tbl.get("fields", [])]
    try:
        i_code = next(i for i, f in enumerate(fields) if "證券代號" in f)
        i_close = next(i for i, f in enumerate(fields) if "收盤價" in f)
    except StopIteration:
        return None
    recs = []
    for row in tbl["data"]:
        code = str(row[i_code]).strip()
        if not _is_stock_code(code):
            continue
        close = _num([row[i_close]]).iloc[0]
        if pd.isna(close) or close <= 0:
            continue
        recs.append({"date": str(date), "code": code, "close": float(close)})
    return pd.DataFrame(recs) if recs else None


def upsert_breadth_history(day_df: pd.DataFrame) -> pd.DataFrame:
    """把單日收盤併入滾動歷史(同日覆蓋),只留近 BREADTH_KEEP_DAYS 個交易日。"""
    try:
        hist = pd.read_csv(BREADTH_CLOSE_PATH, dtype={"date": str, "code": str})
    except Exception:
        hist = pd.DataFrame(columns=["date", "code", "close"])
    dates_new = set(day_df["date"].unique())
    hist = hist[~hist["date"].isin(dates_new)]
    hist = pd.concat([hist, day_df], ignore_index=True)
    keep = sorted(hist["date"].unique())[-BREADTH_KEEP_DAYS:]
    hist = hist[hist["date"].isin(keep)].sort_values(["date", "code"]).reset_index(drop=True)
    hist.to_csv(BREADTH_CLOSE_PATH, index=False, compression="gzip")
    return hist


def compute_breadth(hist: pd.DataFrame) -> dict:
    """由收盤歷史算:騰落家數(對前一交易日)、站上60MA比例。"""
    out: dict = {}
    pv = hist.pivot_table(index="date", columns="code", values="close").sort_index()
    if len(pv) >= 2:
        diff = pv.iloc[-1] - pv.iloc[-2]
        adv, dec = int((diff > 0).sum()), int((diff < 0).sum())
        out.update({"advancers": adv, "decliners": dec, "adv_dec_ratio": round(adv / max(dec, 1), 3)})
    if len(pv) >= BREADTH_MIN_DAYS:
        ma60 = pv.rolling(BREADTH_MIN_DAYS).mean().iloc[-1]
        last = pv.iloc[-1]
        valid = last.notna() & ma60.notna()
        if int(valid.sum()) > 100:
            out["pct_above_ma60"] = round(float((last[valid] > ma60[valid]).mean() * 100), 2)
    return out


# ================================================================ S4 國際
def fetch_intl() -> Optional[dict]:
    """SOX 乖離/5日報酬 + 台積電ADR溢價。抓到的是台股收盤前最後可得的美股資料。"""
    import yfinance as yf  # 延遲載入:CLI 失敗不拖累其他維度

    def closes(sym, period="6mo"):
        return yf.Ticker(sym).history(period=period)["Close"].dropna()

    sox = closes("^SOX")
    if len(sox) < 61:
        return None
    c, ma60 = float(sox.iloc[-1]), float(sox.rolling(60).mean().iloc[-1])
    out = {
        "sox_bias_ma60_pct": round((c / ma60 - 1) * 100, 2),
        "sox_ret_5d_pct": round((c / float(sox.iloc[-6]) - 1) * 100, 2),
    }
    try:
        tsm = float(closes("TSM", "1mo").iloc[-1])
        tw = float(closes("2330.TW", "1mo").iloc[-1])
        fx = float(closes("TWD=X", "1mo").iloc[-1])
        out["adr_premium_pct"] = round((tsm * fx / (tw * 5) - 1) * 100, 2)  # 1 ADR = 5 普通股
    except Exception:
        pass
    return out


# ================================================================ 計分
def _pct_score(series: pd.Series, value: float, invert: bool = False) -> float:
    """近一年(252筆)百分位 → 0~100 風險分;歷史 <60 筆回 NaN 讓呼叫端走絕對門檻。"""
    s = pd.to_numeric(series, errors="coerce").dropna().tail(252)
    if len(s) < 60:
        return float("nan")
    pct = float((s < value).mean() * 100)
    return 100 - pct if invert else pct


def compute_scores(hist: pd.DataFrame, today: dict) -> dict:
    """hist = 既有 market_risk_history(不含今日);today = 今日原始訊號。"""
    out = dict(today)

    # S1 外資期貨淨OI:越空風險越高
    v = today.get("foreign_tx_net_oi")
    if v is not None and pd.notna(v):
        s1 = _pct_score(hist.get("foreign_tx_net_oi", pd.Series(dtype=float)), v, invert=True)
        if pd.isna(s1):
            s1 = 85 if v < -30000 else 65 if v < -15000 else 45 if v < 0 else 25
        out["score_chip"] = round(float(s1), 1)

    # S2 融資5日增速 − 指數5日漲幅:融資追價越兇風險越高
    if today.get("margin_balance_k") is not None:
        m = pd.concat([hist, pd.DataFrame([today])], ignore_index=True)
        if m["margin_balance_k"].notna().sum() >= 6:
            # fill_method=None:維度缺席日留 NaN,不做前向填補(pandas 2.x 相容)
            gap_series = (
                m["margin_balance_k"].pct_change(5, fill_method=None)
                - m["taiex_close"].pct_change(5, fill_method=None)
            ) * 100
            gap = float(gap_series.iloc[-1])
            if pd.notna(gap):
                s2 = _pct_score(gap_series.iloc[:-1], gap)
                if pd.isna(s2):
                    s2 = 80 if gap > 3 else 60 if gap > 1.5 else 40 if gap > 0 else 25
                out["margin_minus_index_5d_pct"] = round(gap, 2)
                out["score_leverage"] = round(float(s2), 1)

    # S3 站上60MA比例:<50% 起算風險越低越危險;>85% 過熱給小幅風險
    p60 = today.get("pct_above_ma60")
    if p60 is not None and pd.notna(p60):
        s3 = 55.0 if p60 >= 85 else max(0.0, min(100.0, (55 - float(p60)) * 2.2 + 30))
        out["score_breadth"] = round(s3, 1)

    # S4 SOX:跌破60MA越深、5日急跌加風險;站穩均線降風險
    bias, ret5 = today.get("sox_bias_ma60_pct"), today.get("sox_ret_5d_pct")
    if bias is not None and ret5 is not None:
        s4 = 50.0
        s4 += min(30, max(0, -float(bias) * 3))
        s4 += min(20, max(0, -float(ret5) * 2.5))
        s4 -= min(20, max(0, min(float(bias), 8) * 1.5))
        out["score_intl"] = round(max(0.0, min(100.0, s4)), 1)

    avail = {k: w for k, w in WEIGHTS.items() if out.get(k) is not None}
    if avail:
        comp = sum(out[k] * w for k, w in avail.items()) / sum(avail.values())
        out["composite_risk"] = round(comp, 1)
        out["light"] = "紅" if comp >= RED_TH else "黃" if comp >= YELLOW_TH else "綠"
    else:
        out["composite_risk"], out["light"] = None, "無資料"
    return out


# ================================================================ 主流程
def run_daily(date=None) -> dict:
    date = date or datetime.now(TAIPEI_TZ).date()
    today: dict = {"date": str(date)}
    failed = []

    try:
        oi = fetch_taifex_foreign_oi(date)
        if oi is not None:
            today["foreign_tx_net_oi"] = oi
    except Exception:
        failed.append("S1 外資期貨")
        print(f"[失敗] S1 外資期貨\n{traceback.format_exc()}")

    try:
        m = fetch_margin_and_index(date)
        if m:
            today.update(m)
    except Exception:
        failed.append("S2 融資/指數")
        print(f"[失敗] S2 融資/指數\n{traceback.format_exc()}")

    try:
        day_close = fetch_all_close(date)
        if day_close is not None and not day_close.empty:
            hist_close = upsert_breadth_history(day_close)
            today.update(compute_breadth(hist_close))
    except Exception:
        failed.append("S3 廣度")
        print(f"[失敗] S3 廣度\n{traceback.format_exc()}")

    try:
        intl = fetch_intl()
        if intl:
            today.update(intl)
    except Exception:
        failed.append("S4 國際")
        print(f"[失敗] S4 國際\n{traceback.format_exc()}")

    try:
        hist = pd.read_csv(RISK_HISTORY_PATH, dtype={"date": str})
        hist = hist[hist["date"] != str(date)]
    except Exception:
        hist = pd.DataFrame(columns=["date"])

    row = compute_scores(hist, today)
    all_df = pd.concat([hist, pd.DataFrame([row])], ignore_index=True).sort_values("date")
    all_df.to_csv(RISK_HISTORY_PATH, index=False)
    print(f"[分數] {json.dumps(row, ensure_ascii=False, default=str)}")
    if failed:
        print(f"[警告] 今日缺席維度:{failed}(合成分數已按剩餘權重正規化)")
    return row


def backfill_breadth(days: int = 90) -> None:
    """冷啟動:用 MI_INDEX 逐日回填收盤歷史。TWSE 有限流,逐日間隔 3 秒。"""
    date = datetime.now(TAIPEI_TZ).date()
    got = 0
    d = date
    while got < days and (date - d).days < days * 2:
        try:
            df = fetch_all_close(d)
            if df is not None and not df.empty:
                upsert_breadth_history(df)
                got += 1
                print(f"[回填] {d}{len(df)} 檔({got}/{days})")
        except Exception as e:
            print(f"[回填失敗] {d}:{e}")
        d -= timedelta(days=1)
        time.sleep(3)
    print(f"[回填完成] 共 {got} 個交易日")


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        i = sys.argv.index("--backfill")
        n = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 90
        backfill_breadth(n)
        run_daily()
    else:
        run_daily()
