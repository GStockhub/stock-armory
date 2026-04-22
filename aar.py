import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from data_center import read_remote_csv, safe_download


def parse_tw_date(d_str):
    try:
        d_str = str(d_str).strip().replace("/", "-").replace(".", "-")
        if not d_str:
            return pd.NaT
        parts = d_str.split("-")
        if len(parts) == 3:
            y = int(parts[0])
            if y < 1911:
                y += 1911
            return pd.to_datetime(f"{y}-{parts[1]}-{parts[2]}")
        return pd.to_datetime(d_str)
    except Exception:
        return pd.NaT


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

    df.columns = df.columns.str.strip()

    required_cols = ["代號", "買進日期", "買進價", "張數"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"AAR 缺少必要欄位：{', '.join(missing)}")
        return

    results = []
    total_pnl = 0.0

    with st.spinner("🧠 AAR 教練正在覆盤中..."):
        for _, row in df.iterrows():
            try:
                sid = str(row.get("代號", "")).strip()
                if not sid:
                    continue

                buy_date = parse_tw_date(row.get("買進日期", ""))
                buy_price = float(str(row.get("買進價", "0")).replace(",", ""))
                shares = float(str(row.get("張數", "0")).replace(",", ""))

                if pd.isna(buy_date) or buy_price <= 0 or shares <= 0:
                    continue

                sell_date_raw = str(row.get("賣出日期", "")).strip()
                sell_price_raw = str(row.get("賣出價", "")).strip()
                is_sold = sell_date_raw != "" and sell_price_raw != ""

                hist = safe_download(sid, fm_token, period="1y")
                if hist.empty:
                    continue

                latest_price = float(hist["Close"].iloc[-1])
                m5 = float(hist["Close"].rolling(5).mean().iloc[-1])
                m10 = float(hist["Close"].rolling(10).mean().iloc[-1])

                if is_sold:
                    sell_date = parse_tw_date(sell_date_raw)
                    sell_price = float(sell_price_raw.replace(",", ""))
                else:
                    sell_date = pd.NaT
                    sell_price = latest_price

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

                if is_sold:
                    total_pnl += pnl

                if latest_price > m5 > m10:
                    structure = "🚀 多頭排列"
                elif latest_price >= m10:
                    structure = "⏳ 守住 M10"
                else:
                    structure = "📉 跌破 M10"

                grade = "⚪ 持股中"
                if is_sold:
                    if roi >= 10:
                        grade = "👑 S級"
                    elif roi > 0:
                        grade = "🥈 A級"
                    elif roi > -5:
                        grade = "⚔️ B級"
                    else:
                        grade = "💀 D級"

                held_days = (sell_date - buy_date).days if is_sold and pd.notna(sell_date) else (datetime.now() - buy_date).days

                results.append({
                    "代號": sid,
                    "評級": grade,
                    "結構": structure,
                    "買進日": buy_date.strftime("%Y-%m-%d"),
                    "賣出日": sell_date.strftime("%Y-%m-%d") if is_sold and pd.notna(sell_date) else "-",
                    "持有天數": held_days,
                    "報酬率": roi,
                    "淨利": pnl,
                })

            except Exception:
                continue

    st.markdown("### 📊 <span class='highlight-primary'>AAR 戰術覆盤室</span>", unsafe_allow_html=True)

    p_color = COLORS["red"] if total_pnl > 0 else COLORS["green"]
    st.markdown(
        f"""
        <div style="background-color:{COLORS['card']}; border-left:5px solid {COLORS['primary']}; padding:15px; border-radius:8px; margin-bottom:15px;">
            <div style="color:{COLORS['subtext']};">已平倉總淨利</div>
            <div style="font-size:28px; font-weight:bold; color:{p_color};">{total_pnl:,.0f} 元</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if results:
        res_df = pd.DataFrame(results)
        styled = (
            res_df.style
            .set_properties(**{
                "text-align": "center",
                "background-color": COLORS["card"],
                "color": COLORS["text"],
                "border-color": COLORS["border"],
            })
            .format({"報酬率": "{:.2f}%", "淨利": "{:,.0f}"})
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.info("AAR 沒有可分析的有效資料。")
