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
            if y < 200: y += 1911  # 民國年自動轉西元
            return pd.to_datetime(f"{y}-{parts[1]}-{parts[2]}")
        elif len(parts) == 2:
            return pd.to_datetime(f"{datetime.now().year}-{parts[0]}-{parts[1]}")
        return pd.to_datetime(d_str)
    except:
        return pd.NaT

# =========================
# FinMind 主引擎
# =========================
def get_finmind_data(sid, start_date, fm_token):
    if not fm_token:
        return pd.DataFrame()
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": sid,
            "start_date": start_date,
            "token": fm_token.strip()
        }
        res = requests.get(url, params=params, timeout=10, verify=False).json()

        # 防禦升級：擋掉「幽靈空資料」與被限流的狀況
        if res.get("msg") != "success":
            return pd.DataFrame()

        if res.get("data") and len(res["data"]) > 0:
            df = pd.DataFrame(res["data"])
            df['date'] = pd.to_datetime(df['date']).dt.date
            df.set_index('date', inplace=True)
            
            df['High'] = pd.to_numeric(df.get('max', df.get('high', df['close'])), errors='coerce')
            df['Close'] = pd.to_numeric(df['close'], errors='coerce')

            df = df[['High', 'Close']].dropna()
            df = df.sort_index()
            return df
    except:
        pass
    return pd.DataFrame()

# =========================
# YF 備援引擎 
# =========================
def get_yf_data(sid, start_date):
    suffixes = [".TW", ".TWO"]
    for suf in suffixes:
        try:
            df = yf.Ticker(f"{sid}{suf}").history(start=start_date, auto_adjust=False)
            if not df.empty:
                df.index = pd.to_datetime(df.index).dt.date
                df['High'] = pd.to_numeric(df.get('High', df['Close']), errors='coerce')
                df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
                
                df = df[['High', 'Close']].dropna()
                df = df.sort_index()
                return df
        except:
            continue
    return pd.DataFrame()

# =========================
# 主函數 (V2.2 終極交易教練升級版)
# =========================
def render_aar_tab(aar_sheet_url, fee_discount, fm_token):

    if not aar_sheet_url:
        st.info("請在左側邊欄輸入交易日誌 CSV 網址，喚醒 AI 覆盤引擎。")
        return

    try:
        df = pd.read_csv(aar_sheet_url)
        df.columns = df.columns.str.strip()

        global_start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")

        cache = {}
        results = []
        total_pnl = 0

        with st.spinner("🧠 交易行為分析 AI v2.2 正在執行雙視角與交易風格運算..."):

            for _, row in df.iterrows():
                try:
                    sid = str(row['代號']).strip()
                    if sid == "" or sid == "nan":
                        continue

                    b_date = parse_tw_date(row['買進日期'])
                    b_price = float(row['買進價'])
                    shares = float(row['張數'])
                    
                    raw_tag = str(row.get('心理標籤', '')).strip()
                    tag = raw_tag.split('(')[0].split('（')[0].strip()

                    fee_rate = 0.001425 * fee_discount
                    tax_rate = 0.001 if sid.startswith('00') else 0.003

                except:
                    continue

                # ========= 抓資料（快取） =========
                if sid not in cache:
                    hist = get_finmind_data(sid, global_start, fm_token)
                    if hist.empty:
                        hist = get_yf_data(sid, global_start)

                    cache[sid] = hist
                    time.sleep(0.1)

                hist = cache[sid]

                diagnosis = "⚠️ 無資料"
                s_price = b_price
                s_date = None
                missed_profit_val = 0 
                
                b_date_str = b_date.strftime('%m/%d') if pd.notnull(b_date) else "-"
                s_date_str = "-"

                # 👑 提前計算持有天數 (為了後面的動態門檻判斷)
                temp_s_date = parse_tw_date(row.get('賣出日期')) if pd.notnull(row.get('賣出日期')) else None
                if temp_s_date is not None and not pd.isna(temp_s_date):
                    held_days = (temp_s_date - b_date).days
                else:
                    held_days = (datetime.now() - b_date).days

                # ========= 未平倉 =========
                if pd.isna(row.get('賣出日期')) or str(row.get('賣出價', '')).strip() == "":
                    if not hist.empty:
                        s_price = float(hist['Close'].iloc[-1])
                        diagnosis = f"⚪ 未平倉 | 現價 {s_price:.1f}"
                    else:
                        diagnosis = "⚪ 未平倉 | 無報價"

                # ========= 已平倉 (雙視角 AI 診斷核心) =========
                else:
                    s_date = temp_s_date
                    s_price = float(row['賣出價'])
                    s_date_str = s_date.strftime('%m/%d') if pd.notnull(s_date) else "-"

                    if hist.empty:
                        diagnosis = "⚠️ 無K線資料"
                    else:
                        hist = hist.sort_index()

                        s_date_obj = s_date.date()
                        
                        future_7d_obj = (s_date + timedelta(days=7)).date()
                        future_20d_obj = (s_date + timedelta(days=20)).date()
                        
                        future_data_7d = hist[(hist.index > s_date_obj) & (hist.index <= future_7d_obj)]
                        future_data_20d = hist[(hist.index > s_date_obj) & (hist.index <= future_20d_obj)]

                        # 👑 防呆機制，避免 High 全是 NaN 導致出錯
                        if future_data_20d.empty or future_data_20d['High'].isna().all():
                            if (datetime.now().date() - s_date_obj).days <= 3:
                                diagnosis = "⏳ 剛賣出"
                            else:
                                diagnosis = f"⚠️ 無後續"
                        else:
                            max_20d = future_data_20d['High'].max()
                            
                            # 👑 短線嚴謹空值判斷，不自我安慰
                            if future_data_7d.empty or future_data_7d['High'].isna().all():
                                max_7d = None
                            else:
                                max_7d = future_data_7d['High'].max()

                            if pd.isna(max_20d):
                                diagnosis = "⚠️ 價格異常"
                            else:
                                if '恐高' in tag or '耐心' in tag:
                                    # 🟢 視角一：短線判斷
                                    if max_7d is None:
                                        short_term = "⏳ 短線資料不足"
                                    elif max_7d > s_price * 1.02:
                                        short_term = "📉 短線即賣飛"
                                    else:
                                        short_term = "✅ 短線躲過震盪"

                                    # 🔴 視角二：波段潛力判斷 (動態門檻)
                                    threshold = 1.03 if held_days <= 3 else 1.05
                                    
                                    if max_20d > s_price * threshold:
                                        max_date = future_data_20d['High'].idxmax()
                                        days_to_high = (max_date - s_date_obj).days
                                        missed_profit_val = (max_20d - s_price) * shares * 1000
                                        long_term = f"🩸 卻錯失主升段 ({days_to_high}天後高點 {max_20d:.1f}，少賺 {missed_profit_val:,.0f}元)"
                                    else:
                                        long_term = "且無錯失大波段，精準撤退！"

                                    diagnosis = f"{short_term} ｜ {long_term}"

                                elif '恐慌' in tag:
                                    if max_20d > b_price:
                                        max_date = future_data_20d['High'].idxmax()
                                        days_to_high = (max_date - s_date_obj).days
                                        diagnosis = f"🩸 洗盤被騙！({days_to_high}天後反彈至 {max_20d:.1f} 解套)"
                                    else:
                                        diagnosis = "🛡️ 停損正確！後續未見大反彈。"

                                elif '紀律' in tag:
                                    diagnosis = "👑 嚴格執行紀律，無須留戀後續漲跌"

                                else:
                                    if max_7d is not None:
                                        diagnosis = f"📊 7天高點 {max_7d:.1f} ｜ 20天高點 {max_20d:.1f}"
                                    else:
                                        diagnosis = f"📊 20天高點 {max_20d:.1f}"

                # ========= 損益計算 =========
                buy_fee = int((b_price * shares * 1000) * fee_rate)
                buy_cost = (b_price * shares * 1000) + buy_fee
                
                sell_fee = int((s_price * shares * 1000) * fee_rate)
                sell_tax = int((s_price * shares * 1000) * tax_rate)
                sell_rev = (s_price * shares * 1000) - sell_fee - sell_tax

                pnl = sell_rev - buy_cost
                roi = (pnl / buy_cost) * 100 if buy_cost > 0 else 0

                total_pnl += pnl

                results.append({
                    "代號": sid,
                    "買進": b_date_str,
                    "賣出": s_date_str,
                    "天數": held_days,
                    "淨利": pnl,
                    "報酬%": roi,
                    "心魔": tag,
                    "AI診斷": diagnosis,
                    "_少賺": missed_profit_val 
                })

        # =========================================================
        # 👑 交易行為分析 AI v2.2 (交易風格判定與完美排版版)
        # =========================================================
        if results:
            res = pd.DataFrame(results)
            
            st.markdown(f"### 🎯 <span class='highlight-gold'>交易教練 V2 總結報告</span>", unsafe_allow_html=True)
            st.markdown(f"#### 💰 歷史戰役總淨利：<span style='color:#EF4444; font-size:28px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
            
            # =====================================================
            # 🤖 新增：交易風格 AI 判斷系統（GPT 核心升級）
            # =====================================================
            analysis_df = res[res['賣出'] != "-"].copy()
            if not analysis_df.empty:
                short_df = analysis_df[analysis_df['天數'] <= 3]
                mid_df = analysis_df[(analysis_df['天數'] >= 4) & (analysis_df['天數'] <= 7)]
                long_df = analysis_df[analysis_df['天數'] >= 8]

                def calc_stats(df_chunk):
                    if df_chunk.empty: return 0, 0
                    win_rate = (df_chunk['淨利'] > 0).mean() * 100
                    avg_roi = df_chunk['報酬%'].mean()
                    return win_rate, avg_roi

                s_win, s_roi = calc_stats(short_df)
                m_win, m_roi = calc_stats(mid_df)
                l_win, l_roi = calc_stats(long_df)

                st.markdown("#### 🧠 您的交易風格與勝率雷達")
                col_s, col_m, col_l = st.columns(3)
                col_s.metric("⚡ 短線 (1~3天)", f"{s_win:.0f}% 勝率", f"{s_roi:.2f}% 均報")
                col_m.metric("🚶 波段 (4~7天)", f"{m_win:.0f}% 勝率", f"{m_roi:.2f}% 均報")
                col_l.metric("🧘 長波段 (8天+)", f"{l_win:.0f}% 勝率", f"{l_roi:.2f}% 均報")

                # AI 判斷核心
                style_title = ""
                style_reason = ""

                if s_win > m_win and s_win > l_win:
                    style_title = "⚡ 您是【短線爆發型交易者】"
                    style_reason = "您在 1~3 天內的勝率最高，代表您抓轉折進出點的能力很強，適合快進快出的游擊戰。"
                elif m_win > s_win and m_win > l_win:
                    style_title = "🚶 您是【波段穩定型交易者】"
                    style_reason = "您在 4~7 天的勝率最好，代表您適合吃一段小趨勢，太快賣反而會錯失獲利。"
                elif l_win > s_win and l_win > m_win:
                    style_title = "🧘 您是【波段耐心型交易者】"
                    style_reason = "您長抱反而勝率最高，代表您的眼光很準，您其實適合賺大波段，千萬要管住手！"
                else:
                    style_title = "⚖️ 您是【混合型交易者】"
                    style_reason = "不同區間表現接近，代表您的策略尚未完全定型，或者您能完美適應各種盤勢。"

                st.markdown(f"""
                <div class='tier-card' style='border-top: 4px solid #38BDF8;'>
                    <h4 style='margin-top:0; color:#38BDF8;'>👑 AI 交易人格診斷</h4>
                    <span style='font-size:20px; font-weight:bold; color:#F59E0B;'>{style_title}</span><br><br>
                    <span style='color:#9CA3AF;'>{style_reason}</span>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("---")

            # =====================================================
            # 🛡️ 戰略弱點掃描 (原有的 3 區塊)
            # =====================================================
            c1, c2, c3 = st.columns(3)
            
            # 1. 🔪 心魔代價排行榜 
            demon_loss = res[res['心魔'] != ""].groupby('心魔')['_少賺'].sum().reset_index()
            demon_loss = demon_loss[demon_loss['_少賺'] > 0].sort_values('_少賺', ascending=False)
            
            avg_missed = res['_少賺'][res['_少賺'] > 0].mean()
            if pd.isna(avg_missed): avg_missed = 0
            
            if not demon_loss.empty:
                top_demon = demon_loss.iloc[0]
                c1_html = f"""
                <div class='tier-card'>
                    <h4 style='margin-top:0;'>🔪 心魔代價排行榜</h4>
                    <span style='color:#9CA3AF;'>您最大的敵人是：</span><br>
                    <span style='color:#EF4444; font-size:22px; font-weight:bold;'>「{top_demon['心魔']}」</span><br><br>
                    <span style='color:#9CA3AF;'>總計讓您少賺了：</span><br>
                    <span style='color:#F59E0B; font-size:18px; font-weight:bold;'>{top_demon['_少賺']:,.0f} 元</span><br>
                    <span style='color:#9CA3AF;'>平均每筆賣飛代價：</span><br>
                    <span style='color:#EF4444; font-size:18px; font-weight:bold;'>{avg_missed:,.0f} 元</span>
                </div>
                """
            else:
                c1_html = "<div class='tier-card'><h4 style='margin-top:0;'>🔪 心魔代價排行榜</h4><br><span style='color:#10B981; font-size:18px;'>✅ 目前無明顯心魔失誤！</span></div>"
            
            with c1: st.markdown(c1_html, unsafe_allow_html=True)

            # 2. ⏳ 最佳持股時長雷達 (保留作為對照)
            res['時長分類'] = res['天數'].apply(lambda x: "⚡ 極短線 (1~3天)" if x <= 3 else ("🚶 短波段 (4~7天)" if x <= 7 else "🧘 長波段 (8天+)"))
            hold_stats = res[res['賣出'] != "-"].groupby('時長分類').agg(
                勝率=('淨利', lambda x: f"{(x > 0).mean() * 100:.0f}%")
            ).reset_index()
            
            c2_content = ""
            if not hold_stats.empty:
                for _, r in hold_stats.iterrows():
                    c2_content += f"<div style='margin-bottom:8px;'><b>{r['時長分類']}</b>：勝率 <span style='color:#38BDF8; font-size:18px; font-weight:bold;'>{r['勝率']}</span></div>"
            else:
                c2_content = "<span style='color:#9CA3AF;'>尚無足夠平倉數據</span>"
                
            c2_html = f"<div class='tier-card'><h4 style='margin-top:0;'>⏳ 持股時長勝率</h4>{c2_content}</div>"
            with c2: st.markdown(c2_html, unsafe_allow_html=True)

            # 3. 🛡️ 紀律勝率對比
            res['操作類型'] = res['心魔'].apply(lambda x: "👑 嚴格紀律" if '紀律' in x else ("👻 情緒干擾" if x else "⚪ 無標籤"))
            type_stats = res[res['賣出'] != "-"].groupby('操作類型').agg(
                均報=('報酬%', 'mean')
            ).reset_index()
            
            c3_content = ""
            if not type_stats.empty:
                for _, r in type_stats.iterrows():
                    color = "#10B981" if r['均報'] > 0 else "#EF4444"
                    c3_content += f"<div style='margin-bottom:8px;'><b>{r['操作類型']}</b>：均報酬 <span style='color:{color}; font-size:18px; font-weight:bold;'>{r['均報']:.2f}%</span></div>"
                    
            c3_html = f"<div class='tier-card'><h4 style='margin-top:0;'>🛡️ 紀律 vs 情緒</h4>{c3_content}</div>"
            with c3: st.markdown(c3_html, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("#### 📜 詳細戰報清單")

            display_df = res.drop(columns=['_少賺', '時長分類', '操作類型'], errors='ignore')

            # =====================================================
            # 👑 救贖之光：強制「自動換行 (Wrap Text)」渲染
            # =====================================================
            styled_df = display_df.style.format({
                "淨利": "{:,.0f}",
                "報酬%": "{:.2f}%"
            }).map(
                lambda x: "color:#EF4444" if x > 0 else "color:#10B981", 
                subset=["淨利", "報酬%"]
            ).set_properties(
                subset=["AI診斷"], **{'white-space': 'pre-wrap'} # 👈 就是這行魔法！強迫文字遇到邊界往下折！
            )

            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "代號": st.column_config.TextColumn("代號", width="small"),
                    "買進": st.column_config.TextColumn("買進", width="small"),
                    "賣出": st.column_config.TextColumn("賣出", width="small"),
                    "天數": st.column_config.NumberColumn("天數", width="small"),
                    "淨利": st.column_config.NumberColumn("淨利", width="small"),
                    "報酬%": st.column_config.TextColumn("報酬%", width="small"),
                    "心魔": st.column_config.TextColumn("心魔", width="small"),
                    "AI診斷": st.column_config.TextColumn("AI毒舌診斷", width="large"),
                }
            )
        else:
            st.warning("沒有資料")

    except Exception as e:
        st.error(f"系統錯誤: {e}")
