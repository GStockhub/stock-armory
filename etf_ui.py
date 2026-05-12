import html
import math

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from etf_engine import load_active_etf_holdings, run_etf_momentum_radar, summarize_active_etf_holdings
from active_etf_holdings import build_active_etf_manager_radar, get_history_status, get_github_history_diagnostics


# =========================
# 格式化工具
# =========================

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


def _to_float(v, default=0.0):
    try:
        return float(str(v).replace('%', '').replace(',', '').strip())
    except Exception:
        return default


def _safe_text(x):
    return html.escape(str(x if x is not None else ""))


# =========================
# ETF 動能區
# =========================

def _render_etf_cards(df, COLORS, title_prefix="ETF"):
    top = df.head(3)
    if top.empty:
        st.info(f"{title_prefix} 動能資料不足。")
        return
    cols = st.columns(3)
    for idx, (_, r) in enumerate(top.iterrows()):
        score = _to_float(r.get("動能分數", 0))
        color = COLORS["green"] if score >= 80 else COLORS["primary"]
        if "過熱" in str(r.get("狀態", "")):
            color = COLORS["accent"]
        if "轉弱" in str(r.get("狀態", "")):
            color = COLORS["red"]
        with cols[idx]:
            st.markdown(f"""
            <div class="tier-card" style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-top:4px solid {color}; border-radius:10px; padding:14px; min-height:168px;">
                <div style="font-size:13px; color:{COLORS['subtext']}; font-weight:700;">{_safe_text(title_prefix)} Top {idx+1}</div>
                <div style="font-size:20px; font-weight:900; color:{color}; margin:4px 0 6px 0; line-height:1.25; word-break:break-word;">
                    {_safe_text(r.get('名稱',''))} <span style="white-space:nowrap;">({_safe_text(r.get('代號',''))})</span>
                </div>
                <div style="font-size:13px; color:{COLORS['subtext']}; margin-bottom:8px;">3日 {_fmt_pct(r.get('3日漲幅(%)'))}｜5日 {_fmt_pct(r.get('5日漲幅(%)'))}｜10日 {_fmt_pct(r.get('10日漲幅(%)'))}</div>
                <div style="background:{COLORS['bg']}; border-radius:8px; padding:8px 10px; margin-bottom:8px;">
                    <div style="font-size:13px; color:{COLORS['text']};"><b>動能分數：</b><span style="font-size:18px; font-weight:900; color:{color};">{_fmt_score(r.get('動能分數'))}</span></div>
                    <div style="font-size:13px; color:{COLORS['text']}; margin-top:3px;"><b>狀態：</b>{_safe_text(r.get('狀態',''))}</div>
                </div>
                <div style="font-size:13px; color:{COLORS['text']}; line-height:1.45;"><b>下一步：</b>{_safe_text(r.get('下一步',''))}</div>
            </div>
            """, unsafe_allow_html=True)


def _format_etf_table(df):
    disp = df.copy()
    if "類型" in disp.columns:
        disp["類型"] = disp["類型"].astype(str).str.replace("ETF", "", regex=False)
    if "狀態" in disp.columns and "下一步" in disp.columns:
        disp["狀態/下一步"] = disp["狀態"].astype(str) + "｜" + disp["下一步"].astype(str)
        disp = disp.drop(columns=["狀態", "下一步"], errors="ignore")
    if "動能分數" in disp.columns:
        disp["動能分數"] = disp["動能分數"].map(_fmt_score)
    for c in ["3日漲幅(%)", "5日漲幅(%)", "10日漲幅(%)", "乖離(%)"]:
        if c in disp.columns:
            disp[c] = disp[c].map(_fmt_pct)
    if "量能比" in disp.columns:
        disp["量能比"] = disp["量能比"].map(_fmt_ratio)
    if "現價" in disp.columns:
        disp["現價"] = disp["現價"].map(_fmt_price)
    return disp


# =========================
# 經理人風向視覺化
# =========================

_DONUT_COLORS = ["#5FA5D9", "#20A05D", "#D8B08C", "#E57373", "#8FA3B0", "#A68A75"]


def _donut_gradient(values):
    total = sum(max(0, float(v)) for v in values)
    if total <= 0:
        return "#E5E7EB 0deg 360deg"
    start = 0.0
    parts = []
    for i, v in enumerate(values):
        deg = max(0, float(v)) / total * 360
        end = start + deg
        parts.append(f"{_DONUT_COLORS[i % len(_DONUT_COLORS)]} {start:.1f}deg {end:.1f}deg")
        start = end
    return ", ".join(parts)


def _render_industry_donut_cards(summary, COLORS, top_n=10):
    """V37.6：產業占比改成一張整合表，不再分散成多張卡片。"""
    industries = summary.get("industries", pd.DataFrame())
    stocks = summary.get("stocks", pd.DataFrame())
    snapshot = summary.get("snapshot", pd.DataFrame())
    if industries is None or industries.empty or snapshot is None or snapshot.empty:
        st.info("產業占比資料不足。若每檔 ETF 只剩 1 筆持股，代表來源只抓到部分持股，需等來源更新或改用 CSV 備援。")
        return

    rows = []
    for _, snap in snapshot.head(top_n).iterrows():
        code = str(snap.get("ETF", ""))
        name = str(snap.get("名稱", code))
        ind_sub = industries[industries["ETF代號"].astype(str).eq(code)].copy()
        stock_sub = stocks[stocks["ETF代號"].astype(str).eq(code)].copy() if stocks is not None and not stocks.empty else pd.DataFrame()
        if ind_sub.empty:
            continue
        ind_sub["權重"] = pd.to_numeric(ind_sub["權重"], errors="coerce").fillna(0)
        ind_sub = ind_sub.sort_values("權重", ascending=False)
        industry_text = "、".join([f"{r['產業']} {float(r['權重']):.1f}%" for _, r in ind_sub.iterrows()])

        if not stock_sub.empty:
            stock_sub["權重"] = pd.to_numeric(stock_sub["權重"], errors="coerce").fillna(0)
            stock_sub = stock_sub.sort_values("權重", ascending=False).head(10)
            stock_text = "、".join([f"{r['成分股名稱']}({r['成分股代號']}) {float(r['權重']):.1f}%" for _, r in stock_sub.iterrows()])
        else:
            stock_text = ""

        rows.append({
            "ETF": code,
            "名稱": name,
            "產業數": int(ind_sub["產業"].nunique()),
            "產業占比": industry_text,
            "前十大個股": stock_text,
        })

    if not rows:
        st.info("產業占比資料不足。")
        return

    disp = pd.DataFrame(rows)
    st.dataframe(
        disp.style.set_properties(**{"text-align": "left", "background-color": COLORS["card"], "color": COLORS["text"], "border-color": COLORS["border"]}),
        use_container_width=True,
        hide_index=True,
        height=min(420, 90 + len(disp) * 46),
    )
    if (disp["產業數"] <= 1).any():
        st.caption("有些 ETF 只顯示 1 種產業，通常不是計算錯，而是自動來源只抓到少量持股；若要完整持股，建議改用 CSV 備援資料源。")


def _render_bar_list(df, COLORS, label_col, value_col, subtitle_col=None, max_rows=10, signed=False):
    if df is None or df.empty or label_col not in df.columns or value_col not in df.columns:
        st.info("資料不足。")
        return
    work = df.copy().head(max_rows)
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce").fillna(0)
    max_abs = float(work[value_col].abs().max()) if not work.empty else 0
    if max_abs <= 0:
        max_abs = 1
    blocks = []
    for _, r in work.iterrows():
        val = float(r[value_col])
        width = min(100, max(3, abs(val) / max_abs * 100))
        color = COLORS["green"] if val >= 0 else COLORS["red"]
        sub = f"｜{_safe_text(r.get(subtitle_col, ''))}" if subtitle_col and subtitle_col in work.columns else ""
        val_text = f"{val:+.2f}%" if signed else f"{val:.2f}%"
        blocks.append(f"""
        <div style="margin:9px 0 11px 0;">
            <div style="display:flex; justify-content:space-between; gap:10px; font-size:13px; margin-bottom:4px;">
                <span style="font-weight:700; color:{COLORS['text']}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{_safe_text(r.get(label_col, ''))}{sub}</span>
                <span style="font-weight:800; color:{color}; white-space:nowrap;">{val_text}</span>
            </div>
            <div style="height:8px; background:{COLORS['bg']}; border-radius:99px; overflow:hidden;">
                <div style="width:{width:.1f}%; height:8px; background:{color}; border-radius:99px;"></div>
            </div>
        </div>
        """)
    # 用 components.html 渲染，避免在某些 Streamlit / Markdown 情境下 HTML 語法外漏。
    height = min(560, max(120, 44 + len(work) * 43))
    html_doc = f"""
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
                overflow: hidden;
            }}
            .bar-card {{
                background: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                padding: 12px 14px;
                box-sizing: border-box;
                width: 100%;
            }}
        </style>
    </head>
    <body>
        <div class="bar-card">{''.join(blocks)}</div>
    </body>
    </html>
    """
    components.html(html_doc, height=height, scrolling=False)


def _render_manager_header_compact(summary, holdings, COLORS, history_status=None, auto_note=""):
    """V35.3.1：把自動更新、歷史快照、GitHub 狀態壓成同一張單行摘要卡。"""
    history_status = history_status or get_history_status(holdings, lookback_days=20)
    days = int(history_status.get("days", 0) or 0)
    latest = str(history_status.get("latest", "-") or "-")
    msg = str(history_status.get("message", "") or "")
    gh_diag = {}
    try:
        gh_diag = get_github_history_diagnostics() or {}
    except Exception:
        gh_diag = {}
    gh_summary = str(gh_diag.get("summary", "GitHub 診斷暫時無法取得") or "GitHub 診斷暫時無法取得")
    snapshot = summary.get("snapshot", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    etf_count = int(snapshot["ETF"].nunique()) if snapshot is not None and not snapshot.empty and "ETF" in snapshot.columns else 0
    changes = summary.get("changes", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    event_count = int(len(changes)) if changes is not None and not changes.empty else 0
    auto_text = str(auto_note or "自動持股來源正常；若 GitHub 寫入失敗則先沿用本機快取。")
    compact_msg = msg.replace("｜", "；")

    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['primary']}; padding:10px 13px; border-radius:10px; margin:6px 0 14px 0;">
        <div style="font-size:14px; color:{COLORS['text']}; line-height:1.65;">
            <b>🧭 主動 ETF 風向狀態：</b>{_safe_text(auto_text)}
            <span style="color:{COLORS['subtext']};">｜</span>
            <b>📦 快照</b> {days} 日，最新 {_safe_text(latest)}，涵蓋 {etf_count} 檔，事件 {event_count} 筆
            <span style="color:{COLORS['subtext']};">｜</span>
            <b>🧪 GitHub</b> {_safe_text(gh_summary)}
        </div>
        <div style="font-size:12px; color:{COLORS['subtext']}; line-height:1.45; margin-top:3px;">{_safe_text(compact_msg)}</div>
    </div>
    """, unsafe_allow_html=True)
    if gh_diag:
        with st.expander("🧪 GitHub 診斷細節", expanded=False):
            checks = gh_diag.get("checks", [])
            if checks:
                st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)
            else:
                st.json({k: v for k, v in gh_diag.items() if k != "checks"})


def _render_etfedge_like_changes(summary, COLORS, table_style):
    changes = summary.get("changes", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    daily_events = summary.get("daily_events", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    shared_actions = summary.get("shared_actions", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    snapshot = summary.get("snapshot", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    manager_profiles = summary.get("manager_profiles", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    hot_etfs = summary.get("hot_etfs", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    meta = summary.get("meta", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()

    st.markdown("##### 📋 主動 ETF 經理人動作追蹤")
    st.caption("母清單保留全部主動 ETF；主畫面鎖定熱門前 10。事件看近 30 天，快照保留 60 天，過濾微調後只看真正調倉。")

    if meta is not None and not meta.empty:
        m = meta.iloc[0].to_dict()
        st.caption(f"資料意義：{m.get('資料意義','')}｜門檻：{m.get('事件門檻','')}｜快照 {m.get('快照保留','')}｜事件 {m.get('事件明細','')}")

    if hot_etfs is not None and not hot_etfs.empty:
        with st.expander("🔥 本週熱門主動 ETF Top 10", expanded=False):
            show_cols = ["熱門名次", "ETF代號", "ETF名稱", "熱門分數", "權重合計", "持股數", "動能分數"]
            disp_hot = hot_etfs[[c for c in show_cols if c in hot_etfs.columns]].copy()
            st.dataframe(
                disp_hot.style.set_properties(**table_style).format({"熱門分數": "{:.1f}", "權重合計": "{:.1f}", "動能分數": "{:.1f}"}),
                use_container_width=True,
                hide_index=True,
                height=260,
            )

    basis = "尚無逐日變化"
    if changes is not None and not changes.empty and "比較基準" in changes.columns:
        basis = str(changes["比較基準"].iloc[0])
    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['primary']}; padding:10px 13px; border-radius:9px; margin:8px 0 12px 0;">
        <b>比較基準：</b>{_safe_text(basis)}
    </div>
    """, unsafe_allow_html=True)

    count_scope = daily_events if daily_events is not None and not daily_events.empty else changes
    if count_scope is None or count_scope.empty:
        counts = {"新增": 0, "刪除": 0, "加碼": 0, "減碼": 0}
    else:
        counts = {k: int((count_scope["狀態"] == k).sum()) for k in ["新增", "刪除", "加碼", "減碼"]}

    cc = st.columns(4)
    for col, (label, val) in zip(cc, [("🆕 新增", counts.get("新增", 0)), ("➕ 加碼", counts.get("加碼", 0)), ("➖ 減碼", counts.get("減碼", 0)), ("❌ 刪除", counts.get("刪除", 0))]):
        with col:
            st.metric(label, f"{val} 筆")

    tabs = st.tabs(["🎯 總覽", "🤝 共同動作", "📅 逐日明細", "📦 ETF明細"])

    with tabs[0]:
        if manager_profiles is None or manager_profiles.empty:
            st.info("目前沒有主動 ETF 經理人差異資料。")
        else:
            show_cols = ["ETF代號", "ETF名稱", "持股數", "集中度", "主要產業", "重點持股"]
            disp = manager_profiles[[c for c in show_cols if c in manager_profiles.columns]].copy()
            st.dataframe(
                disp.style.set_properties(**table_style).format({"集中度": "{:.2f}%"}),
                use_container_width=True,
                hide_index=True,
                height=340,
            )

    with tabs[1]:
        if shared_actions is None or shared_actions.empty:
            st.info("近 30 天沒有出現 2 檔以上主動 ETF 對同一個股同步新增、刪除、加碼或減碼。")
        else:
            status_filter = st.multiselect("動作篩選", ["新增", "加碼", "減碼", "刪除"], default=["新增", "加碼", "減碼", "刪除"], key="active_etf_shared_status")
            sub = shared_actions[shared_actions["狀態"].isin(status_filter)].copy() if status_filter else shared_actions.copy()
            show_cols = ["狀態", "成分股代號", "成分股名稱", "產業", "ETF數", "事件數", "涉及ETF", "合計股數變化", "合計變化", "資料模式"]
            disp = sub[[c for c in show_cols if c in sub.columns]].head(120).copy()
            st.dataframe(
                disp.style.set_properties(**table_style).format({"合計股數變化": "{:,.0f}", "合計變化": "{:+.2f}%"}),
                use_container_width=True,
                hide_index=True,
                height=430,
            )

    with tabs[2]:
        if daily_events is None or daily_events.empty:
            st.info("目前沒有逐日事件。若持股來源多日未更新，這裡會維持空白。")
        else:
            status_filter = st.multiselect("逐日動作篩選", ["新增", "加碼", "減碼", "刪除"], default=["新增", "加碼", "減碼", "刪除"], key="active_etf_daily_status")
            sub = daily_events[daily_events["狀態"].isin(status_filter)].copy() if status_filter else daily_events.copy()
            show_cols = ["事件日期", "比較基準", "資料模式", "ETF代號", "狀態", "成分股代號", "成分股名稱", "產業", "持有股數_舊", "持有股數_新", "股數變化率", "權重_舊", "權重_新", "變化"]
            disp = sub[[c for c in show_cols if c in sub.columns]].copy().sort_values(["事件日期", "狀態", "變化"], ascending=[False, True, False]).head(240)
            st.dataframe(
                disp.style.set_properties(**table_style).format({"持有股數_舊": "{:,.0f}", "持有股數_新": "{:,.0f}", "股數變化率": "{:+.1%}", "權重_舊": "{:.2f}%", "權重_新": "{:.2f}%", "變化": "{:+.2f}%"}),
                use_container_width=True,
                hide_index=True,
                height=460,
            )

    with tabs[3]:
        if snapshot is None or snapshot.empty:
            st.info("目前沒有可顯示的持股快照。")
        else:
            show_cols = ["熱門名次", "ETF", "名稱", "持股數", "前十集中度", "前十大產業", "前十大個股"]
            disp = snapshot[[c for c in show_cols if c in snapshot.columns]].copy()
            st.dataframe(
                disp.style.set_properties(**table_style).format({"前十集中度": "{:.2f}%"}),
                use_container_width=True,
                hide_index=True,
                height=340,
            )


def _render_manager_visuals(summary, holdings, COLORS, table_style, history_status=None, auto_note=""):
    history_status = history_status or get_history_status(holdings, lookback_days=20)

    st.markdown("##### 主動 ETF 產業占比 / 重點持股")
    _render_industry_donut_cards(summary, COLORS, top_n=10)

    # Top 主動 ETF 產業占比 與 下方共同重倉/加減碼區塊 的垂直間距
    # 避免兩個區塊黏在一起，手機與桌機都保留呼吸感。
    st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)

    # 左右兩區改用中間 spacer，避免共同重倉股與加減碼族群靠太近
    c1, _gap, c2 = st.columns([1, 0.08, 1])
    with c1:
        st.markdown("##### 共同重倉股")
        common = summary.get("common_holdings", pd.DataFrame())
        if common is None or common.empty:
            st.info("目前 Top 主動 ETF 共同重倉不明顯。")
        else:
            common = common.copy()
            common["顯示"] = common["成分股名稱"].astype(str) + "(" + common["成分股代號"].astype(str) + ")"
            _render_bar_list(common, COLORS, "顯示", "合計權重", subtitle_col="產業", max_rows=10, signed=False)

    with c2:
        st.markdown("##### 近 30 日共同加碼 / 減碼族群")
        industry_changes = summary.get("industry_changes", pd.DataFrame())
        if industry_changes is None or industry_changes.empty:
            st.info("近 30 日產業變化資料不足。若只有單日快照，需等後續交易日累積。")
        else:
            inc = industry_changes[pd.to_numeric(industry_changes["變化"], errors="coerce").fillna(0) > 0].sort_values("變化", ascending=False).head(6)
            dec = industry_changes[pd.to_numeric(industry_changes["變化"], errors="coerce").fillna(0) < 0].sort_values("變化", ascending=True).head(6)
            if inc.empty and dec.empty:
                st.info("近 5 日產業變化不明顯。")
            else:
                if not inc.empty:
                    st.markdown("<div style='font-size:13px;font-weight:800;margin-bottom:4px;'>🟢 共同加碼族群</div>", unsafe_allow_html=True)
                    _render_bar_list(inc, COLORS, "產業", "變化", max_rows=6, signed=True)
                if not dec.empty:
                    st.markdown("<div style='font-size:13px;font-weight:800;margin:12px 0 4px 0;'>🔴 共同減碼族群</div>", unsafe_allow_html=True)
                    _render_bar_list(dec, COLORS, "產業", "變化", max_rows=6, signed=True)

    _render_etfedge_like_changes(summary, COLORS, table_style)

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    _render_manager_header_compact(summary, holdings, COLORS, history_status=history_status, auto_note=auto_note)


# =========================
# 主頁籤
# =========================

def render_etf_tab(COLORS, fm_token, industry_map, name_map, etf_holdings_url="", table_style=None):
    table_style = table_style or {"text-align": "center"}
    st.markdown("### 📈 <span class='highlight-primary'>ETF 主體倉雷達</span>", unsafe_allow_html=True)
    st.caption("ETF 區服務你的 60% 主體倉：主動/被動 ETF 分開看，綜合排名放同一張表，不再用下拉切換。")

    radar = run_etf_momentum_radar(fm_token)
    if radar.empty:
        st.warning("ETF 動能資料暫時不足。")
        active_pool = active_df = passive_df = pd.DataFrame()
    else:
        active_pool = radar[radar["類型"].eq("主動ETF")].head(5).copy()
        active_df = active_pool.head(3).copy()
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
        formatted = _format_etf_table(disp)
        ordered_cols = ["代號", "名稱", "類型", "狀態/下一步", "動能分數", "3日漲幅(%)", "5日漲幅(%)", "10日漲幅(%)", "乖離(%)", "量能比", "現價"]
        formatted = formatted[[c for c in ordered_cols if c in formatted.columns]]
        st.dataframe(formatted.style.set_properties(**table_style), use_container_width=True, hide_index=True, height=350)

    st.markdown("#### 🧭 主動 ETF 經理人風向")
    st.caption("持股快照與近 5 日變化合併；自動資料若不可得，可用側邊欄 CSV 備援。這區看產業風向，不是照抄成分股。")

    holdings = load_active_etf_holdings(etf_holdings_url) if etf_holdings_url else pd.DataFrame()
    auto_note = ""
    history_status = None
    if holdings.empty:
        manager_radar = active_pool if isinstance(active_pool, pd.DataFrame) and not active_pool.empty else radar
        auto_result = build_active_etf_manager_radar(
            manager_radar, industry_map, name_map, top_n=10, lookback_days=20,
            cache_path="active_etf_holdings_history.csv"
        )
        summary = auto_result.get("summary")
        holdings = auto_result.get("holdings", pd.DataFrame())
        auto_note = auto_result.get("message", "")
        history_status = auto_result.get("history_status")
    else:
        summary = summarize_active_etf_holdings(holdings, industry_map, name_map, top_n=10, lookback_days=20)
        history_status = get_history_status(holdings, lookback_days=20)
        auto_note = "已使用側邊欄 CSV 備援資料。"

    if holdings.empty or summary is None or summary.get("snapshot", pd.DataFrame()).empty:
        st.info(f"{auto_note or '自動持股來源目前抓不到資料。'} ETF 動能排行仍可正常使用；若要啟用經理人風向，請使用側邊欄 CSV 備援。")
    else:
        _render_manager_visuals(summary, holdings, COLORS, table_style, history_status=history_status, auto_note=auto_note)
