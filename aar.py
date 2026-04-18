import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import yfinance as yf
import numpy as np

def robust_yf_download(sid, start_date):
    """YF 備援引擎：強制清理日期格式與時區"""
    suffixes = [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            sym = f"{sid}{suffix}"
            df = yf.Ticker(sym).history(start=start_date)
            if not df.empty:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                # 欄位統一對齊
                if 'High' not in df.columns and 'high' in df.columns: df['High'] = df['high']
                if 'Close' not in df.columns and 'close' in df.columns: df['Close'] = df['close']
                return df
        except:
            continue
    return pd.DataFrame()

def render_aar_tab(aar_sheet_url, fee_discount, fm_token):
    if not aar_sheet_url:
        st.info("請在左側邊欄輸入您的【交易日誌】CSV 網址。")
        return
        
    try:
        aar_df = pd.read_csv(aar_sheet_url, dtype=str)
        aar_df.columns = aar_df.columns.str.strip()
        
        # 👑 拉長到 800 天，確保 3/18 以前的歷史也能被涵蓋
        global_start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")

        review_results = []
        total_realized_pnl = 0
        active_fee_rate = 0.001425 * fee_discount
        
        with st.spinner('🕵️ AI 正在掃描歷史戰報 (執行軍規級防誤殺邏輯)...'):
            aar_cache = {} 
            
            for idx, row in aar_df.iterrows():
                try:
                    sid = str(row['代號']).strip()
                    b_date = pd.to_datetime(row['買進日期']).replace(tzinfo=None)
                    b_price = float(row['買進價'])
                    shares = float(row['張數'])
                    tag = str(row['心理標籤']) if not pd.isna(row['心理標籤']) else ""
                    
                    tax_rate = 0.001 if sid.startswith('00') else 0.003
                    buy_fee = int((b_price * shares * 1000) * active_fee_rate)
                    cost = (b_price * shares * 1000) + buy_fee
                except: continue 

                diagnosis = "🔄 診斷中..." 
                s_price = 0.0
                s_date = None
                api_debug_msg = ""
                
                # --- 1. 資料抓取與快取 ---
                if sid not in aar_cache:
                    hist_full = pd.DataFrame()
                    try:
                        fm_url = "https://api.finmindtrade.com/api/v4/data"
                        fm_params = {"dataset":"TaiwanStockPrice", "data_id":sid, "start_date":global_start, "token":fm_token}
                        fm_res = requests.get(fm_url, params=fm_params, timeout=10, verify=False).json()
                        if fm_res.get("msg") == "success" and len(fm_res.get("data", [])) > 0:
                            hist_full = pd.DataFrame(fm_res["data"])
                            hist_full['date'] = pd.to_datetime(hist_full['date']).dt.tz_localize(None)
                            hist_full.set_index('date', inplace=True)
                            # GPT 建議：萬用欄位解析
                            if 'max' in hist_full.columns: hist_full['High'] = hist_full['max']
                            elif 'high' in hist_full.columns: hist_full['High'] = hist_full['high']
                            if 'close' in hist_full.columns: hist_full['Close'] = hist_full['close']
                        else: api_debug_msg = f"FM空值"
                    except: api_debug_msg = f"FM異常"
                    
                    if hist_full.empty:
                        hist_full = robust_yf_download(sid, global_start)
                        if hist_full.empty: api_debug_msg += "|YF無效"
                    
                    aar_cache[sid] = hist_full
                    time.sleep(0.05) 
                    
                hist_current = aar_cache[sid].copy()

                # --- 2. 核心診斷邏輯 (GPT 修正版) ---
                if pd.isna(row['賣出日期']) or str(row['賣出價']).strip() == "":
                    if not hist_current.empty:
                        s_price = float(hist_current['Close'].iloc[-1])
                        diagnosis = "⚪ 尚未平倉"
                    else:
                        s_price = b_price
                        diagnosis = "⚪ 查無現價"
                else:
                    s_date = pd.to_datetime(row['賣出日期']).replace(tzinfo=None)
                    s_price = float(row['賣出價'])
                    
                    if not hist_current.empty:
                        future_end = s_date + timedelta(days=20)
                        # GPT 建議：改用 loc 區間抓取
                        try:
                            future_hist = hist_current.loc[s_date:future_end].copy()
                            # GPT 修正：防止誤殺資料，只有大於 1 筆才切掉第一天
                            if len(future_hist) > 1:
                                future_hist = future_hist.iloc[1:]
                            
                            if future_hist.empty:
                                if (datetime.now() - s_date).days <= 3:
                                    diagnosis = "⏳ 剛賣出不久"
                                else:
                                    diagnosis = f"⚠️ 無未來數據 ({api_debug_msg})"
                            else:
                                # GPT 建議：保底修復 High 欄位
                                if 'High' not in future_hist.columns or future_hist['High'].isna().all():
                                    future_hist['High'] = future_hist['Close']

                                max_future_price = future_hist['High'].max()
                                
                                if pd.isna(max_future_price):
                                    diagnosis = f"⚠️ 價格異常 ({api_debug_msg})"
                                else:
                                    # 毒舌判斷
                                    if '恐高早退' in tag or '失去耐心' in tag:
                                        if max_future_price > s_price * 1.02:
                                            missed = (max_future_price - s_price) * shares * 1000
                                            diagnosis = f"⚠️ 賣早了！後高{max_future_price:.1f}，少賺{missed:,.0f}"
                                        else: diagnosis = "✅ 撤退精準"
                                    elif '恐慌砍倉' in tag:
                                        if max_future_price > b_price: diagnosis = "🩸 被洗出場"
                                        else: diagnosis = "🛡️ 砍倉正確"
                                    elif '紀律' in tag:
                                        diagnosis = "👑 紀律正確"
                                    else:
                                        diagnosis = f"✅ 已結案 | 高點 {max_future_price:.1f}"
                        except:
                            diagnosis = "⚠️ 切片失敗"
                    else:
                        diagnosis = f"⚠️ 查無 K 線資料 ({api_debug_msg})"

                # 損益計算
                sell_fee = int((s_price * shares * 1000) * active_fee_rate)
                sell_tax = int((s_price * shares * 1000) * tax_rate)
                net_profit = (s_price * shares * 1000) - sell_fee - sell_tax - cost
                roi = (net_profit / cost) * 100 if cost > 0 else 0
                total_realized_pnl += net_profit
                
                review_results.append({
                    '代號': sid,
                    '持股天數': (s_date - b_date).days if s_date else (datetime.now() - b_date).days,
                    '淨利(元)': net_profit,
                    '報酬(%)': roi,
                    '心魔檢定': tag.split('(')[0].strip() if '(' in tag else tag, 
                    'AI 毒舌診斷': diagnosis
                })

        if review_results:
            res_df = pd.DataFrame(review_results)
            p_color = "#EF4444" if total_realized_pnl > 0 else "#10B981"
            st.markdown(f"#### 💰 歷史戰役總淨利：<span style='color:{p_color}; font-size:24px;'>{total_realized_pnl:,.0f} 元</span>", unsafe_allow_html=True)
            st.dataframe(res_df.style.format({'淨利(元)':'{:,.0f}', '報酬(%)':'{:.2f}%'}), use_container_width=True, hide_index=True)
        else: st.warning("日誌無效。")
    except Exception as e: st.error(f"❌ 嚴重錯誤：{e}")
