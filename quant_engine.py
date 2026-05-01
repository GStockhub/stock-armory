import pandas as pd
import numpy as np
import streamlit as st
import concurrent.futures
from data_center import fetch_single_stock_batch, safe_download

@st.cache_data(ttl=900, show_spinner=False)
def run_sandbox_sim(sid, TWSE_NAME_MAP, fm_token=None):
    sid = str(sid).strip()
    df = safe_download(sid, fm_token)
    if df is None or df.empty or len(df) < 20: return None
    
    df = df[~df.index.duplicated(keep="last")].copy()
    if "Volume" not in df.columns: df["Volume"] = 0
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
    df["Volume"] = df["Volume"].replace(0, np.nan).ffill().fillna(1000)

    close_s = pd.to_numeric(df["Close"], errors="coerce")
    open_s = pd.to_numeric(df["Open"], errors="coerce")
    high_s = pd.to_numeric(df["High"], errors="coerce")
    low_s = pd.to_numeric(df["Low"], errors="coerce")
    vol_s = pd.to_numeric(df["Volume"], errors="coerce")

    if close_s.isna().all() or len(close_s.dropna()) < 20: return None

    p_now = float(close_s.iloc[-1])
    m5 = float(close_s.rolling(5).mean().iloc[-1])
    m10 = float(close_s.rolling(10).mean().iloc[-1])
    m20 = float(close_s.rolling(20).mean().iloc[-1])
    
    if m20 == 0: return None
    bias = ((p_now - m20) / m20) * 100

    vol_now = float(vol_s.iloc[-1])
    vol_ma5 = float(vol_s.rolling(5).mean().iloc[-1])

    is_strong_candle = p_now > open_s.iloc[-1] and (p_now - open_s.iloc[-1]) > (high_s.iloc[-1] - p_now) * 2
    tactic_a_strong = p_now > m5 > m10 and vol_now > vol_ma5 * 1.5
    tactic_a_weak = p_now < m10 and p_now < m5

    try:
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

    sim_returns = []
    buy_prices = []
    
    if len(close_s) >= 40:
        for i in range(20, len(close_s) - 5):
            c_p = close_s.iloc[i]
            c_m5 = close_s.rolling(5).mean().iloc[i]
            c_m10 = close_s.rolling(10).mean().iloc[i]
            if c_p > c_m5 > c_m10:
                buy_prices.append(c_p)
                sim_returns.append((close_s.iloc[i+5] - c_p) / c_p)
                
    if len(sim_returns) < 5: win_rate, avg_ret = 50.0, 0.0
    else: win_rate, avg_ret = (np.array(sim_returns) > 0).mean() * 100, np.array(sim_returns).mean() * 100

    ind = TWSE_NAME_MAP.get(sid, "未知")
    stop_price = max(m10, p_now - 1.5 * atr_now)

    return {
        "代號": sid,
        "名稱": TWSE_NAME_MAP.get(sid, sid),
        "現價": p_now,
        "M5": m5,
        "M10": m10,
        "乖離": bias,
        "勝率": win_rate,
        "停損價": stop_price
    }

@st.cache_data(ttl=900, show_spinner=False)
def level2_quant_engine(calc_list, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, fm_token=None):
    if not calc_list: return pd.DataFrame()

    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_single_stock_batch, sid, fm_token): sid for sid in calc_list}
        for future in concurrent.futures.as_completed(futures):
            sid, df = future.result()
            if df is not None and not df.empty: bulk_data[sid] = df

    if not bulk_data: return None

    intel_results = []
    for sid in calc_list:
        try:
            df = bulk_data.get(sid)
            if df is None or df.empty: continue
            
            df = df[~df.index.duplicated(keep="last")].copy()
            if "Volume" not in df.columns: df["Volume"] = 0
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).replace(0, np.nan).ffill().fillna(1000)

            close_s = pd.to_numeric(df["Close"], errors="coerce")
            open_s = pd.to_numeric(df["Open"], errors="coerce")
            high_s = pd.to_numeric(df["High"], errors="coerce")
            low_s = pd.to_numeric(df["Low"], errors="coerce")
            vol_s = pd.to_numeric(df["Volume"], errors="coerce")

            if close_s.isna().all() or len(close_s.dropna()) < 20: continue

            p_now = float(close_s.iloc[-1])
            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            
            if m20 == 0: continue
            bias = ((p_now - m20) / m20) * 100

            vol_now = float(vol_s.iloc[-1])
            vol_ma5 = float(vol_s.rolling(5).mean().iloc[-1])
            vol_ma20 = float(vol_s.rolling(20).mean().iloc[-1])

            vol_ratio = vol_now / vol_ma5 if vol_ma5 > 0 else 1
            close_position = (p_now - float(low_s.iloc[-1])) / (float(high_s.iloc[-1]) - float(low_s.iloc[-1])) if float(high_s.iloc[-1]) != float(low_s.iloc[-1]) else 0.5

            try:
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
            
            atr_percent = (atr_now / p_now) * 100

            # 🚀 V32.3 新增武器：布林通道 (BBAND)
            std20 = float(close_s.rolling(20).std().iloc[-1])
            bb_upper = m20 + 2 * std20

            # 🚀 V32.3 新增武器：RSI(14)
            delta = close_s.diff()
            up = delta.clip(lower=0)
            down = -1 * delta.clip(upper=0)
            ema_up = up.ewm(com=13, adjust=False).mean()
            ema_down = down.ewm(com=13, adjust=False).mean()
            rs = ema_up / ema_down
            rsi = 100 - (100 / (1 + rs))
            rsi_now = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

            # 🚀 V32.3 新增武器：MACD(12,26,9) 翻正判定
            exp1 = close_s.ewm(span=12, adjust=False).mean()
            exp2 = close_s.ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            hist = macd - signal
            hist_now = float(hist.iloc[-1])
            hist_prev = float(hist.iloc[-2]) if len(hist) > 1 else hist_now
            macd_cross = (hist_now > 0 and hist_prev <= 0) # 剛翻正

            ind = TWSE_IND_MAP.get(sid, "未知")

            is_strong_candle = p_now > open_s.iloc[-1] and (p_now - open_s.iloc[-1]) > (high_s.iloc[-1] - p_now) * 2
            tactic_a_strong = p_now > m5 > m10 and vol_now > vol_ma5 * 1.4
            tactic_a_weak = p_now < m10 and p_now < m5

            tactic = "⚪ 震盪"
            if p_now > m5 > m10 and vol_now > vol_ma5 * 1.5: tactic = "🔥 爆量主升"
            elif p_now > m5 > m10: tactic = "🚀 穩步多頭"
            elif p_now > m10 and p_now < m5: tactic = "🛡️ 回踩 M10"
            elif p_now < m10: tactic = "⚠️ 跌破短均"

            sim_returns = []
            if len(close_s) >= 40:
                for i in range(20, len(close_s) - 5):
                    c_p = close_s.iloc[i]
                    c_m5 = close_s.rolling(5).mean().iloc[i]
                    c_m10 = close_s.rolling(10).mean().iloc[i]
                    if c_p > c_m5 > c_m10:
                        sim_returns.append((close_s.iloc[i+5] - c_p) / c_p)
                        
            if len(sim_returns) < 5: win_rate, avg_ret = 50.0, 0.0
            else: win_rate, avg_ret = (np.array(sim_returns) > 0).mean() * 100, np.array(sim_returns).mean() * 100

            s_score = MACRO_SCORE
            if p_now > m5: s_score += 1
            if p_now > m20: s_score += 1
            else: s_score -= 1
            if is_strong_candle: s_score += 1

            hot_industries = ["半導體", "電腦及週邊設備業", "電子零組件業", "其他電子業"]
            if any(h_ind in ind for h_ind in hot_industries): s_score += 1

            if bias > 10: s_score -= 2
            elif 0 <= bias <= 5: s_score += 1

            if tactic_a_strong: s_score += 1
            elif tactic_a_weak: s_score -= 1

            stop_price = max(m10, p_now - 1.5 * atr_now)
            raw_risk = max(p_now - stop_price, 0.01)

            intel_results.append({
                "代號": sid, "名稱": TWSE_NAME_MAP.get(sid, sid), "產業": ind, "現價": p_now, "成交量": vol_now, "今日放量": (vol_now > vol_ma5 * 1.4),
                "乖離(%)": bias, "M5": m5, "M10": m10, "勝率(%)": win_rate, "均報(%)": avg_ret, "戰術型態": tactic,
                "停損價": stop_price, "原始風險差額": raw_risk, "基本達標": (s_score >= 6 and bias <= 8), "安全指數": s_score,
                "vol_ratio": vol_ratio, "close_position": close_position,
                "vol_ma20": vol_ma20, "atr_percent": atr_percent,
                "ATR": atr_now, "BB_Upper": bb_upper, "RSI": rsi_now, "MACD_Cross": macd_cross # 🚀 新增指標輸出
            })
        except Exception as e:
            continue

    return pd.DataFrame(intel_results)
