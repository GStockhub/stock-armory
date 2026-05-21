import pandas as pd
import numpy as np
import streamlit as st
import concurrent.futures
from data_center import fetch_single_stock_batch, safe_download, ACTIVE_ETF_NAME_MAP


def _is_etf_like(sid):
    return str(sid).strip().upper().startswith("00")


def _last_roll(series, window, fallback=None):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return fallback
    if len(s) >= window:
        v = s.rolling(window).mean().iloc[-1]
    else:
        v = s.mean()
    if pd.isna(v):
        return fallback if fallback is not None else float(s.iloc[-1])
    return float(v)

def _liquidity_profile(price, today_volume, avg_volume_20):
    """短線流動性濾網。

    price_provider 可能回傳「股」或「張」。這裡用數量級自動判斷並統一換算成張與成交金額。
    - 地雷級 / 不適合短線：不應進 S/A/B 主推薦。
    - 可交易：最多 B 級。
    - 理想短線：可依原本分數進 S/A/B。
    """
    try:
        price = float(price or 0)
        today_volume = float(today_volume or 0)
        avg_volume_20 = float(avg_volume_20 or 0)
    except Exception:
        price, today_volume, avg_volume_20 = 0.0, 0.0, 0.0

    # TWSE 官方為股，部分來源可能已是張；用 100,000 作為保守分界。
    unit_is_shares = max(today_volume, avg_volume_20) >= 100000
    today_lots = today_volume / 1000.0 if unit_is_shares else today_volume
    avg_lots_20 = avg_volume_20 / 1000.0 if unit_is_shares else avg_volume_20
    avg_amount_20 = avg_volume_20 * price if unit_is_shares else avg_volume_20 * 1000.0 * price

    if avg_lots_20 < 300 or avg_amount_20 < 20_000_000:
        tier = "地雷級"
        status = "⛔ 地雷級：流動性不足"
        tradable = False
        max_grade = "排除"
        penalty = 45
    elif avg_lots_20 < 500 or avg_amount_20 < 30_000_000:
        tier = "不適合短線"
        status = "⛔ 不適合短線：量/成交金額不足"
        tradable = False
        max_grade = "觀察"
        penalty = 35
    elif avg_lots_20 < 1000 or avg_amount_20 < 80_000_000:
        tier = "可交易"
        status = "🟡 可交易但不理想"
        tradable = True
        max_grade = "B"
        penalty = 10
    else:
        tier = "理想短線"
        status = "🟢 理想短線流動性"
        tradable = True
        max_grade = "S"
        penalty = 0

    return {
        "今日量(張)": round(today_lots, 1),
        "20日均量(張)": round(avg_lots_20, 1),
        "20日均成交金額": round(avg_amount_20, 0),
        "流動性分級": tier,
        "流動性狀態": status,
        "短線可交易": bool(tradable),
        "最高評級限制": max_grade,
        "流動性扣分": penalty,
    }


def _is_fake_volume_spike(vol_ratio, today_lots):
    try:
        return float(vol_ratio or 0) >= 2.0 and float(today_lots or 0) < 500
    except Exception:
        return False

def _simulate_sop_returns(close_s, open_s, high_s, low_s, vol_s, max_hold_bars=10):
    """用接近你真實SOP的方式估算：隔日開盤進、跳空>4.5%不追、+5.5%先出半、M5/M10控風險。"""
    df_bt = pd.DataFrame({"Close": close_s, "Open": open_s, "High": high_s, "Low": low_s, "Volume": vol_s}).dropna()
    if len(df_bt) < 35:
        return []
    df_bt["MA5"] = df_bt["Close"].rolling(5).mean()
    df_bt["MA10"] = df_bt["Close"].rolling(10).mean()
    df_bt["MA20"] = df_bt["Close"].rolling(20).mean()
    df_bt["VolMA5"] = df_bt["Volume"].rolling(5).mean()
    df_bt["PrevClose"] = df_bt["Close"].shift(1)
    tr1 = df_bt["High"] - df_bt["Low"]
    tr2 = (df_bt["High"] - df_bt["PrevClose"]).abs()
    tr3 = (df_bt["Low"] - df_bt["PrevClose"]).abs()
    df_bt["ATR"] = np.maximum(tr1, np.maximum(tr2, tr3)).rolling(14).mean()

    returns = []
    for i in range(20, len(df_bt) - 2):
        row = df_bt.iloc[i]
        if pd.isna(row["MA5"]) or pd.isna(row["MA10"]) or pd.isna(row["MA20"]):
            continue
        close_pos = (row["Close"] - row["Low"]) / (row["High"] - row["Low"]) if row["High"] > row["Low"] else 0.5
        trend_signal = row["Close"] > row["MA5"] > row["MA10"]
        pullback_signal = row["Close"] >= row["MA10"] and row["Close"] <= row["MA5"] * 1.015 and row["Close"] > row["Open"]
        volume_ok = row["Volume"] >= row["VolMA5"] * 0.8 if row["VolMA5"] > 0 else True
        if not ((trend_signal and close_pos >= 0.55 and volume_ok) or pullback_signal):
            continue

        entry_idx = i + 1
        entry = float(df_bt.iloc[entry_idx]["Open"])
        prev_close = float(row["Close"])
        if prev_close > 0 and entry > prev_close * 1.045:
            continue

        atr = float(row["ATR"]) if pd.notna(row["ATR"]) and row["ATR"] > 0 else entry * 0.03
        stop = max(float(row["MA10"]), entry - 1.5 * atr, entry * 0.97)
        take_half = entry * 1.055
        sold_half = False
        ret = 0.0
        end_idx = min(entry_idx + max_hold_bars, len(df_bt) - 1)

        for j in range(entry_idx, end_idx + 1):
            rj = df_bt.iloc[j]
            curr = float(rj["Close"])
            ma5 = float(rj["MA5"]) if pd.notna(rj["MA5"]) else curr
            ma10 = float(rj["MA10"]) if pd.notna(rj["MA10"]) else stop
            if curr >= entry * 1.035:
                stop = max(stop, entry)
            if not sold_half and curr >= take_half:
                sold_half = True
            if curr < ma10 or curr < stop:
                exit_p = max(min(curr, ma10), stop)
                ret = (0.5 * ((take_half - entry) / entry) + 0.5 * ((exit_p - entry) / entry)) if sold_half else ((exit_p - entry) / entry)
                break
            if sold_half and curr < ma5:
                ret = 0.5 * ((take_half - entry) / entry) + 0.5 * ((ma5 - entry) / entry)
                break
        else:
            final_p = float(df_bt.iloc[end_idx]["Close"])
            ret = 0.5 * ((take_half - entry) / entry) + 0.5 * ((final_p - entry) / entry) if sold_half else ((final_p - entry) / entry)
        returns.append(ret)
    return returns


@st.cache_data(ttl=900, show_spinner=False)
def run_sandbox_sim(sid, TWSE_NAME_MAP, fm_token=None):
    sid = str(sid).strip()
    df = safe_download(sid, fm_token, min_bars=(1 if _is_etf_like(sid) else 20))
    if df is None or df.empty or len(df) < (1 if _is_etf_like(sid) else 20): return None
    
    df = df[~df.index.duplicated(keep="last")].copy()
    if "Volume" not in df.columns: df["Volume"] = 0
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
    df["Volume"] = df["Volume"].replace(0, np.nan).ffill().fillna(1000)

    close_s = pd.to_numeric(df["Close"], errors="coerce")
    open_s = pd.to_numeric(df["Open"], errors="coerce")
    high_s = pd.to_numeric(df["High"], errors="coerce")
    low_s = pd.to_numeric(df["Low"], errors="coerce")
    vol_s = pd.to_numeric(df["Volume"], errors="coerce")

    valid_close = close_s.dropna()
    min_need = 1 if _is_etf_like(sid) else 20
    if close_s.isna().all() or len(valid_close) < min_need: return None

    p_now = float(valid_close.iloc[-1])
    m5 = _last_roll(close_s, 5, p_now)
    m10 = _last_roll(close_s, 10, m5)
    m20 = _last_roll(close_s, 20, m10)
    
    if not np.isfinite(m20) or m20 == 0: return None
    bias = ((p_now - m20) / m20) * 100

    vol_now = float(vol_s.iloc[-1])
    vol_ma5 = _last_roll(vol_s, 5, 1.0)

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

    sim_returns = _simulate_sop_returns(close_s, open_s, high_s, low_s, vol_s)
                
    if len(sim_returns) < 5: win_rate, avg_ret = 50.0, 0.0
    else: win_rate, avg_ret = (np.array(sim_returns) > 0).mean() * 100, np.array(sim_returns).mean() * 100

    ind = TWSE_NAME_MAP.get(sid, "未知")
    stop_price = max(m10, p_now - 1.5 * atr_now)

    return {
        "代號": sid,
        "名稱": TWSE_NAME_MAP.get(sid, ACTIVE_ETF_NAME_MAP.get(sid, sid)),
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

            valid_close = close_s.dropna()
            min_need = 1 if _is_etf_like(sid) else 20
            if close_s.isna().all() or len(valid_close) < min_need: continue

            p_now = float(valid_close.iloc[-1])
            prev_close = float(valid_close.iloc[-2]) if len(valid_close) >= 2 else p_now
            close_3_base = float(valid_close.iloc[-4]) if len(valid_close) >= 4 else p_now
            close_5_base = float(valid_close.iloc[-6]) if len(valid_close) >= 6 else p_now
            day_return = (p_now / prev_close - 1) * 100 if prev_close > 0 else 0.0
            ret_3d = (p_now / close_3_base - 1) * 100 if close_3_base > 0 else 0.0
            ret_5d = (p_now / close_5_base - 1) * 100 if close_5_base > 0 else 0.0
            m5 = _last_roll(close_s, 5, p_now)
            m10 = _last_roll(close_s, 10, m5)
            m20 = _last_roll(close_s, 20, m10)
            
            if not np.isfinite(m20) or m20 == 0: continue
            bias = ((p_now - m20) / m20) * 100

            vol_now = float(vol_s.iloc[-1])
            vol_ma5 = _last_roll(vol_s, 5, 1.0)
            vol_ma20 = _last_roll(vol_s, 20, vol_ma5)

            vol_ratio = vol_now / vol_ma5 if vol_ma5 > 0 else 1
            liq = _liquidity_profile(p_now, vol_now, vol_ma20)
            fake_volume_spike = _is_fake_volume_spike(vol_ratio, liq.get("今日量(張)", 0))
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
            std20 = float(close_s.dropna().tail(20).std()) if len(close_s.dropna()) >= 2 else 0.0
            if pd.isna(std20): std20 = 0.0
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

            sim_returns = _simulate_sop_returns(close_s, open_s, high_s, low_s, vol_s)
                        
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
            if fake_volume_spike:
                s_score -= 2
            if not liq.get("短線可交易", True):
                s_score -= 3

            stop_price = max(m10, p_now - 1.5 * atr_now)
            raw_risk = max(p_now - stop_price, 0.01)

            intel_results.append({
                "代號": sid, "名稱": TWSE_NAME_MAP.get(sid, ACTIVE_ETF_NAME_MAP.get(sid, sid)), "產業": ind, "現價": p_now, "成交量": vol_now, "今日放量": (vol_now > vol_ma5 * 1.4),
                "日漲幅(%)": day_return, "3日漲幅(%)": ret_3d, "5日漲幅(%)": ret_5d,
                "乖離(%)": bias, "M5": m5, "M10": m10, "勝率(%)": win_rate, "均報(%)": avg_ret, "戰術型態": tactic,
                "停損價": stop_price, "原始風險差額": raw_risk, "基本達標": (s_score >= 6 and bias <= 8), "安全指數": s_score,
                "vol_ratio": vol_ratio, "close_position": close_position,
                "vol_ma20": vol_ma20, "atr_percent": atr_percent,
                "今日量(張)": liq.get("今日量(張)", 0), "20日均量(張)": liq.get("20日均量(張)", 0),
                "20日均成交金額": liq.get("20日均成交金額", 0), "流動性分級": liq.get("流動性分級", ""),
                "流動性狀態": liq.get("流動性狀態", ""), "短線可交易": liq.get("短線可交易", True),
                "最高評級限制": liq.get("最高評級限制", "S"), "流動性扣分": liq.get("流動性扣分", 0),
                "假放量警告": bool(fake_volume_spike),
                "ATR": atr_now, "BB_Upper": bb_upper, "RSI": rsi_now, "MACD_Cross": macd_cross # 🚀 新增指標輸出
            })
        except Exception as e:
            continue

    return pd.DataFrame(intel_results)
