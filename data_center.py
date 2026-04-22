import pandas as pd
import numpy as np
import yfinance as yf
import requests
import urllib3
import time
from datetime import datetime, timedelta
import streamlit as st
from urllib.parse import urlparse, parse_qs

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}


def convert_gsheet_url(url: str) -> str:
    """將常見的 Google Sheet 分享網址轉成可直接給 pandas 讀取的 CSV 匯出網址。"""
    if not url:
        return ""

    url = str(url).strip()
    if not url:
        return ""

    if 'output=csv' in url or 'export?format=csv' in url:
        return url

    if 'docs.google.com/spreadsheets' not in url:
        return url

    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]
        if 'd' not in path_parts:
            return url
        file_id = path_parts[path_parts.index('d') + 1]
        qs = parse_qs(parsed.query)
        gid = qs.get('gid', ['0'])[0]
        return f'https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}'
    except Exception:
        return url


@st.cache_data(ttl=86400, show_spinner=False)
def load_industry_map():
    ind_map, name_map = {}, {}
    try:
        df = pd.read_csv('industry_map.csv', dtype=str)
        for _, row in df.iterrows():
            cid = str(row['代號']).strip()
            ind_map[cid] = str(row['產業']).strip()
            name_map[cid] = str(row['名稱']).strip()
    except Exception:
        pass
    return ind_map, name_map


def _request_json(url: str, params: dict | None = None, timeout: int = 8):
    try:
        r = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=timeout, verify=False)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def safe_download(sid, fm_token=None, retries=2):
    sid = str(sid).strip()
    if not sid:
        return pd.DataFrame()

    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    for suffix in ['.TW', '.TWO']:
        for _ in range(retries):
            try:
                sym = f'{sid}{suffix}'
                df = yf.Ticker(sym, session=session).history(period='6mo', auto_adjust=False)
                if not df.empty and len(df) >= 20:
                    return df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            except Exception:
                time.sleep(0.4 + np.random.rand() * 0.6)

    if fm_token and str(fm_token).strip():
        try:
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
            params = {
                'dataset': 'TaiwanStockPrice',
                'data_id': sid,
                'start_date': start_date,
                'token': str(fm_token).strip(),
            }
            res = _request_json('https://api.finmindtrade.com/api/v4/data', params=params)
            data = res.get('data', [])
            if res.get('msg') == 'success' and data:
                df = pd.DataFrame(data)
                df = df.rename(columns={
                    'date': 'Date', 'open': 'Open', 'max': 'High', 'min': 'Low',
                    'close': 'Close', 'Trading_Volume': 'Volume'
                })
                df['Date'] = pd.to_datetime(df['Date'])
                for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                df = df.set_index('Date')[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
                if len(df) >= 20:
                    return df
        except Exception:
            pass

    return pd.DataFrame()


def fetch_single_stock_batch(sid, fm_token=None):
    df = safe_download(sid, fm_token)
    return sid, (df if not df.empty else None)


@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_dashboard():
    score = 5.0
    macro_data = []
    indices = {
        '^TWII': ('台股加權', '2330.TW'),
        '^PHLX_SO': ('美費半導體', 'SOXX'),
        '^IXIC': ('那斯達克', 'QQQ'),
        '^VIX': ('恐慌指數', 'VIXY'),
    }

    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    for main_sym, (base_name, fallback_sym) in indices.items():
        display_name = base_name
        hist = pd.DataFrame()
        try:
            hist = yf.Ticker(main_sym, session=session).history(period='3mo', auto_adjust=False)
        except Exception:
            hist = pd.DataFrame()

        if hist.empty:
            try:
                hist = yf.Ticker(fallback_sym, session=session).history(period='3mo', auto_adjust=False)
                if not hist.empty:
                    display_name = f'{base_name} (備援)'
            except Exception:
                hist = pd.DataFrame()

        if hist.empty:
            macro_data.append({'戰區': display_name, '現值': '抓取失敗', '月線': '-', '狀態': '⚪ 斷線'})
            continue

        try:
            close_s = pd.to_numeric(hist['Close'], errors='coerce').dropna()
            last_p = float(close_s.iloc[-1])
            ma20 = float(close_s.rolling(20).mean().iloc[-1])
            status = '🟢 多頭' if last_p > ma20 else '🔴 空頭'

            if base_name == '恐慌指數':
                status = '🔴 恐慌' if last_p > 25 else ('🟡 警戒' if last_p > 18 else '🟢 安定')
                if last_p > 25:
                    score -= 2
                elif last_p < 18:
                    score += 1
            else:
                score += 1 if last_p > ma20 else -1

            macro_data.append({'戰區': display_name, '現值': f'{last_p:.2f}', '月線': f'{ma20:.2f}', '狀態': status})
        except Exception:
            macro_data.append({'戰區': display_name, '現值': '計算失敗', '月線': '-', '狀態': '⚪ 斷線'})

    return max(1, min(10, int(score))), pd.DataFrame(macro_data)


@st.cache_data(ttl=14400, show_spinner=False)
def fetch_chips_data(fm_token=None):
    chip_dict = {}
    date_ptr = datetime.now()
    attempts = 0

    while len(chip_dict) < 10 and attempts < 20:
        if date_ptr.weekday() < 5:
            d_str = date_ptr.strftime('%Y%m%d')
            fm_d_str = date_ptr.strftime('%Y-%m-%d')
            success = False

            try:
                url = 'https://www.twse.com.tw/rwd/zh/fund/T86'
                params = {'date': d_str, 'selectType': 'ALLBUT0999', 'response': 'json'}
                res = _request_json(url, params=params)
                if res.get('stat') == 'OK' and res.get('data'):
                    df = pd.DataFrame(res['data'], columns=res['fields'])
                    tru_cols = [c for c in df.columns if '投信' in c and '買賣超' in c]
                    for_cols = [c for c in df.columns if '外資' in c and '買賣超' in c]
                    self_cols = [c for c in df.columns if '自營' in c and '買賣超' in c]

                    def parse_col(col_name):
                        return pd.to_numeric(df[col_name].astype(str).str.replace(',', ''), errors='coerce').fillna(0) / 1000

                    clean = pd.DataFrame()
                    clean['代號'] = df[[c for c in df.columns if '代號' in c][0]].astype(str).str.strip()
                    clean['名稱'] = df[[c for c in df.columns if '名稱' in c][0]].astype(str).str.strip()
                    clean['投信(張)'] = parse_col(tru_cols[0]) if tru_cols else 0
                    clean['外資(張)'] = sum(parse_col(c) for c in for_cols) if for_cols else 0
                    clean['自營(張)'] = sum(parse_col(c) for c in self_cols) if self_cols else 0
                    clean['三大法人合計'] = clean['投信(張)'] + clean['外資(張)'] + clean['自營(張)']
                    chip_dict[d_str] = clean
                    success = True
            except Exception:
                success = False

            if not success and fm_token and str(fm_token).strip():
                try:
                    params = {
                        'dataset': 'TaiwanStockInstitutionalInvestorsBuySell',
                        'start_date': fm_d_str,
                        'end_date': fm_d_str,
                        'token': str(fm_token).strip(),
                    }
                    res_fm = _request_json('https://api.finmindtrade.com/api/v4/data', params=params)
                    if res_fm.get('msg') == 'success' and res_fm.get('data'):
                        df_fm = pd.DataFrame(res_fm['data'])
                        df_fm['net'] = (pd.to_numeric(df_fm['buy'], errors='coerce').fillna(0) - pd.to_numeric(df_fm['sell'], errors='coerce').fillna(0)) / 1000
                        pivot_df = df_fm.pivot_table(index='stock_id', columns='name', values='net', aggfunc='sum').fillna(0)

                        clean = pd.DataFrame({'代號': pivot_df.index.astype(str)})
                        trust_cols = [c for c in pivot_df.columns if '投信' in c]
                        for_cols = [c for c in pivot_df.columns if '外資' in c]
                        deal_cols = [c for c in pivot_df.columns if '自營' in c]
                        clean['名稱'] = clean['代號']
                        clean['投信(張)'] = pivot_df[trust_cols].sum(axis=1).values if trust_cols else 0
                        clean['外資(張)'] = pivot_df[for_cols].sum(axis=1).values if for_cols else 0
                        clean['自營(張)'] = pivot_df[deal_cols].sum(axis=1).values if deal_cols else 0
                        clean['三大法人合計'] = clean['投信(張)'] + clean['外資(張)'] + clean['自營(張)']
                        chip_dict[d_str] = clean
                        success = True
                except Exception:
                    success = False

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
    for sid_str in id_list:
        _, df = fetch_single_stock_batch(sid_str, fm_token)
        if df is not None and not df.empty:
            bulk_data[sid_str] = df
        time.sleep(0.05)

    for sid in id_list:
        try:
            df_stock = bulk_data.get(sid)
            if df_stock is None or df_stock.empty:
                continue
            close_s = pd.to_numeric(df_stock['Close'], errors='coerce').dropna()
            if len(close_s) < 20:
                continue

            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            ind = TWSE_IND_MAP.get(sid) or '其他'
            if sid.startswith('00'):
                ind = 'ETF'

            intel_results.append({
                '代號': sid,
                '產業': ind,
                '現價': p_now,
                'M5': m5,
                'M10': m10,
                'M20': m20,
                '停損價': max(m10, p_now * 0.97),
            })
        except Exception:
            continue

    return pd.DataFrame(intel_results)
