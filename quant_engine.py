import pandas as pd
import numpy as np
import streamlit as st
import concurrent.futures
from data_center import fetch_single_stock_batch, safe_download


def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df = df[~df.index.duplicated(keep='last')].sort_index()
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['Volume'] = df['Volume'].replace(0, np.nan).ffill().fillna(1000)
    return df.dropna(subset=['Open', 'High', 'Low', 'Close'])


def _build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df_bt = pd.DataFrame({
        'Close': df['Close'],
        'Open': df['Open'],
        'High': df['High'],
        'Low': df['Low'],
        'Volume': df['Volume'],
    })
    df_bt['MA5'] = df_bt['Close'].rolling(5).mean()
    df_bt['MA10'] = df_bt['Close'].rolling(10).mean()
    df_bt['MA20'] = df_bt['Close'].rolling(20).mean()
    df_bt['RollMax20'] = df_bt['Close'].rolling(20).max()
    df_bt['Vol_MA5'] = df_bt['Volume'].rolling(5).mean()
    low9 = df_bt['Low'].rolling(9).min()
    high9 = df_bt['High'].rolling(9).max()
    denom = (high9 - low9).replace(0, np.nan)
    df_bt['RSV'] = ((df_bt['Close'] - low9) / denom) * 100
    df_bt['K'] = df_bt['RSV'].ewm(alpha=1 / 3, adjust=False).mean()
    df_bt['D'] = df_bt['K'].ewm(alpha=1 / 3, adjust=False).mean()
    df_bt['RedK'] = df_bt['Close'] > df_bt['Open']
    df_bt['ClosePos'] = np.where(
        (df_bt['High'] - df_bt['Low']) > 0,
        (df_bt['Close'] - df_bt['Low']) / (df_bt['High'] - df_bt['Low']),
        0,
    )
    df_bt['Bias20'] = np.where(df_bt['MA20'] > 0, (df_bt['Close'] - df_bt['MA20']) / df_bt['MA20'] * 100, 0)
    return df_bt


def _simulate_returns(df_bt: pd.DataFrame):
    sig_trend = (df_bt['MA5'] > df_bt['MA10']) & (df_bt['MA10'] > df_bt['MA20'])
    sig_a = (
        (df_bt['Volume'] > df_bt['Vol_MA5'] * 1.5)
        & (df_bt['K'] > 80)
        & (df_bt['Close'] >= df_bt['RollMax20'] * 0.98)
        & (df_bt['ClosePos'] > 0.7)
    )
    bt_on_m5 = (df_bt['Close'] >= df_bt['MA5']) & (df_bt['Close'] <= df_bt['MA5'] * 1.03)
    bt_on_m10 = (df_bt['Close'] >= df_bt['MA10']) & (df_bt['Close'] <= df_bt['MA10'] * 1.03)
    sig_b = (df_bt['Bias20'] < 7) & df_bt['RedK'] & (bt_on_m5 | bt_on_m10) & (df_bt['K'] > df_bt['D'])
    signals_idx = df_bt[sig_trend & (sig_a | sig_b)].index

    sim_returns = []
    for idx in signals_idx:
        loc_idx = df_bt.index.get_loc(idx)
        if loc_idx + 1 >= len(df_bt):
            continue
        entry_p = float(df_bt.iloc[loc_idx + 1]['Open'])
        prev_close = float(df_bt.iloc[loc_idx]['Close'])
        if entry_p > prev_close * 1.02:
            continue

        future_data = df_bt.iloc[loc_idx + 1: loc_idx + 21]
        if future_data.empty:
            continue

        stop_loss = max(float(df_bt.iloc[loc_idx]['MA10']), entry_p * 0.97)
        sold_half = False
        ret = 0.0

        for _, row in future_data.iterrows():
            curr_p = float(row['Close'])
            curr_m5 = float(row['MA5']) if pd.notna(row['MA5']) else curr_p
            if not sold_half and curr_p >= entry_p * 1.06:
                sold_half = True

            if sold_half:
                if curr_p < curr_m5:
                    ret = 0.5 * 0.06 + 0.5 * ((curr_m5 - entry_p) / entry_p)
                    break
            else:
                if curr_p < stop_loss:
                    ret = (stop_loss - entry_p) / entry_p
                    break
        else:
            final_p = float(future_data['Close'].iloc[-1])
            if sold_half:
                ret = 0.5 * 0.06 + 0.5 * ((final_p - entry_p) / entry_p)
            else:
                ret = (final_p - entry_p) / entry_p

        sim_returns.append(ret)

    if len(sim_returns) < 5:
        return 50.0, 0.0
    arr = np.array(sim_returns, dtype=float)
    return float((arr > 0).mean() * 100), float(arr.mean() * 100)


@st.cache_data(ttl=900, show_spinner=False)
def run_sandbox_sim(sid, TWSE_NAME_MAP, fm_token=None):
    sid = str(sid).strip()
    df = _prepare_df(safe_download(sid, fm_token))
    if df.empty or len(df) < 20:
        return None

    close_s = df['Close']
    p_now = float(close_s.iloc[-1])
    m5 = float(close_s.rolling(5).mean().iloc[-1])
    m10 = float(close_s.rolling(10).mean().iloc[-1])
    m20 = float(close_s.rolling(20).mean().iloc[-1])
    bias = ((p_now - m20) / m20) * 100 if m20 > 0 else 0
    df_bt = _build_indicators(df)
    win_rate, _ = _simulate_returns(df_bt)

    return {
        '代號': sid,
        '名稱': TWSE_NAME_MAP.get(sid, sid),
        '現價': p_now,
        'M5': m5,
        'M10': m10,
        'M20': m20,
        '乖離': bias,
        '勝率': win_rate,
        '停損價': max(m10, p_now * 0.97),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def level2_quant_engine(id_tuple, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, fm_token=None):
    id_list = [str(x).strip() for x in list(id_tuple) if str(x).strip()]
    if not id_list:
        return pd.DataFrame()

    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_single_stock_batch, sid, fm_token): sid for sid in id_list}
        for future in concurrent.futures.as_completed(futures):
            sid_str, df = future.result()
            if df is not None and not df.empty:
                bulk_data[sid_str] = _prepare_df(df)

    intel_results = []
    hot_industries = ['半導體', '電腦及週邊設備業', '電子零組件業', '其他電子業']

    for sid in id_list:
        try:
            if not sid.startswith('00') and not sid.isdigit():
                continue
            ind = TWSE_IND_MAP.get(sid) or '其他'
            if sid.startswith('00'):
                ind = 'ETF'
            if '金融' in ind or '保險' in ind:
                continue

            df_stock = bulk_data.get(sid)
            if df_stock is None or df_stock.empty or len(df_stock) < 20:
                continue

            close_s = df_stock['Close']
            open_s = df_stock['Open']
            high_s = df_stock['High']
            low_s = df_stock['Low']
            vol_s = df_stock['Volume']

            p_now = float(close_s.iloc[-1])
            open_now = float(open_s.iloc[-1])
            high_now = float(high_s.iloc[-1])
            low_now = float(low_s.iloc[-1])
            prev_close = float(close_s.iloc[-2]) if len(close_s) > 1 else open_now
            vol_now = float(vol_s.iloc[-1]) / 1000

            if prev_close > 0 and ((open_now - prev_close) / prev_close * 100) > 3.5:
                continue
            if p_now < 10 or vol_now < 0.3:
                continue

            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            if pd.isna(m10) or pd.isna(m20):
                continue

            vol_ma5 = float(vol_s.rolling(5).mean().iloc[-1]) / 1000 if len(vol_s) >= 5 else vol_now
            bias = ((p_now - m20) / m20) * 100 if m20 > 0 else 0
            df_bt = _build_indicators(df_stock)
            k_now = float(df_bt['K'].iloc[-1]) if pd.notna(df_bt['K'].iloc[-1]) else 50.0
            d_now = float(df_bt['D'].iloc[-1]) if pd.notna(df_bt['D'].iloc[-1]) else 50.0
            red_k = p_now > open_now
            close_position = (p_now - low_now) / (high_now - low_now) if high_now > low_now else 0
            is_strong_candle = ((p_now - open_now) / open_now) > 0.04 if open_now > 0 else False
            trend_strength = (m5 > m10) and (m10 > m20)
            vol_ratio = vol_now / vol_ma5 if vol_ma5 > 0 else 0
            is_breakout_base = (vol_ratio > 1.3) and (k_now > 75) and (p_now >= close_s.iloc[-20:].max() * 0.975)
            on_m5 = (p_now >= m5 * 0.995) and (p_now <= m5 * 1.035)
            on_m10 = (p_now >= m10 * 0.995) and (p_now <= m10 * 1.04)
            tactic_b = (bias < 8) and red_k and (on_m5 or on_m10) and (k_now >= d_now)
            tactic_a_strong = is_breakout_base and (vol_ratio >= 1.6) and (close_position > 0.68)
            tactic_a_weak = is_breakout_base and not tactic_a_strong
            is_candidate = trend_strength and (is_breakout_base or tactic_b or (p_now >= m10 and bias < 5 and vol_ratio >= 0.8))

            if tactic_a_strong and tactic_b:
                tactic_label = '🔥 雙戰術共振'
            elif tactic_a_strong:
                tactic_label = '🚀 S級主升段'
            elif tactic_a_weak:
                tactic_label = '⚠️ 弱勢震盪'
            elif tactic_b:
                tactic_label = '🛡️ 穩健回踩'
            else:
                tactic_label = '⏳ 觀望盤整'

            win_rate, avg_ret = _simulate_returns(df_bt)

            s_score = float(MACRO_SCORE)
            if p_now > m5:
                s_score += 1
            if p_now > m20:
                s_score += 1
            else:
                s_score -= 2
            if is_strong_candle:
                s_score += 1
            if any(h in ind for h in hot_industries):
                s_score += 1
            if p_now < m10:
                s_score -= 3
            if bias > 9:
                s_score -= 2
            elif 0 <= bias <= 5:
                s_score += 1

            intel_results.append({
                '代號': sid,
                '名稱': TWSE_NAME_MAP.get(sid, sid),
                '產業': ind,
                '現價': p_now,
                'M5': m5,
                'M10': m10,
                'M20': m20,
                '乖離(%)': bias,
                '基本達標': bool(is_candidate),
                '安全指數': max(1, min(10, int(round(s_score)))),
                '勝率(%)': win_rate,
                '均報(%)': avg_ret,
                '停損價': max(m10, p_now * 0.97),
                '原始風險差額': max(p_now - max(m10, p_now * 0.97), 0.01),
                '戰術型態': tactic_label,
            })
        except Exception:
            continue

    return pd.DataFrame(intel_results)
