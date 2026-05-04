import html

import pandas as pd
import streamlit as st

from etf_engine import load_active_etf_holdings, run_etf_momentum_radar, summarize_active_etf_holdings


def _fmt_pct(x):
    try:
        return f"{float(x):+.2f}%"
    except Exception:
        return str(x)


def _score_color(score, COLORS):
    try:
        v = float(score)
        if v >= 80:
            return f"color:{COLORS['green']}; font-weight:800;"
        if v < 55:
            return f"color:{COLORS['red']}; font-weight:800;"
        return f"color:{COLORS['primary']}; font-weight:800;"
    except Exception:
        return ""


def _render_etf_cards(df, COLORS):
    top = df.head(3)
    if top.empty:
        st.info("ETF 動能資料不足，請稍後重整或檢查資料源。")
        return
    cols = st.columns(3)
    for idx, (_, r) in enumerate(top.iterrows()):
        color = COLORS["green"] if float(r.get("動能分數", 0)) >= 80 else COLORS["primary"]
        if "過熱" in str(r.get("狀態", "")):
            color = COLORS["accent"]
        if "轉弱" in str(r.get("狀態", "")):
            color = COLORS["red"]
        with cols[idx]:
            st.markdown(f"""
            <div class="tier-card" style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-top:4px solid {color}; border-radius:10px; padding:14px; min-height:170px;">
                <div style="font-size:13px; color:{COLORS['subtext']}; font-weight:700;">ETF Top {idx+1}｜{html.escape(str(r.get('類型','ETF')))}</div>
                <div style="font-size:21px; font-weight:900; color:{color}; margin:4px 0 6px 0; line-height:1.25;">{html.escape(str(r.get('名稱','')))} <span style="white-space:nowrap;">({html.escape(str(r.get('代號','')) )})</span></div>
                <div style="font-size:13px; color:{COLORS['subtext']}; margin-bottom:8px;">3日 {_fmt_pct(r.get('3日漲幅(%)'))}｜5日 {_fmt_pct(r.get('5日漲幅(%)'))}｜10日 {_fmt_pct(r.get('10日漲幅(%)'))}</div>
                <div style="background:{COLORS['bg']}; border-radius:8px; padding:8px 10px; margin-bottom:8px;">
                    <div style="font-size:13px; color:{COLORS['text']};"><b>動能分數：</b><span style="font-size:18px; font-weight:900; color:{color};">{r.get('動能分數')}</span></div>
                    <div style="font-size:13px; color:{COLORS['text']}; margin-top:3px;"><b>狀態：</b>{html.escape(str(r.get('狀態','')))}</div>
                </div>
                <div style="font-size:13px; color:{COLORS['text']}; line-height:1.45;"><b>下一步：</b>{html.escape(str(r.get('下一步','')))}</div>
            </div>
            """, unsafe_allow_html=True)


def render_etf_tab(COLORS, fm_token, industry_map, name_map, etf_holdings_url="", table_style=None):
    table_style = table_style or {"text-align": "center"}
    st.markdown("### 📈 <span class='highlight-primary'>ETF 主體倉雷達</span>", unsafe_allow_html=True)
    st.caption("ETF 區服務你的 60% 主體倉：先看動能，再看主動 ETF 經理人風向；不與個股 S/A/B 混排。")

    sub1, sub2, sub3 = st.tabs(["⚡ ETF 動能 Top 5", "🧭 主動 ETF 持股快照", "🔁 近 5 日持股變化"])

    with sub1:
        filter_col, note_col = st.columns([1, 3])
        with filter_col:
            etf_filter = st.selectbox("ETF 類型", ["全部", "主動ETF", "被動ETF"], index=0)
        with note_col:
            st.info("分數重視 5 日動能，其次 3 日啟動、10 日延續、站上 M5/M10、量能；乖離過高會扣分。", icon="💡")
        radar = run_etf_momentum_radar(fm_token)
        if radar.empty:
            st.warning("ETF 動能資料暫時不足。")
        else:
            if etf_filter != "全部":
                radar_view = radar[radar["類型"].eq(etf_filter)].copy()
            else:
                radar_view = radar.copy()
            radar_top5 = radar_view.head(5).copy()
            _render_etf_cards(radar_top5, COLORS)
            st.markdown("#### 📋 ETF 動能 Top 5 表格")
            if radar_top5.empty:
                st.info("目前沒有符合類型的 ETF 動能資料。")
            else:
                show_cols = ["代號", "名稱", "類型", "狀態", "下一步", "動能分數", "3日漲幅(%)", "5日漲幅(%)", "10日漲幅(%)", "乖離(%)", "量能比", "現價"]
                disp = radar_top5[[c for c in show_cols if c in radar_top5.columns]].copy()
                for c in ["3日漲幅(%)", "5日漲幅(%)", "10日漲幅(%)", "乖離(%)"]:
                    if c in disp.columns:
                        disp[c] = disp[c].map(lambda x: f"{float(x):+.2f}%")
                styled = disp.style.set_properties(**table_style).map(lambda v: _score_color(v, COLORS), subset=["動能分數"] if "動能分數" in disp.columns else None)
                st.dataframe(styled, use_container_width=True, hide_index=True)

    holdings = load_active_etf_holdings(etf_holdings_url) if etf_holdings_url else pd.DataFrame()
    summary = summarize_active_etf_holdings(holdings, industry_map, name_map, top_n=3, lookback_days=5) if not holdings.empty else None

    with sub2:
        st.markdown("#### 🧭 主動 ETF 經理人風向 Top 3")
        st.caption("這區不是照抄買進清單，而是觀察主動 ETF 目前押注的產業與共同重倉。")
        if not etf_holdings_url:
            st.info("尚未設定【主動 ETF 持股 CSV】。請在側邊欄貼上持股快照 CSV；未設定時仍可使用 ETF 動能排行。")
        elif holdings.empty or summary is None or summary.get("snapshot", pd.DataFrame()).empty:
            st.warning("主動 ETF 持股 CSV 讀取不到資料，或欄位格式不足。需要欄位：日期、ETF代號、成分股代號、權重。")
        else:
            snapshot = summary["snapshot"]
            st.dataframe(snapshot.style.set_properties(**table_style), use_container_width=True, hide_index=True, height=260)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### 前十大產業明細")
                ind = summary.get("industries", pd.DataFrame()).head(30)
                if not ind.empty:
                    st.dataframe(ind.style.set_properties(**table_style).format({"權重":"{:.2f}%"}), use_container_width=True, hide_index=True, height=360)
            with c2:
                st.markdown("##### 共同重倉股")
                common = summary.get("common_holdings", pd.DataFrame())
                if common.empty:
                    st.info("目前 Top 3 主動 ETF 共同重倉不明顯。")
                else:
                    st.dataframe(common.style.set_properties(**table_style).format({"合計權重":"{:.2f}%"}), use_container_width=True, hide_index=True, height=360)

    with sub3:
        st.markdown("#### 🔁 主動 ETF 近 5 日持股變化")
        st.caption("預設看近 5 日，較貼近你 5～10 天 ETF 短波段；單日變化容易太雜。")
        if not etf_holdings_url:
            st.info("尚未設定【主動 ETF 持股 CSV】，此區暫不啟用。")
        elif holdings.empty or summary is None:
            st.warning("持股變化資料不足。")
        else:
            changes = summary.get("changes", pd.DataFrame())
            industry_changes = summary.get("industry_changes", pd.DataFrame())
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown("##### 共同加碼 / 減碼族群")
                if industry_changes.empty:
                    st.info("近 5 日產業變化資料不足。")
                else:
                    st.dataframe(industry_changes.head(15).style.set_properties(**table_style).format({"變化":"{:+.2f}%"}), use_container_width=True, hide_index=True, height=360)
            with c2:
                st.markdown("##### 新增 / 刪除 / 加碼 / 減碼明細")
                if changes.empty:
                    st.info("近 5 日沒有明顯持股變化，或資料只有單一日期。")
                else:
                    show_cols = ["比較基準", "ETF代號", "成分股代號", "成分股名稱", "產業", "狀態", "權重_舊", "權重_新", "變化"]
                    disp = changes[[c for c in show_cols if c in changes.columns]].copy().head(80)
                    st.dataframe(disp.style.set_properties(**table_style).format({"權重_舊":"{:.2f}%", "權重_新":"{:.2f}%", "變化":"{:+.2f}%"}), use_container_width=True, hide_index=True, height=420)

    with st.expander("📌 ETF 雷達使用說明", expanded=False):
        st.markdown("""
        * **ETF 動能排行**：用來選 60% 主體倉候選，不代表 Top 5 全買；實際挑 1～2 檔即可。  
        * **主動 ETF 持股快照**：用來看經理人風向與產業共識，不是照抄成分股。  
        * **近 5 日變化**：比今日對昨日更穩，較符合你的 5～10 天 ETF 短波段節奏。  
        * **共同加碼族群**：比單一股票更重要，代表多檔主動 ETF 可能正在偏向同一主題。  
        """)
