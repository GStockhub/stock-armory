import io
import time
from datetime import datetime, timedelta
import concurrent.futures
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7"
    })
    return session

def convert_gsheet_url(url: str) -> str:
    url = str(url).strip()
    if not url: return url
    if "/pub" in url or "export" in url or "output=csv" in url: return url
    if "/edit" in url or "/view" in url:
        import re
        match = re.search(r'/d/([a-zA-Z0-9-_]{40,})', url)
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
        df = pd.read_csv("industry_map.csv", dtype=str)
        df.columns = df.columns.str.replace('\ufeff', '', regex=False).str.strip()
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

            results.append({
                "名稱": name, 
                "現價": f"{p_now:.2f}", 
                "月線(M20)": f"{m20:.2f}", 
                "乖離(%)": f"{bias:.2f}%", 
                "狀態": status
            })

        macro_df = pd.DataFrame(results)
    except Exception as e:
        return 5, pd.DataFrame([{"名稱": "系統", "現價": "0", "月線(M20)": "0", "乖離(%)": "0", "狀態": f"⚠️ {e}"}]), False
        
    return max(0, min(10, int(score))), macro_df, overheat_flag

@st.cache_data(ttl=14400, show_spinner=False)
def fetch_chips_data(fm_token=None):
    chip_dict = {}
    date_ptr = datetime.now()
    attempts = 0
    session = get_retry_session()
    
    # 🚀 紀錄最後一次失敗的真實原因，不再讓將軍瞎猜！
    last_error_msg = "無"

    while len(chip_dict) < 5 and attempts < 20:
        if date_ptr.weekday() < 5:
            d_str = date_ptr.strftime("%Y%m%d")
            fm_d_str = date_ptr.strftime("%Y-%m-%d")
            success = False

            try:
                fm_url = "https://api.finmindtrade.com/api/v4/data"
                params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "start_date": fm_d_str, "end_date": fm_d_str}
                if fm_token and str(fm_token).strip(): params["token"] = str(fm_token).strip()

                r = session.get(fm_url, params=params, timeout=15, verify=False)
                if r.status_code == 200:
                    try: res = r.json()
                    except: res = {}
                    
                    if res.get("msg") == "success" and res.get("data"):
                        df = pd.DataFrame(res["data"])
                        if not df.empty and "stock_id" in df.columns and "name" in df.columns and "buy" in df.columns and "sell" in df.columns:
                            df["buy"] = pd.to_numeric(df["buy"], errors="coerce").fillna(0)
                            df["sell"] = pd.to_numeric(df["sell"], errors="coerce").fillna(0)
                            df["net"] = (df["buy"] - df["sell"]) / 1000

                            pivot = df.pivot_table(index="stock_id", columns="name", values="net", aggfunc="sum").fillna(0)
                            clean = pd.DataFrame()
                            clean["代號"] = pivot.index.astype(str)
                            clean["名稱"] = clean["代號"]

                            trust_cols = [c for c in pivot.columns if "Investment_Trust" in str(c) or "投信" in str(c)]
                            foreign_cols = [c for c in pivot.columns if "Foreign" in str(c) or "外資" in str(c)]
                            dealer_cols = [c for c in pivot.columns if "Dealer" in str(c) or "自營" in str(c)]

                            clean["投信(張)"] = pivot[trust_cols].sum(axis=1).values if trust_cols else 0
                            clean["外資(張)"] = pivot[foreign_cols].sum(axis=1).values if foreign_cols else 0
                            clean["自營(張)"] = pivot[dealer_cols].sum(axis=1).values if dealer_cols else 0
                            clean["三大法人合計"] = clean["投信(張)"] + clean["外資(張)"] + clean["自營(張)"]
                            
                            chip_dict[d_str] = clean
                            success = True
                    elif res.get("msg") != "success":
                        last_error_msg = f"FinMind 官方拒絕: {res.get('msg')}"
            except Exception as e: 
                last_error_msg = f"FinMind 連線崩潰: {e}"

            if not success:
                try:
                    twse_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={d_str}&selectType=ALLBUT0999&response=json"
                    r = session.get(twse_url, timeout=15, verify=False)
                    if r.status_code == 200:
                        try: res = r.json()
                        except: res = {}
                        if res.get("stat") == "OK" and res.get("data") and res.get("fields"):
                            df = pd.DataFrame(res["data"], columns=res["fields"])
                            code_cols = [c for c in df.columns if "代號" in c]
                            name_cols = [c for c in df.columns if "名稱" in c]

                            if code_cols and name_cols:
                                code_col, name_col = code_cols[0], name_cols[0]
                                trust_cols = [c for c in df.columns if "投信" in c and "買賣超" in c]
                                foreign_cols = [c for c in df.columns if "外資" in c and "買賣超" in c]
                                dealer_cols = [c for c in df.columns if "自營" in c and "買賣超" in c]

                                def parse_col(col_name):
                                    return pd.to_numeric(df[col_name].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0) / 1000

                                clean = pd.DataFrame()
                                clean["代號"] = df[code_col].astype(str).str.strip()
                                clean["名稱"] = df[name_col].astype(str).str.strip()
                                clean["投信(張)"] = sum(parse_col(c) for c in trust_cols) if trust_cols else 0
                                clean["外資(張)"] = sum(parse_col(c) for c in foreign_cols) if foreign_cols else 0
                                clean["自營(張)"] = sum(parse_col(c) for c in dealer_cols) if dealer_cols else 0
                                clean["三大法人合計"] = clean["投信(張)"] + clean["外資(張)"] + clean["自營(張)"]
                                chip_dict[d_str] = clean
                                success = True
                        elif res.get("stat") != "OK":
                            last_error_msg = f"證交所拒絕: {res.get('stat')}"
                    if not success: time.sleep(3.5)
                except Exception as e: 
                    last_error_msg = f"證交所連線崩潰: {e}"

        date_ptr -= timedelta(days=1)
        attempts += 1
        time.sleep(0.2)

    # 🚀 將真實錯誤訊息爆出來！
    if not chip_dict:
        st.error(f"🚨 **全面斷線**：系統已盡力嘗試 20 次皆無法取得籌碼資料！\n\n**🔍 攔截到的最後真實錯誤原因**： `{last_error_msg}`", icon="💥")

    return chip_dict

def fetch_single_stock_batch(sid, fm_token=None, period="60d"):
    sid = str(sid).strip()
    df = safe_download(sid, fm_token, period=period)
    return sid, df

def safe_download(sid, fm_token=None, period="60d"):
    try:
        ticker = f"{sid}.TW"
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

@st.cache_data(ttl=900, show_spinner=False)
def get_holding_intel(id_tuple, TWSE_IND_MAP, fm_token=None):
    id_list = [str(x).strip() for x in list(id_tuple) if str(x).strip()]
    if not id_list: return pd.DataFrame()

    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_single_stock_batch, sid, fm_token): sid for sid in id_list}
        for future in concurrent.futures.as_completed(futures):
            sid, df = future.result()
            if df is not None and not df.empty: bulk_data[sid] = df

    if len(bulk_data) == 0: return pd.DataFrame()

    results = []
    for sid in id_list:
        try:
            df = bulk_data.get(sid)
            if df is None or df.empty: continue
            
            df = df[~df.index.duplicated(keep="last")].copy()
            close_s = pd.to_numeric(df["Close"], errors="coerce")
            if close_s.isna().all() or len(close_s.dropna()) < 10: continue

            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])

            try:
                high_s = pd.to_numeric(df["High"], errors="coerce")
                low_s = pd.to_numeric(df["Low"], errors="coerce")
                tmp = pd.DataFrame({"Close": close_s, "High": high_s, "Low": low_s}).dropna()
                tmp["PrevClose"] = tmp["Close"].shift(1)
                tr1 = tmp["High"] - tmp["Low"]
                tr2 = (tmp["High"] - tmp["PrevClose"]).abs()
                tr3 = (tmp["Low"] - tmp["PrevClose"]).abs()
                tmp["TR"] = np.maximum(tr1, np.maximum(tr2, tr3))
                tmp["ATR"] = tmp["TR"].rolling(14).mean()
                atr_now = float(tmp["ATR"].iloc[-1])
                if pd.isna(atr_now) or atr_now <= 0: atr_now = p_now * 0.03
            except Exception: atr_now = p_now * 0.03

            ind = TWSE_IND_MAP.get(sid, "未知")
            results.append({"代號": sid, "產業": ind, "現價": round(p_now, 2), "M5": round(m5, 2), "M10": round(m10, 2), "ATR": round(atr_now, 2)})
        except Exception: continue

    return pd.DataFrame(results)
