import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import yfinance as yf

# =========================
# 👑 台灣專屬：民國年校正模組
# =========================
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
    except:
        return pd.NaT

# =========================
# 名稱對照模組 (新增)
# =========================
@st.cache_data(ttl=86400, show_spinner=False)
def load_names():
    name_map = {}
    try:
        df = pd.read_csv("industry_map.csv", dtype=str)
        for _, row in df.iterrows():
            name_map[str(row['代號']).strip()] = str(row['名稱']).strip()
    except:
        pass
    return name_map

# =========================
# FinMind 主引擎
# =========================
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
            df['Close'] = pd.to_numeric(df['close'], errors='coerce')
            return df[['High', 'Close']].dropna().sort_index()
    except: pass
    return pd.DataFrame()

# =========================
# YF 備援引擎 
# =========================
def get_yf_data(sid, start_date):
    for suf in [".TW", ".TWO"]:
        try:
            df = yf.Ticker(f"{sid}{suf}").history(start=start_date, auto_adjust=False)
            if not df.empty:
                df.index = pd.to_datetime(df.index).dt.date
                df['High'] = pd.to_numeric(df.get('High', df['Close']), errors='coerce')
                df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
                return df[['High', 'Close']].dropna().sort_index()
        except: continue
    return pd.DataFrame()

# =========================
# 主函數 (V2.3 混合型收割者 + 完美動線版)
# =========================
def render_aar_tab(aar_sheet_url, fee_discount, fm_token):
    if not aar_sheet_url:
        st.info("請在左側邊欄輸入【交易日誌】網址。")
        return

    try:
        # 👑 修正點：自動偵測 Pandas 版本，避免 applymap 被拔除的報錯
        df = pd.read_csv(aar_sheet_url, dtype=str)
        if hasattr(df, 'map'):
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        else:
            df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
            
        df.columns = df.columns.str.strip()
        global_start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")
        cache, results, total_pnl = {}, [], 0
        name_map = load_names() # 載入名稱字典

        with st.spinner("🧠 混合型收割者 AI 正在掃描戰場潛力..."):
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
                diagnosis, s_price, s_date, missed_profit = "⚠️ 無資料", b_price, None, 0
                b_date_str, s_date_str = b_date.strftime('%m/%d'), "-"
                s_name = name_map.get(sid, "未知") # 獲取名稱

                # 判定持有天數
                temp_s = parse_tw_date(row.get('賣出日期'))
                held_days = (temp_s - b_date).days if pd.notnull(temp_s) else (datetime.now() - b_date).days

                if pd.isna(row.get('賣出日期')) or str(row.get('賣出價', '')).strip() == "":
                    if not hist.empty:
                        s_price = float(hist['Close'].iloc[-1])
                        diagnosis = f"⚪ 持股中 | 現價 {s_price:.1f}"
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
                            diagnosis = "⏳ 剛賣出或暫無後續"
                        else:
                            # 🟢 短線視角
                            if f7.empty or f7['High'].isna().all(): 
                                short_text = "⏳ 缺短線資料"
                                m7 = None
                            else:
                                m7 = f7['High'].max()
                                short_text = "✅ 精準收割" if m7 <= s_price * 1.02 else "📉 短線留肉"
                            
                            # 🔴 波段潛力與少賺精算
                            m20 = f20['High'].max()
                            threshold = 1.03 if held_days <= 3 else 1.05
                            
                            if pd.notna(m20) and m20 > s_price * threshold:
                                days_to_h = (f20['High'].idxmax() - s_obj).days
                                missed_profit = (m20 - s_price) * shares * 1000
                                long_text = f"🔭 強勢股(20天內續創高 {((m20/s_price)-1)*100:.1f}%)，可圖 {missed_profit:,.0f}元"
                            else: long_text = "🔭 趨勢轉弱，撤退正確"
                            
                            diagnosis = f"{short_text} ｜ {long_text}"

                # 損益計算
                b_cost = (b_price * shares * 1000) + int((b_price * shares * 1000) * fee_rate)
                s_rev = (s_price * shares * 1000) - int((s_price * shares * 1000) * fee_rate) - int((s_price * shares * 1000) * tax_rate)
                pnl = s_rev - b_cost
                roi = (pnl / b_cost) * 100 if b_cost > 0 else 0
                total_pnl += pnl

                # 👑 將資料以大將軍指定的順序寫入字典
                results.append({
                    "代號": sid, "名稱": s_name, "AI診斷": diagnosis,
                    "買": b_date_str, "賣": s_date_str, "天": held_days,
                    "淨利": pnl, "報酬%": roi, "心魔": tag, "_少賺": missed_profit
                })

        if results:
            res = pd.DataFrame(results)
            st.markdown(f"### 🎯 <span class='highlight-gold'>游擊隊 V2.3 戰果看板</span>", unsafe_allow_html=True)
            st.markdown(f"#### 💰 總收割淨利：<span style='color:#EF4444; font-size:28px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)

            # --- 交易風格分析 ---
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
                st.markdown(f"""<div class='tier-card' style='border-top:4px solid #F59E0B;'>
                    <h4 style='margin:0;'>👑 混合型收割者分析</h4>
                    <b>人格診斷：</b> 您能適應各種持股天數，屬於全方位游擊手。<br>
                    <b>收割效率：</b> 每一筆獲利交易平均留給市場 <span style='color:#EF4444;'>{avg_m if not pd.isna(avg_m) else 0:,.0f} 元</span>。
                    這不是損失，而是下次<b>『回頭收割』</b>的潛在空間！</div>""", unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("#### 📜 詳細收割清單")
            
            # 👑 依大將軍指定順序排列顯示
            display_cols = ["代號", "名稱", "AI診斷", "買", "賣", "天", "淨利", "報酬%", "心魔"]
            display_df = res[display_cols]

            st.dataframe(
                display_df.style.format({"淨利":"{:,.0f}", "報酬%":"{:.2f}%"})
                .map(lambda x: "color:#EF4444" if x > 0 else "color:#10B981", subset=["淨利", "報酬%"])
                .set_properties(subset=["AI診斷"], **{'white-space': 'pre-wrap'}),
                use_container_width=True, hide_index=True,
                column_config={
                    "代號": st.column_config.TextColumn(width="small"),
                    "名稱": st.column_config.TextColumn(width="small"),
                    "AI診斷": st.column_config.TextColumn(width="large"), # 放在左側第3欄，霸佔主要視野
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
