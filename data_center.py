import io
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def convert_gsheet_url(url):
    url = str(url).strip()
    if not url:
        return ""

    if "docs.google.com/spreadsheets/d/" in url and "export?format=csv" not in url:
        import re
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
        if match:
            doc_id = match.group(1)
            gid_match = re.search(r"[#?&]gid=(\d+)", url)
            gid = gid_match.group(1) if gid_match else "0"
            return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"
    return url


def read_remote_csv(url, dtype=str):
    url = convert_gsheet_url(url)
    if not url:
        return pd.DataFrame()

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    resp = requests.get(url, headers=headers, timeout=20, verify=False)
    resp.raise_for_status()

    text = resp.text.strip()
    if not text:
        return pd.DataFrame()

    return pd.read_csv(io.StringIO(text), dtype=dtype)


@st.cache_data(ttl=86400, show_spinner=False)
def load_industry_map():
    ind_map, name_map = {}, {}
    try:
        df = pd.read_csv("industry_map.csv", dtype=str)
        for _, row in df.iterrows():
            cid = str(row["代號"]).strip()
            ind_map[cid] = str(row["產業"]).strip()
            name_map[cid] = str(row["名稱"]).strip()
    except Exception:
        pass
    return ind_map, name_map


def get_yf_session():
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
    )
    return session


def safe_download(sid, fm_token=None, period="3mo"):
    sid_str = str(sid).strip()
    if not sid_str:
        return pd.DataFrame()

    is_tw_stock = sid_str[0].isdigit()

    if is_tw_stock and fm_token and str(fm_token).strip():
        try:
            start_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
            url = "https://api.finmindtrade.com/api/v4/data"
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": sid_str,
                "start_date": start_date,
                "token": str(fm_token).strip(),
            }
            res = requests.get(url, params=params, timeout=10, verify=False).json()
            if res.get("msg") == "success" and res.get("data"):
                df = pd.DataFrame(res["data"])
                rename_map = {
                    "date": "Date",
                    "open": "Open",
                    "max": "High",
                    "min": "Low",
                    "close": "Close",
                    "Trading_Volume": "Volume",
                    "trading_volume": "Volume",
                }
                df.rename(columns=rename_map, inplace=True)
                if "Date" not in df.columns:
                    return pd.DataFrame()

                df["Date"] = pd.to_datetime(df["Date"])
                df.set_index("Date", inplace=True)

                for col in ["Open", "High", "Low", "Close", "Volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

                keep_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
                df = df[keep_cols].sort_index()
                if "Volume" not in df.columns:
                    df["Volume"] = 0
                df = df.dropna(subset=["Close"])
                if len(df) >= 20:
                    return df
        except Exception:
            pass

    try:
        session = get_yf_session()
        symbols = [f"{sid_str}.TW", f"{sid_str}.TWO"] if is_tw_stock else [sid_str]

        for sym in symbols:
            try:
                df = yf.download(sym, period=period, progress=False, auto_adjust=False, session=session)
                if df is not None and not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)

                    for col in ["Open", "High", "Low", "Close", "Volume"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")

                    keep_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
                    df = df[keep_cols].sort_index()
                    if "Volume" not in df.columns:
                        df["Volume"] = 0
                    df = df.dropna(subset=["Close"])
                    if len(df) >= 20:
                        return df
            except Exception:
                continue
    except Exception:
        pass

    return pd.DataFrame()


def fetch_single_stock_batch(sid, fm_token=None):
    sid = str(sid).strip()
    df = safe_download(sid, fm_token)
    if not df.empty:
        return sid, df
    return sid, None


@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_dashboard():
    score = 5.0
    macro_data = []
    overheat_flag = False

    indices = {
        "^TWII": ("台股加權", "0050.TW"),
        "^PHLX_SO": ("美費半導體", "SOXX"),
        "^IXIC": ("那斯達克", "QQQ"),
        "^VIX": ("恐慌指數", "VIXY"),
        "TWD=X": ("美元/台幣(匯率)", "TWD=X"),
    }

    for main_sym, (base_name, fallback_sym) in indices.items():
        display_name = base_name

        hist = safe_download(main_sym)
        if hist.empty:
            hist = safe_download(fallback_sym)
            if not hist.empty:
                display_name = f"{base_name} (備援)"

        if hist.empty:
            macro_data.append({"戰區": display_name, "現值": "抓取失敗", "月線": "-", "狀態": "⚪ 斷線"})
            continue

        try:
            close_s = hist["Close"]
            last_p = float(close_s.iloc[-1])
            ma20 = float(close_s.rolling(20).mean().iloc[-1])
            bias = ((last_p - ma20) / ma20) * 100 if ma20 > 0 else 0

            status = "🟢 多頭" if last_p > ma20 else "🔴 空頭"

            if "恐慌" in base_name:
                status = "🔴 恐慌" if last_p > 25 else ("🟡 警戒" if last_p > 18 else "🟢 安定")
                if last_p > 25:
                    score -= 2
                elif last_p < 18:
                    score += 1

            elif "匯率" in base_name:
                if last_p > ma20:
                    status = "🔴 貶值(資金外逃)"
                    score -= 1.5
                else:
                    status = "🟢 升值(熱錢湧入)"
                    score += 1.5

            else:
                if last_p > ma20:
                    score += 1
                else:
                    score -= 1

                if "台股加權" in base_name and bias > 5:
                    overheat_flag = True
                    score -= 3
                    status = "🔥 高檔過熱"

            macro_data.append(
                {
                    "戰區": display_name,
                    "現值": f"{last_p:.2f}",
                    "月線": f"{ma20:.2f}",
                    "狀態": status,
                }
            )
        except Exception:
            macro_data.append({"戰區": display_name, "現值": "計算失敗", "月線": "-", "狀態": "⚪ 斷線"})

    return max(1, min(10, int(score))), pd.DataFrame(macro_data), overheat_flag


@st.cache_data(ttl=14400, show_spinner=False)
def fetch_chips_data(fm_token=None):
    chip_dict = {}
    date_ptr = datetime.now()
    attempts = 0

    while len(chip_dict) < 10 and attempts < 20:
        if date_ptr.weekday() < 5:
            d_str = date_ptr.strftime("%Y%m%d")
            fm_d_str = date_ptr.strftime("%Y-%m-%d")
            success = False

            if fm_token and str(fm_token).strip():
                try:
                    fm_url = "https://api.finmindtrade.com/api/v4/data"
                    params = {
                        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
                        "start_date": fm_d_str,
                        "end_date": fm_d_str,
                        "token": str(fm_token).strip(),
                    }
                    r_fm = requests.get(fm_url, params=params, timeout=10, verify=False)
                    if r_fm.status_code == 200:
                        res_fm = r_fm.json()
                        if res_fm.get("msg") == "success" and res_fm.get("data"):
                            df_fm = pd.DataFrame(res_fm["data"])
                            df_fm["net"] = (pd.to_numeric(df_fm["buy"], errors="coerce").fillna(0) -
                                            pd.to_numeric(df_fm["sell"], errors="coerce").fillna(0)) / 1000
                            pivot_df = df_fm.pivot_table(index="stock_id", columns="name", values="net", aggfunc="sum").fillna(0)

                            clean = pd.DataFrame()
                            clean["代號"] = pivot_df.index.astype(str)
                            clean["名稱"] = clean["代號"]

                            trust_cols = [c for c in pivot_df.columns if "投信" in str(c)]
                            for_cols = [c for c in pivot_df.columns if "外資" in str(c)]
                            deal_cols = [c for c in pivot_df.columns if "自營" in str(c)]

                            clean["投信(張)"] = pivot_df[trust_cols].sum(axis=1).values if trust_cols else 0
                            clean["外資(張)"] = pivot_df[for_cols].sum(axis=1).values if for_cols else 0
                            clean["自營(張)"] = pivot_df[deal_cols].sum(axis=1).values if deal_cols else 0
                            clean["三大法人合計"] = clean["投信(張)"] + clean["外資(張)"] + clean["自營(張)"]

                            chip_dict[d_str] = clean
                            success = True
                except Exception:
                    pass

            if not success:
                try:
                    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={d_str}&selectType=ALLBUT0999&response=json"
                    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, verify=False)
                    if r.status_code == 200:
                        res = r.json()
                        if res.get("stat") == "OK":
                            df = pd.DataFrame(res["data"], columns=res["fields"])

                            tru_cols = [c for c in df.columns if "投信" in c and "買賣超" in c]
                            for_cols = [c for c in df.columns if "外資" in c and "買賣超" in c]
                            self_cols = [c for c in df.columns if "自營" in c and "買賣超" in c]

                            def parse_col(col_name):
                                return pd.to_numeric(
                                    df[col_name].astype(str).str.replace(",", "", regex=False),
                                    errors="coerce"
                                ).fillna(0) / 1000

                            clean = pd.DataFrame()
                            clean["代號"] = df[[c for c in df.columns if "代號" in c][0]].astype(str).str.strip()
                            clean["名稱"] = df[[c for c in df.columns if "名稱" in c][0]].astype(str).str.strip()
                            clean["投信(張)"] = parse_col(tru_cols[0]) if tru_cols else 0
                            clean["外資(張)"] = sum(parse_col(c) for c in for_cols) if for_cols else 0
                            clean["自營(張)"] = sum(parse_col(c) for c in self_cols) if self_cols else 0
                            clean["三大法人合計"] = clean["投信(張)"] + clean["外資(張)"] + clean["自營(張)"]

                            chip_dict[d_str] = clean
                            success = True
                except Exception:
                    pass

            if success:
                time.sleep(0.15)

        date_ptr -= timedelta(days=1)
        attempts += 1

    return chip_dict


@st.cache_data(ttl=3600, show_spinner=False)
def get_holding_intel(id_tuple, TWSE_IND_MAP, fm_token=None):
    id_list = [str(x).strip() for x in list(id_tuple) if str(x).strip()]
    intel_results = []

    if not id_list:
        return pd.DataFrame()

    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_single_stock_batch, sid, fm_token): sid
            for sid in id_list
        }
        for future in concurrent.futures.as_completed(futures):
            sid, df = future.result()
            if df is not None and not df.empty:
                bulk_data[sid] = df

    for sid in id_list:
        try:
            df_stock = bulk_data.get(sid)
            if df_stock is None or df_stock.empty:
                continue

            close_s = df_stock["Close"]
            if len(close_s) < 20:
                continue

            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])

            try:
                tmp = df_stock.copy()
                tmp["PrevClose"] = tmp["Close"].shift(1)
                tr1 = tmp["High"] - tmp["Low"]
                tr2 = (tmp["High"] - tmp["PrevClose"]).abs()
                tr3 = (tmp["Low"] - tmp["PrevClose"]).abs()
                tmp["TR"] = np.maximum(tr1, np.maximum(tr2, tr3))
                tmp["ATR"] = tmp["TR"].rolling(14).mean()
                atr_now = float(tmp["ATR"].iloc[-1])
                if pd.isna(atr_now) or atr_now <= 0:
                    atr_now = p_now * 0.03
            except Exception:
                atr_now = p_now * 0.03

            ind = TWSE_IND_MAP.get(sid, "其他")
            if sid.startswith("00"):
                ind = "ETF"

            intel_results.append(
                {
                    "代號": sid,
                    "產業": ind,
                    "現價": p_now,
                    "M5": m5,
                    "M10": m10,
                    "M20": m20,
                    "ATR": atr_now,
                    "停損價": max(m10, p_now - 1.5 * atr_now),
                }
            )
        except Exception:
            continue

    return pd.DataFrame(intel_results)
