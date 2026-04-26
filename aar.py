import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_center import read_remote_csv, safe_download, load_industry_map

def parse_tw_date(d_str):
    try:
        d_str = str(d_str).strip().replace("/", "-").replace(".", "-")
        if not d_str: return pd.NaT
        parts = d_str.split("-")
        if len(parts) == 3:
            y = int(parts[0])
            if y < 1911: y += 1911
            return pd.to_datetime(f"{y}-{parts[1]}-{parts[2]}")
        elif len(parts) == 2:
            return pd.to_datetime(f"{datetime.now().year}-{parts[0]}-{parts[1]}")
        return pd.to_datetime(d_str)
    except Exception: return pd.NaT

def render_aar_tab(aar_sheet_url, fee_discount, fm_token, COLORS):
    if not aar_sheet_url:
        st.info("請在左側邊欄輸入【交易日誌】CSV 網址。")
        return

    try:
        df = read_remote_csv(aar_sheet_url, dtype=str)
    except Exception as e:
        st.error(f"系統錯誤: {e}")
        return

    if df.empty:
        st.info("交易日誌沒有資料。")
        return

    df.columns = df.columns.str.replace('\ufeff', '', regex=False).str.strip()

    def get_val(row, possible_keys, default=""):
        for k in possible_keys:
            if k in row and pd.notna(row[k]): return str(row[k]).strip()
        return default

    results = []
    total_pnl = 0.0
    win_trades = 0
    total_closed_trades = 0
    demons = []
    max_missed_profit = 0
    max_missed_stock = ""

    _, TWSE_NAME_MAP = load_industry_map()

    with st.spinner("🧠 AAR 戰術教練正在深度覆盤您的交易歷史..."):
        for _, row in df.iterrows():
            try:
                sid_raw = get_val(row, ["代號", "股票代號", "證券代號", "股票代碼", "stock_id"])
                sid = str(sid_raw).strip()
                if not sid: continue

                buy_date_raw = get_val(row, ["買進日期", "買進日", "日期", "建倉日"])
                buy_price_raw = get_val(row, ["買進價", "成本價", "成本", "買價", "均價"])
                shares_raw = get_val(row, ["張數", "庫存張數", "庫存", "股數", "數量"])
                
                # 🚀 讀取大將軍手動記錄的專屬心魔！
                user_demon = get_val(row, ["心理標籤", "心魔", "標籤", "心理狀態"])

                if not buy_date_raw or not buy_price_raw or not shares_raw: continue

                buy_date = parse_tw_date(buy_date_raw)
                buy_price = float(buy_price_raw.replace(",", ""))
                shares = float(shares_raw.replace(",", ""))

                if pd.isna(buy_date) or buy_price <= 0 or shares <= 0: continue

                sell_date_raw = get_val(row, ["賣出日期", "賣出日", "平倉日"])
                sell_price_raw = get_val(row, ["賣出價", "賣價", "平倉價"])
                is_sold = sell_date_raw != "" and sell_price_raw != ""

                # 現在 safe_download 已經準備好接收 period="1y" 這個引數了！
                hist = safe_download(sid, fm_token, period="1y")
                if hist is None or hist.empty: continue
                
                hist.index = pd.to_datetime(hist.index).tz_localize(None)

                latest_price = float(hist["Close"].iloc[-1])
                m5 = float(hist["Close"].rolling(5).mean().iloc[-1])
                m10 = float(hist["Close"].rolling(10).mean().iloc[-1])

                sell_date = pd.NaT
                sell_price = latest_price
                if is_sold:
                    sell_date = parse_tw_date(sell_date_raw)
                    sell_price = float(sell_price_raw.replace(",", ""))

                fee_rate = 0.001425 * fee_discount
                tax_rate = 0.001 if sid.startswith("00") else 0.003

                buy_cost = buy_price * shares * 1000
                buy_cost += buy_cost * fee_rate

                sell_rev = sell_price * shares * 1000
                sell_rev -= sell_rev * fee_rate
                if is_sold: sell_rev -= sell_rev * tax_rate

                pnl = sell_rev - buy_cost
                roi = (pnl / buy_cost) * 100 if buy_cost > 0 else 0

                held_days = (sell_date - buy_date).days if is_sold and pd.notna(sell_date) else (datetime.now() - buy_date).days

                # === 深度診斷與心魔判定 ===
                demon = ""
                comment = ""

                if is_sold:
                    total_pnl += pnl
                    total_closed_trades += 1
                    if pnl > 0: win_trades += 1

                    post_sell_hist = hist.loc[sell_date:]
                    if not post_sell_hist.empty and len(post_sell_hist) > 1:
                        post_hist = post_sell_hist.iloc[1:] 
                        if not post_hist.empty:
                            max_row = post_hist.loc[post_hist['High'].idxmax()]
                            min_row = post_hist.loc[post_hist['Low'].idxmin()]
                            
                            max_after_sell = float(max_row['High'])
                            min_after_sell = float(min_row['Low'])
                            
                            days_to_max = (max_row.name - sell_date).days
                            days_to_min = (min_row.name - sell_date).days
                            
                            missed_pnl = (max_after_sell - sell_price) * shares * 1000
                            avoided_loss = (sell_price - min_after_sell) * shares * 1000
                            
                            if missed_pnl > max_missed_profit:
                                max_missed_profit = missed_pnl
                                max_missed_stock = f"{TWSE_NAME_MAP.get(sid, sid)} ({missed_pnl:,.0f}元)"

                            if roi > 0:
                                if missed_pnl > buy_cost * 0.03: 
                                    grade = "🥈 A級"
                                    comment = f"🕊️獲利了結！後於第{days_to_max}天漲至{max_after_sell:.1f}元，潛在+{missed_pnl:,.0f}元。"
                                    demon = "🕊️ 賣飛"
                                else:
                                    grade = "👑 S級"
                                    comment = "👑完美停利！賣出後未見大幅創高，波段高點精準入袋！"
                            else:
                                if avoided_loss > buy_cost * 0.03: 
                                    grade = "⚔️ B級"
                                    comment = f"🛡️果斷停損！後於第{days_to_min}天跌至{min_after_sell:.1f}元，防止-{avoided_loss:,.0f}元的虧損"
                                    demon = "🛡️ 紀律"
                                else:
                                    grade = "⚠️ C級"
                                    comment = f"😨砍在阿呆谷！後於第{days_to_max}天反彈至{max_after_sell:.1f}元，潛在+{missed_pnl:,.0f}元"
                                    demon = "😨 恐慌"
                        else:
                            grade = "👑 S級" if roi > 0 else "⚔️ B級"
                            comment = "⏳ 剛平倉，無足夠的後續交易日可供覆盤"
                    else:
                        grade = "👑 S級" if roi > 0 else "⚔️ B級"
                        comment = "⏳ 剛平倉，無足夠的後續交易日可供覆盤"
                else:
                    grade = "⚪ 戰鬥中"
                    if latest_price > m5 > m10: comment = "🚀 強勢多頭排列，跌破 M5 前死抱不賣！"
                    elif latest_price >= m10: comment = "⏳ 均線收斂整理中，防守底線設於 M10。"
                    else: 
                        comment = "⚠️ 已跌破 M10 防守線，強烈建議檢視是否該停損！"
                        demon = "⚓ 凹單"

                # 🚀 如果大將軍有寫心理標籤，強制優先覆蓋系統的自動判定！
                if user_demon:
                    demon = f"👤 {user_demon}"

                if demon and "紀律" not in demon and "完美" not in demon:
                    demons.append(demon)

                buy_str = buy_date.strftime("%m-%d")
                sell_str = sell_date.strftime("%m-%d") if is_sold and pd.notna(sell_date) else "-"

                results.append({
                    "代號": sid,
                    "名稱": TWSE_NAME_MAP.get(sid, sid),
                    "診斷詳情": comment,
                    "評級": grade,
                    "買進日": buy_str,
                    "賣出日": sell_str,
                    "持有天數": int(held_days),
                    "報酬率(%)": roi,
                    "淨利": int(pnl),
                })
            except Exception as e:
                continue

    win_rate = (win_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0
    top_demon = pd.Series(demons).mode()[0] if demons else "無"
    p_color = COLORS["red"] if total_pnl > 0 else COLORS["green"]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"<div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['primary']};'><div style='color:{COLORS['subtext']}; font-size:14px;'>已平倉總淨利</div><div style='font-size:24px; font-weight:bold; color:{p_color};'>{total_pnl:,.0f}</div></div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['accent']};'><div style='color:{COLORS['subtext']}; font-size:14px;'>實戰勝率</div><div style='font-size:24px; font-weight:bold; color:{COLORS['text']};'>{win_rate:.1f}%</div></div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['red']};'><div style='color:{COLORS['subtext']}; font-size:14px;'>最痛的賣飛</div><div style='font-size:18px; font-weight:bold; color:{COLORS['text']};'>{max_missed_stock if max_missed_stock else '無'}</div></div>", unsafe_allow_html=True)
    with col4:
        st.markdown(f"<div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['green']};'><div style='color:{COLORS['subtext']}; font-size:14px;'>最大心魔</div><div style='font-size:20px; font-weight:bold; color:{COLORS['text']};'>{top_demon}</div></div>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    if results:
        res_df = pd.DataFrame(results)
        
        def grade_color(val):
            if 'S級' in str(val): return f"color: {COLORS['primary']}; font-weight: bold;"
            if 'C級' in str(val): return f"color: {COLORS['green']}; font-weight: bold;"
            if 'B級' in str(val): return f"color: {COLORS['accent']}; font-weight: bold;"
            if 'A級' in str(val): return f"color: {COLORS['red']}; font-weight: bold;"
            return f"color: {COLORS['subtext']};"

        table_style = {"text-align": "center", "background-color": COLORS["card"], "color": COLORS["text"], "border-color": COLORS["border"]}
        
        styled = (
            res_df.style.set_properties(**table_style)
            .format({"報酬率(%)": "{:.2f}%", "淨利": "{:,.0f}"})
            .map(lambda x: f"color:{COLORS['red']}; font-weight:bold;" if x > 0 else (f"color:{COLORS['green']}; font-weight:bold;" if x < 0 else ""), subset=["淨利", "報酬率(%)"])
            .map(grade_color, subset=["評級"])
            .set_properties(subset=["診斷詳情"], **{'text-align': 'left', 'white-space': 'pre-wrap'})
        )
        
        st.dataframe(
            styled, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "代號": st.column_config.TextColumn(width="small"),
                "名稱": st.column_config.TextColumn(width="small"),
                "診斷詳情": st.column_config.TextColumn(width="large"),
                "評級": st.column_config.TextColumn(width="small"),
                "買進日": st.column_config.TextColumn(width="small"),
                "賣出日": st.column_config.TextColumn(width="small"),
                "持有天數": st.column_config.NumberColumn(width="small"),
            }
        )
    else:
        st.info("AAR 沒有可分析的有效資料。請確認 CSV 格式包含：代號、買進日期、買進價、張數。")
