import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time

def render_aar_tab(aar_sheet_url, fee_discount, fm_token):
    """
    獨立的 AAR 戰術覆盤引擎：
    吃 FinMind 皇家金鑰，自帶情報快取，絕不干擾主雷達。
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

        review_results = []
        total_realized_pnl = 0
        active_fee_rate = 0.001425 * fee_discount
        
        with st.spinner('🕵️ 情報兵正在調閱歷史戰報，啟動 FinMind 皇家快取引擎...'):
            
            # 👑 核心快取字典：同檔股票不管幾筆，只向 FinMind 請求一次
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
                
                # ===================================================
                # 👑 裝載將軍專屬金鑰，向 FinMind 請求 1 年的歷史數據
                # ===================================================
                if sid not in aar_cache:
                    hist_full = pd.DataFrame()
                    try:
                        fm_url = "https://api.finmindtrade.com/api/v4/data"
                        # 直接往前抓 365 天，確保不管多早以前的交易都能覆蓋
                        fm_start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
                        
                        fm_params = {
                            "dataset": "TaiwanStockPrice",
                            "data_id": sid,
                            "start_date": fm_start
                        }
                        
                        # 👑 破案關鍵：將金鑰放入 Headers 中 (Bearer Token)
                        fm_headers = {
                            "Authorization": f"Bearer {fm_token}"
                        }
                        
                        fm_res = requests.get(fm_url, params=fm_params, headers=fm_headers, timeout=10, verify=False).json()
                        
                        if fm_res.get("msg") == "success" and len(fm_res.get("data", [])) > 0:
                            hist_full = pd.DataFrame(fm_res["data"])
                            hist_full['date'] = pd.to_datetime(hist_full['date'])
                            hist_full.set_index('date', inplace=True)
                            hist_full.rename(columns={'max': 'High', 'close': 'Close'}, inplace=True)
                    except Exception:
                        pass
                    
                    aar_cache[sid] = hist_full
                    # 有金鑰的合法連線，稍微停頓 0.1 秒即可
                    time.sleep(0.1) 
                    
                hist_current = aar_cache[sid].copy()

                if pd.isna(row['賣出日期']) or pd.isna(row['賣出價']) or str(row['賣出價']).strip() == "":
                    if not hist_current.empty:
                        s_price = float(hist_current['Close'].iloc[-1])
                        diagnosis = "⚪ 尚未平倉 (計算目前帳面損益)"
                    else:
                        s_price = b_price
                        diagnosis = "⚪ 尚未平倉 (查無該股，無法取得現價)"
                else:
                    s_date = pd.to_datetime(row['賣出日期'])
                    s_price = float(row['賣出價'])
                    
                    # 放寬到 20 天包容假日
                    future_end = s_date + timedelta(days=20)
                    future_hist = pd.DataFrame() 
                    
                    if not hist_current.empty:
                        # 切割賣出後 20 天內的資料
                        mask = (hist_current.index > s_date) & (hist_current.index <= future_end)
                        future_hist = hist_current.loc[mask]
                    
                    # GPT 防禦：若無資料或資料過少(<3天)，避免誤判
                    if future_hist.empty or len(future_hist) < 3:
                        if (datetime.now() - s_date).days <= 3:
                            diagnosis = "⏳ 剛賣出不久，尚無足夠未來數據比對"
                        else:
                            diagnosis = "⚠️ 查無該區間足夠數據，無法診斷"
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
