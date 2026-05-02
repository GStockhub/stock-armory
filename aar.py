import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
import html
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

                        comment = "⚠️ 已跌破 M10 防守線，強烈建議檢視是否該停損！"

                        demon = "⚓ 凹單"

                        

                if user_demon:

                    # 🚀 括號斬斷器：遇到半形 ( 或全形 （ 就切斷，只保留前面的主標題

                    clean_demon = str(user_demon).split("(")[0].split("（")[0].strip()

                    demon = f"👤 {clean_demon}"



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



    # ===================================================

    # 🧠 個人化統計：從你的真實日誌反推最佳模式

    # ===================================================

    if results:

        res_df_stat = pd.DataFrame(results)

        closed_stat = res_df_stat[res_df_stat["賣出日"] != "-"].copy()

        closed_stat["報酬率_num"] = pd.to_numeric(closed_stat["報酬率(%)"], errors="coerce")

        closed_stat["淨利_num"] = pd.to_numeric(closed_stat["淨利"], errors="coerce")

        closed_stat["持有天數_num"] = pd.to_numeric(closed_stat["持有天數"], errors="coerce")



        with st.expander("🧠 個人化勝率分析 (從你的歷史反推最佳模式)", expanded=True):

            st.markdown(f"<div style='color:{COLORS['subtext']}; font-size:13px; margin-bottom:16px;'>以下分析基於你的 <b style='color:{COLORS['text']}'>{len(closed_stat)}</b> 筆平倉紀錄，協助系統認識你。</div>", unsafe_allow_html=True)



            pcol1, pcol2 = st.columns(2)



            with pcol1:

                st.markdown(f"<b style='color:{COLORS['text']}'>📅 持倉天數 vs 勝率</b>", unsafe_allow_html=True)

                def day_bucket(d):

                    if d <= 2: return "1-2天 (隔日沖)"

                    elif d <= 5: return "3-5天 (短線甜蜜點)"

                    elif d <= 10: return "6-10天 (短波段)"

                    else: return "11天以上"



                if not closed_stat.empty:

                    closed_stat["天數區間"] = closed_stat["持有天數_num"].apply(day_bucket)

                    day_grp = closed_stat.groupby("天數區間").apply(

                        lambda x: pd.Series({

                            "筆數": len(x),

                            "勝率(%)": (x["報酬率_num"] > 0).mean() * 100,

                            "平均報酬(%)": x["報酬率_num"].mean()

                        })

                    ).reset_index()

                    order = ["1-2天 (隔日沖)", "3-5天 (短線甜蜜點)", "6-10天 (短波段)", "11天以上"]

                    day_grp["排序"] = day_grp["天數區間"].apply(lambda x: order.index(x) if x in order else 99)

                    day_grp = day_grp.sort_values("排序").drop(columns=["排序"])

                    for _, row_g in day_grp.iterrows():

                        wr = row_g["勝率(%)"]

                        avg_r = row_g["平均報酬(%)"]

                        cnt = int(row_g["筆數"])

                        bar_color = COLORS["green"] if wr >= 70 else (COLORS["primary"] if wr >= 50 else COLORS["red"])

                        st.markdown(f"<div style='margin-bottom:10px;'><div style='display:flex; justify-content:space-between; font-size:13px;'><span style='color:{COLORS['text']}'>{row_g['天數區間']}</span><span style='color:{bar_color}; font-weight:bold;'>{wr:.0f}% ({cnt}筆)</span></div><div style='background:{COLORS['border']}; border-radius:4px; height:8px; margin-top:4px;'><div style='background:{bar_color}; width:{min(wr,100):.0f}%; height:8px; border-radius:4px;'></div></div><div style='font-size:11px; color:{COLORS['subtext']}; margin-top:2px;'>平均報酬 {avg_r:+.2f}%</div></div>", unsafe_allow_html=True)



            with pcol2:

                st.markdown(f"<b style='color:{COLORS['text']}'>⚖️ Kelly Criterion 個人化建議倉位</b>", unsafe_allow_html=True)

                if not closed_stat.empty and len(closed_stat) >= 5:

                    wins = closed_stat[closed_stat["報酬率_num"] > 0]["報酬率_num"]

                    losses = closed_stat[closed_stat["報酬率_num"] <= 0]["報酬率_num"].abs()

                    p_win = len(wins) / len(closed_stat)

                    avg_win_pct = wins.mean() / 100 if len(wins) > 0 else 0.03

                    avg_loss_pct = losses.mean() / 100 if len(losses) > 0 else 0.03

                    b_ratio = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 1

                    kelly_full = (p_win * b_ratio - (1 - p_win)) / b_ratio if b_ratio > 0 else 0

                    kelly_half = max(kelly_full * 0.5, 0)

                    kelly_color = COLORS["green"] if kelly_half > 0.1 else (COLORS["primary"] if kelly_half > 0 else COLORS["red"])

                    st.markdown(f"<div style='background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-radius:8px; padding:14px;'><div style='font-size:12px; color:{COLORS['subtext']}; margin-bottom:8px;'>基於你的 {len(closed_stat)} 筆真實交易</div><div style='display:flex; justify-content:space-between; margin-bottom:6px;'><span style='color:{COLORS['subtext']}; font-size:13px;'>真實勝率</span><span style='color:{COLORS['text']}; font-weight:bold;'>{p_win*100:.1f}%</span></div><div style='display:flex; justify-content:space-between; margin-bottom:6px;'><span style='color:{COLORS['subtext']}; font-size:13px;'>平均盈虧比</span><span style='color:{COLORS['text']}; font-weight:bold;'>1 : {b_ratio:.2f}</span></div><div style='display:flex; justify-content:space-between; margin-bottom:6px;'><span style='color:{COLORS['subtext']}; font-size:13px;'>Full Kelly</span><span style='color:{COLORS['primary']};'>{kelly_full*100:.1f}%</span></div><div style='display:flex; justify-content:space-between; padding-top:8px; border-top:1px solid {COLORS['border']};'><span style='color:{COLORS['text']}; font-weight:bold; font-size:14px;'>建議單筆倉位 (半Kelly)</span><span style='color:{kelly_color}; font-weight:bold; font-size:18px;'>{kelly_half*100:.1f}%</span></div><div style='font-size:11px; color:{COLORS['subtext']}; margin-top:6px;'>半Kelly為保守安全值，Full Kelly風險過高不建議直接使用</div></div>", unsafe_allow_html=True)

                else:

                    st.info("至少需要 5 筆平倉紀錄才能計算 Kelly 建議倉位。")



            st.markdown("<br>", unsafe_allow_html=True)

            st.markdown(f"<b style='color:{COLORS['text']}'>🚨 心魔分布</b>", unsafe_allow_html=True)

            if demons:

                demon_counts = pd.Series(demons).value_counts()

                total_d = len(demons)

                for dm, cnt in demon_counts.items():

                    pct = cnt / total_d * 100

                    dm_color = COLORS["red"] if "凹單" in dm else (COLORS["accent"] if "恐高" in dm else COLORS["primary"])

                    st.markdown(f"<div style='margin-bottom:8px;'><div style='display:flex; justify-content:space-between; font-size:13px;'><span style='color:{COLORS['text']}'>{dm}</span><span style='color:{dm_color}; font-weight:bold;'>{cnt}次 ({pct:.0f}%)</span></div><div style='background:{COLORS['border']}; border-radius:4px; height:6px; margin-top:3px;'><div style='background:{dm_color}; width:{pct:.0f}%; height:6px; border-radius:4px;'></div></div></div>", unsafe_allow_html=True)



    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"<div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['primary']};'><div style='color:{COLORS['subtext']}; font-size:14px;'>已平倉總淨利</div><div style='font-size:24px; font-weight:bold; color:{p_color};'>{total_pnl:,.0f}</div></div>", unsafe_allow_html=True)

    with col2:
        st.markdown(f"<div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['accent']};'><div style='color:{COLORS['subtext']}; font-size:14px;'>實戰勝率</div><div style='font-size:24px; font-weight:bold; color:{COLORS['text']};'>{win_rate:.1f}%</div></div>", unsafe_allow_html=True)

    with col3:
        st.markdown(f"<div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['red']};'><div style='color:{COLORS['subtext']}; font-size:14px;'>最痛的賣飛</div><div style='font-size:18px; font-weight:bold; color:{COLORS['text']};'>{max_missed_stock if max_missed_stock else '無'}</div></div>", unsafe_allow_html=True)

    with col4:
        st.markdown(f"<div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['green']};'><div style='color:{COLORS['subtext']}; font-size:14px;'>最大心魔</div><div style='font-size:20px; font-weight:bold; color:{COLORS['text']};'>{top_demon}</div></div>", unsafe_allow_html=True)


    
    # ===================================================
    # 🧙 神仙模式（理論最大獲利）
    # ===================================================
    god_total_pnl = 0

    for i, row in df.iterrows():
        try:
            sid = get_val(row, ["代號", "股票代號", "證券代號", "股票代碼"])
            if not sid:
                continue

            buy_date_raw = get_val(row, ["買進日期", "買進日", "日期"], exclude_keys=["賣"])
            buy_price_raw = get_val(row, ["買進價", "成本價", "成本"])
            shares_raw = get_val(row, ["張數", "庫存張數", "股數"])

            if not buy_date_raw or not buy_price_raw or not shares_raw:
                continue

            buy_date = parse_tw_date(buy_date_raw)
            buy_price = extract_number(buy_price_raw)
            shares = extract_number(shares_raw)

            if pd.isna(buy_date) or buy_price <= 0 or shares <= 0:
                continue

            hist = safe_download(sid, fm_token, period="6mo")
            if hist is None or hist.empty:
                continue

            hist.index = pd.to_datetime(hist.index).tz_localize(None)

            future_hist = hist.loc[buy_date:]
            if future_hist.empty:
                continue

            max_price = future_hist["High"].max()

            fee_rate = 0.001425 * fee_discount
            tax_rate = 0.001 if sid.startswith("00") else 0.003

            buy_cost = buy_price * shares * 1000
            buy_cost += buy_cost * fee_rate

            sell_rev = max_price * shares * 1000
            sell_rev -= sell_rev * fee_rate
            sell_rev -= sell_rev * tax_rate

            god_pnl = sell_rev - buy_cost
            god_total_pnl += god_pnl

        except:
            continue

    missed_total = god_total_pnl - total_pnl
    capture_rate = (total_pnl / god_total_pnl * 100) if god_total_pnl > 0 else 0

    # 🎯 顯示 UI（新一排）
    g1, g2, g3 = st.columns(3)

    with g1:
        st.markdown(f"""
        <div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['primary']};'>
            <div style='color:{COLORS['subtext']}; font-size:14px;'>🧙 神仙最大淨利</div>
            <div style='font-size:22px; font-weight:bold; color:{COLORS['text']};'>{god_total_pnl:,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    with g2:
        color_miss = COLORS["red"] if missed_total > 0 else COLORS["green"]
        st.markdown(f"""
        <div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {color_miss};'>
            <div style='color:{COLORS['subtext']}; font-size:14px;'>📉 少賺空間</div>
            <div style='font-size:22px; font-weight:bold; color:{color_miss};'>{missed_total:,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    with g3:
        st.markdown(f"""
        <div style='background-color:{COLORS['card']}; padding:15px; border-radius:8px; border-left:5px solid {COLORS['accent']};'>
            <div style='color:{COLORS['subtext']}; font-size:14px;'>🎯 獲利捕捉率</div>
            <div style='font-size:22px; font-weight:bold; color:{COLORS['text']};'>{capture_rate:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)



    if skipped_rows:

        with st.expander(f"⚠️ 系統跳過了 {len(skipped_rows)} 筆格式異常的資料，點擊查看詳細原因", expanded=False):

            st.dataframe(pd.DataFrame(skipped_rows), use_container_width=True)



    if results:
        res_df = pd.DataFrame(results)

        # ===================================================
        # ✅ AAR 表格：診斷詳情完整顯示版
        # 使用 components.html 讓 HTML 真正渲染，不會外漏原始語法
        # ===================================================
        def grade_text_color(val):
            if 'S級' in str(val): return COLORS['primary']
            if 'C級' in str(val): return COLORS['green']
            if 'B級' in str(val): return COLORS['accent']
            if 'A級' in str(val): return COLORS['red']
            return COLORS['subtext']

        def pnl_text_color(val):
            try:
                v = float(val)
                if v > 0: return COLORS['red']
                if v < 0: return COLORS['green']
                return COLORS['text']
            except Exception:
                return COLORS['text']

        def fmt_roi(v):
            try:
                return f"{float(v):.2f}%"
            except Exception:
                return str(v)

        def fmt_money(v):
            try:
                return f"{float(v):,.0f}"
            except Exception:
                return str(v)

        table_rows = ""
        for _, r in res_df.iterrows():
            code = html.escape(str(r.get("代號", "")))
            name = html.escape(str(r.get("名稱", "")))
            detail = html.escape(str(r.get("診斷詳情", "")))
            grade = html.escape(str(r.get("評級", "")))
            buy_date = html.escape(str(r.get("買進日", "")))
            sell_date = html.escape(str(r.get("賣出日", "")))
            held = html.escape(str(r.get("持有天數", "")))
            roi_raw = r.get("報酬率(%)", 0)
            pnl_raw = r.get("淨利", 0)
            roi = html.escape(fmt_roi(roi_raw))
            pnl = html.escape(fmt_money(pnl_raw))
            g_color = grade_text_color(grade)
            roi_color = pnl_text_color(roi_raw)
            pnl_color = pnl_text_color(pnl_raw)

            table_rows += f"""
            <tr>
                <td class="aar-code">{code}</td>
                <td class="aar-name">{name}</td>
                <td class="aar-detail">{detail}</td>
                <td class="aar-grade" style="color:{g_color};">{grade}</td>
                <td class="aar-date">{buy_date}</td>
                <td class="aar-date">{sell_date}</td>
                <td class="aar-days">{held}</td>
                <td class="aar-roi" style="color:{roi_color};">{roi}</td>
                <td class="aar-pnl" style="color:{pnl_color};">{pnl}</td>
            </tr>
            """

        # 固定元件高度：讓 AAR 表格自己內部滾動，首列可凍結
        table_height = 560

        aar_table_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="UTF-8">
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                color: {COLORS['text']};
            }}
            .aar-wrap {{
                width: 100%;
                height: 520px;                 /* 表格固定高度，內部自己滑 */
                overflow: auto;                /* 同時支援上下左右捲動 */
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                background: {COLORS['card']};
            }}
            table.aar-table {{
                width: 100%;
                min-width: 980px;              /* 避免小螢幕擠爆，但電腦版仍吃滿 */
                border-collapse: collapse;
                table-layout: fixed;
                font-size: 13px;
                background: {COLORS['card']};
                color: {COLORS['text']};
            }}
            table.aar-table th {{
                position: sticky;              /* 首列凍結 */
                top: 0;
                z-index: 5;
                background: {COLORS['card']};
                color: {COLORS['subtext']};
                font-weight: 700;
                padding: 8px 7px;
                border-bottom: 1px solid {COLORS['border']};
                border-right: 1px solid {COLORS['border']};
                text-align: left;
                white-space: nowrap;
                box-shadow: 0 1px 0 {COLORS['border']};
            }}
            table.aar-table td {{
                padding: 8px 7px;
                border-bottom: 1px solid {COLORS['border']};
                border-right: 1px solid {COLORS['border']};
                vertical-align: top;
                color: {COLORS['text']};
            }}
            table.aar-table tr:last-child td {{
                border-bottom: none;
            }}
            .aar-code {{ width: 6%; white-space: nowrap; }}
            .aar-name {{width: 8%;white-space: normal !important;word-break: break-all;overflow-wrap: anywhere;line-height: 1.35;}}
            .aar-detail {{
                width: 48%;                    /* 診斷詳情吃最多空間 */
                text-align: left;
                white-space: normal !important;
                word-break: break-word;
                overflow-wrap: anywhere;
                line-height: 1.45;
            }}
            .aar-grade {{ width: 7%; white-space: nowrap; font-weight: 700; }}
            .aar-date {{ width: 7%; white-space: nowrap; }}
            .aar-days {{ width: 6%; white-space: nowrap; text-align: right; }}
            .aar-roi {{ width: 7%; white-space: nowrap; text-align: right; font-weight: 700; }}
            .aar-pnl {{ width: 6%; white-space: nowrap; text-align: right; font-weight: 700; }}
            @media (max-width: 900px) {{
                table.aar-table {{ min-width: 1050px; }}
                .aar-detail {{ width: 44%; }}
            }}
        </style>
        </head>
        <body>
            <div class="aar-wrap">
                <table class="aar-table">
                    <thead>
                        <tr>
                            <th class="aar-code">代號</th>
                            <th class="aar-name">名稱</th>
                            <th class="aar-detail">診斷詳情</th>
                            <th class="aar-grade">評級</th>
                            <th class="aar-date">買進日</th>
                            <th class="aar-date">賣出日</th>
                            <th class="aar-days">持有天數</th>
                            <th class="aar-roi">報酬率(%)</th>
                            <th class="aar-pnl">淨利</th>
                        </tr>
                    </thead>
                    <tbody>{table_rows}</tbody>
                </table>
            </div>
        </body>
        </html>
        """

        components.html(aar_table_html, height=table_height, scrolling=False)

    else:
        st.info("AAR 解析完畢後，沒有可分析的有效資料。請查看上方的警告面板了解原因。")
