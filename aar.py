import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import yfinance as yf
import numpy as np

def robust_yf_download(sid, start_date):
    """YF 備援：強制重置索引，轉為純粹的 date 欄位"""
    suffixes = [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            sym = f"{sid}{suffix}"
            df = yf.Ticker(sym).history(start=start_date)
            if not df.empty:
                df = df.reset_index()
                # 統一時間欄位名稱
                if 'Date' in df.columns: df.rename(columns={'Date': 'date'}, inplace=True)
                elif 'Datetime' in df.columns: df.rename(columns={'Datetime': 'date'}, inplace=True)
                
                df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                
                if 'High' not in df.columns and 'high' in df.columns: df['High'] = df['high']
                if 'Close' not in df.columns and 'close' in df.columns: df['Close'] = df['close']
                return df
        except:
            continue
    return pd.DataFrame()

def fetch_finmind(sid, start_date, token):
    """FM 主攻：回傳最單純的 DataFrame，不設定 index"""
    try:
        fm_url = "https://api.finmindtrade.com/api/v4/data"
        fm_params = {"dataset":"TaiwanStockPrice", "data_id":sid, "start_date":start_date, "token":token}
        res = requests.get(fm_url, params=fm_params, timeout=10, verify=False).json()
        if res.get("msg") == "success" and len(res.get("data", [])) > 0:
            df = pd.DataFrame(res["data"])
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            
            if 'max' in df.columns: df['High'] = df['max']
            elif 'high' in df.columns: df['High'] = df['high']
            if 'close' in df.columns: df['Close'] = df['close']
            return df
    except:
        pass
    return pd.DataFrame()

def render_aar_tab(aar_sheet_url, fee_discount, fm_token):
    if not aar_sheet_url:
        st.info("請在左側邊欄輸入您的【交易日誌】CSV 網址。")
        return
        
    try:
        aar_df = pd.read_csv(aar_sheet_url, dtype=str)
        aar_df.columns = aar_df.columns.str.strip()
        
        # 全域起點：抓 2.5 年
        global_start = (datetime.now() - timedelta(days=900)).strftime("%Y-%m-%d")

        review_results = []
        total_realized_pnl = 0
        active_fee_rate = 0.001425 * fee_discount
        
        with st.spinner('🕵️ AI 正在執行降維 K 線掃描 (完全屏除 Pandas 索引干擾)...'):
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

                diagnosis = "✅ 戰報已收錄" 
                s_price = 0.0
                s_date = None
                
                # --- 1. 抓取資料並放入快取 ---
                if sid not in aar_cache:
                    hist_full = fetch_finmind(sid, global_start, fm_token)
                    if hist_full.empty:
                        hist_full = robust_yf_download(sid, global_start)
                    
                    # 確保按時間排序
                    if not hist_full.empty:
                        hist_full = hist_full.sort_values('date')
                        
                    aar_cache[sid] = hist_full
                    time.sleep(0.05) 
                    
                hist_current = aar_cache[sid].copy()

                # --- 2. 暴力降維過濾邏輯 ---
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
                        
                        # 👑 拋棄 .loc 索引！直接用普通欄位做大於小於篩選
                        mask = (hist_current['date'] > s_date) & (hist_current['date'] <= future_end)
                        future_hist = hist_current[mask].copy()
                        
                        if future_hist.empty:
                            if (datetime.now() - s_date).days <= 3:
                                diagnosis = "⏳ 剛賣出不久"
                            else:
                                # 👑 X 光顯影：印出庫存裡的真實資料範圍，讓我們知道為什麼空掉！
                                d_min = hist_current['date'].min().strftime('%Y/%m/%d')
                                d_max = hist_current['date'].max().strftime('%Y/%m/%d')
                                diagnosis = f"⚠️ 無區間資料 (賣出:{s_date.strftime('%m/%d')}, 快取:{d_min}~{d_max}, 共{len(hist_current)}筆)"
                        else:
                            if 'High' not in future_hist.columns or future_hist['High'].isna().all():
                                future_hist['High'] = future_hist['Close']
                            
                            max_future_price = future_hist['High'].max()
                            
                            if pd.isna(max_future_price):
                                diagnosis = f"⚠️ 價格資料異常 (High為空)"
                            else:
                                if '恐高早退' in tag or '失去耐心' in tag:
                                    if max_future_price > s_price * 1.02:
                                        missed = (max_future_price - s_price) * shares * 1000
                                        diagnosis = f"⚠️ 錯失飆漲！後續高達 {max_future_price:.1f}，少賺 +{missed:,.0f}"
                                    else: diagnosis = "✅ 賣出後未見創高，撤退精準！"
                                elif '恐慌砍倉' in tag:
                                    if max_future_price > b_price: diagnosis = "🩸 賣出後反彈解套，被洗出局。"
                                    else: diagnosis = "🛡️ 後續未反彈，提早砍倉正確。"
                                elif '紀律' in tag:
                                    diagnosis = "👑 嚴格執行紀律，不參與後續波動。"
                                else:
                                    diagnosis = f"✅ 已結案 | 撤退後最高 {max_future_price:.1f}"
                    else:
                        diagnosis = f"⚠️ 查無此代號之 K 線資料"

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
