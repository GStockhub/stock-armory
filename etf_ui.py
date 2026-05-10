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


def _render_industry_donut_cards(summary, COLORS, top_n=5):
    industries = summary.get("industries", pd.DataFrame())
    snapshot = summary.get("snapshot", pd.DataFrame())
    if industries is None or industries.empty or snapshot is None or snapshot.empty:
        st.info("產業占比資料不足。")
        return

    # 依 snapshot 順序顯示，最多 5 張，手機會自動換行。
    rows = []
    for _, snap in snapshot.head(top_n).iterrows():
        code = str(snap.get("ETF", ""))
        name = str(snap.get("名稱", code))
        sub = industries[industries["ETF代號"].astype(str).eq(code)].copy()
        if sub.empty:
            continue
        sub["權重"] = pd.to_numeric(sub["權重"], errors="coerce").fillna(0)
        sub = sub.sort_values("權重", ascending=False).head(5)
        rows.append((code, name, sub))

    if not rows:
        st.info("產業占比資料不足。")
        return

    for start in range(0, len(rows), 3):
        cols = st.columns(min(3, len(rows) - start))
        for col, (code, name, sub) in zip(cols, rows[start:start+3]):
            labels = sub["產業"].astype(str).tolist()
            weights = sub["權重"].astype(float).tolist()
            gradient = _donut_gradient(weights)
            legend = "".join(
                f"<div style='display:flex; justify-content:space-between; gap:8px; font-size:12.5px; margin:3px 0;'>"
                f"<span style='white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'><span style='display:inline-block;width:9px;height:9px;border-radius:50%;background:{_DONUT_COLORS[i % len(_DONUT_COLORS)]};margin-right:5px;'></span>{_safe_text(label)}</span>"
                f"<b>{weight:.1f}%</b></div>"
                for i, (label, weight) in enumerate(zip(labels, weights))
            )
            with col:
                st.markdown(f"""
                <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-radius:10px; padding:13px 14px; min-height:275px;">
                    <div style="font-size:13px; color:{COLORS['subtext']}; font-weight:700;">主動 ETF 產業占比</div>
                    <div style="font-size:18px; font-weight:900; color:{COLORS['text']}; margin:3px 0 10px 0;">{_safe_text(name)} <span style="white-space:nowrap;">({_safe_text(code)})</span></div>
                    <div style="width:118px; height:118px; border-radius:50%; margin:4px auto 12px auto; background:conic-gradient({gradient}); position:relative; box-shadow:inset 0 0 0 1px rgba(0,0,0,.05);">
                        <div style="position:absolute; inset:28px; border-radius:50%; background:{COLORS['card']}; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:800; color:{COLORS['subtext']};">Top 5</div>
                    </div>
                    {legend}
                </div>
                """, unsafe_allow_html=True)


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
    history_status = history_status or get_history_status(holdings, lookback_days=5)
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
    auto_text = _safe_text(auto_note or "自動持股來源正常；若 GitHub 寫入失敗則先沿用本機快取。")
    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['primary']}; padding:12px 14px; border-radius:10px; margin:6px 0 14px 0;">
        <div style="display:flex; flex-wrap:wrap; gap:14px; align-items:flex-start;">
            <div style="flex:1 1 260px; min-width:220px;">
                <div style="font-size:13px; color:{COLORS['subtext']}; font-weight:800;">⚙️ 自動更新狀態</div>
                <div style="font-size:14px; color:{COLORS['text']}; line-height:1.55; margin-top:4px;">{auto_text}</div>
            </div>
            <div style="flex:1 1 220px; min-width:200px; border-left:1px solid {COLORS['border']}; padding-left:12px;">
                <div style="font-size:13px; color:{COLORS['subtext']}; font-weight:800;">📦 歷史快照</div>
                <div style="font-size:14px; color:{COLORS['text']}; line-height:1.55; margin-top:4px;">{days} 個交易日｜最新 { _safe_text(latest) }<br>涵蓋 {etf_count} 檔主動 ETF｜事件 {event_count} 筆</div>
                <div style="font-size:12px; color:{COLORS['subtext']}; margin-top:4px;">{_safe_text(msg)}</div>
            </div>
            <div style="flex:1 1 220px; min-width:200px; border-left:1px solid {COLORS['border']}; padding-left:12px;">
                <div style="font-size:13px; color:{COLORS['subtext']}; font-weight:800;">🧪 GitHub 歷史庫</div>
                <div style="font-size:14px; color:{COLORS['text']}; line-height:1.55; margin-top:4px;">{_safe_text(gh_summary)}</div>
                <div style="font-size:12px; color:{COLORS['subtext']}; margin-top:4px;">只顯示 repo / branch / path / HTTP 狀態，不顯示 token。</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    if gh_diag:
        with st.expander("🧪 查看 GitHub 歷史庫診斷細節", expanded=False):
            checks = gh_diag.get("checks", [])
            if checks:
                st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)
            else:
                st.json({k: v for k, v in gh_diag.items() if k != "checks"})


def _render_etfedge_like_changes(summary, COLORS, table_style):
    changes = summary.get("changes", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    snapshot = summary.get("snapshot", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    st.markdown("##### 📋 ETF 持股事件總覽（濃縮版）")
    if changes is None or changes.empty:
        counts = {"新增": 0, "刪除": 0, "加碼": 0, "減碼": 0}
    else:
        counts = {k: int((changes["狀態"] == k).sum()) for k in ["新增", "刪除", "加碼", "減碼"]}
    cc = st.columns(4)
    metric_specs = [("🆕 新增", counts.get("新增", 0)), ("➕ 加碼", counts.get("加碼", 0)), ("➖ 減碼", counts.get("減碼", 0)), ("❌ 刪除", counts.get("刪除", 0))]
    for col, (label, val) in zip(cc, metric_specs):
        with col:
            st.metric(label, f"{val} 筆")

    tabs = st.tabs(["📦 快照總覽", "🆕 新增", "➕ 加碼", "➖ 減碼", "❌ 刪除"])
    with tabs[0]:
        if snapshot is None or snapshot.empty:
            st.info("目前沒有可顯示的持股快照。")
        else:
            show_cols = ["ETF", "名稱", "持股數", "前十集中度", "前十大產業", "前十大個股"]
            disp = snapshot[[c for c in show_cols if c in snapshot.columns]].copy()
            st.dataframe(disp.style.set_properties(**table_style).format({"前十集中度":"{:.2f}%"}), use_container_width=True, hide_index=True, height=280)

    for tab, status in zip(tabs[1:], ["新增", "加碼", "減碼", "刪除"]):
        with tab:
            if changes is None or changes.empty:
                st.info("近 5 日沒有明顯持股變化，或資料只有單一日期。")
                continue
            sub = changes[changes["狀態"].eq(status)].copy()
            if sub.empty:
                st.info(f"目前沒有『{status}』事件。")
                continue
            if status == "新增":
                sub = sub.sort_values(["權重_新", "變化"], ascending=[False, False])
            elif status == "刪除":
                sub = sub.sort_values(["權重_舊", "變化"], ascending=[False, True])
            elif status == "加碼":
                sub = sub.sort_values("變化", ascending=False)
            else:
                sub = sub.sort_values("變化", ascending=True)
            show_cols = ["比較基準", "ETF代號", "成分股代號", "成分股名稱", "產業", "狀態", "權重_舊", "權重_新", "變化"]
            disp = sub[[c for c in show_cols if c in sub.columns]].head(120).copy()
            st.dataframe(disp.style.set_properties(**table_style).format({"權重_舊":"{:.2f}%", "權重_新":"{:.2f}%", "變化":"{:+.2f}%"}), use_container_width=True, hide_index=True, height=420)


def _render_manager_visuals(summary, holdings, COLORS, table_style, history_status=None, auto_note=""):
    history_status = history_status or get_history_status(holdings, lookback_days=5)
    _render_manager_header_compact(summary, holdings, COLORS, history_status=history_status, auto_note=auto_note)

    st.markdown("##### Top 主動 ETF 產業占比")
    _render_industry_donut_cards(summary, COLORS, top_n=5)

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
        st.markdown("##### 近 5 日共同加碼 / 減碼族群")
        industry_changes = summary.get("industry_changes", pd.DataFrame())
        if industry_changes is None or industry_changes.empty:
            st.info("近 5 日產業變化資料不足。若只有單日快照，需等後續交易日累積。")
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
        formatted = _format_etf_table(disp)
        st.dataframe(formatted.style.set_properties(**table_style), use_container_width=True, hide_index=True, height=390)

    st.markdown("#### 🧭 主動 ETF 經理人風向")
    st.caption("持股快照與近 5 日變化合併；自動資料若不可得，可用側邊欄 CSV 備援。這區看產業風向，不是照抄成分股。")

    holdings = load_active_etf_holdings(etf_holdings_url) if etf_holdings_url else pd.DataFrame()
    auto_note = ""
    history_status = None
    if holdings.empty:
        auto_result = build_active_etf_manager_radar(
            radar, industry_map, name_map, top_n=5, lookback_days=5,
            cache_path="active_etf_holdings_history.csv"
        )
        summary = auto_result.get("summary")
        holdings = auto_result.get("holdings", pd.DataFrame())
        auto_note = auto_result.get("message", "")
        history_status = auto_result.get("history_status")
    else:
        summary = summarize_active_etf_holdings(holdings, industry_map, name_map, top_n=5, lookback_days=5)
        history_status = get_history_status(holdings, lookback_days=5)
        auto_note = "已使用側邊欄 CSV 備援資料。"

    if holdings.empty or summary is None or summary.get("snapshot", pd.DataFrame()).empty:
        st.info(f"{auto_note or '自動持股來源目前抓不到資料。'} ETF 動能排行仍可正常使用；若要啟用經理人風向，請使用側邊欄 CSV 備援。")
    else:
        if auto_note:
            st.success(auto_note)
        _render_manager_visuals(summary, holdings, COLORS, table_style, history_status=history_status, auto_note=auto_note)

    with st.expander("📌 ETF 雷達使用說明", expanded=False):
        st.markdown("""
        * **主動 / 被動 Top 3**：直接同屏比較，不再切換下拉，避免手機與 Streamlit 重跑卡頓。  
        * **ETF 綜合 Top 10**：主動與被動混合排序，實際主體倉只挑 1～3 檔，不是 Top 10 全買。  
        * **主動 ETF 經理人風向**：看產業占比、共同重倉與加減碼族群，不代表直接照抄成分股。  
        * **歷史快照**：自動快照會寫入本機與 session；若 Streamlit Cloud 重新部署導致歷史遺失，可用側邊欄 CSV 做持久化備援。  
        """)
