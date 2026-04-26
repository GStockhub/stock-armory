import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
from data_center import read_remote_csv, safe_download, load_industry_map

# 🚀 終極日期解析器：暴力斬斷尾巴，並封殺 1970 年的幽靈數字
def parse_tw_date(d_str):
    try:
        raw = str(d_str).strip()

        if not raw or raw.lower() in ["nan", "nat", "none", "0", "-"]:
            return pd.NaT

        raw = raw.split(" ")[0].split("T")[0]
        raw = raw.replace("/", "-").replace(".", "-")

        # 先處理 Excel 日期序號，例如 45400、45580
        if re.fullmatch(r"\d{5}", raw):
            serial = int(raw)
            if 30000 <= serial <= 60000:
                dt = pd.to_datetime("1899-12-30") + pd.to_timedelta(serial, unit="D")
                if 2000 <= dt.year <= datetime.now().year + 1:
                    return dt
            return pd.NaT

        # 處理 8 碼西元日期，例如 20260423
        if re.fullmatch(r"\d{8}", raw):
            y = int(raw[:4])
            m = int(raw[4:6])
            d = int(raw[6:8])
            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")
            if pd.notna(dt) and 2000 <= dt.year <= datetime.now().year + 1:
                return dt
            return pd.NaT

        # 處理 7 碼民國日期，例如 1140423
        if re.fullmatch(r"\d{7}", raw):
            y = int(raw[:3]) + 1911
            m = int(raw[3:5])
            d = int(raw[5:7])
            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")
            if pd.notna(dt) and 2000 <= dt.year <= datetime.now().year + 1:
                return dt
            return pd.NaT

        parts = raw.split("-")

        if len(parts) == 3:
            y = int(parts[0])
            m = int(parts[1])
            d = int(parts[2])

            # 民國年，例如 114-04-23
            if y < 1911:
                y += 1911

            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")

        elif len(parts) == 2:
            y = datetime.now().year
            m = int(parts[0])
            d = int(parts[1])
            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")

        else:
            dt = pd.to_datetime(raw, errors="coerce")

        if pd.isna(dt):
            return pd.NaT

        if dt.year < 2000 or dt.year > datetime.now().year + 1:
            return pd.NaT

        return dt

    except Exception:
        return pd.NaT

def extract_number(val_str):
    try:
        s = str(val_str).replace(',', '').strip()
        match = re.search(r'-?\d+\.?\d*', s)
        if match:
            return float(match.group(0))
        return 0.0
    except Exception:
        return 0.0

# 絕對精準欄位鎖定
def get_val(row, possible_keys, exclude_keys=None, default=""):
    if exclude_keys is None: exclude_keys = []
    
    # 1. 絕對精準比對 (優先)
    for col in row.index:
        col_str = str(col).strip()
        if col_str in possible_keys:
            val = row[col]
            if pd.notna(val) and str(val).strip() != "":
                return str(val).strip()
                
    # 2. 模糊比對 (備用)
    for col in row.index:
        col_str = str(col).strip()
        if any(x in col_str for x in exclude_keys):
            continue
        for k in possible_keys:
            if k in col_str:
                val = row[col]
                if pd.notna(val) and str(val).strip() != "":
                    return str(val).strip()
    return default

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

    results = []
    skipped_rows = []
    total_pnl = 0.0
    win_trades = 0
    total_closed_trades = 0
    demons = []
    max_missed_profit = 0
    max_missed_stock = ""

    _, TWSE_NAME_MAP = load_industry_map()

    with st.spinner("🧠 AAR 戰術教練正在深度覆盤您的交易歷史..."):
        for i, row in df.iterrows():
            try:
                sid_raw = get_val(row, ["代號", "股票代號", "證券代號", "股票代碼", "stock_id"])
                sid = str(sid_raw).strip()
                if not sid: 
                    skipped_rows.append({"行數 (Excel)": i+2, "代號": "未知", "原因": "找不到【代號】欄位"})
                    continue

                buy_date_raw = get_val(row, ["買進日期", "買進日", "日期", "建倉日"], exclude_keys=["賣", "平"])
                buy_price_raw = get_val(row, ["買進價", "成本價", "成本", "買價", "均價"], exclude_keys=["賣", "平"])
                shares_raw = get_val(row, ["張數", "庫存張數", "庫存", "股數", "數量"])
                user_demon = get_val(row, ["心理標籤", "心魔", "標籤", "心理狀態"])

                if not buy_date_raw or not buy_price_raw or not shares_raw:
                    skipped_rows.append({"行數 (Excel)": i+2, "代號": sid, "原因": f"缺少數值 (買日:{buy_date_raw}, 買價:{buy_price_raw}, 張數:{shares_raw})"})
                    continue

                buy_date = parse_tw_date(buy_date_raw)
                buy_price = extract_number(buy_price_raw)
                shares = extract_number(shares_raw)

                if pd.isna(buy_date) or buy_price <= 0 or shares <= 0:
                    skipped_rows.append({"行數 (Excel)": i+2, "代號": sid, "原因": f"數值無法辨識 (日:{buy_date_raw}, 價:{buy_price}, 張:{shares})"})
                    continue

                sell_date_raw = get_val(row, ["賣出日期", "賣出日", "平倉日"])
                sell_price_raw = get_val(row, ["賣出價", "賣價", "平倉價"])
                is_sold = sell_date_raw != "" and sell_price_raw != ""

                hist = safe_download(sid, fm_token, period="1y")
                if hist is None or hist.empty:
                    skipped_rows.append({"行數 (Excel)": i+2, "代號": sid, "原因": "Yahoo/FinMind 皆抓不到歷史報價"})
                    continue
                
                hist.index = pd.to_datetime(hist.index).tz_localize(None)

                latest_price = float(hist["Close"].iloc[-1])
                m5 = float(hist["Close"].rolling(5).mean().iloc[-1])
                m10 = float(hist["Close"].rolling(10).mean().iloc[-1])

                sell_date = pd.NaT
                sell_price = latest_price
                
                if is_sold:
                    sell_date = parse_tw_date(sell_date_raw)
                    sell_price = extract_number(sell_price_raw)

                fee_rate = 0.001425 * fee_discount
                tax_rate = 0.001 if sid.startswith("00") else 0.003

                buy_cost = buy_price * shares * 1000
                buy_cost += buy_cost * fee_rate

                sell_rev = sell_price * shares * 1000
                sell_rev -= sell_rev * fee_rate
                if is_sold: sell_rev -= sell_rev * tax_rate

                pnl = sell_rev - buy_cost
                roi = (pnl / buy_cost) * 100 if buy_cost > 0 else 0

                if is_sold and pd.notna(sell_date):
                    held_days = (sell_date - buy_date).days
                else:
                    held_days = (pd.Timestamp(datetime.now()) - buy_date).days
                    if held_days < 0 or held_days > 3650:
                        held_days = 0

                demon = ""
                comment = ""

                if is_sold:
                    total_pnl += pnl
                    total_closed_trades += 1
                    if pnl > 0: win_trades += 1

                    post_sell_hist = hist.loc[sell_date:]
                    if not post_sell_hist.empty and len(post_sell_hist) > 1:
                        # 🚀 統帥規矩：只抓賣出後的 20 個交易日！不再當無止盡追蹤的恐怖情人！
                        post_hist = post_sell_hist.iloc[1:21] 
                        if not post_hist.empty:
                            max_idx = post_hist['High'].idxmax()
                            min_idx = post_hist['Low'].idxmin()
                            
                            max_row = post_hist.loc[max_idx]
                            min_row = post_hist.loc[min_idx]
                            
                            max_after_sell = float(max_row['High'])
                            min_after_sell = float(min_row['Low'])
                            
                            s_date = pd.to_datetime(sell_date)
                            max_date = pd.to_datetime(max_idx)
                            min_date = pd.to_datetime(min_idx)
                            
                            # 計算日曆天數
                            days_to_max = (max_date - s_date).days
                            days_to_min = (min_date - s_date).days
                            
                            # 避免極端異常值 (如果還是算錯，強制轉成文字)
                            disp_days_max = str(days_to_max) if 0 <= days_to_max <= 50 else "?"
                            disp_days_min = str(days_to_min) if 0 <= days_to_min <= 50 else "?"
                            
                            missed_pnl = (max_after_sell - sell_price) * shares * 1000
                            avoided_loss = (sell_price - min_after_sell) * shares * 1000
                            
                            if missed_pnl > max_missed_profit:
                                max_missed_profit = missed_pnl
                                max_missed_stock = f"{TWSE_NAME_MAP.get(sid, sid)} ({missed_pnl:,.0f}元)"

                            if roi > 0:
                                if missed_pnl > buy_cost * 0.03: 
                                    grade = "🥈 A級"
                                    comment = f"🕊️獲利了結！後於第 {disp_days_max} 天漲至 {max_after_sell:.1f} 元，潛在 +{missed_pnl:,.0f} 元。"
                                    demon = "🕊️ 賣飛"
                                else:
                                    grade = "👑 S級"
                                    comment = "👑完美停利！賣出後未見大幅創高，波段高點精準入袋！"
                            else:
                                if avoided_loss > buy_cost * 0.03: 
                                    grade = "⚔️ B級"
                                    comment = f"🛡️果斷停損！後於第 {disp_days_min} 天跌至 {min_after_sell:.1f} 元，防止 -{avoided_loss:,.0f} 元的虧損"
                                    demon = "🛡️ 紀律"
                                else:
                                    grade = "⚠️ C級"
                                    comment = f"😨砍在阿呆谷！後於第 {disp_days_max} 天反彈至 {max_after_sell:.1f} 元，潛在 +{missed_pnl:,.0f} 元"
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

                if user_demon:
                    demon = f"👤 {user_demon}"

                if demon and "紀律" not in demon and "完美" not in demon:
                    demons.append(demon)

                buy_str = buy_date.strftime("%m-%d")
                sell_str = sell_date.strftime("%m-%d") if is_sold and pd.notna(sell_date) else "-"

                # 確保持有天數不會出現負數或離譜數字
                disp_held = int(held_days) if 0 <= held_days <= 10000 else 0

                results.append({
                    "代號": sid,
                    "名稱": TWSE_NAME_MAP.get(sid, sid),
                    "診斷詳情": comment,
                    "評級": grade,
                    "買進日": buy_str,
                    "賣出日": sell_str,
                    "持有天數": disp_held,
                    "報酬率(%)": roi,
                    "淨利": int(pnl),
                })
            except Exception as e:
                skipped_rows.append({"行數 (Excel)": i+2, "代號": sid_raw, "原因": f"底層運算當機: {e}"})
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

    if skipped_rows:
        with st.expander(f"⚠️ 系統跳過了 {len(skipped_rows)} 筆格式異常的資料，點擊查看詳細原因", expanded=False):
            st.dataframe(pd.DataFrame(skipped_rows), use_container_width=True)

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
        st.info("AAR 解析完畢後，沒有可分析的有效資料。請查看上方的警告面板了解原因。")
