import pandas as pd
import numpy as np
import streamlit as st
import concurrent.futures
from data_center import fetch_single_stock_batch, safe_download

@st.cache_data(ttl=3600, show_spinner=False)
def run_sandbox_sim(sid, TWSE_NAME_MAP, fm_token=None):
    df = safe_download(sid, fm_token)
    if df is None or df.empty or len(df) < 20: return None
    
    # 🩹 V26.8 盤中搶修：YF 零量 Bug 補救
    df = df.copy()
    if float(df['Volume'].iloc[-1]) == 0 and len(df) > 1:
        df.loc[df.index[-1], 'Volume'] = df['Volume'].iloc[-2]
        
    close_s, open_s, vol_s = df['Close'], df['Open'], df['Volume']
    p_now = float(close_s.iloc[-1])
    m5 = float(close_s.rolling(5).mean().iloc[-1])
    m10 = float(close_s.rolling(10).mean().iloc[-1])
    m20 = float(close_s.rolling(20).mean().iloc[-1])
    bias = ((p_now - m20) / m20) * 100

    df_bt = pd.DataFrame({'Close': close_s, 'Open': open_s, 'High': df['High'], 'Low': df['Low'], 'Volume': df['Volume']})
    df_bt['MA5'] = df_bt['Close'].rolling(5).mean()
    df_bt['MA10'] = df_bt['Close'].rolling(10).mean()
    df_bt['MA20'] = df_bt['Close'].rolling(20).mean()
    df_bt['RollMax20'] = df_bt['Close'].rolling(20).max()
    df_bt['Vol_MA5'] = df_bt['Volume'].rolling(5).mean()
    
    # ATR 指標實裝
    df_bt['PrevClose'] = df_bt['Close'].shift(1)
    df_bt['TR'] = np.maximum(df_bt['High'] - df_bt['Low'], np.maximum(abs(df_bt['High'] - df_bt['PrevClose']), abs(df_bt['Low'] - df_bt['PrevClose'])))
    df_bt['ATR'] = df_bt['TR'].rolling(14).mean()
    atr_now = float(df_bt['ATR'].iloc[-1])
    if pd.isna(atr_now) or atr_now == 0: atr_now = p_now * 0.03
    
    df_bt['RSV'] = (df_bt['Close'] - df_bt['Low'].rolling(9).min()) / (df_bt['High'].rolling(9).max() - df_bt['Low'].rolling(9).min()) * 100
    df_bt['K'] = df_bt['RSV'].ewm(alpha=1/3, adjust=False).mean()
    df_bt['D'] = df_bt['K'].ewm(alpha=1/3, adjust=False).mean()
    df_bt['RedK'] = df_bt['Close'] > df_bt['Open']
    df_bt['ClosePos'] = np.where((df_bt['High'] - df_bt['Low']) > 0, (df_bt['Close'] - df_bt['Low']) / (df_bt['High'] - df_bt['Low']), 0)
    
    sig_trend = (df_bt['MA5'] > df_bt['MA10']) & (df_bt['MA10'] > df_bt['MA20'])
    sig_a = (df_bt['Volume'] > df_bt['Vol_MA5'] * 1.5) & (df_bt['K'] > 80) & (df_bt['Close'] >= df_bt['RollMax20'] * 0.98) & (df_bt['ClosePos'] > 0.7)
    on_m5 = (df_bt['Close'] >= df_bt['MA5']) & (df_bt['Close'] <= df_bt['MA5'] * 1.03)
    on_m10 = (df_bt['Close'] >= df_bt['MA10']) & (df_bt['Close'] <= df_bt['MA10'] * 1.03)
    bias_col = (df_bt['Close'] - df_bt['MA20']) / df_bt['MA20'] * 100
    sig_b = (bias_col < 7) & df_bt['RedK'] & (on_m5 | on_m10) & (df_bt['K'] > df_bt['D'])

    sig_mask = sig_trend & (sig_a | sig_b)
    signals_idx = df_bt[sig_mask].index

    sim_returns = []
    for i in range(len(signals_idx)):
        loc_idx = df_bt.index.get_loc(signals_idx[i])
        if loc_idx + 1 >= len(df_bt): continue
        entry_p, prev_close = df_bt.iloc[loc_idx + 1]['Open'], df_bt.iloc[loc_idx]['Close']
        if entry_p > prev_close * 1.02: continue 

        entry_atr = df_bt.iloc[loc_idx]['ATR']
        if pd.isna(entry_atr) or entry_atr == 0: entry_atr = entry_p * 0.03

        future_data = df_bt.iloc[loc_idx + 1 : loc_idx + 21]
        if future_data.empty: continue

        stop_loss = entry_p - 1.5 * entry_atr
        tp_target = entry_p + 2.0 * entry_atr
        sold_half, ret = False, 0.0
        
        for f_idx, row in future_data.iterrows():
            curr_p = row['Close']
            curr_m5 = row['MA5']
            if curr_p > entry_p + entry_atr: stop_loss = max(stop_loss, entry_p) 
            if not sold_half and curr_p >= tp_target: sold_half = True
            
            if sold_half:
                if curr_p < curr_m5:
                    ret = 0.5 * ((tp_target - entry_p)/entry_p) + 0.5 * ((curr_m5 - entry_p) / entry_p)
                    break
            else:
                if curr_p < stop_loss:
                    ret = (stop_loss - entry_p) / entry_p
                    break
        else:
            final_p = future_data['Close'].iloc[-1]
            if sold_half: ret = 0.5 * ((tp_target - entry_p)/entry_p) + 0.5 * ((final_p - entry_p) / entry_p)
            else: ret = (final_p - entry_p) / entry_p
        sim_returns.append(ret)

    if len(sim_returns) < 5: win_rate = 50.0
    else: win_rate = (np.array(sim_returns) > 0).mean() * 100
        
    name = TWSE_NAME_MAP.get(sid, sid)

    return {
        '代號': sid, '名稱': name, '現價': p_now,
        'M5': m5, 'M10': m10, 'M20': m20, '乖離': bias, 'ATR': atr_now,
        '勝率': win_rate, '停損價': p_now - 1.5 * atr_now
    }

@st.cache_data(ttl=3600, show_spinner=False)
def level2_quant_engine(id_tuple, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, fm_token=None):
    id_list = list(id_tuple)
    intel_results = []
    if not id_list: return pd.DataFrame()
    bulk_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_single_stock_batch, sid, fm_token): sid for sid in id_list}
        for future in concurrent.futures.as_completed(futures):
            sid, df = future.result()
            if df is not None: bulk_data[sid] = df
            
    for sid in id_list:
        try:
            if not sid.startswith('00') and not sid.isdigit(): continue
            ind = TWSE_IND_MAP.get(sid) or "其他"
            if sid.startswith('00'): ind = "ETF"
            if "金融" in ind or "保險" in ind: continue
            
            df_stock = bulk_data.get(sid)
            if df_stock is None or df_stock.empty: continue
            
            # 🩹 V26.8 盤中搶修：YF 零量 Bug 補救
            df_stock = df_stock.copy()
            if float(df_stock['Volume'].iloc[-1]) == 0 and len(df_stock) > 1:
                df_stock.loc[df_stock.index[-1], 'Volume'] = df_stock['Volume'].iloc[-2]
            
            close_s, open_s, high_s, low_s, vol_s = df_stock['Close'], df_stock['Open'], df_stock['High'], df_stock['Low'], df_stock['Volume']
            p_now = float(close_s.iloc[-1])
            open_now = float(open_s.iloc[-1])
            high_now = float(high_s.iloc[-1])
            low_now = float(low_s.iloc[-1])
            prev_close = float(close_s.iloc[-2]) if len(close_s) > 1 else open_now
            vol_now = float(vol_s.iloc[-1]) / 1000
            
            # ⚔️ 放寬跳空限制為 4.5% (75分均衡突擊裝甲)
            if ((open_now - prev_close) / prev_close * 100) > 4.5: continue
            
            if p_now < 20 or vol_now < 1.5: continue
            
            m5, m10, m20 = float(close_s.rolling(5).mean().iloc[-1]), float(close_s.rolling(10).mean().iloc[-1]), float(close_s.rolling(20).mean().iloc[-1])
            if p_now < m10: continue
                
            vol_ma5 = float(vol_s.rolling(5).mean().iloc[-1]) / 1000
            bias = ((p_now - m20) / m20) * 100
            
            df_bt = pd.DataFrame({'Close': close_s, 'Open': open_s, 'High': high_s, 'Low': low_s, 'Volume': vol_s})
            df_bt['MA5'] = df_bt['Close'].rolling(5).mean()
            df_bt['MA10'] = df_bt['Close'].rolling(10).mean()
            df_bt['MA20'] = df_bt['Close'].rolling(20).mean()
            df_bt['RollMax20'] = df_bt['Close'].rolling(20).max()
            df_bt['Vol_MA5'] = df_bt['Volume'].rolling(5).mean()
            
            df_bt['PrevClose'] = df_bt['Close'].shift(1)
            df_bt['TR'] = np.maximum(df_bt['High'] - df_bt['Low'], np.maximum(abs(df_bt['High'] - df_bt['PrevClose']), abs(df_bt['Low'] - df_bt['PrevClose'])))
            df_bt['ATR'] = df_bt['TR'].rolling(14).mean()
            atr_now = float(df_bt['ATR'].iloc[-1])
            if pd.isna(atr_now) or atr_now == 0: atr_now = p_now * 0.03
            
            df_bt['RSV'] = (df_bt['Close'] - df_bt['Low'].rolling(9).min()) / (df_bt['High'].rolling(9).max() - df_bt['Low'].rolling(9).min()) * 100
            df_bt['K'] = df_bt['RSV'].ewm(alpha=1/3, adjust=False).mean()
            df_bt['D'] = df_bt['K'].ewm(alpha=1/3, adjust=False).mean()
            df_bt['RedK'] = df_bt['Close'] > df_bt['Open']
            df_bt['ClosePos'] = np.where((df_bt['High'] - df_bt['Low']) > 0, (df_bt['Close'] - df_bt['Low']) / (df_bt['High'] - df_bt['Low']), 0)
            
            k_now, d_now = float(df_bt['K'].iloc[-1]), float(df_bt['D'].iloc[-1])
            red_k = p_now > open_now
            close_position = (p_now - low_now) / (high_now - low_now) if high_now > low_now else 0
            is_strong_candle = ((p_now - open_now) / open_now) > 0.04
            
            trend_strength = (m5 > m10) and (m10 > m20)
            vol_ratio = vol_now / vol_ma5 if vol_ma5 > 0 else 0
            is_breakout_base = (vol_ratio > 1.5) and (k_now > 80) and (p_now >= close_s.iloc[-20:].max() * 0.98)
            
            tactic_a_strong = is_breakout_base and (vol_ratio >= 1.8) and (close_position > 0.7)
            tactic_a_weak = is_breakout_base and (not tactic_a_strong)
            
            on_m5 = (p_now >= m5) and (p_now <= m5 * 1.03)
            on_m10 = (p_now >= m10) and (p_now <= m10 * 1.03)
            tactic_b = (bias < 7) and red_k and (on_m5 or on_m10) and (k_now > d_now)
            
            is_candidate = trend_strength and (is_breakout_base or tactic_b)
            
            if tactic_a_strong and tactic_b: tactic_label = "🔥 雙戰術共振"
            elif tactic_a_strong: tactic_label = "🚀 S級主升段 (重擊)"
            elif tactic_a_weak: tactic_label = "⚠️ 降級弱突破 (避雷)"
            elif tactic_b: tactic_label = "🛡️ 穩健回踩"
            else: tactic_label = "⏳ 觀望盤整"
            
            sig_trend = (df_bt['MA5'] > df_bt['MA10']) & (df_bt['MA10'] > df_bt['MA20'])
            sig_a = (df_bt['Volume'] > df_bt['Vol_MA5'] * 1.5) & (df_bt['K'] > 80) & (df_bt['Close'] >= df_bt['RollMax20'] * 0.98) & (df_bt['ClosePos'] > 0.7)
            bt_on_m5 = (df_bt['Close'] >= df_bt['MA5']) & (df_bt['Close'] <= df_bt['MA5'] * 1.03)
            bt_on_m10 = (df_bt['Close'] >= df_bt['MA10']) & (df_bt['Close'] <= df_bt['MA10'] * 1.03)
            sig_b = (bias_col < 7) & df_bt['RedK'] & (bt_on_m5 | bt_on_m10) & (df_bt['K'] > df_bt['D'])
            
            sig_mask = sig_trend & (sig_a | sig_b)
            signals_idx = df_bt[sig_mask].index
            
            sim_returns = []
            for i in range(len(signals_idx)):
                loc_idx = df_bt.index.get_loc(signals_idx[i])
                if loc_idx + 1 >= len(df_bt): continue 
                entry_p, prev_close_bt = df_bt.iloc[loc_idx + 1]['Open'], df_bt.iloc[loc_idx]['Close']
                if entry_p > prev_close_bt * 1.02: continue
                
                entry_atr = df_bt.iloc[loc_idx]['ATR']
                if pd.isna(entry_atr) or entry_atr == 0: entry_atr = entry_p * 0.03
                
                future_data = df_bt.iloc[loc_idx + 1 : loc_idx + 21] 
                if future_data.empty: continue
                
                stop_loss = entry_p - 1.5 * entry_atr
                tp_target = entry_p + 2.0 * entry_atr
                sold_half, ret = False, 0.0
                
                for f_idx, row in future_data.iterrows():
                    curr_p = row['Close']
                    curr_m5 = row['MA5']
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
                    final_p = future_data['Close'].iloc[-1]
                    if sold_half: ret = 0.5 * ((tp_target - entry_p) / entry_p) + 0.5 * ((final_p - entry_p) / entry_p)
                    else: ret = (final_p - entry_p) / entry_p
                sim_returns.append(ret)
                
            if len(sim_returns) < 5: win_rate, avg_ret = 50.0, 0.0
            else: win_rate, avg_ret = ((np.array(sim_returns) > 0).mean() * 100, np.array(sim_returns).mean() * 100)

            s_score = MACRO_SCORE
            if p_now > m5: s_score += 1
            if p_now > m20: s_score += 1
            else: s_score -= 2
            if is_strong_candle: s_score += 1
            hot_industries = ["半導體", "電腦及週邊設備業", "電子零組件業", "其他電子業"]
            if any(h_ind in ind for h_ind in hot_industries): s_score += 1

            intel_results.append({
                '代號': sid, '名稱': TWSE_NAME_MAP.get(sid, sid), '產業': ind, '現價': p_now, '成交量': vol_now, '今日放量': (vol_now > vol_ma5 * 1.5),
                'M5': m5, 'M10': m10, 'M20': m20, '乖離(%)': bias, '基本達標': is_candidate, '安全指數': max(1, min(10, int(s_score))),
                '勝率(%)': win_rate, '均報(%)': avg_ret, 'ATR': atr_now, 
                '停損價': p_now - 1.5 * atr_now, '原始風險差額': 1.5 * atr_now,
                '戰術型態': tactic_label
            })
        except: continue
    return pd.DataFrame(intel_results)
