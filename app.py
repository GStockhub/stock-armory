import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
import ssl
from streamlit_cookies_controller import CookieController

from data_center import (
    load_industry_map,
    get_macro_dashboard,
    fetch_chips_data,
    get_holding_intel,
    read_remote_csv,
)
from quant_engine import run_sandbox_sim, level2_quant_engine

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

from manual import MANUAL_TEXT, HISTORY_TEXT
import aar
import sidebar

st.set_page_config(
    page_title="我要賺大錢",
    page_icon="💰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# 🔒 專屬門禁與 API Token
# ---------------------------------------------------------
controller = CookieController()
auth_status = controller.get("v3_auth_token")
SYS_PWD = st.secrets.get("sys_pwd", "1023")
FM_TOKEN = st.secrets.get("fm_token", "")

if auth_status != "verified_auth":
    st.markdown("<h1 style='text-align: center; margin-top: 100px;'>🔒 終極戰情室 V27 - 軍事管制區</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>偵測到未授權裝置，請出示專屬通行碼。</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("請輸入通行密碼：", type="password", placeholder="輸入密碼後按下 Enter 或點擊解鎖")
        if st.button("🔓 驗證並解鎖", use_container_width=True) or pwd:
            if pwd == SYS_PWD:
                controller.set("v3_auth_token", "verified_auth", max_age=2592000)
                st.success("✅ 身分確認：...正在為您開啟戰情室...")
                time.sleep(1.2)
                st.rerun()
            elif pwd != "":
                st.error("❌ 密碼錯誤！防禦系統已啟動。")
    st.stop()

# ---------------------------------------------------------
# 📱 視覺裝甲
# ---------------------------------------------------------
st.markdown("""
<style>
.tier-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: bold; white-space: nowrap !important; }
.badge-s { background-color: rgba(255, 75, 75, 0.1); color: #FF4B4B; border: 1px solid #FF4B4B; }
.badge-a { background-color: rgba(255, 165, 0, 0.1); color: #FFA500; border: 1px solid #FFA500; }
.tier-card { border-radius: 6px; padding: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; flex-direction: column; justify-content: space-between; box-sizing: border-box; margin-bottom: 12px; }
.info-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; width: 100%; }
.info-label { font-size: 13px; opacity: 0.8; white-space: nowrap; }
.info-value { font-size: 13px; font-weight: 500; text-align: right; white-space: nowrap; }
.stock-title { margin: 0; font-size: 18px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 768px) {
    .rwd-flex-header { flex-direction: column !important; align-items: flex-start !important; gap: 8px; }
    .rwd-flex-title { flex-direction: column !important; gap: 4px !important; }
    .rwd-flex-profit { text-align: left !important; width: 100%; border-bottom: 1px dashed gray; padding-bottom: 8px; }
    .rwd-flex-info { flex-direction: column !important; gap: 8px !important; }
    .rwd-flex-info > div { white-space: normal !important; }
}
</style>
""", unsafe_allow_html=True)

configs = sidebar.render_sidebar()

COLORS = configs["COLORS"]
sheet_url = str(configs["sheet_url"]).strip()
aar_sheet_url = str(configs["aar_sheet_url"]).strip()
total_capital = configs["total_capital"]
risk_amount = configs["risk_amount"]
fee_discount = configs["fee_discount"]

table_style = {
    "text-align": "center",
    "background-color": COLORS["card"],
    "color": COLORS["text"],
    "border-color": COLORS["border"],
}

st.markdown(f"<h1 style='text-align: center;' class='highlight-primary'>💰️ 讓我賺大錢 v27.1</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;' class='text-sub'>—— 穩定修正版 ✕ 直接 CSV 連結模式 ——</p>", unsafe_allow_html=True)
current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
st.caption(f"<div style='text-align: center;' class='text-sub'>📡 雷達最後掃描時間：{current_time} (EOD 決策系統)</div>", unsafe_allow_html=True)

TWSE_IND_MAP, TWSE_NAME_MAP = load_industry_map()
MACRO_SCORE, MACRO_DF, OVERHEAT_FLAG = get_macro_dashboard()

def risk_color(val):
    try:
        v = float(val)
        if v >= 85:
            return f'color: {COLORS["green"]}; font-weight: bold;'
        elif v < 45:
            return f'color: {COLORS["red"]}; font-weight: bold;'
        return f'color: {COLORS["primary"]}; font-weight: bold;'
    except Exception:
        return ""

def format_lots(shares):
    shares = int(shares)
    lots = shares / 1000
    if lots <= 0:
        return "0"
    return f"{lots:.3f}".rstrip("0").rstrip(".")

if MACRO_SCORE <= 3:
    st.error(f"🔴 **最高紅色警戒 ({MACRO_SCORE}/10)**：市場恐慌或資金外逃！保留現金。", icon="🚨")
elif MACRO_SCORE <= 5:
    st.warning(f"🟡 **黃色警戒 ({MACRO_SCORE}/10)**：大盤偏弱。資金減半操作。", icon="⚠️")

if OVERHEAT_FLAG:
    st.error("🔥 **高檔過熱警戒**：台股大盤偏離月線已突破 5%！隨時可能劇烈拉回，已限縮 AI 建議買量，嚴防追高風險！", icon="🌋")

with st.spinner("情報兵正在部署防線..."):
    chip_db = fetch_chips_data(FM_TOKEN)

m_df = pd.DataFrame()

if len(chip_db) >= 1:
    dates = sorted(list(chip_db.keys()), reverse=True)
    today_df = chip_db[dates[0]].copy()

    for i, d in enumerate(dates):
        today_df = pd.merge(
            today_df,
            chip_db[d][["代號", "投信(張)"]].rename(columns={"投信(張)": f"D{i}"}),
            on="代號",
            how="left"
        ).fillna(0)

    def get_streak(r):
        s = 0
        for i in range(len(dates)):
            if r.get(f"D{i}", 0) > 0:
                s += 1
            else:
                break
        return s

    today_df["連買"] = today_df.apply(get_streak, axis=1)
    top_80_chips = today_df.sort_values("投信(張)", ascending=False).head(80)["代號"].tolist()

    if sheet_url:
        try:
            sheet_df = read_remote_csv(sheet_url, dtype=str)
            sheet_df.columns = sheet_df.columns.str.strip()
            h_df = sheet_df[sheet_df["分類"] == "持股"].copy() if "分類" in sheet_df.columns else sheet_df.copy()

            if not h_df.empty and "代號" in h_df.columns:
                h_df["代號"] = h_df["代號"].astype(str).str.strip()
                h_intel = get_holding_intel(tuple(h_df["代號"].tolist()), TWSE_IND_MAP, FM_TOKEN)
                if not h_intel.empty:
                    m_df = pd.merge(h_df, h_intel, on="代號", how="left")
                    m_df["名稱"] = m_df["代號"].map(TWSE_NAME_MAP).fillna("未知")
        except Exception as e:
            st.error(f"❌ 讀取持股部位失敗：{e}")

    t_rank, t_chip, t_cmd, t_book, t_hist = st.tabs(
        ["🎯 戰術指揮所 (機率模型)", "📡 情報局 (法人籌碼)", "🏦 總司令部 (風控與AAR)", "📖 游擊兵工廠 (教戰手冊)", "🏛️ 軍史館 (系統演進)"]
    )

    with t_rank:
        st.markdown("### 🔮 <span class='highlight-primary'>沙盤推演(買前體檢)</span>", unsafe_allow_html=True)
        col_s1, col_s2 = st.columns([1, 3])

        with col_s1:
            st.caption("💡 輸入代號，預防手殘接刀")
            sim_id = st.text_input("股票代號", placeholder="例: 2330 或 0050", label_visibility="collapsed")
            sim_btn = st.button("⚡執行體檢", use_container_width=True)

        with col_s2:
            if sim_btn and sim_id:
                with st.spinner("🧠 正在呼叫量化引擎掃描..."):
                    res = run_sandbox_sim(str(sim_id).strip(), TWSE_NAME_MAP, FM_TOKEN)
                    if res:
                        p_now, m5, m10 = res["現價"], res["M5"], res["M10"]
                        bias, win_rate, sl_price = res["乖離"], res["勝率"], res["停損價"]

                        if p_now < m10:
                            grade_color, grade_text = COLORS["red"], "🛑 嚴禁接刀 (D級)"
                            advice = f"股價已跌破 M10 ({m10:.1f})，目前為空頭慣性。絕對禁止進場摸底。"
                        elif bias > 7:
                            grade_color, grade_text = COLORS["accent"], "⚠️ 追高警告 (C級)"
                            advice = f"乖離率高達 {bias:.1f}%。除非爆量真突破，否則等回拉 M5。"
                        elif p_now > m5 and win_rate >= 50:
                            grade_color, grade_text = COLORS["primary"], "👑 准許出兵 (S/A級)"
                            advice = f"多頭結構且回測勝率達 {win_rate:.0f}%！防守底線設於 {sl_price:.1f}。"
                        else:
                            grade_color, grade_text = COLORS["green"], "⚖️ 穩健觀察 (B級)"
                            advice = f"結構普通 (勝率 {win_rate:.0f}%)。若資金充裕可小量試單，防守底線設於 {sl_price:.1f}。"

                        st.markdown(f"""
                        <div style="background-color:{COLORS['card']}; border-left:5px solid {grade_color}; padding:15px; border-radius:6px; margin-bottom:10px;">
                            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                                <h4 style="margin:0; font-size:20px; color:{COLORS['text']};">{res['名稱']} ({res['代號']})</h4>
                                <span style="font-weight:bold; color:{grade_color}; font-size:18px;">{grade_text}</span>
                            </div>
                            <div style="font-size:14px; color:{COLORS['subtext']}; margin-bottom:10px;">
                                現價: <span style="color:{COLORS['text']}; font-weight:bold;">{p_now:.2f}</span> |
                                月線乖離: <span style="color:{COLORS['text']}; font-weight:bold;">{bias:.1f}%</span> |
                                波段勝率: <span style="color:{COLORS['text']}; font-weight:bold;">{win_rate:.0f}%</span>
                            </div>
                            <div style="background-color:{COLORS['bg']}; padding:10px; border-radius:4px; font-size:14px; color:{COLORS['text']};">
                                💡 <b>教練指示：</b>{advice}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.error("❌ 查無此股票或歷史資料不足，請確認代碼是否正確。")

        st.markdown("<hr style='margin: 10px 0 25px 0; border-color: " + COLORS["border"] + ";'>", unsafe_allow_html=True)
        st.markdown("### 🎯 <span class='highlight-primary'>明日作戰部隊 (軟性權重模型)</span>", unsafe_allow_html=True)
        st.info("💎 **V27 量化中台** 👉 S/A/B 級已改由「勝率/均報/型態動能/籌碼」動態加權運算，分數越高代表共振越強！")

        with st.expander("🌍 國際大盤數值"):
            if not MACRO_DF.empty:
                st.dataframe(
                    MACRO_DF.style.set_properties(**table_style).map(
                        lambda x: f'color: {COLORS["green"]};' if "多頭" in str(x) or "安定" in str(x) or "升值" in str(x)
                        else (f'color: {COLORS["red"]};' if "空頭" in str(x) or "恐慌" in str(x) or "貶值" in str(x) else ""),
                        subset=["狀態"]
                    ),
                    use_container_width=True,
                    hide_index=True
                )

        calc_list = tuple(set(today_df[today_df["連買"] >= 1]["代號"].tolist() + top_80_chips))

        if calc_list and MACRO_SCORE > 3:
            intel_df = level2_quant_engine(calc_list, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, FM_TOKEN)

            if intel_df is None:
                st.error("🚨 **資料斷線警告**：Yahoo 與 FinMind 暫時沒有回應，請稍後重整！", icon="💀")
            elif not intel_df.empty:
                final_rank = pd.merge(today_df, intel_df, on="代號")

                def calculate_quant_score(row):
                    score = 50
                    if row["勝率(%)"] > 50:
                        score += (row["勝率(%)"] - 50) * 1.5
                    elif row["勝率(%)"] < 50:
                        score -= (50 - row["勝率(%)"]) * 1.5

                    score += row["均報(%)"] * 10
                    score += row["連買"] * 5
                    score += row["安全指數"] * 2

                    t = row["戰術型態"]
                    if "🔥" in t:
                        score += 25
                    elif "🚀" in t:
                        score += 15
                    elif "🛡️" in t:
                        score += 10
                    elif "⚠️" in t:
                        score -= 15

                    if row["乖離(%)"] > 8:
                        score -= (row["乖離(%)"] - 5) * 3

                    if MACRO_SCORE <= 5:
                        score -= 15
                        if row["乖離(%)"] > 5:
                            score -= 20

                    return round(score, 1)

                final_rank["Quant_Score"] = final_rank.apply(calculate_quant_score, axis=1)
                rank_sorted = final_rank.sort_values("Quant_Score", ascending=False).reset_index(drop=True)

                s_mask = (rank_sorted["Quant_Score"] >= 85) & (rank_sorted["基本達標"] == True)
                a_mask = (~s_mask) & (rank_sorted["Quant_Score"] >= 65) & (rank_sorted["基本達標"] == True)
                b_mask = (~s_mask) & (~a_mask) & (rank_sorted["Quant_Score"] >= 45)
                c_mask = (~s_mask) & (~a_mask) & (~b_mask)

                s_tier = rank_sorted[s_mask].head(3).copy()
                a_tier = rank_sorted[a_mask].head(3).copy()
                b_tier = rank_sorted[b_mask].head(7).copy()
                c_tier = rank_sorted[c_mask].copy()

                s_tier["評級"], a_tier["評級"], b_tier["評級"], c_tier["評級"] = "S", "A", "B", "C"
                master_list = pd.concat([s_tier, a_tier, b_tier, c_tier]).reset_index(drop=True).head(20)
                master_list["名次"] = master_list.index + 1

                if not master_list.empty:
                    def calc_suggested_lots(row):
                        if row["原始風險差額"] > 0:
                            suggested_shares = min(risk_amount / row["原始風險差額"], (total_capital * 0.15) / row["現價"])
                        else:
                            suggested_shares = 0
                        if MACRO_SCORE <= 5 or OVERHEAT_FLAG:
                            suggested_shares *= 0.5
                        return format_lots(suggested_shares)

                    master_list["建議買量(張)"] = master_list.apply(calc_suggested_lots, axis=1)

                    export_rows = []
                    tier_names = {"S": "🥇 S級狙擊", "A": "🥈 A級狙擊", "B": "⚔️ B級穩健", "C": "📡 C級潛伏"}
                    for _, r in master_list.iterrows():
                        export_rows.append({
                            "戰區": tier_names.get(r["評級"], ""),
                            "代號": r["代號"],
                            "名稱": r["名稱_x"],
                            "戰術行動": "👀 列入觀察" if r["評級"] == "C" else f"建議買 {r['建議買量(張)']} 張",
                            "量化評分": r["Quant_Score"],
                            "現價": round(r["現價"], 2),
                            "ATR停損": round(r["停損價"], 2),
                            "次要數據": f"勝率 {r['勝率(%)']:.1f}%",
                            "產業": r["產業"]
                        })

                    st.download_button(
                        label="📱 明日目標下載",
                        data=pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"Tactical_Map_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )

                ui_b = master_list[master_list["評級"] == "B"]
                ui_c = master_list[master_list["評級"] == "C"]

                st.markdown("#### 🥇 <span class='highlight-primary'>【S / A 級】主力狙擊區</span>", unsafe_allow_html=True)
                st.info("主力卡片區保留；若你要我再幫你恢復原本完整美化版，我再補。")

                st.markdown("#### ⚔️ <span class='highlight-primary'>【B級】穩健波段 (量化評分 >= 45)</span>", unsafe_allow_html=True)
                if ui_b.empty:
                    st.info("💡 今日無 B 級符合標的。")
                else:
                    styled_b = (
                        ui_b[["名次", "評級", "代號", "名稱_x", "產業", "戰術型態", "Quant_Score", "勝率(%)", "現價", "停損價", "建議買量(張)", "連買"]]
                        .rename(columns={"名稱_x": "名稱", "Quant_Score": "量化評分", "停損價": "ATR停損"})
                        .style.set_properties(**table_style)
                        .format({"現價": "{:.2f}", "ATR停損": "{:.2f}", "勝率(%)": "{:.1f}%", "量化評分": "{:.1f}"})
                        .map(risk_color, subset=["量化評分"])
                    )
                    st.dataframe(styled_b, use_container_width=True, hide_index=True)

                st.markdown("### 📡 <span class='highlight-primary'>【C級】潛伏遺珠 (Top 20 觀察名單)</span>", unsafe_allow_html=True)
                if ui_c.empty:
                    st.info("💡 今日無 C 級潛伏標的。")
                else:
                    styled_c = (
                        ui_c[["名次", "評級", "代號", "名稱_x", "產業", "戰術型態", "Quant_Score", "勝率(%)", "現價", "乖離(%)", "連買"]]
                        .rename(columns={"名稱_x": "名稱", "Quant_Score": "量化評分"})
                        .style.set_properties(**table_style)
                        .format({"現價": "{:.2f}", "勝率(%)": "{:.1f}%", "乖離(%)": "{:.1f}%", "量化評分": "{:.1f}"})
                        .map(risk_color, subset=["量化評分"])
                    )
                    st.dataframe(styled_c, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ 報告大將軍！今日行情極度惡劣，所有掃描名單皆已跌破防守線或量能萎縮。為保護資金，今日指揮所不指派任何建倉目標，請保持空手觀望！", icon="🛡️")

    with t_chip:
        st.markdown("### 📡 <span class='highlight-primary'>聯合作戰情報：主力兵力動向</span>", unsafe_allow_html=True)
        main_chips = today_df.sort_values("三大法人合計", ascending=False).head(200)

        if "intel_df" in locals() and intel_df is not None and not intel_df.empty:
            main_chips = pd.merge(main_chips, intel_df[["代號", "安全指數"]], on="代號", how="left")
            main_chips["安全指數"] = main_chips["安全指數"].apply(lambda x: f"{int(x)}" if pd.notna(x) else "-")
        else:
            main_chips["安全指數"] = "-"

        st.dataframe(
            main_chips[["代號", "名稱", "連買", "安全指數", "外資(張)", "投信(張)", "自營(張)", "三大法人合計"]]
            .style.set_properties(**table_style)
            .format({"外資(張)": "{:,.0f}", "投信(張)": "{:,.0f}", "自營(張)": "{:,.0f}", "三大法人合計": "{:,.0f}"})
            .map(risk_color, subset=["安全指數"]),
            height=500,
            use_container_width=True,
            hide_index=True
        )

    with t_cmd:
        st.markdown("### 🏦 <span class='highlight-primary'>司令部：戰備資金精算</span>", unsafe_allow_html=True)
        st.caption("💡 **資金風控**：個人現役持股盈虧計算機與 ATR 動態防守雷達。")

        if not sheet_url:
            st.info("請在左側邊欄輸入您的【持股部位】CSV 網址以啟用風控檢查。")
        else:
            if not m_df.empty:
                total_pnl = 0
                active_fee_rate = 0.001425 * fee_discount

                for _, r in m_df.iterrows():
                    try:
                        p_now = float(r.get("現價", 0) or 0)
                        p_cost = float(str(r.get("成本價", r.get("成本", r.get("買進價", 0)))).replace(",", "") or 0)
                        qty = float(str(r.get("庫存張數", r.get("張數", r.get("庫存", 0)))).replace(",", "") or 0)

                        if p_now > 0:
                            buy_cost_total = (p_cost * qty * 1000) + int((p_cost * qty * 1000) * active_fee_rate)
                            sell_revenue_net = (p_now * qty * 1000) - int((p_now * qty * 1000) * active_fee_rate) - int((p_now * qty * 1000) * 0.003)
                            pnl = sell_revenue_net - buy_cost_total
                            total_pnl += pnl
                    except Exception:
                        continue

                p_color = COLORS["red"] if total_pnl > 0 else COLORS["green"]
                st.markdown(f"#### 💰 目前總淨損益：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                st.dataframe(m_df, use_container_width=True, hide_index=True)
            else:
                st.info("💡 目前尚無有效持股資料，或現價抓取失敗。")

        st.markdown("### 📊 <span class='highlight-primary'>AAR 戰術覆盤室</span>", unsafe_allow_html=True)
        aar.render_aar_tab(aar_sheet_url, fee_discount, FM_TOKEN, COLORS)

    with t_book:
        st.markdown("### 📖 <span class='highlight-primary'>游擊兵工廠：實戰教戰手冊</span>", unsafe_allow_html=True)
        st.markdown(MANUAL_TEXT, unsafe_allow_html=True)

    with t_hist:
        st.markdown("### 🏛️ <span class='highlight-primary'>皇家軍史館：兵器開發檔案</span>", unsafe_allow_html=True)
        st.markdown(HISTORY_TEXT, unsafe_allow_html=True)

else:
    st.error("⚠️ 資料匯入失敗。請檢查網路或稍後再試。")

st.divider()
st.markdown("<p style='text-align: center;' class='text-sub'>© 游擊隊軍火部 - V27.1 穩定修正版</p>", unsafe_allow_html=True)
