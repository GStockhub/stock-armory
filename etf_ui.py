import html

import pandas as pd
import streamlit as st

from etf_engine import load_active_etf_holdings, run_etf_momentum_radar, summarize_active_etf_holdings


def _fmt_pct(x):
    try:
        return f"{float(x):+.2f}%"
    except Exception:
        return str(x)


def _fmt_price(x):
    try:
        return f"{float(x):.2f}"
    except Exception:
        return str(x)


def _fmt_score(x):
    try:
        return f"{float(x):.0f}"
    except Exception:
        return str(x)


def _fmt_ratio(x):
    try:
        return f"{float(x):.2f}x"
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


def _render_etf_cards(df, COLORS, title_prefix="ETF"):
    top = df.head(3)
    if top.empty:
        st.info(f"{title_prefix} 動能資料不足。")
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
            <div class="tier-card" style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-top:4px solid {color}; border-radius:10px; padding:14px; min-height:168px;">
                <div style="font-size:13px; color:{COLORS['subtext']}; font-weight:700;">{html.escape(title_prefix)} Top {idx+1}</div>
                <div style="font-size:20px; font-weight:900; color:{color}; margin:4px 0 6px 0; line-height:1.25; word-break:break-word;">{html.escape(str(r.get('名稱','')))} <span style="white-space:nowrap;">({html.escape(str(r.get('代號','')) )})</span></div>
                <div style="font-size:13px; color:{COLORS['subtext']}; margin-bottom:8px;">3日 {_fmt_pct(r.get('3日漲幅(%)'))}｜5日 {_fmt_pct(r.get('5日漲幅(%)'))}｜10日 {_fmt_pct(r.get('10日漲幅(%)'))}</div>
                <div style="background:{COLORS['bg']}; border-radius:8px; padding:8px 10px; margin-bottom:8px;">
                    <div style="font-size:13px; color:{COLORS['text']};"><b>動能分數：</b><span style="font-size:18px; font-weight:900; color:{color};">{_fmt_score(r.get('動能分數'))}</span></div>
                    <div style="font-size:13px; color:{COLORS['text']}; margin-top:3px;"><b>狀態：</b>{html.escape(str(r.get('狀態','')))}</div>
                </div>
                <div style="font-size:13px; color:{COLORS['text']}; line-height:1.45;"><b>下一步：</b>{html.escape(str(r.get('下一步','')))}</div>
            </div>
            """, unsafe_allow_html=True)


def _format_etf_table(df):
    disp = df.copy()
    for c in ["動能分數"]:
        if c in disp.columns:
            disp[c] = disp[c].map(_fmt_score)
    for c in ["3日漲幅(%)", "5日漲幅(%)", "10日漲幅(%)", "乖離(%)"]:
        if c in disp.columns:
            disp[c] = disp[c].map(_fmt_pct)
    if "量能比" in disp.columns:
        disp["量能比"] = disp["量能比"].map(_fmt_ratio)
    if "現價" in disp.columns:
        disp["現價"] = disp["現價"].map(_fmt_price)
    return disp


def render_etf_tab(COLORS, fm_token, industry_map, name_map, etf_holdings_url="", table_style=None):
    table_style = table_style or {"text-align": "center"}
    st.markdown("### 📈 <span class='highlight-primary'>ETF 主體倉雷達</span>", unsafe_allow_html=True)
    st.caption("ETF 區服務你的 60% 主體倉：主動/被動 ETF 分開看，綜合排名放同一張表，不再用下拉切換。")

    radar = run_etf_momentum_radar(fm_token)
    if radar.empty:
        st.warning("ETF 動能資料暫時不足。")
        active_df = passive_df = pd.DataFrame()
    else:
        active_df = radar[radar["類型"].eq("主動ETF")].head(3).copy()
        passive_df = radar[radar["類型"].eq("被動ETF")].head(3).copy()

    st.markdown("#### 🧭 主動 ETF 動能 Top 3")
    _render_etf_cards(active_df, COLORS, "主動ETF")

    st.markdown("#### ⚙️ 被動 ETF 動能 Top 3")
    _render_etf_cards(passive_df, COLORS, "被動ETF")

    st.markdown("#### 📋 ETF 綜合動能 Top 10")
    if radar.empty:
        st.info("目前沒有 ETF 動能資料。")
    else:
        show_cols = ["代號", "名稱", "類型", "狀態", "下一步", "動能分數", "3日漲幅(%)", "5日漲幅(%)", "10日漲幅(%)", "乖離(%)", "量能比", "現價"]
        disp = radar.head(10)[[c for c in show_cols if c in radar.columns]].copy()
        styled = _format_etf_table(disp).style.set_properties(**table_style).map(_score_color, subset=["動能分數"] if "動能分數" in disp.columns else None, COLORS=COLORS)
        st.dataframe(styled, use_container_width=True, hide_index=True, height=390)

    st.markdown("#### 🧭 主動 ETF 經理人風向")
    st.caption("持股快照與近 5 日變化合併；自動資料若不可得，可用側邊欄 CSV 備援。這區看產業風向，不是照抄成分股。")
    holdings = load_active_etf_holdings(etf_holdings_url) if etf_holdings_url else pd.DataFrame()
    summary = summarize_active_etf_holdings(holdings, industry_map, name_map, top_n=3, lookback_days=5) if not holdings.empty else None

    if not etf_holdings_url:
        st.info("尚未設定【主動 ETF 持股 CSV】。ETF 動能排行仍可正常使用；持股風向需等自動來源或 CSV 備援。")
    elif holdings.empty or summary is None or summary.get("snapshot", pd.DataFrame()).empty:
        st.warning("主動 ETF 持股資料讀取不到，或欄位格式不足。需要欄位：日期、ETF代號、成分股代號、權重。")
    else:
        snapshot = summary["snapshot"]
        st.markdown("##### Top 3 主動 ETF 持股快照")
        st.dataframe(snapshot.style.set_properties(**table_style), use_container_width=True, hide_index=True, height=245)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 共同重倉股")
            common = summary.get("common_holdings", pd.DataFrame())
            if common.empty:
                st.info("目前 Top 3 主動 ETF 共同重倉不明顯。")
            else:
                st.dataframe(common.head(20).style.set_properties(**table_style).format({"合計權重":"{:.2f}%"}), use_container_width=True, hide_index=True, height=330)
        with c2:
            st.markdown("##### 近 5 日共同加碼 / 減碼族群")
            industry_changes = summary.get("industry_changes", pd.DataFrame())
            if industry_changes.empty:
                st.info("近 5 日產業變化資料不足。")
            else:
                st.dataframe(industry_changes.head(15).style.set_properties(**table_style).format({"變化":"{:+.2f}%"}), use_container_width=True, hide_index=True, height=330)

        with st.expander("🔁 查看新增 / 刪除 / 加碼 / 減碼明細", expanded=False):
            changes = summary.get("changes", pd.DataFrame())
            if changes.empty:
                st.info("近 5 日沒有明顯持股變化，或資料只有單一日期。")
            else:
                show_cols = ["比較基準", "ETF代號", "成分股代號", "成分股名稱", "產業", "狀態", "權重_舊", "權重_新", "變化"]
                disp = changes[[c for c in show_cols if c in changes.columns]].copy().head(80)
                st.dataframe(disp.style.set_properties(**table_style).format({"權重_舊":"{:.2f}%", "權重_新":"{:.2f}%", "變化":"{:+.2f}%"}), use_container_width=True, hide_index=True, height=420)

    with st.expander("📌 ETF 雷達使用說明", expanded=False):
        st.markdown("""
        * **主動 / 被動 Top 3**：直接同屏比較，不再切換下拉，避免手機與 Streamlit 重跑卡頓。  
        * **ETF 綜合 Top 10**：主動與被動混合排序，實際主體倉只挑 1～3 檔，不是 Top 10 全買。  
        * **主動 ETF 經理人風向**：看產業共識與共同重倉，不代表直接照抄成分股。  
        * **近 5 日變化**：比今日對昨日更穩，較符合你的 5～10 天 ETF 短波段節奏。  
        """)
