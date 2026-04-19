import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time
import yfinance as yf

def parse_tw_date(d_str):
    try:
        d_str = str(d_str).strip().replace('/', '-').replace('.', '-')
        parts = d_str.split('-')
        if len(parts) == 3:
            y = int(parts[0])
            if y < 200: y += 1911  
            return pd.to_datetime(f"{y}-{parts[1]}-{parts[2]}")
        elif len(parts) == 2:
            return pd.to_datetime(f"{datetime.now().year}-{parts[0]}-{parts[1]}")
        return pd.to_datetime(d_str)
    except: return pd.NaT

@st.cache_data(ttl=86400, show_spinner=False)
def load_names():
    name_map = {}
    try:
        df = pd.read_csv("industry_map.csv", dtype=str)
        for _, row in df.iterrows():
            name_map[str(row['代號']).strip()] = str(row['名稱']).strip()
    except: pass
    return name_map

def get_finmind_data(sid, start_date, fm_token):
    if not fm_token: return pd.DataFrame()
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockPrice", "data_id": sid, "start_date": start_date, "token": fm_token.strip()}
        res = requests.get(url, params=params, timeout=10, verify=False).json()
        if res.get("msg") != "success": return pd.DataFrame()
        if res.get("data") and len(res["data"]) > 0:
            df = pd.DataFrame(res["data"])
            df['date'] = pd.to_datetime(df['date']).dt.date
            df.set_index('date', inplace=True)
            df['High'] = pd.to_numeric(df.get('max', df.get('high', df['close'])), errors='coerce')
            df['Low'] = pd.to_numeric(df.get('min', df.get('low', df['close'])), errors='coerce') 
            df['Close'] = pd.to_numeric(df['close'], errors='coerce')
            return df[['High', 'Low', 'Close']].dropna().sort_index()
    except: pass
    return pd.DataFrame()

def get_yf_data(sid, start_date):
    for suf in [".TW", ".TWO"]:
        try:
            df = yf.Ticker(f"{sid}{suf}").history(start=start_date, auto_adjust=False)
            if not df.empty:
                df.index = pd.to_datetime(df.index).dt.date
                df['High'] = pd.to_numeric(df.get('High', df['Close']), errors='coerce')
                df['Low'] = pd.to_numeric(df.get('Low', df['Close']), errors='coerce') 
                df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
                return df[['High', 'Low', 'Close']].dropna().sort_index()
        except: continue
    return pd.DataFrame()

def render_aar_tab(aar_sheet_url, fee_discount, fm_token, COLORS):
    if not aar_sheet_url:
        st.info("請在左側邊欄輸入【交易日誌】網址。")
        return

    try:
        df = pd.read_csv(aar_sheet_url, dtype=str)
        if hasattr(df, 'map'): df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        else: df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
            
        df.columns = df.columns.str.strip()
        global_start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")
        cache, results, total_pnl = {}, [], 0
        name_map = load_names() 

        with st.spinner("🧠 V3 量化教練正在掃描 K 線結構與持股心魔..."):
            for _, row in df.iterrows():
                try:
                    sid = str(row['代號'])
                    if sid in ["", "nan"]: continue
                    b_date = parse_tw_date(row['買進日期'])
                    b_price, shares = float(row['買進價']), float(row['張數'])
                    tag = str(row.get('心理標籤', '')).split('(')[0].split('（')[0].strip()
                    fee_rate = 0.001425 * fee_discount
                    tax_rate = 0.001 if sid.startswith('00') else 0.003
                except: continue

                if sid not in cache:
                    hist = get_finmind_data(sid, global_start, fm_token)
                    if hist.empty: hist = get_yf_data(sid, global_start)
                    if not hist.empty:
                        hist['M5'] = hist['Close'].rolling(5).mean()
                        hist['M10'] = hist['Close'].rolling(10).mean()
                        hist['M20'] = hist['Close'].rolling(20).mean()
                    cache[sid] = hist
                    time.sleep(0.05)

                hist = cache[sid]
                s_price, s_date, missed_profit = b_price, None, 0
                b_date_str, s_date_str = b_date.strftime('%m/%d'), "-"
                s_name = name_map.get(sid, sid) 
                
                temp_s = parse_tw_date(row.get('賣出日期'))
                held_days = (temp_s - b_date).days if pd.notnull(temp_s) else (datetime.now() - b_date).days
                
                structure_text = "⚪ 持股中/不明"
                coach_text = "等待平倉結算"
                grade = "⚪ 未評級"
                roi = 0
                
                is_sold = pd.notna(row.get('賣出日期')) and str(row.get('賣出價', '')).strip() != ""
                
                if not is_sold:
                    if not hist.empty:
                        s_price = float(hist['Close'].iloc[-1])
                        coach_text = "⚪ 仍在戰場中，請堅守紀律"
                else:
                    s_date = temp_s
                    s_price = float(row['賣出價'])
                    s_date_str = s_date.strftime('%m/%d')
                    
                    if not hist.empty:
                        hist = hist.sort_index()
                        s_obj = s_date.date()
                        
                        if s_obj in hist.index:
                            m5_s = hist.loc[s_obj, 'M5']
                            m10_s = hist.loc[s_obj, 'M10']
                            if pd.notna(m5_s) and pd.notna(m10_s):
                                if s_price > m5_s and m5_s > m10_s:
                                    structure_text = "📈 多頭排列 (強勢區)"
                                elif s_price < m10_s:
                                    structure_text = "📉 跌破 M10 (轉弱區)"
                                else:
                                    structure_text = "⏳ 均線糾結 (盤整區)"

                        f20 = hist[(hist.index > s_obj) & (hist.index <= (s_date + timedelta(days=20)).date())]
                        
                        if f20.empty or f20['High'].isna().all():
                            coach_text = "⏳ 剛賣出，尚無後續數據"
                        else:
                            m20 = f20['High'].max()
                            min20 = f20['Low'].min()
                            threshold = 1.03 if held_days <= 3 else 1.05
                            
                            if pd.notna(m20) and m20 > s_price * threshold:
                                days_to_h = (f20['High'].idxmax() - s_obj).days
                                missed_profit = (m20 - s_price) * shares * 1000
                                pct_up = ((m20 / s_price) - 1) * 100
                                coach_text = f"🔭 第 {days_to_h} 天後見高 (+{pct_up:.1f}%)，潛在少賺 {missed_profit:,.0f} 元"
                            elif pd.notna(min20) and min20 < s_price * 0.98:
                                days_to_l = (f20['Low'].idxmin() - s_obj).days
                                avoided_loss = (s_price - min20) * shares * 1000
                                pct_down = ((min20 / s_price) - 1) * 100
                                coach_text = f"🛡️ 第 {days_to_l} 天後殺低 ({pct_down:.1f}%)，成功避開 {avoided_loss:,.0f} 元損失"
                            else:
                                coach_text = "⚖️ 賣出後陷入橫盤，資金無效率，撤退合理"

                b_cost = (b_price * shares * 1000) + int((b_price * shares * 1000) * fee_rate)
                s_rev = (s_price * shares * 1000) - int((s_price * shares * 1000) * fee_rate) - int((s_price * shares * 1000) * tax_rate)
                pnl = s_rev - b_cost
                roi = (pnl / b_cost) * 100 if b_cost > 0 else 0
                if is_sold: total_pnl += pnl

                if is_sold:
                    if roi <= -5:
                        grade = "💀 D級 (情緒扛損)"
                    elif structure_text == "📈 多頭排列 (強勢區)" and missed_profit > 0 and roi < 10:
                        grade = "🤡 C級 (強勢賣飛)"
                    elif roi >= 10:
                        grade = "👑 S級 (完美收割)"
                    elif structure_text == "📉 跌破 M10 (轉弱區)" and -5 < roi <= 0:
                        grade = "🛡️ A級 (紀律停損)"
                    elif roi > 0:
                        grade = "🥈 A級 (穩健獲利)"
                    else:
                        grade = "⚔️ B級 (普通操作)"

                if is_sold:
                    final_diagnosis = f"【結構】{structure_text}\n【結果】{coach_text}"
                else:
                    final_diagnosis = coach_text

                results.append({
                    "代號": sid, "名稱": s_name, "評級": grade, 
                    "診斷詳情": final_diagnosis,
                    "買": b_date_str, "賣": s_date_str, "天": held_days,
                    "淨利": pnl if is_sold else 0, "報酬%": roi, "心魔": tag, "_少賺": missed_profit, "_is_sold": is_sold
                })

        if results:
            res = pd.DataFrame(results)
            sold_df = res[res['_is_sold'] == True].copy()
            
            total_missed = sold_df['_少賺'].sum()
            god_mode_pnl = total_pnl + total_missed
            
            st.markdown(f"### 🎯 <span class='highlight-primary'>教練覆盤室 V3 (決策透視版)</span>", unsafe_allow_html=True)
            
            col_pnl1, col_pnl2 = st.columns(2)
            with col_pnl1:
                p_color = COLORS['red'] if total_pnl > 0 else COLORS['green']
                st.markdown(f"""
                <div class="tier-card" style="border-top: 4px solid {COLORS['primary']};">
                    <p style="margin:0; color:{COLORS['subtext']};">💰 實際落袋總淨利</p>
                    <h2 style="margin:0; color:{p_color};">{total_pnl:,.0f} 元</h2>
                </div>
                """, unsafe_allow_html=True)
            with col_pnl2:
                st.markdown(f"""
                <div class="tier-card" style="border-top: 4px solid {COLORS['accent']};">
                    <p style="margin:0; color:{COLORS['subtext']};">✨ 理論極限淨利 (神仙模式)</p>
                    <h2 style="margin:0; color:{COLORS['primary']};">{god_mode_pnl:,.0f} 元</h2>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 💀 <span class='highlight-red'>系統洞察：賣飛心魔分析</span>", unsafe_allow_html=True)
            
            missed_df = sold_df[sold_df['_少賺'] > 0]
            if not missed_df.empty:
                max_miss_row = missed_df.loc[missed_df['_少賺'].idxmax()]
                max_miss_name = f"{max_miss_row['名稱']}({max_miss_row['代號']})"
                max_miss_amt = max_miss_row['_少賺']
                
                avg_days = missed_df['天'].mean()
                mode_days = missed_df['天'].mode()
                freq_day = mode_days[0] if not mode_days.empty else avg_days
                
                st.markdown(f"""
                <div style="background-color: {COLORS['bg']}; padding: 20px; border-radius: 8px; border-left: 5px solid {COLORS['red']};">
                    <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 15px;">
                        <div>
                            <span style="color:{COLORS['subtext']}; font-size:14px;">🩸 最痛的一筆賣飛</span><br>
                            <span style="font-size:20px; font-weight:bold; color:{COLORS['text']};">{max_miss_name} <span style="color:{COLORS['red']};">-{max_miss_amt:,.0f}元</span></span>
                        </div>
                        <div>
                            <span style="color:{COLORS['subtext']}; font-size:14px;">⏳ 賣飛單平均持股天數</span><br>
                            <span style="font-size:20px; font-weight:bold; color:{COLORS['primary']};">{avg_days:.1f} 天</span>
                        </div>
                        <div>
                            <span style="color:{COLORS['subtext']}; font-size:14px;">🎯 死亡交叉點 (最常在第幾天賣飛)</span><br>
                            <span style="font-size:20px; font-weight:bold; color:{COLORS['accent']};">第 {freq_day:.0f} 天</span>
                        </div>
                    </div>
                    <div style="margin-top: 15px; padding-top: 15px; border-top: 1px dashed {COLORS['border']};">
                        💡 <b>教練點評：</b> 您高達 <b>{len(missed_df)/len(sold_df)*100:.0f}%</b> 的獲利單提前下車。數據顯示，您最難熬過持股的 <b>第 {freq_day:.0f} 天</b>。下次在多頭結構中，請強迫自己綁住雙手，突破這個天數魔咒！
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.success("🎉 太神啦！目前系統判定您沒有任何嚴重的賣飛行為，收割極度精準！")

            st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 📜 逐筆交易評分清單")
            
            # 👑 變更順序：將「診斷詳情」移動到「評級」之前
            display_cols = ["代號", "名稱", "診斷詳情", "評級", "買", "賣", "天", "淨利", "報酬%", "心魔"]
            display_df = res[display_cols]
            
            table_style = {'text-align': 'center', 'background-color': COLORS['card'], 'color': COLORS['text'], 'border-color': COLORS['border']}

            def grade_color(val):
                if 'S級' in str(val): return f"color: {COLORS['primary']}; font-weight: bold;"
                if 'C級' in str(val): return f"color: {COLORS['accent']}; font-weight: bold;"
                if 'D級' in str(val): return f"color: {COLORS['red']}; font-weight: bold;"
                if 'A級' in str(val): return f"color: {COLORS['green']}; font-weight: bold;"
                return f"color: {COLORS['subtext']};"

            st.dataframe(
                display_df.style.set_properties(**table_style).format({"淨利":"{:,.0f}", "報酬%":"{:.2f}%"})
                .map(lambda x: f"color:{COLORS['red']}" if x > 0 else (f"color:{COLORS['green']}" if x < 0 else ""), subset=["淨利", "報酬%"])
                .map(grade_color, subset=["評級"])
                .set_properties(subset=["診斷詳情"], **{'white-space': 'pre-wrap', 'text-align': 'left'}),
                use_container_width=True, hide_index=True,
                column_config={
                    "代號": st.column_config.TextColumn(width="small"),
                    "名稱": st.column_config.TextColumn(width="small"),
                    "診斷詳情": st.column_config.TextColumn(width="large"),
                    "評級": st.column_config.TextColumn(width="medium"),
                    "買": st.column_config.TextColumn(width="small"),
                    "賣": st.column_config.TextColumn(width="small"),
                    "天": st.column_config.NumberColumn(width="small"),
                    "淨利": st.column_config.NumberColumn(width="small"),
                    "報酬%": st.column_config.TextColumn(width="small"),
                    "心魔": st.column_config.TextColumn(width="small")
                }
            )
        else: st.warning("尚無資料")
    except Exception as e: st.error(f"系統錯誤: {e}")
