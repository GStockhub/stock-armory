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
    bias = ((p_now - m20) / m20) * 100 if m20 > 0 else 0.0

    df_bt = pd.DataFrame({"Close": close_s, "Open": open_s, "High": high_s, "Low": low_s, "Volume": vol_s}).dropna(subset=["Close", "Open", "High", "Low"])
    if len(df_bt) < 20: return None

    df_bt["MA5"] = df_bt["Close"].rolling(5).mean()
    df_bt["MA10"] = df_bt["Close"].rolling(10).mean()
    df_bt["MA20"] = df_bt["Close"].rolling(20).mean()
    df_bt["RollMax20"] = df_bt["Close"].rolling(20).max()
    df_bt["Vol_MA5"] = df_bt["Volume"].rolling(5).mean()

    try:
        df_bt["PrevClose"] = df_bt["Close"].shift(1)
        tr1 = df_bt["High"] - df_bt["Low"]
        tr2 = (df_bt["High"] - df_bt["PrevClose"]).abs()
        tr3 = (df_bt["Low"] - df_bt["PrevClose"]).abs()
        df_bt["TR"] = np.maximum(tr1, np.maximum(tr2, tr3))
        df_bt["ATR"] = df_bt["TR"].rolling(14).mean()
        atr_now = float(df_bt["ATR"].iloc[-1])
        if pd.isna(atr_now) or atr_now <= 0: atr_now = p_now * 0.03
    except Exception: atr_now = p_now * 0.03

    low_9 = df_bt["Low"].rolling(9).min()
    high_9 = df_bt["High"].rolling(9).max()
    range_9 = (high_9 - low_9).replace(0, np.nan)

    df_bt["RSV"] = ((df_bt["Close"] - low_9) / range_9) * 100
    df_bt["RSV"] = df_bt["RSV"].fillna(0)
    df_bt["K"] = df_bt["RSV"].ewm(alpha=1/3, adjust=False).mean()
    df_bt["D"] = df_bt["K"].ewm(alpha=1/3, adjust=False).mean()
    df_bt["RedK"] = df_bt["Close"] > df_bt["Open"]
    df_bt["ClosePos"] = np.where((df_bt["High"] - df_bt["Low"]) > 0, (df_bt["Close"] - df_bt["Low"]) / (df_bt["High"] - df_bt["Low"]), 0)

    sig_trend = (df_bt["MA5"] > df_bt["MA10"]) & (df_bt["MA10"] > df_bt["MA20"])
    sig_a = ((df_bt["Volume"] > df_bt["Vol_MA5"] * 1.4) & (df_bt["K"] > 75) & (df_bt["Close"] >= df_bt["RollMax20"] * 0.98) & (df_bt["ClosePos"] > 0.65))
    on_m5 = (df_bt["Close"] >= df_bt["MA5"] * 0.985) & (df_bt["Close"] <= df_bt["MA5"] * 1.04)
    on_m10 = (df_bt["Close"] >= df_bt["MA10"] * 0.985) & (df_bt["Close"] <= df_bt["MA10"] * 1.04)
    bias_col = (df_bt["Close"] - df_bt["MA20"]) / df_bt["MA20"] * 100
    sig_b = (bias_col < 8) & df_bt["RedK"] & (on_m5 | on_m10) & (df_bt["K"] > df_bt["D"])

    sig_mask = sig_trend & (sig_a | sig_b)
    signals_idx = df_bt[sig_mask].index

    sim_returns = []
    for idx in signals_idx:
        loc_idx = df_bt.index.get_loc(idx)
        if loc_idx + 1 >= len(df_bt): continue
        entry_p = float(df_bt.iloc[loc_idx + 1]["Open"])
        prev_close = float(df_bt.iloc[loc_idx]["Close"])

        if prev_close > 0 and entry_p > prev_close * 1.04: continue

        try:
            entry_atr = float(df_bt.iloc[loc_idx]["ATR"])
            if pd.isna(entry_atr) or entry_atr <= 0: entry_atr = entry_p * 0.03
        except Exception: entry_atr = entry_p * 0.03

        future_data = df_bt.iloc[loc_idx + 1: loc_idx + 21]
        if future_data.empty: continue

        stop_loss = entry_p - 1.5 * entry_atr
        tp_target = entry_p + 2.0 * entry_atr
        sold_half = False
        ret = 0.0

        for _, row in future_data.iterrows():
            curr_p = float(row["Close"])
            curr_m5 = float(row["MA5"]) if pd.notna(row["MA5"]) else curr_p
            if curr_p > entry_p + entry_atr: stop_loss = max(stop_loss, entry_p)
            if not sold_half and curr_p >= tp_target: sold_half = True
            if sold_half:
                if curr_p < curr_m5:
                    ret = 0.5 * ((tp_target - entry_p) / entry_p) + 0.5 * ((curr_m5 - entry_p) / entry_p)
                    break
            else:
                if curr_p < stop_loss:
                    ret = (stop_loss - entry_p) / entry_p
                    break
        else:
            final_p = float(future_data["Close"].iloc[-1])
            if sold_half: ret = 0.5 * ((tp_target - entry_p) / entry_p) + 0.5 * ((final_p - entry_p) / entry_p)
            else: ret = (final_p - entry_p) / entry_p
        sim_returns.append(ret)

    win_rate = 50.0 if len(sim_returns) < 5 else (np.array(sim_returns) > 0).mean() * 100

    return {"代號": sid, "名稱": TWSE_NAME_MAP.get(sid, sid), "現價": p_now, "M5": m5, "M10": m10, "M20": m20, "乖離": bias, "ATR": atr_now, "勝率": win_rate, "停損價": max(m10, p_now - 1.5 * atr_now)}

@st.cache_data(ttl=3600, show_spinner=False)
def level2_quant_engine(id_tuple, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, fm_token=None):
    id_list = [str(x).strip() for x in list(id_tuple) if str(x).strip()]
    intel_results = []
    if not id_list: return pd.DataFrame()

    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_single_stock_batch, sid, fm_token): sid for sid in id_list}
        for future in concurrent.futures.as_completed(futures):
            sid_str, df = future.result()
            if df is not None and not df.empty: bulk_data[sid_str] = df

    if len(bulk_data) == 0: return None

    for sid in id_list:
        try:
            if not sid.startswith("00") and not sid.isdigit(): continue
            ind = TWSE_IND_MAP.get(sid) or "其他"
            if sid.startswith("00"): ind = "ETF"
            if "金融" in ind or "保險" in ind: continue

            df_stock = bulk_data.get(sid)
            if df_stock is None or df_stock.empty: continue
            df_stock = df_stock[~df_stock.index.duplicated(keep="last")].copy()

            if "Volume" not in df_stock.columns: df_stock["Volume"] = 0
            df_stock["Volume"] = pd.to_numeric(df_stock["Volume"], errors="coerce").fillna(0)
            df_stock["Volume"] = df_stock["Volume"].replace(0, np.nan).ffill().fillna(1000)

            close_s = pd.to_numeric(df_stock["Close"], errors="coerce")
            open_s = pd.to_numeric(df_stock["Open"], errors="coerce")
            high_s = pd.to_numeric(df_stock["High"], errors="coerce")
            low_s = pd.to_numeric(df_stock["Low"], errors="coerce")
            vol_s = pd.to_numeric(df_stock["Volume"], errors="coerce")

            if len(close_s.dropna()) < 20: continue

            p_now = float(close_s.iloc[-1])
            open_now = float(open_s.iloc[-1])
            high_now = float(high_s.iloc[-1])
            low_now = float(low_s.iloc[-1])
            prev_close = float(close_s.iloc[-2]) if len(close_s) > 1 else open_now
            vol_now = float(vol_s.iloc[-1]) / 1000

            if prev_close > 0 and ((open_now - prev_close) / prev_close * 100) > 6.0: continue
            if p_now < 10 or vol_now < 0.3: continue

            m5 = float(close_s.rolling(5).mean().iloc[-1])
            m10 = float(close_s.rolling(10).mean().iloc[-1])
            m20 = float(close_s.rolling(20).mean().iloc[-1])
            vol_ma5 = float(vol_s.rolling(5).mean().iloc[-1]) / 1000 if len(vol_s) >= 5 else vol_now
            bias = ((p_now - m20) / m20) * 100 if m20 > 0 else 0.0

            df_bt = pd.DataFrame({"Close": close_s, "Open": open_s, "High": high_s, "Low": low_s, "Volume": vol_s}).dropna(subset=["Close", "Open", "High", "Low"])
            if len(df_bt) < 20: continue

            df_bt["MA5"] = df_bt["Close"].rolling(5).mean()
            df_bt["MA10"] = df_bt["Close"].rolling(10).mean()
            df_bt["MA20"] = df_bt["Close"].rolling(20).mean()
            df_bt["RollMax20"] = df_bt["Close"].rolling(20).max()
            df_bt["Vol_MA5"] = df_bt["Volume"].rolling(5).mean()

            try:
                df_bt["PrevClose"] = df_bt["Close"].shift(1)
                tr1 = df_bt["High"] - df_bt["Low"]
                tr2 = (df_bt["High"] - df_bt["PrevClose"]).abs()
                tr3 = (df_bt["Low"] - df_bt["PrevClose"]).abs()
                df_bt["TR"] = np.maximum(tr1, np.maximum(tr2, tr3))
                df_bt["ATR"] = df_bt["TR"].rolling(14).mean()
                atr_now = float(df_bt["ATR"].iloc[-1])
                if pd.isna(atr_now) or atr_now <= 0: atr_now = p_now * 0.03
            except Exception: atr_now = p_now * 0.03

            low_9 = df_bt["Low"].rolling(9).min()
            high_9 = df_bt["High"].rolling(9).max()
            range_9 = (high_9 - low_9).replace(0, np.nan)

            df_bt["RSV"] = ((df_bt["Close"] - low_9) / range_9) * 100
            df_bt["RSV"] = df_bt["RSV"].fillna(0)
            df_bt["K"] = df_bt["RSV"].ewm(alpha=1/3, adjust=False).mean()
            df_bt["D"] = df_bt["K"].ewm(alpha=1/3, adjust=False).mean()
            df_bt["RedK"] = df_bt["Close"] > df_bt["Open"]
            df_bt["ClosePos"] = np.where((df_bt["High"] - df_bt["Low"]) > 0, (df_bt["Close"] - df_bt["Low"]) / (df_bt["High"] - df_bt["Low"]), 0)

            k_now = float(df_bt["K"].iloc[-1])
            d_now = float(df_bt["D"].iloc[-1])
            red_k = p_now > open_now
            close_position = (p_now - low_now) / (high_now - low_now) if high_now > low_now else 0
            is_strong_candle = ((p_now - open_now) / open_now) > 0.035 if open_now > 0 else False

            trend_strength = (m5 > m10) and (m10 > m20)
            soft_trend_strength = (m5 > m10) or (p_now > m20)

            vol_ratio = vol_now / vol_ma5 if vol_ma5 > 0 else 0
            is_breakout_base = (vol_ratio > 1.3) and (k_now > 70) and (p_now >= close_s.iloc[-20:].max() * 0.975)

            tactic_a_strong = is_breakout_base and (vol_ratio >= 1.6) and (close_position > 0.65)
            tactic_a_weak = is_breakout_base and (not tactic_a_strong)

            on_m5 = (p_now >= m5 * 0.985) and (p_now <= m5 * 1.04)
            on_m10 = (p_now >= m10 * 0.985) and (p_now <= m10 * 1.04)
            tactic_b = (bias < 8) and red_k and (on_m5 or on_m10) and (k_now >= d_now)

            is_candidate = soft_trend_strength and (is_breakout_base or tactic_b or trend_strength)

            if tactic_a_strong and tactic_b: tactic_label = "🔥 雙戰術共振"
            elif tactic_a_strong: tactic_label = "🚀 S級突破"
            elif tactic_a_weak: tactic_label = "⚠️ 弱勢震盪"
            elif tactic_b: tactic_label = "🛡️ 穩健回踩"
            else: tactic_label = "⏳ 觀望盤整"

            sig_trend = (df_bt["MA5"] > df_bt["MA10"]) & (df_bt["MA10"] > df_bt["MA20"])
            sig_a = ((df_bt["Volume"] > df_bt["Vol_MA5"] * 1.4) & (df_bt["K"] > 75) & (df_bt["Close"] >= df_bt["RollMax20"] * 0.98) & (df_bt["ClosePos"] > 0.65))
            bt_on_m5 = (df_bt["Close"] >= df_bt["MA5"] * 0.985) & (df_bt["Close"] <= df_bt["MA5"] * 1.04)
            bt_on_m10 = (df_bt["Close"] >= df_bt["MA10"] * 0.985) & (df_bt["Close"] <= df_bt["MA10"] * 1.04)
            bias_col = (df_bt["Close"] - df_bt["MA20"]) / df_bt["MA20"] * 100
            sig_b = (bias_col < 8) & df_bt["RedK"] & (bt_on_m5 | bt_on_m10) & (df_bt["K"] > df_bt["D"])

            sig_mask = sig_trend & (sig_a | sig_b)
            signals_idx = df_bt[sig_mask].index

            sim_returns = []
            for idx in signals_idx:
                loc_idx = df_bt.index.get_loc(idx)
                if loc_idx + 1 >= len(df_bt): continue
                entry_p = float(df_bt.iloc[loc_idx + 1]["Open"])
                prev_close_bt = float(df_bt.iloc[loc_idx]["Close"])
                if prev_close_bt > 0 and entry_p > prev_close_bt * 1.04: continue

                try:
                    entry_atr = float(df_bt.iloc[loc_idx]["ATR"])
                    if pd.isna(entry_atr) or entry_atr <= 0: entry_atr = entry_p * 0.03
                except Exception: entry_atr = entry_p * 0.03

                future_data = df_bt.iloc[loc_idx + 1: loc_idx + 21]
                if future_data.empty: continue

                stop_loss = entry_p - 1.5 * entry_atr
                tp_target = entry_p + 2.0 * entry_atr
                sold_half = False
                ret = 0.0

                for _, row in future_data.iterrows():
                    curr_p = float(row["Close"])
                    curr_m5 = float(row["MA5"]) if pd.notna(row["MA5"]) else curr_p
                    if curr_p > entry_p + entry_atr: stop_loss = max(stop_loss, entry_p)
                    if not sold_half and curr_p >= tp_target: sold_half = True
                    if sold_half:
                        if curr_p < curr_m5:
                            ret = 0.5 * ((tp_target - entry_p) / entry_p) + 0.5 * ((curr_m5 - entry_p) / entry_p)
                            break
                    else:
                        if curr_p < stop_loss:
                            ret = (stop_loss - entry_p) / entry_p
                            break
                else:
                    final_p = float(future_data["Close"].iloc[-1])
                    if sold_half: ret = 0.5 * ((tp_target - entry_p) / entry_p) + 0.5 * ((final_p - entry_p) / entry_p)
                    else: ret = (final_p - entry_p) / entry_p
                sim_returns.append(ret)

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
                "M5": m5, "M10": m10, "M20": m20, "乖離(%)": bias, "ATR": atr_now, "基本達標": bool(is_candidate), "安全指數": max(1, min(10, int(s_score))),
                "勝率(%)": round(win_rate, 1), "均報(%)": round(avg_ret, 2), "停損價": round(stop_price, 2), "停利價": round(p_now + 2.0 * atr_now, 2),
                "原始風險差額": round(raw_risk, 4), "戰術型態": tactic_label,
                "vol_ratio": round(vol_ratio, 2), "close_position": round(close_position, 2)
            })
        except Exception: continue
    return pd.DataFrame(intel_results)
