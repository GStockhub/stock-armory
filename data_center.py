import io
import time
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_retry_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5, 
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    return session

def convert_gsheet_url(url: str) -> str:
    url = str(url).strip()
    if not url: return url
    # 🚀 救星：強制將 Web 網頁連結轉為 CSV 下載連結
    if "pubhtml" in url: url = url.replace("pubhtml", "pub?output=csv")
    if "/pub" in url or "export" in url or "output=csv" in url: return url
    if "/edit" in url or "/view" in url:
        import re
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        if match:
            doc_id = match.group(1)
            gid = "0"
            if "gid=" in url: gid = url.split("gid=")[1].split("&")[0]
            return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"
    return url

def read_remote_csv(url: str, dtype=str) -> pd.DataFrame:
    url = convert_gsheet_url(url)
    if not url: return pd.DataFrame()
    session = get_retry_session()
    try:
        resp = session.get(url, timeout=20, verify=False)
        resp.raise_for_status()
        content = resp.content.decode('utf-8-sig')
        return pd.read_csv(io.StringIO(content), dtype=dtype)
    except Exception as e:
        print(f"Read CSV Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=86400, show_spinner=False)
def load_industry_map():
    try:
        # 🚀 救星：強制使用 utf-8-sig 讀取，徹底消滅 BOM 亂碼，名字絕對出得來！
        with open("industry_map.csv", "r", encoding="utf-8-sig") as f:
            df = pd.read_csv(f, dtype=str)
        df.columns = df.columns.str.strip()
        df["代號"] = df["代號"].astype(str).str.strip()
        df["產業"] = df["產業"].astype(str).str.strip()
        df["名稱"] = df["名稱"].astype(str).str.strip()
        
        ind_map = dict(zip(df["代號"], df["產業"]))
        name_map = dict(zip(df["代號"], df["名稱"]))
        return ind_map, name_map
    except Exception as e:
        print(f"❌ 讀取自建產業地圖失敗: {e}")
        return {}, {}

@st.cache_data(ttl=1800, show_spinner=False)
def get_macro_dashboard():
    indices = {"^TWII": "台股加權", "^IXIC": "那斯達克", "^GSPC": "標普500", "^VIX": "恐慌指數", "USDTWD=X": "美元/台幣"}
    results = []
    score = 0
    macro_df = pd.DataFrame()
    overheat_flag = False

    try:
        data = yf.download(list(indices.keys()), period="60d", threads=False, progress=False)
        if data.empty or "Close" not in data.columns:
            return 5, pd.DataFrame([{"名稱": "系統", "現價": "0", "月線(M20)": "0", "乖離(%)": "0", "狀態": "⚠️ Yahoo資料中斷"}]), False

        for tk, name in indices.items():
            if tk not in data["Close"].columns: continue
            s = data["Close"][tk].dropna()
            if len(s) < 20: continue

            p_now = float(s.iloc[-1])
            m20 = float(s.rolling(20).mean().iloc[-1])
            bias = ((p_now - m20) / m20) * 100

            if tk in ["^VIX", "USDTWD=X"]:
                status = "🔴 恐慌升高 (在月線上)" if p_now > m20 else "🟢 安定 (在月線下)"
                if tk == "USDTWD=X":
                    status = "🔴 台幣貶值 (資金外逃)" if p_now > m20 else "🟢 台幣升值 (資金流入)"
                    if p_now > m20: score -= 1.5
                else:
                    if p_now < m20: score += 2
            else:
                status = "🟢 多頭 (在月線上)" if p_now > m20 else "🔴 空頭 (跌破月線)"
                if p_now > m20:
                    score += 2 if tk == "^TWII" else 1.5
                if tk == "^TWII" and bias > 5:
                    overheat_flag = True
                    status += " 🔥過熱"

            # 🚀 救星：物理閹割大盤小數點
            results.append({"名稱": name, "現價": f"{p_now:.2f}", "月線(M20)": f"{m20:.2f}", "乖離(%)": f"{bias:.2f}%", "狀態": status})

        macro_df = pd.DataFrame(results)
    except Exception as e:
        return 5, pd.DataFrame([{"名稱": "系統", "現價": "0", "月線(M20)": "0", "乖離(%)": "0", "狀態": f"⚠️ {e}"}]), False
        
    return max(0, min(10, int(score))), macro_df, overheat_flag

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_chips_data(fm_token=None):
    chip_dict = {}
    date_ptr = datetime.now()
    attempts = 0
    session = get_retry_session()

    def parse_num(s):
        return pd.to_numeric(
            pd.Series(s).astype(str).str.replace(",", "", regex=False),
            errors="coerce"
        ).fillna(0)

    def build_from_twse(d_str):
        twse_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={d_str}&selectType=ALLBUT0999&response=json"
        r = session.get(twse_url, timeout=20, verify=False)
        if r.status_code != 200:
            return pd.DataFrame()

        try:
            res = r.json()
        except Exception:
            return pd.DataFrame()

        if res.get("stat") != "OK" or not res.get("data") or not res.get("fields"):
            return pd.DataFrame()

        df = pd.DataFrame(res["data"], columns=res["fields"])
        if df.empty:
            return pd.DataFrame()

        code_cols = [c for c in df.columns if "代號" in c]
        name_cols = [c for c in df.columns if "名稱" in c]
        if not code_cols:
            return pd.DataFrame()

        code_col = code_cols[0]
        name_col = name_cols[0] if name_cols else code_col

        trust_cols = [c for c in df.columns if "投信" in c and "買賣超" in c]
        foreign_cols = [c for c in df.columns if "外資" in c and "買賣超" in c]
        dealer_cols = [c for c in df.columns if "自營" in c and "買賣超" in c]

        clean = pd.DataFrame()
        clean["代號"] = df[code_col].astype(str).str.strip()
        clean["名稱"] = df[name_col].astype(str).str.strip()

        clean["投信(張)"] = sum(parse_num(df[c]) for c in trust_cols) / 1000 if trust_cols else 0
        clean["外資(張)"] = sum(parse_num(df[c]) for c in foreign_cols) / 1000 if foreign_cols else 0
        clean["自營(張)"] = sum(parse_num(df[c]) for c in dealer_cols) / 1000 if dealer_cols else 0
        clean["三大法人合計"] = clean["投信(張)"] + clean["外資(張)"] + clean["自營(張)"]

        return clean

    def build_from_finmind(fm_d_str):
        fm_url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "start_date": fm_d_str,
            "end_date": fm_d_str,
        }

        if fm_token and str(fm_token).strip():
            params["token"] = str(fm_token).strip()

        r = session.get(fm_url, params=params, timeout=20, verify=False)
        if r.status_code != 200:
            return pd.DataFrame()

        try:
            res = r.json()
        except Exception:
            return pd.DataFrame()

        if res.get("msg") != "success" or not res.get("data"):
            return pd.DataFrame()

        df = pd.DataFrame(res["data"])
        need_cols = {"stock_id", "name", "buy", "sell"}
        if df.empty or not need_cols.issubset(set(df.columns)):
            return pd.DataFrame()

        df["buy"] = pd.to_numeric(df["buy"], errors="coerce").fillna(0)
        df["sell"] = pd.to_numeric(df["sell"], errors="coerce").fillna(0)
        df["net"] = (df["buy"] - df["sell"]) / 1000

        pivot = df.pivot_table(
            index="stock_id",
            columns="name",
            values="net",
            aggfunc="sum"
        ).fillna(0)

        clean = pd.DataFrame()
        clean["代號"] = pivot.index.astype(str)
        clean["名稱"] = clean["代號"]

        def pick_cols(keywords):
            result = []
            for c in pivot.columns:
                cs = str(c).lower()
                if any(k.lower() in cs for k in keywords):
                    result.append(c)
            return result

        trust_cols = pick_cols(["Investment_Trust", "投信"])
        foreign_cols = pick_cols(["Foreign", "外資"])
        dealer_cols = pick_cols(["Dealer", "自營"])

        clean["投信(張)"] = pivot[trust_cols].sum(axis=1).values if trust_cols else 0
        clean["外資(張)"] = pivot[foreign_cols].sum(axis=1).values if foreign_cols else 0
        clean["自營(張)"] = pivot[dealer_cols].sum(axis=1).values if dealer_cols else 0
        clean["三大法人合計"] = clean["投信(張)"] + clean["外資(張)"] + clean["自營(張)"]

        return clean

    while len(chip_dict) < 5 and attempts < 35:
        if date_ptr.weekday() < 5:
            d_str = date_ptr.strftime("%Y%m%d")
            fm_d_str = date_ptr.strftime("%Y-%m-%d")

            clean = pd.DataFrame()

            # 先用 TWSE，因為官方 T86 有股票名稱，且不吃 FinMind 額度
            try:
                clean = build_from_twse(d_str)
            except Exception as e:
                print(f"TWSE T86 failed {d_str}: {e}")

            # TWSE 失敗才用 FinMind 補
            if clean.empty:
                try:
                    clean = build_from_finmind(fm_d_str)
                except Exception as e:
                    print(f"FinMind chips failed {fm_d_str}: {e}")

            if not clean.empty:
                chip_dict[d_str] = clean
                time.sleep(0.25)
            else:
                time.sleep(0.8)

        date_ptr -= timedelta(days=1)
        attempts += 1

    return chip_dict

def fetch_single_stock_batch(sid, fm_token=None, period="60d"):
    sid = str(sid).strip()
    df = safe_download(sid, fm_token, period=period)
    return sid, df

def safe_download(sid, fm_token=None, period="60d"):
    # 🚀 救星：先試上市 (.TW)，再試上櫃 (.TWO)。99% 股票直接抓到，再也不用看 FinMind 臉色！
    for suffix in [".TW", ".TWO"]:
        try:
            ticker = f"{sid}{suffix}"
            df = yf.download(ticker, period=period, threads=False, progress=False)
            if df is not None and not df.empty and "Close" in df.columns:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                if len(df.dropna(subset=['Close'])) > 10: return df
        except Exception: pass

    try:
        session = get_retry_session()
        url = "https://api.finmindtrade.com/api/v4/data"
        days_back = 365 if period == "1y" else 90
        start_d = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        payload = {"dataset": "TaiwanStockPrice", "data_id": sid, "start_date": start_d}
        if fm_token: payload["token"] = fm_token
        
        resp = session.get(url, params=payload, timeout=10)
        if resp.status_code == 200:
            try: data = resp.json()
            except: data = {}
            if data.get("msg") == "success" and data.get("data"):
                fm_df = pd.DataFrame(data["data"])
                fm_df["date"] = pd.to_datetime(fm_df["date"])
                fm_df = fm_df.set_index("date").rename(columns={
                    "open": "Open", "max": "High", "min": "Low", "close": "Close", "Trading_Volume": "Volume"
                })
                if not fm_df.empty and len(fm_df) > 10: return fm_df
    except Exception: pass
         
    return None
