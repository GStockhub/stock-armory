import html
import re
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from data_center import load_industry_map, read_remote_csv, safe_download
from aar_insights import normalize_demon, infer_tactic, render_context_insights


# 🚀 終極日期解析器：暴力斬斷尾巴，並封殺 1970 年的幽靈數字
def parse_tw_date(d_str):
    try:
        raw = str(d_str).strip()
        if not raw or raw.lower() in ["nan", "nat", "none", "0", "-"]:
            return pd.NaT

        raw = raw.split(" ")[0].split("T")[0].replace("/", "-").replace(".", "-")

        # Excel 日期序號，例如 45400、45580
        if re.fullmatch(r"\d{5}", raw):
            serial = int(raw)
            if 30000 <= serial <= 60000:
                dt = pd.to_datetime("1899-12-30") + pd.to_timedelta(serial, unit="D")
                if 2000 <= dt.year <= datetime.now().year + 1:
                    return dt
            return pd.NaT

        # 8 碼西元日期，例如 20260423
        if re.fullmatch(r"\d{8}", raw):
            y, m, d = int(raw[:4]), int(raw[4:6]), int(raw[6:8])
            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")
            return dt if pd.notna(dt) and 2000 <= dt.year <= datetime.now().year + 1 else pd.NaT

        # 7 碼民國日期，例如 1140423
        if re.fullmatch(r"\d{7}", raw):
            y, m, d = int(raw[:3]) + 1911, int(raw[3:5]), int(raw[5:7])
            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")
            return dt if pd.notna(dt) and 2000 <= dt.year <= datetime.now().year + 1 else pd.NaT

        parts = raw.split("-")
        if len(parts) == 3:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 1911:
                y += 1911
            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")
        elif len(parts) == 2:
            y, m, d = datetime.now().year, int(parts[0]), int(parts[1])
            dt = pd.to_datetime(f"{y}-{m:02d}-{d:02d}", errors="coerce")
        else:
            dt = pd.to_datetime(raw, errors="coerce")

        if pd.isna(dt) or dt.year < 2000 or dt.year > datetime.now().year + 1:
            return pd.NaT
        return dt
    except Exception:
        return pd.NaT


def extract_number(val_str):
    try:
        s = str(val_str).replace(",", "").strip()
        match = re.search(r"-?\d+\.?\d*", s)
        return float(match.group(0)) if match else 0.0
    except Exception:
        return 0.0


# 絕對精準欄位鎖定
def get_val(row, possible_keys, exclude_keys=None, default=""):
    exclude_keys = exclude_keys or []

    # 1. 絕對精準比對（優先）
    for col in row.index:
        col_str = str(col).strip()
        if col_str in possible_keys:
            val = row[col]
            if pd.notna(val) and str(val).strip() != "":
                return str(val).strip()

    # 2. 模糊比對（備用）
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


def _money(v):
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return str(v)


def _roi(v):
    try:
        return f"{float(v):.2f}%"
    except Exception:
        return str(v)


def _safe_color(COLORS, key, fallback):
    return COLORS.get(key, fallback) if isinstance(COLORS, dict) else fallback


def _metric_card_html(title, value, accent, COLORS, sub="", value_color=None):
    text = _safe_color(COLORS, "text", "#111827")
    subtext = _safe_color(COLORS, "subtext", "#6B7280")
    card = _safe_color(COLORS, "card", "#FFFFFF")
    border = _safe_color(COLORS, "border", "#E5E7EB")
    value_color = value_color or text
    return f"""
    <div class="aar-metric-card" style="background:{card}; border:1px solid {border}; border-left:5px solid {accent};">
        <div class="aar-metric-title" style="color:{subtext};">{html.escape(str(title))}</div>
        <div class="aar-metric-value" style="color:{value_color};">{html.escape(str(value))}</div>
        {f'<div class="aar-metric-sub" style="color:{subtext};">{html.escape(str(sub))}</div>' if sub else ''}
    </div>
    """


def _render_metric_grid(cards_html, COLORS):
    bg = _safe_color(COLORS, "bg", "transparent")
    components.html(
        f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="UTF-8">
        <style>
            html, body {{ margin:0; padding:0; background:{bg}; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
            .aar-metric-grid {{
                display:grid;
                grid-template-columns: repeat(4, minmax(180px, 1fr));
                gap:16px;
                width:100%;
                box-sizing:border-box;
                padding:2px 0 14px 0;
            }}
            .aar-metric-card {{
                min-height:82px;
                box-sizing:border-box;
                border-radius:10px;
                padding:14px 16px;
                box-shadow:0 1px 2px rgba(0,0,0,0.04);
                display:flex;
                flex-direction:column;
                justify-content:center;
                overflow:hidden;
            }}
            .aar-metric-title {{ font-size:14px; line-height:1.2; margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
            .aar-metric-value {{ font-size:clamp(18px, 2.2vw, 24px); line-height:1.18; font-weight:800; white-space:normal; overflow-wrap:anywhere; word-break:break-word; }}
            .aar-metric-sub {{ font-size:12px; line-height:1.35; margin-top:6px; white-space:normal; overflow-wrap:anywhere; word-break:break-word; }}
            @media (max-width: 900px) {{ .aar-metric-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap:12px; }} }}
            @media (max-width: 520px) {{ .aar-metric-grid {{ grid-template-columns: 1fr; }} }}
        </style>
        </head>
        <body><div class="aar-metric-grid">{''.join(cards_html)}</div></body>
        </html>
        """,
        height=245,
        scrolling=False,
    )


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

    df.columns = df.columns.str.replace("\ufeff", "", regex=False).str.strip()

    results = []
    skipped_rows = []
    total_pnl = 0.0
    win_trades = 0
    total_closed_trades = 0
    demons = []
    max_missed_profit = 0
    max_missed_stock = ""
    god_total_pnl = 0.0
    god_best_pnl = 0.0
    god_best_stock = ""
    god_trade_count = 0
    missed_k_records = []
    missed_money_records = []

    TWSE_IND_MAP, TWSE_NAME_MAP = load_industry_map()

    with st.spinner("🧠 AAR 戰術教練正在深度覆盤您的交易歷史..."):
        for i, row in df.iterrows():
            sid_raw = "未知"
            try:
                sid_raw = get_val(row, ["代號", "股票代號", "證券代號", "股票代碼", "stock_id"])
                sid = str(sid_raw).strip()
                if not sid:
                    skipped_rows.append({"行數 (Excel)": i + 2, "代號": "未知", "原因": "找不到【代號】欄位"})
                    continue

                buy_date_raw = get_val(row, ["買進日期", "買進日", "日期", "建倉日"], exclude_keys=["賣", "平"])
                buy_price_raw = get_val(row, ["買進價", "成本價", "成本", "買價", "均價"], exclude_keys=["賣", "平"])
                shares_raw = get_val(row, ["張數", "庫存張數", "庫存", "股數", "數量"])
                user_demon = get_val(row, ["心理標籤", "心魔", "標籤", "心理狀態"])

                if not buy_date_raw or not buy_price_raw or not shares_raw:
                    skipped_rows.append({"行數 (Excel)": i + 2, "代號": sid, "原因": f"缺少數值 (買日:{buy_date_raw}, 買價:{buy_price_raw}, 張數:{shares_raw})"})
                    continue

                buy_date = parse_tw_date(buy_date_raw)
                buy_price = extract_number(buy_price_raw)
                shares = extract_number(shares_raw)
                if pd.isna(buy_date) or buy_price <= 0 or shares <= 0:
                    skipped_rows.append({"行數 (Excel)": i + 2, "代號": sid, "原因": f"數值無法辨識 (日:{buy_date_raw}, 價:{buy_price}, 張:{shares})"})
                    continue

                sell_date_raw = get_val(row, ["賣出日期", "賣出日", "平倉日"])
                sell_price_raw = get_val(row, ["賣出價", "賣價", "平倉價"])
                is_sold = sell_date_raw != "" and sell_price_raw != ""

                hist = safe_download(sid, fm_token, period="1y")
                if hist is None or hist.empty:
                    skipped_rows.append({"行數 (Excel)": i + 2, "代號": sid, "原因": "Yahoo/FinMind 皆抓不到歷史報價"})
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
                if is_sold:
                    sell_rev -= sell_rev * tax_rate

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
                    if pnl > 0:
                        win_trades += 1

                    # 🧙 神仙模式：同一筆買進，假設後續歷史最高點賣出（只統計已平倉，和「已平倉總淨利」口徑一致）
                    future_hist = hist.loc[buy_date:]
                    if not future_hist.empty:
                        max_price = float(future_hist["High"].max())
                        god_sell_rev = max_price * shares * 1000
                        god_sell_rev -= god_sell_rev * fee_rate
                        god_sell_rev -= god_sell_rev * tax_rate
                        god_pnl = god_sell_rev - buy_cost
                        god_total_pnl += god_pnl
                        god_trade_count += 1
                        if god_pnl > god_best_pnl:
                            god_best_pnl = god_pnl
                            god_best_stock = f"{TWSE_NAME_MAP.get(sid, sid)} ({god_pnl:,.0f}元)"

                    post_sell_hist = hist.loc[sell_date:]
                    if not post_sell_hist.empty and len(post_sell_hist) > 1:
                        post_hist = post_sell_hist.iloc[1:21]  # 賣出後 20 個交易日
                        if not post_hist.empty:
                            max_idx = post_hist["High"].idxmax()
                            min_idx = post_hist["Low"].idxmin()
                            max_after_sell = float(post_hist.loc[max_idx, "High"])
                            min_after_sell = float(post_hist.loc[min_idx, "Low"])
                            s_date = pd.to_datetime(sell_date)
                            k_days_max = post_hist.index.get_loc(max_idx) + 1
                            k_days_min = post_hist.index.get_loc(min_idx) + 1
                            s_date = pd.to_datetime(sell_date)
                            max_date = pd.to_datetime(max_idx)
                            min_date = pd.to_datetime(min_idx)
                            cal_days_max = (max_date - s_date).days
                            cal_days_min = (min_date - s_date).days
                            disp_days_max = f"{k_days_max}根K" if 0 <= k_days_max <= 50 else "?"
                            disp_days_min = f"{k_days_min}根K" if 0 <= k_days_min <= 50 else "?"
                            missed_pnl = (max_after_sell - sell_price) * shares * 1000
                            avoided_loss = (sell_price - min_after_sell) * shares * 1000
                            if missed_pnl > buy_cost * 0.03:
                                missed_k_records.append(k_days_max)
                                missed_money_records.append(missed_pnl)

                            if missed_pnl > max_missed_profit:
                                max_missed_profit = missed_pnl
                                max_missed_stock = f"{TWSE_NAME_MAP.get(sid, sid)} ({missed_pnl:,.0f}元)"

                            if roi > 0:
                                if missed_pnl > buy_cost * 0.03:
                                    grade = "🥈 A級"
                                    comment = f"🕊️獲利了結，後於第{disp_days_max}，漲至{max_after_sell:.1f}元，潛在+{missed_pnl:,.0f}元"
                                    demon = "🕊️ 賣飛"
                                else:
                                    grade = "👑 S級"
                                    comment = "👑完美停利，賣出後未見大幅創高，波段高點精準入袋"
                            else:
                                if avoided_loss > buy_cost * 0.03:
                                    grade = "⚔️ B級"
                                    comment = f"🛡️果斷停損，後於第{disp_days_min}，跌至{min_after_sell:.1f}元，防止-{avoided_loss:,.0f}元虧損"
                                    demon = "🛡️ 紀律"
                                else:
                                    grade = "⚠️ C級"
                                    comment = f"😨砍在山谷，後於第{disp_days_max}，反彈至{max_after_sell:.1f}元，潛在+{missed_pnl:,.0f}元"
                                    demon = "😨 恐慌"
                        else:
                            grade = "👑 S級" if roi > 0 else "⚔️ B級"
                            comment = "⏳ 剛平倉，無足夠的後續交易日可供覆盤"
                    else:
                        grade = "👑 S級" if roi > 0 else "⚔️ B級"
                        comment = "⏳ 剛平倉，無足夠的後續交易日可供覆盤"
                else:
                    grade = "⚪ 戰鬥中"
                    if latest_price > m5 > m10:
                        comment = "🚀 強勢多頭排列，跌破 M5 前死抱不賣！"
                    elif latest_price >= m10:
                        comment = "⏳ 均線收斂整理中，防守底線設於 M10。"
                    else:
                        comment = "⚠️ 已跌破 M10 防守線，強烈建議檢視是否該停損！"
                        demon = "⚓ 凹單"

                clean_demon_label = normalize_demon(user_demon, demon)
                if user_demon:
                    clean_demon = str(user_demon).split("(")[0].split("（")[0].strip()
                    demon = f"👤 {clean_demon}"

                if demon and "紀律" not in demon and "完美" not in demon:
                    demons.append(demon)

                industry = "ETF" if sid.startswith("00") else TWSE_IND_MAP.get(sid, "未知")
                tactic_guess = infer_tactic(roi, held_days, clean_demon_label, comment, grade)

                results.append({
                    "代號": sid,
                    "名稱": TWSE_NAME_MAP.get(sid, sid),
                    "產業": industry,
                    "戰術推定": tactic_guess,
                    "心魔分類": clean_demon_label,
                    "診斷詳情": comment,
                    "評級": grade,
                    "買進日": buy_date.strftime("%m-%d"),
                    "賣出日": sell_date.strftime("%m-%d") if is_sold and pd.notna(sell_date) else "-",
                    "持有天數": int(held_days) if 0 <= held_days <= 10000 else 0,
                    "報酬率(%)": roi,
                    "淨利": int(pnl),
                })
            except Exception as e:
                skipped_rows.append({"行數 (Excel)": i + 2, "代號": sid_raw, "原因": f"底層運算當機: {e}"})
                continue

    win_rate = (win_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0
    top_demon = pd.Series(demons).mode()[0] if demons else "無"
    p_color = _safe_color(COLORS, "red", "#D64B4B") if total_pnl > 0 else _safe_color(COLORS, "green", "#00875A")

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
            st.markdown(
                f"<div style='color:{COLORS['subtext']}; font-size:13px; margin-bottom:16px;'>以下分析基於你的 <b style='color:{COLORS['text']}'>{len(closed_stat)}</b> 筆平倉紀錄，協助系統認識你。</div>",
                unsafe_allow_html=True,
            )
            pcol1, pcol2 = st.columns(2)

            with pcol1:
                st.markdown(f"<b style='color:{COLORS['text']}'>📅 持倉天數 vs 勝率</b>", unsafe_allow_html=True)

                def day_bucket(d):
                    if d <= 2:
                        return "1-2天 (隔日沖)"
                    if d <= 5:
                        return "3-5天 (短線甜蜜點)"
                    if d <= 10:
                        return "6-10天 (短波段)"
                    return "11天以上"

                if not closed_stat.empty:
                    closed_stat["天數區間"] = closed_stat["持有天數_num"].apply(day_bucket)
                    day_grp = closed_stat.groupby("天數區間").apply(
                        lambda x: pd.Series({
                            "筆數": len(x),
                            "勝率(%)": (x["報酬率_num"] > 0).mean() * 100,
                            "平均報酬(%)": x["報酬率_num"].mean(),
                        })
                    ).reset_index()
                    order = ["1-2天 (隔日沖)", "3-5天 (短線甜蜜點)", "6-10天 (短波段)", "11天以上"]
                    day_grp["排序"] = day_grp["天數區間"].apply(lambda x: order.index(x) if x in order else 99)
                    day_grp = day_grp.sort_values("排序").drop(columns=["排序"])

                    for _, row_g in day_grp.iterrows():
                        wr, avg_r, cnt = row_g["勝率(%)"], row_g["平均報酬(%)"], int(row_g["筆數"])
                        bar_color = COLORS["green"] if wr >= 70 else (COLORS["primary"] if wr >= 50 else COLORS["red"])
                        st.markdown(
                            f"<div style='margin-bottom:10px;'><div style='display:flex; justify-content:space-between; font-size:13px;'><span style='color:{COLORS['text']}'>{row_g['天數區間']}</span><span style='color:{bar_color}; font-weight:bold;'>{wr:.0f}% ({cnt}筆)</span></div><div style='background:{COLORS['border']}; border-radius:4px; height:8px; margin-top:4px;'><div style='background:{bar_color}; width:{min(wr,100):.0f}%; height:8px; border-radius:4px;'></div></div><div style='font-size:11px; color:{COLORS['subtext']}; margin-top:2px;'>平均報酬 {avg_r:+.2f}%</div></div>",
                            unsafe_allow_html=True,
                        )

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
                    st.markdown(
                        f"<div style='background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-radius:8px; padding:14px;'><div style='font-size:12px; color:{COLORS['subtext']}; margin-bottom:8px;'>基於你的 {len(closed_stat)} 筆真實交易</div><div style='display:flex; justify-content:space-between; margin-bottom:6px;'><span style='color:{COLORS['subtext']}; font-size:13px;'>真實勝率</span><span style='color:{COLORS['text']}; font-weight:bold;'>{p_win*100:.1f}%</span></div><div style='display:flex; justify-content:space-between; margin-bottom:6px;'><span style='color:{COLORS['subtext']}; font-size:13px;'>平均盈虧比</span><span style='color:{COLORS['text']}; font-weight:bold;'>1 : {b_ratio:.2f}</span></div><div style='display:flex; justify-content:space-between; margin-bottom:6px;'><span style='color:{COLORS['subtext']}; font-size:13px;'>Full Kelly</span><span style='color:{COLORS['primary']};'>{kelly_full*100:.1f}%</span></div><div style='display:flex; justify-content:space-between; padding-top:8px; border-top:1px solid {COLORS['border']};'><span style='color:{COLORS['text']}; font-weight:bold; font-size:14px;'>建議單筆倉位 (半Kelly)</span><span style='color:{kelly_color}; font-weight:bold; font-size:18px;'>{kelly_half*100:.1f}%</span></div><div style='font-size:11px; color:{COLORS['subtext']}; margin-top:6px;'>半Kelly為保守安全值，Full Kelly風險過高不建議直接使用</div></div>",
                        unsafe_allow_html=True,
                    )
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
                    st.markdown(
                        f"<div style='margin-bottom:8px;'><div style='display:flex; justify-content:space-between; font-size:13px;'><span style='color:{COLORS['text']}'>{dm}</span><span style='color:{dm_color}; font-weight:bold;'>{cnt}次 ({pct:.0f}%)</span></div><div style='background:{COLORS['border']}; border-radius:4px; height:6px; margin-top:3px;'><div style='background:{dm_color}; width:{pct:.0f}%; height:6px; border-radius:4px;'></div></div></div>",
                        unsafe_allow_html=True,
                    )

    # ===================================================
    # 🧬 AAR 進階分析：產業 × 戰術 × 心魔
    # ===================================================
    if results:
        with st.expander("🧬 產業 × 戰術 × 心魔分析", expanded=True):
            render_context_insights(pd.DataFrame(results), COLORS)

    # ===================================================
    # 📌 指標卡片區：用同一個 grid，避免兩排卡片黏在一起
    # ===================================================
    missed_total = god_total_pnl - total_pnl
    capture_rate = (total_pnl / god_total_pnl * 100) if god_total_pnl > 0 else 0
    red = _safe_color(COLORS, "red", "#D64B4B")
    green = _safe_color(COLORS, "green", "#00875A")
    primary = _safe_color(COLORS, "primary", "#A98565")
    accent = _safe_color(COLORS, "accent", "#D99A2B")
    bluegray = "#78909C"

    cards = [
        _metric_card_html("已平倉總淨利", _money(total_pnl), primary, COLORS, value_color=p_color),
        _metric_card_html("實戰勝率", f"{win_rate:.1f}%", bluegray, COLORS),
        _metric_card_html("最痛的賣飛", max_missed_stock if max_missed_stock else "無", red, COLORS),
        _metric_card_html("最大心魔", top_demon, green, COLORS),
        _metric_card_html("🧙 神仙模式", _money(god_total_pnl), primary, COLORS, sub=f"已平倉 {god_trade_count} 筆理論最高點"),
        _metric_card_html("📉 少賺空間", _money(missed_total), red if missed_total > 0 else green, COLORS, value_color=red if missed_total > 0 else green),
        _metric_card_html("🎯 獲利捕捉率", f"{capture_rate:.1f}%", bluegray, COLORS, sub="實際淨利 ÷ 神仙最大淨利"),
        _metric_card_html("👑 最強買點", god_best_stock if god_best_stock else "無", accent, COLORS),
    ]
    _render_metric_grid(cards, COLORS)

    # ===================================================
    # 🧠 AAR 戰術糾錯中心：融合「自動糾錯」與「行為建議」
    # 只保留一張卡，避免 AAR 區重複提示同一件事。
    # ===================================================
    avg_missed_k = float(np.mean(missed_k_records)) if missed_k_records else 0
    avg_missed_money = float(np.mean(missed_money_records)) if missed_money_records else 0
    demon_text = " ".join([str(x) for x in demons])
    loss_hint_count = sum(1 for x in demons if any(k in str(x) for k in ["凹", "停損", "認賠", "破線", "死抱", "虧"]))
    chase_hint_count = sum(1 for x in demons if any(k in str(x) for k in ["追高", "開高", "跳空", "急拉"]))
    panic_hint_count = sum(1 for x in demons if any(k in str(x) for k in ["恐慌", "恐高", "怕", "洗出去"]))

    if god_total_pnl > 0 and capture_rate < 30:
        correction_title = "主要問題：出場太早，獲利捕捉率偏低"
        evidence = f"獲利捕捉率僅 {capture_rate:.1f}%，實際淨利 {_money(total_pnl)}，神仙模式理論可達 {_money(god_total_pnl)}。"
        command = "S/A 級獲利單不要一次清空；達 +5～6% 先出半，剩餘部位守 M5，跌破 M5 且站不回再撤。"
        card_color = COLORS["primary"]
    elif "賣飛" in str(top_demon) or missed_k_records:
        correction_title = "主要問題：賣飛仍是最大改善空間"
        evidence = f"{top_demon} 是目前最明顯標籤；{('賣飛高點平均出現在賣後第 %.1f 根K，平均少賺約 %,.0f 元。' % (avg_missed_k, avg_missed_money)) if missed_k_records else '賣飛樣本仍在累積中。'}"
        command = "把『全部停利』改成『半倉停利＋半倉追蹤』；只要趨勢未破 M5 / M10，就讓剩餘部位繼續跑。"
        card_color = COLORS["accent"]
    elif chase_hint_count >= 2:
        correction_title = "主要問題：追高 / 跳空急拉風險偏高"
        evidence = f"近期 AAR 約 {chase_hint_count} 筆帶有追高、開高或急拉相關標籤。"
        command = "跳空 >4.5% 直接列禁追；若真的想做，只允許等回踩 M5 或 13:00 後重新站穩。"
        card_color = COLORS["red"]
    elif loss_hint_count >= 2:
        correction_title = "主要問題：虧損擴大或破線處理偏慢"
        evidence = f"近期 AAR 約 {loss_hint_count} 筆帶有凹單、停損、認賠或破線相關標籤。"
        command = "跌破 M10 或原定停損線先降倉，不攤平弱股；救援單只能等反抽，不再追加風險。"
        card_color = COLORS["red"]
    elif panic_hint_count >= 2 or "恐慌" in str(top_demon):
        correction_title = "主要問題：回檔時容易情緒出場"
        evidence = f"近期 AAR 約 {panic_hint_count} 筆帶有恐慌、恐高或洗出場相關標籤。"
        command = "虧損單守紀律，但獲利單回測 M5 不等於轉弱；真正破 M10 或 ATR 底線再執行撤退。"
        card_color = COLORS["accent"]
    else:
        correction_title = "目前行為穩定：維持紀律，避免新增太多規則"
        evidence = f"已平倉 {total_closed_trades} 筆、勝率 {win_rate:.1f}%，目前沒有單一心魔明顯過熱。"
        command = "下一步不是加規則，而是固定照 SOP：S/A 分批停利、B 級低接、弱股破線處理。"
        card_color = COLORS["green"]

    # 用 Streamlit 原生標題先固定顯示，避免 HTML 標題被主題或舊快取吃掉。
    st.markdown("#### 🧠 AAR 戰術糾錯中心")
    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {card_color}; border-radius:10px; padding:14px 16px; margin: 8px 0 16px 0;">
        <div style="font-size:15px; font-weight:900; color:{COLORS['text']}; margin-bottom:6px;">{correction_title}</div>
        <div style="font-size:13px; line-height:1.6; color:{COLORS['subtext']}; margin-bottom:5px;"><b>證據：</b>{evidence}</div>
        <div style="font-size:13.5px; line-height:1.65; color:{COLORS['text']};"><b>下一次修正指令：</b>{command}</div>
    </div>
    """, unsafe_allow_html=True)

    if skipped_rows:
        with st.expander(f"⚠️ 系統跳過了 {len(skipped_rows)} 筆格式異常的資料，點擊查看詳細原因", expanded=False):
            st.dataframe(pd.DataFrame(skipped_rows), use_container_width=True)

    if results:
        res_df = pd.DataFrame(results)

        def grade_text_color(val):
            if "S級" in str(val):
                return COLORS["primary"]
            if "C級" in str(val):
                return COLORS["green"]
            if "B級" in str(val):
                return COLORS["accent"]
            if "A級" in str(val):
                return COLORS["red"]
            return COLORS["subtext"]

        def pnl_text_color(val):
            try:
                v = float(val)
                if v > 0:
                    return COLORS["red"]
                if v < 0:
                    return COLORS["green"]
                return COLORS["text"]
            except Exception:
                return COLORS["text"]

        table_rows = ""
        for _, r in res_df.iterrows():
            code = html.escape(str(r.get("代號", "")))
            name = html.escape(str(r.get("名稱", "")))
            detail = html.escape(str(r.get("診斷詳情", "")))
            grade = html.escape(str(r.get("評級", "")))
            held = html.escape(str(r.get("持有天數", "")))
            roi_raw = r.get("報酬率(%)", 0)
            pnl_raw = r.get("淨利", 0)
            roi = html.escape(_roi(roi_raw))
            pnl = html.escape(_money(pnl_raw))
            table_rows += f"""
            <tr>
                <td class="aar-code">{code}</td>
                <td class="aar-name">{name}</td>
                <td class="aar-detail">{detail}</td>
                <td class="aar-grade" style="color:{grade_text_color(grade)};">{grade}</td>
                <td class="aar-days">{held}</td>
                <td class="aar-roi" style="color:{pnl_text_color(roi_raw)};">{roi}</td>
                <td class="aar-pnl" style="color:{pnl_text_color(pnl_raw)};">{pnl}</td>
            </tr>
            """

        table_height = 560
        aar_table_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="UTF-8">
        <style>
            html, body {{ margin:0; padding:0; background:transparent; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; color:{COLORS['text']}; }}
            .aar-wrap {{ width:100%; height:560px; overflow:auto; border:1px solid {COLORS['border']}; border-radius:8px; background:{COLORS['card']}; }}
            table.aar-table {{ width:100%; min-width:760px; border-collapse:collapse; table-layout:fixed; font-size:13px; background:{COLORS['card']}; color:{COLORS['text']}; }}
            table.aar-table th {{ position:sticky; top:0; z-index:5; background:{COLORS['card']}; color:{COLORS['subtext']}; font-weight:700; padding:8px 7px; border-bottom:1px solid {COLORS['border']}; border-right:1px solid {COLORS['border']}; text-align:left; white-space:nowrap; box-shadow:0 1px 0 {COLORS['border']}; }}
            table.aar-table td {{ padding:8px 7px; border-bottom:1px solid {COLORS['border']}; border-right:1px solid {COLORS['border']}; vertical-align:top; color:{COLORS['text']}; }}
            table.aar-table tr:last-child td {{ border-bottom:none; }}
            .aar-code {{ width:7%; white-space:nowrap; }}
            .aar-name {{ width:10%; white-space:normal !important; word-break:break-all; overflow-wrap:anywhere; line-height:1.35; }}
            .aar-detail {{ width:52%; text-align:left; white-space:normal !important; word-break:break-word; overflow-wrap:anywhere; line-height:1.48; }}
            .aar-grade {{ width:8%; white-space:normal; font-weight:700; }}
            .aar-days {{ width:7%; white-space:nowrap; text-align:right; }}
            .aar-roi {{ width:8%; white-space:nowrap; text-align:right; font-weight:700; }}
            .aar-pnl {{ width:8%; white-space:nowrap; text-align:right; font-weight:700; }}
            @media (max-width:900px) {{ table.aar-table {{ min-width:820px; }} .aar-detail {{ width:50%; }} }}
        </style>
        </head>
        <body>
            <div class="aar-wrap">
                <table class="aar-table">
                    <thead>
                        <tr>
                            <th class="aar-code">代號</th><th class="aar-name">名稱</th><th class="aar-detail">診斷詳情</th><th class="aar-grade">評級</th>
                            <th class="aar-days">持有天數</th><th class="aar-roi">報酬率(%)</th><th class="aar-pnl">淨利</th>
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
