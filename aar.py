import streamlit as st
import pandas as pd
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
        if hasattr(df, 'map'):
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        else:
            df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
            
        df.columns = df.columns.str.strip()
        global_start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")
        cache, results, total_pnl = {}, [], 0
        name_map = load_names() 

        with st.spinner("🧠 混合型收割者 AI 正在掃描戰場潛力與避險績效..."):
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
                    cache[sid] = hist
                    time.sleep(0.05)

                hist = cache[sid]
                diagnosis, s_price, s_date, missed_profit = "⚠️無資料", b_price, None, 0
                b_date_str, s_date_str = b_date.strftime('%m/%d'), "-"
                s_name = name_map.get(sid, sid) 

                temp_s = parse_tw_date(row.get('賣出日期'))
                held_days = (temp_s - b_date).days if pd.notnull(temp_s) else (datetime.now() - b_date).days

                if pd.isna(row.get('賣出日期')) or str(row.get('賣出價', '')).strip() == "":
                    if not hist.empty:
                        s_price = float(hist['Close'].iloc[-1])
                        diagnosis = f"⚪持股中｜現價{s_price:.1f}"
                else:
                    s_date = temp_s
                    s_price = float(row['賣出價'])
                    s_date_str = s_date.strftime('%m/%d')
                    if not hist.empty:
                        hist = hist.sort_index()
                        s_obj = s_date.date()
                        f7 = hist[(hist.index > s_obj) & (hist.index <= (s_date + timedelta(days=7)).date())]
                        f20 = hist[(hist.index > s_obj) & (hist.index <= (s_date + timedelta(days=20)).date())]

                        if f20.empty or f20['High'].isna().all():
                            diagnosis = "⏳剛賣出或暫無後續"
                        else:
                            if f7.empty or f7['High'].isna().all(): 
                                short_text = "⏳缺短線資料"
                            else:
                                m7 = f7['High'].max()
                                short_text = "✅精準收割" if m7 <= s_price * 1.02 else "📉短線留肉"
                            
                            m20 = f20['High'].max()
                            min20 = f20['Low'].min()
                            threshold = 1.03 if held_days <= 3 else 1.05
                            
                            if pd.notna(m20) and m20 > s_price * threshold:
                                days_to_h = (f20['High'].idxmax() - s_obj).days
                                missed_profit = (m20 - s_price) * shares * 1000
                                pct_up = ((m20 / s_price) - 1) * 100
                                long_text = f"🔭第{days_to_h}天見高 {m20:.1f} (+{pct_up:.1f}%)，🔴潛在+{missed_profit:,.0f}元"
                            
                            elif pd.notna(min20) and min20 < s_price * 0.98:
                                days_to_l = (f20['Low'].idxmin() - s_obj).days
                                avoided_loss = (s_price - min20) * shares * 1000
                                pct_down = ((min20 / s_price) - 1) * 100
                                long_text = f"🛡️第{days_to_l}天跌至 {min20:.1f} ({pct_down:.1f}%)，🟢避開-{avoided_loss:,.0f}元"
                            else:
                                long_text = "🛡️賣出後陷入橫盤，撤退精準！"
                            
                            diagnosis = f"{short_text}｜{long_text}"

                b_cost = (b_price * shares * 1000) + int((b_price * shares * 1000) * fee_rate)
                s_rev = (s_price * shares * 1000) - int((s_price * shares * 1000) * fee_rate) - int((s_price * shares * 1000) * tax_rate)
                pnl = s_rev - b_cost
                roi = (pnl / b_cost) * 100 if b_cost > 0 else 0
                total_pnl += pnl

                results.append({
                    "代號": sid, "名稱": s_name, "AI診斷": diagnosis,
                    "買": b_date_str, "賣": s_date_str, "天": held_days,
                    "淨利": pnl, "報酬%": roi, "心魔": tag, "_少賺": missed_profit
                })

        if results:
            res = pd.DataFrame(results)
            total_missed = res['_少賺'].sum()
            god_mode_pnl = total_pnl + total_missed
            
            st.markdown(f"### 🎯 <span class='highlight-primary'>游擊隊 V2.3 戰果看板</span>", unsafe_allow_html=True)
            st.markdown(f"#### 💰 總收割淨利：<span style='color:{COLORS['red']}; font-size:28px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
            st.caption(f"✨ **【神仙模式】理論極限淨利**：<span style='color:{COLORS['primary']}; font-size:16px;'>**{god_mode_pnl:,.0f}**</span> 元 (若每筆皆賣在絕對高點，尚有 {total_missed:,.0f} 元的潛在空間)", unsafe_allow_html=True)

            ad = res[res['賣'] != "-"].copy()
            if not ad.empty:
                def get_s(df): return (df['淨利']>0).mean()*100, df['報酬%'].mean()
                s_w, s_r = get_s(ad[ad['天']<=3])
                m_w, m_r = get_s(ad[(ad['天']>=4)&(ad['天']<=7)])
                l_w, l_r = get_s(ad[ad['天']>=8])
                
                col1, col2, col3 = st.columns(3)
                col1.metric("⚡ 隔日/極短 (1~3天)", f"{s_w:.0f}% 勝率", f"{s_r:.2f}% 均報")
                col2.metric("🚶 短波段 (4~7天)", f"{m_w:.0f}% 勝率", f"{m_r:.2f}% 均報")
                col3.metric("🧘 長波段 (8天+)", f"{l_w:.0f}% 勝率", f"{l_r:.2f}% 均報")

                avg_m = res['_少賺'][res['_少賺']>0].mean()
                st.markdown(f"""<div class='tier-card' style='border-top:4px solid {COLORS['primary']};'>
                    <h4 style='margin:0;'>👑 混合型收割者分析</h4>
                    <span class='text-sub'><b>人格診斷：</b> 您能適應各種持股天數，屬於全方位游擊手。<br>
                    <b>收割效率：</b> 每一筆獲利交易平均留給市場</span> <span style='color:{COLORS['red']}; font-weight:bold;'>{avg_m if not pd.isna(avg_m) else 0:,.0f} 元</span>。<span class='text-sub'>
                    這不是損失，而是下次<b>『回頭收割』</b>的潛在空間！</span></div>""", unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("#### 📜 詳細收割清單")
            display_cols = ["代號", "名稱", "AI診斷", "買", "賣", "天", "淨利", "報酬%", "心魔"]
            display_df = res[display_cols]
            
            # 套用與主程式相同的表格背景設定
            table_style = {'text-align': 'center', 'background-color': COLORS['card'], 'color': COLORS['text'], 'border-color': COLORS['border']}

            st.dataframe(
                display_df.style.set_properties(**table_style).format({"淨利":"{:,.0f}", "報酬%":"{:.2f}%"})
                .map(lambda x: f"color:{COLORS['red']}" if x > 0 else f"color:{COLORS['green']}", subset=["淨利", "報酬%"])
                .set_properties(subset=["AI診斷"], **{'white-space': 'pre-wrap'}),
                use_container_width=True, hide_index=True,
                column_config={
                    "代號": st.column_config.TextColumn(width="small"),
                    "名稱": st.column_config.TextColumn(width="small"),
                    "AI診斷": st.column_config.TextColumn(width="large"),
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
