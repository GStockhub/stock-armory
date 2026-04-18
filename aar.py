import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import yfinance as yf
import numpy as np

def robust_yf_download(sid, start_date):
    """YF 備援引擎：針對台股代號進行多重嘗試"""
    suffixes = [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            sym = f"{sid}{suffix}"
            df = yf.Ticker(sym).history(start=start_date)
            if not df.empty and len(df) > 0:
                if df.index.tz is not None:
                    df.index = pd.to_datetime(df.index).tz_localize(None)
                # 確保欄位統一
                if 'High' not in df.columns and 'high' in df.columns:
                    df['High'] = df['high']
                if 'Close' not in df.columns and 'close' in df.columns:
                    df['Close'] = df['close']
                return df
        except:
            continue
    return pd.DataFrame()

def render_aar_tab(aar_sheet_url, fee_discount, fm_token):
    """
    軍規級 AAR 戰術覆盤引擎
    融合 GPT 容錯邏輯與 FinMind/YF 雙引擎
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

        # 👑 時間邏輯升級：拉長到 800 天，確保覆蓋所有區間
        global_start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")

        review_results = []
        total_realized_pnl = 0
        active_fee_rate = 0.001425 * fee_discount
        
        with st.spinner('🕵️ AI 正在掃描歷史戰報 (執行軍規級容錯對齊)...'):
            
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
                except:
                    continue 
                
                diagnosis = "✅ 戰報已收錄" 
                s_price = 0.0
                s_date = None
                api_debug_msg = ""
                
                # ===================================================
                # 👑 雙引擎抓取 (FinMind -> YF) + 欄位萬用對齊
                # ===================================================
                if sid not in aar_cache:
                    hist_full = pd.DataFrame()
                    
                    # 1. FinMind (強制 Token 參數)
                    try:
                        fm_url = "https://api.finmindtrade.com/api/v4/data"
                        fm_params = {
                            "dataset": "TaiwanStockPrice",
                            "data_id": sid,
                            "start_date": global_start,
                            "token": fm_token
                        }
                        fm_res = requests.get(fm_url, params=fm_params, timeout=10, verify=False).json()
                        
                        if fm_res.get("msg") == "success" and len(fm_res.get("data", [])) > 0:
                            hist_full = pd.DataFrame(fm_res["data"])
                            hist_full['date'] = pd.to_datetime(hist_full['date'])
                            hist_full.set_index('date', inplace=True)
                            
                            # GPT 建議：欄位萬用對齊
                            if 'max' in hist_full.columns: hist_full['High'] = hist_full['max']
                            elif 'high' in hist_full.columns: hist_full['High'] = hist_full['high']
                            
                            if 'close' in hist_full.columns: hist_full['Close'] = hist_full['close']
                        else:
                            api_debug_msg = f"FM:{fm_res.get('msg', '無資料')}"
                    except Exception as e:
                        api_debug_msg = f"FM異常:{str(e)[:10]}"
                    
                    # 2. YF 備援
                    if hist_full.empty:
                        hist_full = robust_yf_download(sid, start_date=global_start)
                        if hist_full.empty:
                            api_debug_msg += " | YF無效"
                    
                    aar_cache[sid] = hist_full
                    time.sleep(0.1) 
                    
                hist_current = aar_cache[sid].copy()

                # ===================================================
                # 👑 診斷邏輯升級 (GPT 的索引切片建議)
                # ===================================================
                if pd.isna(row['賣出日期']) or pd.isna(row['賣出價']) or str(row['賣出價']).strip() == "":
                    if not hist_current.empty:
                        s_price = float(hist_current['Close'].iloc[-1])
                        diagnosis = "⚪ 尚未平倉 (計算目前帳面損益)"
                    else:
                        s_price = b_price
                        diagnosis = f"⚪ 尚未平倉 (查無現價資料)"
                else:
                    s_date = pd.to_datetime(row['賣出日期'])
                    s_price = float(row['賣出價'])
                    
                    if not hist_current.empty:
                        # GPT 建議：改用 loc 區間抓取，再用 iloc[1:] 跳過賣出當天
                        future_end = s_date + timedelta(days=20)
                        try:
                            future_hist = hist_current.loc[s_date:future_end].copy()
                            future_hist = future_hist.iloc[1:] # 移除賣出日當天
                            
                            if future_hist.empty:
                                if (datetime.now() - s_date).days <= 3:
                                    diagnosis = "⏳ 剛賣出不久，尚無足夠未來數據"
                                else:
                                    diagnosis = f"⚠️ 無未來數據 (原因:{api_debug_msg if api_debug_msg else '區間空值'})"
                            else:
                                max_future_price = future_hist['High'].max()
                                # 判斷邏輯
                                if '恐高早退' in tag or '失去耐心' in tag:
                                    if max_future_price > s_price * 1.02:
                                        missed = (max_future_price - s_price) * shares * 1000
                                        diagnosis = f"⚠️ 錯失飆漲！後續最高達 {max_future_price:.1f}，少賺約 +{missed:,.0f}元。"
                                    else:
                                        diagnosis = "✅ 賣出後未見顯著創高，撤退精準！"
                                elif '恐慌砍倉' in tag:
                                    if max_future_price > b_price:
                                        diagnosis = "🩸 賣出後股價成功反彈解套，被洗出局了。"
                                    else:
                                        diagnosis = "🛡️ 後續未反彈，提早砍倉算是不幸中大幸。"
                                elif '紀律' in tag:
                                    diagnosis = "👑 嚴格執行紀律，不參與後續波動。"
                                else:
                                    diagnosis = f"✅ 已結案 | 撤退後最高價 {max_future_price:.1f}"
                        except:
                            diagnosis = f"⚠️ 數據切片失敗 ({api_debug_msg})"
                    else:
                        diagnosis = f"⚠️ 無法調閱 K 線資料 ({api_debug_msg})"

                # 計算損益
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
        st.error(f"❌ 系統嚴重崩潰：{e}")
