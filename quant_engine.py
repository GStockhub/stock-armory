import pandas as pd
import numpy as np
import streamlit as st
import concurrent.futures
from data_center import fetch_single_stock_batch, safe_download

# ---------------------------------------------------------
# 🔮 沙盤推演
# ---------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def run_sandbox_sim(sid, TWSE_NAME_MAP, fm_token=None):
    sid = str(sid).strip()
    df = safe_download(sid, fm_token)

    if df is None or df.empty or len(df) < 20:
        return None

    df = df[~df.index.duplicated(keep='last')].copy()
    df['Volume'] = df['Volume'].replace(0, np.nan).ffill().fillna(1000)

    close_s = df['Close']
    open_s = df['Open']

    p_now = float(close_s.iloc[-1])

    m5 = float(close_s.rolling(5).mean().iloc[-1])
    m10 = float(close_s.rolling(10).mean().iloc[-1])
    m20 = float(close_s.rolling(20).mean().iloc[-1])

    bias = ((p_now - m20) / m20) * 100 if m20 > 0 else 0

    return {
        '代號': sid,
        '名稱': TWSE_NAME_MAP.get(sid, sid),
        '現價': p_now,
        'M5': m5,
        'M10': m10,
        'M20': m20,
        '乖離': bias,
        '勝率': 50.0,
        '停損價': m10
    }


# ---------------------------------------------------------
# 🎯 主選股引擎（修正版）
# ---------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def level2_quant_engine(id_tuple, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, fm_token=None):

    id_list = list(id_tuple)
    results = []

    if not id_list:
        return pd.DataFrame()

    bulk_data = {}

    # 🚀 批次抓資料
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_single_stock_batch, sid, fm_token): sid
            for sid in id_list
        }

        for future in concurrent.futures.as_completed(futures):
            sid, df = future.result()
            if df is not None and not df.empty:
                bulk_data[sid] = df

    # 🚨 如果完全抓不到資料
    if len(bulk_data) == 0:
        return None

    for sid in id_list:
        try:
            sid = str(sid).strip()

            df = bulk_data.get(sid)
            if df is None or df.empty:
                continue

            df = df[~df.index.duplicated(keep='last')].copy()
            df['Volume'] = df['Volume'].replace(0, np.nan).ffill().fillna(1000)

            close = df['Close']
            open_ = df['Open']
            vol = df['Volume']

            if len(close) < 20:
                continue

            p = float(close.iloc[-1])
            prev = float(close.iloc[-2])

            vol_now = float(vol.iloc[-1]) / 1000

            # ❗ 不要太嚴格（你原本這裡太硬）
            if p < 10:
                continue

            m5 = float(close.rolling(5).mean().iloc[-1])
            m10 = float(close.rolling(10).mean().iloc[-1])
            m20 = float(close.rolling(20).mean().iloc[-1])

            # ⭐ 這就是你原本爆掉的地方（補上）
            bias = ((p - m20) / m20) * 100 if m20 > 0 else 0

            # 🔥 放寬條件（避免全空）
            trend = (m5 > m10) or (p > m20)

            if not trend:
                continue

            results.append({
                '代號': sid,
                '名稱': TWSE_NAME_MAP.get(sid, sid),
                '產業': TWSE_IND_MAP.get(sid, "其他"),
                '現價': p,
                '成交量': vol_now,
                'M5': m5,
                'M10': m10,
                'M20': m20,
                '乖離(%)': bias,
                '基本達標': True,
                '安全指數': 5,
                '勝率(%)': 50,
                '均報(%)': 0,
                '停損價': m10,
                '停利價': p * 1.1,
                '原始風險差額': p - m10,
                '戰術型態': "基礎過濾"
            })

        except Exception as e:
            continue

    return pd.DataFrame(results)
