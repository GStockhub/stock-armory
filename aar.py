import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import yfinance as yf
import numpy as np

def robust_yf_download(sid, start_date):
    """YF 備援引擎：附帶抖動延遲與重試機制"""
    suffixes = [".TW", ".TWO"]
    for attempt in range(2):
        for suffix in suffixes:
            try:
                sym = f"{sid}{suffix}"
                # 改為用 start_date 抓取，確保涵蓋所有歷史
                df = yf.Ticker(sym).history(start=start_date)
                if not df.empty and len(df) > 5:
                    if df.index.tz is not None:
                        df.index = pd.to_datetime(df.index).tz_localize(None)
                    return df
            except:
                pass
        time.sleep(1.0 + np.random.rand())
    return pd.DataFrame()

def render_aar_tab(aar_sheet_url, fee_discount, fm_token):
    """
    獨立的 AAR 戰術覆盤引擎：雙引擎備援 (FinMind主攻 -> YFinance備援)
    """
    if not aar_sheet_url:
        st.info("請在左側邊欄輸入您的【交易日誌】CSV 網址，喚醒 AI 覆盤引擎。")
        return
        
    try:
        aar_df = pd.read_csv(aar_sheet_url, dtype=str)
        aar_df.columns = aar_df.columns.str.strip()
        
        required_cols = ['代號', '買進日期', '買進價', '賣出日期', '賣出價', '張數', '心理標籤']
        if not all(col in aar_df.columns for col in required_cols):
            st.error(f"❌ 欄位不符！請確保包含：{', '.join(required_cols)}")
            return

        # 👑 破案關鍵：找出日誌中最古老的那一筆交易，往前推 30 天當作全域抓取起點
        try:
            earliest_date = pd.to_datetime(aar_df['買進日期']).min()
            global_start = (earliest_date - timedelta(days=30)).strftime("%Y-%m-%d")
        except:
            global_start = "2020-01-01" # 萬一日期解析失敗，直接從2020年開始抓，絕對不漏！

        review_results = []
        total_realized_pnl = 0
        active_fee_rate = 0.001425 * fee_discount
        
        with st.spinner('🕵️ 情報兵正在調閱歷史戰報，啟動雙引擎快取庫...'):
            
            aar_cache = {} 
            
            for idx, row in aar_df.iterrows():
                try:
                    if pd.isna(row['代號']): continue
                    sid = str(row['代號']).strip()
                    b_date = pd.to_datetime(row['買進日期'])
                    b_price = float(row['買進價'])
                    shares = float(row['張數'])
                    tag = str(row['心理標籤'])
                    if pd.isna(tag) or tag.lower() == "nan": tag = ""
                    
                    tax_rate = 0.001 if sid.startswith('00') else 0.003
                    buy_fee = int((b_price * shares * 1000) * active_fee_rate)
                    cost = (b_price * shares * 1000) + buy_fee
                except Exception:
                    continue 
                
                diagnosis = "✅ 戰報已收錄" 
                s_price = 0.0
                s_date = None
                api_debug_msg = ""
                
                if sid not in aar_cache:
                    hist_full = pd.DataFrame()
                    
                    # 1. 主攻：FinMind API
                    try:
                        fm_url = "https://api.finmindtrade.com/api/v4/data"
                        fm_params = {
                            "dataset": "TaiwanStockPrice",
                            "data_id": sid,
                            "start_date": global_start, # 👈 使用最古老日期作為起點
                            "token": fm_token
                        }
                        
                        fm_res = requests.get(fm_url, params=fm_params, timeout=10, verify=False).json()
                        
                        if fm_res.get("msg") == "success" and len(fm_res.get("data", [])) > 0:
                            hist_full = pd.DataFrame(fm_res["data"])
                            hist_full['date'] = pd.to_datetime(hist_full['date'])
                            hist_full.set_index('date', inplace=True)
                            hist_full.rename(columns={'max': 'High', 'close': 'Close'}, inplace=True)
                        else:
                            api_debug_msg = fm_res.get("msg", "空資料")
                    except Exception as e:
                        api_debug_msg = str(e)[:20]
                    
                    # 2. 備援：YFinance
                    if hist_full.empty:
                        hist_full = robust_yf_download(sid, start_date=global_start)
                        if hist_full.empty:
                            api_debug_msg += " | YF亦無資料"
                    
                    aar_cache[sid] = hist_full
                    time.sleep(0.1) 
                    
                hist_current = aar_cache[sid].copy()

                if pd.isna(row['賣出日期']) or pd.isna(row['賣出價']) or str(row['賣出價']).strip() == "":
                    if not hist_current.empty:
                        s_price = float(hist_current['Close'].iloc[-1])
                        diagnosis = "⚪ 尚未平倉 (計算目前帳面損益)"
                    else:
                        s_price = b_price
                        diagnosis = f"⚪ 尚未平倉 (查無現價: {api_debug_msg})"
                else:
                    s_date = pd.to_datetime(row['賣出日期'])
                    s_price = float(row['賣出價'])
                    
                    future_end = s_date + timedelta(days=20)
                    future_hist = pd.DataFrame() 
                    
                    if not hist_current.empty:
                        mask = (hist_current.index > s_date) & (hist_current.index <= future_end)
                        future_hist = hist_current.loc[mask]
                    
                    if future_hist.empty or len(future_hist) < 3:
                        if (datetime.now() - s_date).days <= 3:
                            diagnosis = "⏳ 剛賣出不久，尚無足夠未來數據比對"
                        else:
                            diagnosis = f"⚠️ 無法診斷 (錯誤代碼: {api_debug_msg})" if api_debug_msg else "⚠️ 查無該區間足夠數據"
                    else:
                        max_future_price = future_hist['High'].max()
                        if '恐高早退' in tag or '失去耐心' in tag:
                            if max_future_price > s_price * 1.02:
                                missed_profit = (max_future_price - s_price) * shares * 1000
                                diagnosis = f"⚠️ 錯失飆漲！後續最高達 {max_future_price:.1f}，少賺約 +{missed_profit:,.0f}元。"
                            else:
                                diagnosis = "✅ 賣出後未見顯著創高，撤退精準！"
                        elif '恐慌砍倉' in tag:
                            if max_future_price > b_price:
                                diagnosis = "🩸 賣出後股價成功反彈解套，被洗出局了。"
                            else:
                                diagnosis = "🛡️ 後續未反彈，提早砍倉算是不幸中大幸。"
                        elif '紀律' in tag:
                            diagnosis = "👑 嚴格執行紀律，無須留戀後續漲跌！"
                        else:
                            diagnosis = f"✅ 已結案 | 撤退後最高價 {max_future_price:.1f}"

                sell_fee = int((s_price * shares * 1000) * active_fee_rate)
                sell_tax = int((s_price * shares * 1000) * tax_rate)
                
                revenue = (s_price * shares * 1000) - sell_fee - sell_tax
                net_profit = revenue - cost
                roi = (net_profit / cost) * 100 if cost > 0 else 0
                total_realized_pnl += net_profit
                
                held_days = (s_date - b_date).days if s_date else (datetime.now() - b_date).days

                review_results.append({
                    '代號': sid,
                    '持股天數': held_days,
                    '淨利(元)': net_profit,
                    '報酬(%)': roi,
                    '心魔檢定': tag.split('(')[0].strip() if '(' in tag else tag, 
                    'AI 毒舌診斷': diagnosis
                })

        if review_results:
            res_df = pd.DataFrame(review_results)
            p_color = "#EF4444" if total_realized_pnl > 0 else "#10B981"
            st.markdown(f"#### 💰 歷史戰役總淨利：<span style='color:{p_color}; font-size:24px;'>{total_realized_pnl:,.0f} 元</span>", unsafe_allow_html=True)
            
            styled_res = (res_df.style.set_properties(**{'text-align': 'center'})
                        .format({'淨利(元)':'{:,.0f}', '報酬(%)':'{:.2f}%'})
                        .map(lambda x: 'color: #EF4444; font-weight: bold;' if x > 0 else ('color: #10B981;' if x < 0 else ''), subset=['淨利(元)', '報酬(%)']))
            st.dataframe(styled_res, use_container_width=True, hide_index=True)
        else:
            st.warning("日誌中無有效交易紀錄。")
    except Exception as e:
        st.error(f"❌ 讀取交易日誌失敗：{e}")
