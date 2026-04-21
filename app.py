import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
import ssl
from streamlit_cookies_controller import CookieController

# 👉 V6：載入全新拆分的後勤大腦與雷達模組
from data_center import load_industry_map, get_macro_dashboard, fetch_chips_data, get_holding_intel
from quant_engine import run_sandbox_sim, level2_quant_engine

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError: pass
else: ssl._create_default_https_context = _create_unverified_https_context

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
# 🔒 專屬門禁系統 (st.secrets 資安保險箱)
# ---------------------------------------------------------
controller = CookieController()
auth_status = controller.get('v3_auth_token')
SYS_PWD = st.secrets.get("sys_pwd", "1023")

if auth_status != 'verified_auth':
    st.markdown("<h1 style='text-align: center; margin-top: 100px;'>🔒 終極戰情室 V6 - 軍事管制區</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>偵測到未授權裝置，請出示專屬通行碼。</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("請輸入通行密碼：", type="password", placeholder="輸入密碼後按下 Enter 或點擊解鎖")
        if st.button("🔓 驗證並解鎖", use_container_width=True) or pwd:
            if pwd == SYS_PWD:
                controller.set('v3_auth_token', 'verified_auth', max_age=2592000)
                st.success("✅ 身分確認：...正在為您開啟戰情室...")
                time.sleep(1.5)
                st.rerun()
            elif pwd != "":
                st.error("❌ 密碼錯誤！防禦系統已啟動。")
    st.stop()

# ---------------------------------------------------------
# 📱 注入 RWD 防跑版變形裝甲
# ---------------------------------------------------------
st.markdown("""
<style>
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
sheet_url = configs["sheet_url"]
aar_sheet_url = configs["aar_sheet_url"]
total_capital = configs["total_capital"]
risk_amount = configs["risk_amount"]
fee_discount = configs["fee_discount"]

table_style = {'text-align': 'center', 'background-color': COLORS['card'], 'color': COLORS['text'], 'border-color': COLORS['border']}

st.markdown(f"<h1 style='text-align: center;' class='highlight-primary'>💰️ 讓我賺大錢 v26.0</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;' class='text-sub'>—— 終極番號 ✕ 交易教練 V6 (機構級中台架構) ——</p>", unsafe_allow_html=True)
current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
st.caption(f"<div style='text-align: center;' class='text-sub'>📡 雷達最後掃描時間：{current_time} (EOD 決策系統)</div>", unsafe_allow_html=True)

# 📡 呼叫 Data Center 取得基礎資料
TWSE_IND_MAP, TWSE_NAME_MAP = load_industry_map()
MACRO_SCORE, MACRO_DF = get_macro_dashboard()

def format_lots(shares):
    shares = int(shares)
    lots = shares / 1000
    if lots <= 0: return "0"
    return f"{lots:.3f}".rstrip('0').rstrip('.')

def risk_color(val):
    try:
        v = int(val)
        if v >= 8: return f'color: {COLORS["green"]}; font-weight: bold;'
        elif v <= 3: return f'color: {COLORS["red"]}; font-weight: bold;'
        return f'color: {COLORS["primary"]}; font-weight: bold;'
    except: return ''

if MACRO_SCORE <= 3: st.error(f"🔴 **最高紅色警戒 ({MACRO_SCORE}/10)**：市場恐慌！保留現金。", icon="🚨")
elif MACRO_SCORE <= 5: st.warning(f"🟡 **黃色警戒 ({MACRO_SCORE}/10)**：大盤偏弱。資金減半操作。", icon="⚠️")

with st.spinner('情報兵正在部署防線...'):
    chip_db = fetch_chips_data()

m_df = pd.DataFrame() 

if len(chip_db) >= 1:
    dates = sorted(list(chip_db.keys()), reverse=True)
    today_df = chip_db[dates[0]].copy()
    for i, d in enumerate(dates): today_df = pd.merge(today_df, chip_db[d][['代號', '投信(張)']].rename(columns={'投信(張)': f'D{i}'}), on='代號', how='left').fillna(0)
    def get_streak(r):
        s = 0
        for i in range(len(dates)):
            if r.get(f'D{i}', 0) > 0: s += 1
            else: break
        return s
    today_df['連買'] = today_df.apply(get_streak, axis=1)

    top_80_chips = today_df.sort_values('投信(張)', ascending=False).head(80)['代號'].tolist()

    if sheet_url:
        try:
            sheet_df = pd.read_csv(sheet_url, dtype=str)
            sheet_df.columns = sheet_df.columns.str.strip()
            
            if '分類' in sheet_df.columns:
                h_df = sheet_df[sheet_df['分類'] == '持股'].copy()
            else:
                h_df = sheet_df.copy()
                
            if not h_df.empty and '代號' in h_df.columns:
                h_df['代號'] = h_df['代號'].astype(str).str.strip()
                # 📡 呼叫 Data Center 取得持股現況
                h_intel = get_holding_intel(tuple(h_df['代號'].tolist()), TWSE_IND_MAP)
                if not h_intel.empty:
                    m_df = pd.merge(h_df, h_intel, on='代號', how='left')
                    m_df['名稱'] = m_df['代號'].map(TWSE_NAME_MAP).fillna('未知')
        except Exception as e: st.error(f"❌ 讀取持股部位失敗：{e}")
    
    t_rank, t_chip, t_cmd, t_book, t_hist = st.tabs(["🎯 戰術指揮所 (S/A/B/C)", "📡 情報局 (法人籌碼)", "🏦 總司令部 (風控與AAR)", "📖 游擊兵工廠 (教戰手冊)", "🏛️ 軍史館 (系統演進)"])

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
                    sid_clean = str(sim_id).strip()
                    # 🧠 呼叫 Quant Engine 進行沙盤推演
                    res = run_sandbox_sim(sid_clean, TWSE_NAME_MAP)
                    if res:
                        p_now = res['現價']
                        m5, m10, m20 = res['M5'], res['M10'], res['M20']
                        bias = res['乖離']
                        win_rate = res['勝率']
                        sl_price = res['停損價']

                        if p_now < m10:
                            grade_color = COLORS['red']
                            grade_text = "🛑 嚴禁接刀 (D級)"
                            advice = f"股價已跌破 M10 ({m10:.1f})，目前為空頭慣性。絕對禁止進場摸底，以免被套牢！"
                        elif bias > 7:
                            grade_color = COLORS['accent']
                            grade_text = "⚠️ 追高警告 (C級)"
                            advice = f"乖離率高達 {bias:.1f}%。極易買在短線最高點，除非爆量真突破，否則等回拉 M5。"
                        elif p_now > m5 and win_rate >= 50:
                            grade_color = COLORS['primary']
                            grade_text = "👑 准許出兵 (S/A級)"
                            advice = f"多頭結構且回測勝率達 {win_rate:.0f}%！防守底線嚴格設於 {sl_price:.1f}，可依戰術進場。"
                        else:
                            grade_color = COLORS['green']
                            grade_text = "⚖️ 穩健觀察 (B級)"
                            advice = f"結構普通 (勝率 {win_rate:.0f}%)。若資金充裕可小量試單，防守底線嚴格設於 {sl_price:.1f}。"

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
                        st.error("❌ 查無此股票或歷史資料不足，請確認代號是否正確。")
        st.markdown("<hr style='margin: 10px 0 25px 0; border-color: " + COLORS['border'] + ";'>", unsafe_allow_html=True)

        st.markdown("### 🎯 <span class='highlight-primary'>明日作戰部隊 (EOD 決策系統)</span>", unsafe_allow_html=True)
        st.info("⏱️ **EOD 操盤時鐘** 👉 09:00~09:30 觀察不買 (過濾大跳空) | 09:30 突擊突破股(S/A) | 13:00 佈署回踩股(B)")

        with st.expander("🌍 國際大盤數值"):
            if not MACRO_DF.empty:
                st.dataframe(MACRO_DF.style.set_properties(**table_style).map(lambda x: f'color: {COLORS["green"]};' if '多頭' in str(x) or '安定' in str(x) else (f'color: {COLORS["red"]};' if '空頭' in str(x) or '恐慌' in str(x) else ''), subset=['狀態']), use_container_width=True, hide_index=True)

        pool_ids = today_df[today_df['連買'] >= 1]['代號'].tolist() 
        calc_list = tuple(set(pool_ids + top_80_chips))
        
        if calc_list and MACRO_SCORE > 3: 
            # 🧠 呼叫 Quant Engine 進行大部隊篩選
            intel_df = level2_quant_engine(calc_list, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE)
            
            if intel_df is not None and not intel_df.empty:
                def calc_suggested_lots(row):
                    if row['原始風險差額'] > 0:
                        suggested_shares = min(risk_amount / row['原始風險差額'], (total_capital * 0.15) / row['現價'])
                    else: suggested_shares = 0
                    if MACRO_SCORE <= 5: suggested_shares *= 0.5
                    return format_lots(suggested_shares)
                    
                intel_df['建議買量(張)'] = intel_df.apply(calc_suggested_lots, axis=1)
                final_rank = pd.merge(today_df, intel_df, on='代號')

                final_rank['Score'] = (final_rank['均報(%)']*150 + final_rank['勝率(%)']*15 + final_rank['安全指數']*100 - abs(final_rank['乖離(%)'])*50)
                final_rank.loc[final_rank['今日放量'] == True, 'Score'] += 100 
                rank_sorted = final_rank.sort_values('Score', ascending=False).reset_index(drop=True)
                
                is_strong_breakout = rank_sorted['戰術型態'].isin(["🔥 雙戰術共振", "🚀 S級主升段 (重擊)"])
                
                s_mask = (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] >= 50) & (
                    (is_strong_breakout) | 
                    ((rank_sorted['勝率(%)'] >= 55) & (rank_sorted['均報(%)'] >= 1.5) & (rank_sorted['連買'] >= 2))
                )
                
                a_mask = (~s_mask) & (rank_sorted['基本達標'] == True) & (rank_sorted['勝率(%)'] >= 50) & (rank_sorted['均報(%)'] >= 1.0) & (rank_sorted['連買'] >= 1)
                
                b_mask = (~s_mask) & (~a_mask) & (rank_sorted['現價'] >= rank_sorted['M10']) & (rank_sorted['勝率(%)'] > 50) & (rank_sorted['成交量'] >= 1.5) & (rank_sorted['連買'] >= 1) & (rank_sorted['乖離(%)'] < 10)
                c_mask = (~s_mask) & (~a_mask) & (~b_mask) & (rank_sorted['現價'] >= rank_sorted['M10']) & (rank_sorted['成交量'] >= 1.5) & (rank_sorted['連買'] >= 1)

                if MACRO_SCORE <= 5:
                    s_mask_macro_defense = (is_strong_breakout & (rank_sorted['連買'] >= 2)) | (~is_strong_breakout & (rank_sorted['乖離(%)'] < 3))
                    s_mask = s_mask & s_mask_macro_defense
                    a_mask = a_mask & (rank_sorted['乖離(%)'] < 3)
                    b_mask = b_mask & (rank_sorted['乖離(%)'] < 3)

                s_tier = rank_sorted[s_mask].head(3).copy()
                a_tier = rank_sorted[a_mask].head(3).copy()
                b_tier = rank_sorted[b_mask].head(7).copy()
                c_tier = rank_sorted[c_mask].copy()

                s_tier['評級'] = 'S'
                a_tier['評級'] = 'A'
                b_tier['評級'] = 'B'
                c_tier['評級'] = 'C'
                
                master_list = pd.concat([s_tier, a_tier, b_tier, c_tier]).reset_index(drop=True).head(20)
                master_list['名次'] = master_list.index + 1
                
                if not master_list.empty:
                    export_rows, active_fee_rate = [], 0.001425 * fee_discount
                    if not m_df.empty:
                        for _, r in m_df.iterrows():
                            try:
                                p_now_raw = r.get('現價', 0)
                                p_now = float(p_now_raw) if pd.notna(p_now_raw) and str(p_now_raw).strip() != '' else 0.0
                                p_cost_raw = r.get('成本價', r.get('成本', r.get('買進價', 0)))
                                qty_raw = r.get('庫存張數', r.get('張數', r.get('庫存', 0)))
                                p_cost = float(str(p_cost_raw).replace(',', '').strip()) if pd.notna(p_cost_raw) and str(p_cost_raw).strip() != '' else 0.0
                                qty = float(str(qty_raw).replace(',', '').strip()) if pd.notna(qty_raw) and str(qty_raw).strip() != '' else 0.0
                                
                                if p_now > 0:
                                    buy_cost_total = (p_cost * qty * 1000) + int((p_cost * qty * 1000) * active_fee_rate)
                                    sell_revenue_net = (p_now * qty * 1000) - int((p_now * qty * 1000) * active_fee_rate) - int((p_now * qty * 1000) * 0.003)
                                    ret = ((sell_revenue_net - buy_cost_total) / buy_cost_total) * 100 if buy_cost_total > 0 else 0
                                else: ret = 0.0
                                
                                m5, m10 = float(r.get('M5', 0)) if pd.notna(r.get('M5', 0)) else 0.0, float(r.get('M10', 0)) if pd.notna(r.get('M10', 0)) else 0.0
                                act = "👑 S級抱緊(防賣飛)" if (ret >= 10 and p_now > m5) else ("💀 破線硬停損" if (p_now > 0 and p_now < m10) else "⏳ 守線續抱")
                                export_rows.append({"戰區": "🛡️ 現役持股", "代號": r['代號'], "名稱": r['名稱'] if '名稱' in r else r.get('代號',''), "戰術行動": act, "現價": round(p_now, 2) if p_now > 0 else "無資料", "防守底線": round(m10, 2) if m10 > 0 else "無資料", "次要數據": f"帳面 {ret:.2f}%", "產業": r['產業']})
                            except: continue
                        export_rows.append({"戰區": "", "代號": "", "名稱": "", "戰術行動": "", "現價": "", "防守底線": "", "次要數據": "", "產業": ""})

                    tier_names = {'S': '🥇 S級狙擊', 'A': '🥈 A級狙擊', 'B': '⚔️ B級穩健', 'C': '📡 C級潛伏'}
                    for _, r in master_list.iterrows():
                        export_rows.append({"戰區": tier_names.get(r['評級'], ""), "代號": r['代號'], "名稱": r['名稱_x'], "戰術行動": "👀 列入觀察" if r['評級'] == 'C' else f"建議買 {r['建議買量(張)']} 張", "現價": round(r['現價'], 2), "防守底線": round(r['停損價'], 2), "次要數據": f"勝率 {r['勝率(%)']:.1f}%", "產業": r['產業']})

                    st.download_button(label="📱 明日目標下載", data=pd.DataFrame(export_rows).to_csv(index=False).encode('utf-8-sig'), file_name=f"Tactical_Map_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
                
                ui_top = master_list[master_list['評級'].isin(['S', 'A'])]
                ui_b = master_list[master_list['評級'] == 'B']
                ui_c = master_list[master_list['評級'] == 'C']

                st.markdown("#### 🥇 <span class='highlight-primary'>【S / A 級】主力狙擊區</span>", unsafe_allow_html=True)
                
                if ui_top.empty: 
                    st.info("💡 今日無主戰力標的符合。")
                else:
                    for i in range(0, len(ui_top), 3):
                        cols_s = st.columns(3)
                        for j in range(3):
                            if i + j < len(ui_top):
                                r = ui_top.iloc[i + j]
                                border_color = COLORS['primary'] if r['評級'] == 'S' else COLORS['accent']
                                title_color = COLORS['primary'] if r['評級'] == 'S' else COLORS['accent']
                                icon_label = "🥇 S級" if r['評級'] == 'S' else "🥈 A級"
                                
                                with cols_s[j]:
                                    st.markdown(f"""
                                    <div class="tier-card" style="border-top: 5px solid {border_color}; margin-bottom: 15px;">
                                        <h3 style="margin:0; color:{title_color};">{icon_label} | {r['名稱_x']} ({r['代號']})</h3>
                                        <p style="color:{COLORS['subtext']}; margin:5px 0 10px 0;">{r['產業']} | 投信連買 {r['連買']} 天</p>
                                        <div style="background-color: {COLORS['bg']}; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
                                            <b>{r['戰術型態']}</b><br>
                                            勝率：<span class="highlight-green">{r['勝率(%)']:.1f}%</span> | 均報：<span class="highlight-accent">+{r['均報(%)']:.2f}%</span>
                                        </div>
                                        <div style="font-size: 15px; line-height: 1.6;">
                                            🛡️ <b>安全指數：</b> {r['安全指數']} 分<br>
                                            💰 <b>現價(進場)：</b> <span class="highlight-primary">{r['現價']:.2f}</span> (乖離 {r['乖離(%)']:.1f}%)<br>
                                            🚨 <b>防爆停損：</b> <span class="highlight-red">{r['停損價']:.2f}</span><br>
                                            ⚖️ <b>AI 建議買量：</b> <span class="highlight-accent">{r['建議買量(張)']}</span> 張
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)

                st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
                st.markdown("#### ⚔️ <span class='highlight-primary'>【B級】穩健波段 (勝率 > 50%)</span>", unsafe_allow_html=True)
                
                if ui_b.empty: st.info("💡 今日無 B 級符合標的。")
                else:
                    styled_b = (ui_b[['名次','評級','代號','名稱_x','產業','戰術型態','安全指數','勝率(%)','均報(%)','現價','停損價','建議買量(張)','連買']].rename(columns={'名稱_x':'名稱'})
                                    .style.set_properties(**table_style)
                                    .format({'現價':'{:.2f}', '停損價':'{:.2f}', '勝率(%)':'{:.1f}%', '均報(%)':'{:.2f}%'})
                                    .map(risk_color, subset=['安全指數'])
                                    .map(lambda x: f'color: {COLORS["green"]}; font-weight: bold;' if x > 60 else '', subset=['勝率(%)']))
                    st.dataframe(styled_b, use_container_width=True, hide_index=True)

                st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
                st.markdown("### 📡 <span class='highlight-primary'>【C級】潛伏遺珠 (Top 20 觀察名單)</span>", unsafe_allow_html=True)
                
                if ui_c.empty: st.info("💡 今日無 C 級潛伏標的。")
                else:
                    styled_c = (ui_c[['名次','評級','代號','名稱_x','產業','戰術型態','安全指數','勝率(%)','現價','乖離(%)','連買']].rename(columns={'名稱_x':'名稱'})
                                    .style.set_properties(**table_style)
                                    .format({'現價':'{:.2f}', '勝率(%)':'{:.1f}%', '乖離(%)':'{:.1f}%'})
                                    .map(risk_color, subset=['安全指數']))
                    st.dataframe(styled_c, use_container_width=True, hide_index=True)

    with t_chip:
        st.markdown("### 📡 <span class='highlight-primary'>聯合作戰情報：主力兵力動向</span>", unsafe_allow_html=True)
        st.caption("💡 **籌碼流向**：當日全台股外資、投信、自營商買賣超Top 200。")
        surprise_atk = today_df[(today_df['連買'] == 1) & (today_df['投信(張)'] > 0) & (today_df['外資(張)'] > 0)].sort_values('三大法人合計', ascending=False).head(3)
        if not surprise_atk.empty:
            st.markdown("#### 🚨 <span class='highlight-green'>土洋合擊區</span>", unsafe_allow_html=True)
            st.dataframe(surprise_atk[['代號','名稱','外資(張)','投信(張)','自營(張)','三大法人合計']].style.set_properties(**table_style).format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}','自營(張)':'{:,.0f}','三大法人合計':'{:,.0f}'}), use_container_width=True, hide_index=True)
            st.markdown("---")
            
        st.markdown("#### <span class='highlight-accent'>穩健建倉部隊 (依三大法人合計排序)</span>", unsafe_allow_html=True)
        main_chips = today_df.sort_values('三大法人合計', ascending=False).head(200)
        if 'intel_df' in locals() and intel_df is not None and not intel_df.empty:
            main_chips = pd.merge(main_chips, intel_df[['代號', '安全指數']], on='代號', how='left')
            main_chips['安全指數'] = main_chips['安全指數'].apply(lambda x: f"{int(x)}" if pd.notna(x) else "-")
        else: main_chips['安全指數'] = '-'
            
        st.dataframe(main_chips[['代號','名稱','連買','安全指數','外資(張)','投信(張)','自營(張)','三大法人合計']]
                     .style.set_properties(**table_style)
                     .format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}','自營(張)':'{:,.0f}','三大法人合計':'{:,.0f}'})
                     .map(risk_color, subset=['安全指數']), height=500, use_container_width=True, hide_index=True)

    with t_cmd:
        st.markdown("### 🏦 <span class='highlight-primary'>司令部：戰備資金精算</span>", unsafe_allow_html=True)
        st.caption("💡 **資金風控**：個人現役持股盈虧計算機與 V5 防賣飛火控雷達。")
        
        if not sheet_url: 
            st.info("請在左側邊欄輸入您的【持股部位】CSV 網址以啟用風控檢查。")
        else:
            if not m_df.empty:
                total_pnl, current_exposure = 0, 0
                active_fee_rate = 0.001425 * fee_discount
                
                html_cards = '<div style="display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px;">'
                
                for _, r in m_df.iterrows():
                    try:
                        p_now_raw = r.get('現價', 0)
                        p_now = float(p_now_raw) if pd.notna(p_now_raw) and str(p_now_raw).strip() != '' else 0.0
                        
                        p_cost_raw = r.get('成本價', r.get('成本', r.get('買進價', 0)))
                        qty_raw = r.get('庫存張數', r.get('張數', r.get('庫存', 0)))
                        
                        p_cost = float(str(p_cost_raw).replace(',', '').strip()) if pd.notna(p_cost_raw) and str(p_cost_raw).strip() != '' else 0.0
                        qty = float(str(qty_raw).replace(',', '').strip()) if pd.notna(qty_raw) and str(qty_raw).strip() != '' else 0.0
                        
                        if p_now > 0:
                            buy_cost_total = (p_cost * qty * 1000) + int((p_cost * qty * 1000) * active_fee_rate)
                            sell_revenue_net = (p_now * qty * 1000) - int((p_now * qty * 1000) * active_fee_rate) - int((p_now * qty * 1000) * 0.003)
                            pnl = sell_revenue_net - buy_cost_total
                            ret = (pnl / buy_cost_total) * 100 if buy_cost_total > 0 else 0
                            current_exposure += (p_now * qty * 1000)
                            total_pnl += pnl
                        else:
                            pnl = 0
                            ret = 0.0
                        
                        m5_raw = r.get('M5', 0)
                        m5 = float(m5_raw) if pd.notna(m5_raw) else 0.0
                        m10_raw = r.get('M10', 0)
                        m10 = float(m10_raw) if pd.notna(m10_raw) else 0.0
                        
                        glow_class = "glow-s-tier" if (ret >= 10 and p_now > m5) else ""
                        border_col = COLORS['primary'] if glow_class else COLORS['border']
                        ret_col = COLORS['red'] if pnl > 0 else (COLORS['green'] if pnl < 0 else COLORS['text'])
                        
                        if p_now == 0.0 or m10 == 0.0:
                            struct = "⚪ 訊號不足 (無有效報價/剛上市)"
                            coach = "無法取得完整均線數據，請手動確認走勢。"
                            border_col = COLORS['border']
                            glow_class = ""
                        elif p_now > m5 and m5 > m10:
                            struct = f"🚀 多頭排列 (現價 > M5: {m5:.1f})"
                            if ret >= 10: coach = "👑 <b>【S級金雞母】</b> 趨勢極強！<b>跌破 M5 前絕對不賣！</b>"
                            elif ret > 0:
                                coach = "⚠️ <b>【防賣飛警告】</b> 主升段啟動！獲利達6%先出一半，剩下死抱 M5！"
                                border_col = COLORS['accent']
                            else: coach = "⏳ 強勢洗盤，請耐心抱緊，防守底線設於 M10。"
                        elif p_now >= m10:
                            struct = f"⏳ 均線收斂 (守住 M10: {m10:.1f})"
                            coach = "🛡️ 洗盤震盪中，尚未破線，請給予耐心與空間。"
                            border_col = COLORS['accent'] if ret > 0 else COLORS['border']
                        else:
                            struct = f"📉 跌破防守線 (現價 < M10: {m10:.1f})"
                            border_col = COLORS['red'] if ret < 0 else COLORS['green']
                            if ret > 0: coach = "🛡️ <b>【停利警報】</b> 趨勢轉弱，建議立刻減碼鎖住獲利！"
                            else: coach = f"💀 <b>【情緒殺預警】</b> 破線硬停損！請無情砍單保命，絕不攤平！"
                        
                        name_display = r['名稱'] if '名稱' in r else r.get('代號','')
                        display_p_now = f"{p_now:.2f}" if p_now > 0 else "抓取中"
                        
                        # 👉 UI 修復：將 margin-bottom 調短為 4px，padding 壓扁為 6px 12px，卡片更俐落！
                        html_cards += f"<div class='holding-card {glow_class}' style='border-left: 5px solid {border_col}; padding: 12px 15px; background-color: {COLORS['card']}; border-radius: 4px;'><div class='rwd-flex-header' style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;'><div class='rwd-flex-title' style='display: flex; align-items: baseline; gap: 15px;'><h3 style='margin: 0; font-size: 20px; font-weight: bold; color: {COLORS['text']};'>{name_display} ({r['代號']})</h3><div style='font-size: 13.5px; color: {COLORS['subtext']};'>現價: <strong style='color:{COLORS['text']}'>{display_p_now}</strong> | 成本: {p_cost:.2f} | 張數: {format_lots(qty * 1000)}</div></div><div class='rwd-flex-profit' style='text-align: right;'><span style='font-size: 16px; font-weight: bold; color: {ret_col};'>{ret:.2f}%</span><span style='font-size: 16px; font-weight: bold; color: {ret_col}; margin-left: 10px;'>{pnl:,.0f} 元</span></div></div><div class='rwd-flex-info' style='background-color: {COLORS['bg']}; padding: 6px 12px; border-radius: 6px; font-size: 13.5px; display: flex; gap: 20px;'><div style='white-space: nowrap;'><span style='color:{COLORS['subtext']}'>📊 結構：</span><span style='color:{COLORS['text']}; font-weight:500;'>{struct}</span></div><div><span style='color:{COLORS['subtext']}'>💡 教練：</span><span style='color:{COLORS['text']}'>{coach}</span></div></div></div>"
                    
                    except Exception as e:
                        st.error(f"⚠️ 卡片渲染錯誤: {r.get('代號', '未知')} - {e}")
                        continue
                
                html_cards += '</div>'
                
                p_color = COLORS['red'] if total_pnl > 0 else COLORS['green']
                st.markdown(f"#### 💰 目前總淨損益：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                
                if total_pnl != 0 or current_exposure != 0 or len(m_df) > 0:
                    st.markdown(html_cards, unsafe_allow_html=True)
                else:
                    st.info("💡 目前尚無有效持股資料，或現價抓取失敗。")
                    
            else:
                st.info("💡 目前尚無有效持股資料，或現價抓取失敗。")
            
            with st.expander("🛠️ 系統除錯中心"):
                st.write("最終合併結果 (若為空代表代號對不上):")
                if 'm_df' in locals() and not m_df.empty:
                    display_df = m_df.drop(columns=['分類'], errors='ignore')
                    st.dataframe(display_df, hide_index=True)
                else:
                    st.write("合併失敗或無資料")

        st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
        st.markdown("### 📊 <span class='highlight-primary'>AAR 戰術覆盤室</span>", unsafe_allow_html=True)
        FM_TOKEN = st.secrets.get("fm_token", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiZGVraTEwMjMiLCJlbWFpbCI6ImRla2kxMDIzQGdtYWlsLmNvbSJ9.-wVo_6BD8ac8cGCOi8C3J58KUGZ1c0CMwTU9lYPltNM")
        aar.render_aar_tab(aar_sheet_url, fee_discount, FM_TOKEN, COLORS)

    with t_book:
        st.markdown("### 📖 <span class='highlight-primary'>實戰準則與系統圖示教範</span>", unsafe_allow_html=True)
        st.markdown(MANUAL_TEXT, unsafe_allow_html=True)

    with t_hist:
        st.markdown("### 🏛️ <span class='highlight-primary'>皇家軍史館：兵器開發檔案</span>", unsafe_allow_html=True)
        st.markdown(HISTORY_TEXT, unsafe_allow_html=True)

else: st.error("⚠️ 資料匯入失敗。請檢查網路或稍後再試。")

st.divider()
st.markdown("<p style='text-align: center;' class='text-sub'>© 游擊隊軍火部 - v26.0 (V6 引擎升級版)</p>", unsafe_allow_html=True)
