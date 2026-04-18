import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import yfinance as yf
import numpy as np

def robust_yf_download(sid, start_date):
    """YF 備援引擎：強制清理日期格式"""
    suffixes = [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            sym = f"{sid}{suffix}"
            df = yf.Ticker(sym).history(start=start_date)
            if not df.empty:
                # 👑 終極日期清理：只保留 YYYY-MM-DD
                df.index = pd.to_datetime(df.index.strftime('%Y-%m-%d'))
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
        
        # 全域抓取起點：抓 2.5 年，絕對夠深
        global_start = (datetime.now() - timedelta(days=900)).strftime("%Y-%m-%d")

        review_results = []
        total_realized_pnl = 0
        active_fee_rate = 0.001425 * fee_discount
        
        with st.spinner('🕵️ AI 正在暴力解析 K 線區間...'):
            aar_cache = {} 
            
            for idx, row in aar_df.iterrows():
                try:
                    sid = str(row['代號']).strip()
                    # 👑 終極日期清理：確保只剩下乾淨的 YYYY-MM-DD
                    b_date_str = pd.to_datetime(row['買進日期']).strftime('%Y-%m-%d')
                    b_date = pd.to_datetime(b_date_str)
                    b_price = float(row['買進價'])
                    shares = float(row['張數'])
                    tag = str(row['心理標籤']) if not pd.isna(row['心理標籤']) else ""
                    
                    tax_rate = 0.001 if sid.startswith('00') else 0.003
                    buy_fee = int((b_price * shares * 1000) * active_fee_rate)
                    cost = (b_price * shares * 1000) + buy_fee
                except: continue 

                diagnosis = "✅ 戰報已收錄" 
                s_price = 0.0
                s_date = None
                api_debug_msg = ""
                
                if sid not in aar_cache:
                    hist_full = pd.DataFrame()
                    # 1. FinMind 抓取
                    try:
                        fm_url = "https://api.finmindtrade.com/api/v4/data"
                        fm_params = {"dataset":"TaiwanStockPrice", "data_id":sid, "start_date":global_start, "token":fm_token}
                        fm_res = requests.get(fm_url, params=fm_params, timeout=10, verify=False).json()
                        if fm_res.get("msg") == "success" and len(fm_res.get("data", [])) > 0:
                            hist_full = pd.DataFrame(fm_res["data"])
                            # 👑 終極日期清理：只保留 YYYY-MM-DD
                            hist_full['date'] = pd.to_datetime(pd.to_datetime(hist_full['date']).dt.strftime('%Y-%m-%d'))
                            hist_full.set_index('date', inplace=True)
                            
                            # 欄位對齊
                            if 'max' in hist_full.columns: hist_full['High'] = hist_full['max']
                            elif 'high' in hist_full.columns: hist_full['High'] = hist_full['high']
                            if 'close' in hist_full.columns: hist_full['Close'] = hist_full['close']
                        else: api_debug_msg = f"FM:{fm_res.get('msg','empty')}"
                    except Exception as e: api_debug_msg = f"FM_Err"
                    
                    # 2. YF 救援
                    if hist_full.empty:
                        hist_full = robust_yf_download(sid, global_start)
                        if hist_full.empty: api_debug_msg += " | YF_Fail"
                    
                    aar_cache[sid] = hist_full
                    time.sleep(0.05) 
                    
                hist_current = aar_cache[sid].copy()

                if pd.isna(row['賣出日期']) or str(row['賣出價']).strip() == "":
                    if not hist_current.empty:
                        s_price = float(hist_current['Close'].iloc[-1])
                        diagnosis = "⚪ 尚未平倉"
                    else:
                        s_price = b_price
                        diagnosis = "⚪ 查無目前現價"
                else:
                    # 👑 終極日期清理：確保 s_date 是最乾淨的午夜 00:00:00
                    s_date_str = pd.to_datetime(row['賣出日期']).strftime('%Y-%m-%d')
                    s_date = pd.to_datetime(s_date_str)
                    s_price = float(row['賣出價'])
                    
                    if not hist_current.empty:
                        future_end = s_date + timedelta(days=20)
                        
                        # 👑 GPT 建議的 loc 區間抓取 (搭配我們已清理乾淨的日期)
                        try:
                            future_hist = hist_current.loc[s_date:future_end].copy()
                            
                            # 防止誤殺，有超過1天才移除當天
                            if len(future_hist) > 1:
                                future_hist = future_hist.iloc[1:]
                                
                            if future_hist.empty:
                                if (datetime.now() - s_date).days <= 3:
                                    diagnosis = "⏳ 剛賣出不久"
                                else:
                                    diagnosis = f"⚠️ 無未來數據 (區間空值)"
                            else:
                                # 👑 GPT 建議：保底修復 High 欄位
                                if 'High' not in future_hist.columns or future_hist['High'].isna().all():
                                    future_hist['High'] = future_hist['Close']
                                
                                max_future_price = future_hist['High'].max()
                                
                                if pd.isna(max_future_price):
                                    diagnosis = f"⚠️ 價格資料異常 ({api_debug_msg})"
                                else:
                                    if '恐高早退' in tag or '失去耐心' in tag:
                                        if max_future_price > s_price * 1.02:
                                            missed = (max_future_price - s_price) * shares * 1000
                                            diagnosis = f"⚠️ 錯失飆漲！後續高達 {max_future_price:.1f}，少賺 +{missed:,.0f}"
                                        else: diagnosis = "✅ 賣出後未見創高，撤退精準！"
                                    elif '恐慌砍倉' in tag:
                                        if max_future_price > b_price: diagnosis = "🩸 賣出後反彈解套，被洗出局。"
                                        else: diagnosis = "🛡️ 後續未反彈，提早砍倉正確。"
                                    else:
                                        diagnosis = f"✅ 已結案 | 撤退後最高 {max_future_price:.1f}"
                        except Exception as e:
                            diagnosis = f"⚠️ 區間解析失敗"
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
