import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
from data_center import read_remote_csv, safe_download, load_industry_map

def parse_tw_date(d_str):
    try:
        raw = str(d_str).strip()
        if not raw or raw.lower() in ["nan", "nat", "none", "0", "-"]:
            return pd.NaT
        raw = raw.split(" ")[0].split("T")[0]
        raw = raw.replace("/", "-").replace(".", "-")

        if re.fullmatch(r"\d{5}", raw):
            serial = int(raw)
            if 30000 <= serial <= 60000:
                dt = pd.to_datetime("1899-12-30") + pd.to_timedelta(serial, unit="D")
                if 2000 <= dt.year <= datetime.now().year + 1:
                    return dt
            return pd.NaT

        if re.fullmatch(r"\d{8}", raw):
            y = int(raw[:4])
            m = int(raw[4:6])
            d = int(raw[6:8])
            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")
            if pd.notna(dt) and 2000 <= dt.year <= datetime.now().year + 1:
                return dt
            return pd.NaT

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

def get_val(row, possible_keys, exclude_keys=None, default=""):
    if exclude_keys is None: exclude_keys = []
    for col in row.index:
        col_str = str(col).strip()
        if col_str in possible_keys:
            val = row[col]
            if pd.notna(val) and str(val).strip() != "":
                return str(val).strip()
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
                        post_hist = post_sell_hist.iloc[1:21] 
                        if not post_hist.empty:
                            max_idx = post_hist['High'].idxmax()
                            min_idx = post_hist['Low'].idxmin()
                            max_after_sell = float(post_hist.loc[max_idx, 'High'])
                            min_after_sell = float(post_hist.loc[min_idx, 'Low'])
                            
                            s_date = pd.to_datetime(sell_date)
                            days_to_max = (pd.to_datetime(max_idx) - s_date).days
                            days_to_min = (pd.to_datetime(min_idx) - s_date).days
                            
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
                                    comment = f"🕊️獲利了結！後於第{disp_days_max}天漲至{max_after_sell:.1f}元，潛在+{missed_pnl:,.0f}元。"
                                    demon = "🕊️ 賣飛"
                                else:
                                    grade = "👑 S級"
                                    comment = "👑完美停利！賣出後未見大幅創高，波段高點精準入袋！"
                            else:
                                if avoided_loss > buy_cost * 0.03: 
                                    grade = "⚔️ B級"
                                    comment = f"🛡️果斷停損！後於第{disp_days_min}天跌至{min_after_sell:.1f}元，防止-{avoided_loss:,.0f}元虧損"
                                    demon = "🛡️ 紀律"
                                else:
                                    grade = "⚠️ C級"
                                    comment = f"😨砍在阿呆谷！後於第{disp_days_max}天反彈至{max_after_sell:.1f}元，潛在+{missed_pnl:,.0f}元"
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
                    comment = "⚠️ 已跌破 M10 防守線，建議檢視是否該停損！"
                    demon = "⚓ 凹單"
                    
            if user_demon:
                clean_demon = str(user_demon).split("(")[0].split("（")[0].strip()
                demon = f"👤 {clean_demon}"

            if demon and "紀律" not in demon and "完美" not in demon:
                demons.append(demon)

            buy_str = buy_date.strftime("%m-%d")
            sell_str = sell_date.strftime("%m-%d") if is_sold and pd.notna(sell_date) else "-"
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

    # ===================================================
    # 🧠 原生 Streamlit UI：極簡、防呆、零報錯
    # ===================================================
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("已平倉總淨利", f"{total_pnl:,.0f} 元")
    col2.metric("實戰勝率", f"{win_rate:.1f}%")
    col3.metric("最痛的賣飛", max_missed_stock if max_missed_stock else '無')
    col4.metric("最大心魔", top_demon)
    
    st.divider()

    if results:
        res_df_stat = pd.DataFrame(results)
        closed_stat = res_df_stat[res_df_stat["賣出日"] != "-"].copy()
        closed_stat["報酬率_num"] = pd.to_numeric(closed_stat["報酬率(%)"], errors="coerce")

        with st.expander("🧠 個人化勝率與 Kelly 建議倉位", expanded=False):
            scol1, scol2 = st.columns(2)
            with scol1:
                st.write("**📅 持倉天數 vs 勝率**")
                if not closed_stat.empty:
                    st.dataframe(closed_stat.groupby(pd.cut(closed_stat['持有天數'], bins=[0,2,5,10,999], labels=["1-2天", "3-5天", "6-10天", "11天以上"])).agg(
                        交易筆數=('報酬率_num', 'count'),
                        勝率=('報酬率_num', lambda x: f"{(x>0).mean()*100:.1f}%"),
                        平均報酬=('報酬率_num', lambda x: f"{x.mean():.2f}%")
                    ).dropna())
            with scol2:
                st.write("**⚖️ Kelly Criterion 倉位精算**")
                if not closed_stat.empty and len(closed_stat) >= 5:
                    wins = closed_stat[closed_stat["報酬率_num"] > 0]["報酬率_num"]
                    losses = closed_stat[closed_stat["報酬率_num"] <= 0]["報酬率_num"].abs()
                    p_win = len(wins) / len(closed_stat)
                    avg_win = wins.mean() / 100 if len(wins) > 0 else 0.03
                    avg_loss = losses.mean() / 100 if len(losses) > 0 else 0.03
                    b_ratio = avg_win / avg_loss if avg_loss > 0 else 1
                    k_full = (p_win * b_ratio - (1 - p_win)) / b_ratio if b_ratio > 0 else 0
                    st.write(f"- 真實勝率：**{p_win*100:.1f}%**")
                    st.write(f"- 盈虧比：**1 : {b_ratio:.2f}**")
                    st.write(f"- 建議單筆安全倉位 (半 Kelly)：**{max(k_full * 0.5, 0)*100:.1f}%**")
                else:
                    st.write("資料不足 5 筆，無法計算。")

    if skipped_rows:
        with st.expander(f"⚠️ 系統跳過了 {len(skipped_rows)} 筆異常資料", expanded=False):
            st.dataframe(pd.DataFrame(skipped_rows))

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
            res_df.style
            .set_properties(**table_style)
            .format({"報酬率(%)": "{:.2f}%", "淨利": "{:,.0f}"})
            .map(lambda x: f"color:{COLORS['red']}; font-weight:bold;" if x > 0 else (f"color:{COLORS['green']}; font-weight:bold;" if x < 0 else ""), subset=["淨利", "報酬率(%)"])
            .map(grade_color, subset=["評級"])
            .set_properties(subset=["代號", "名稱", "評級", "買進日", "賣出日", "持有天數", "報酬率(%)", "淨利"], **{'white-space': 'nowrap', 'width': '1%'})
            .set_properties(subset=["診斷詳情"], **{'text-align': 'left', 'white-space': 'pre-wrap', 'width': '99%'})
        )
        
        st.table(styled)
    else:
        st.info("AAR 解析完畢，無有效資料。")
