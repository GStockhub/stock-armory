import html
import json
import math
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from etf_engine import load_active_etf_holdings, run_etf_momentum_radar, summarize_active_etf_holdings
from active_etf_holdings import get_history_status


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


@st.cache_data(ttl=300, show_spinner=False)
def _load_local_active_etf_history(path="data/active_etf_holdings_history.csv"):
    """V37.9.1：ETF 經理人風向只讀本機 ETL 產物，不在頁面載入時即時爬官方/第三方。"""
    if not os.path.exists(path):
        return pd.DataFrame()
    return load_active_etf_holdings(path)


@st.cache_data(ttl=300, show_spinner=False)
def _load_local_etl_report(path="data/active_etf_etl_report.json"):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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
    """V37.7：本週熱門主動 ETF 持股總覽，用情報卡呈現，不再堆表格。"""
    snapshot = summary.get("snapshot", pd.DataFrame())
    quality = summary.get("quality", pd.DataFrame())
    if snapshot is None or snapshot.empty:
        st.info("目前沒有可顯示的熱門 ETF 持股總覽。")
        return

    st.markdown("##### 🔥 本週熱門主動 ETF 持股總覽")
    st.caption("顯示本週熱門 Top N 的目前持股狀況：持股數、集中度、前幾大產業與前五大重倉。資料不完整者不納入共同動作。")

    rows = snapshot.copy().head(top_n)
    for start_idx in range(0, len(rows), 2):
        cols = st.columns(min(2, len(rows) - start_idx))
        for col, (_, r) in zip(cols, rows.iloc[start_idx:start_idx+2].iterrows()):
            code = str(r.get("ETF", ""))
            name = str(r.get("名稱", code))
            rank = r.get("熱門名次", "-")
            hold_cnt = r.get("持股數", "-")
            conc = r.get("前十集中度", "-")
            industries = str(r.get("前十大產業", "")) or "資料不足"
            stocks = str(r.get("前十大個股", "")) or "資料不足"
            q_note = ""
            if quality is not None and not quality.empty and "ETF代號" in quality.columns:
                q = quality[quality["ETF代號"].astype(str).eq(code)]
                if not q.empty:
                    q_note = f"{q.iloc[0].get('資料狀態','')}｜{q.iloc[0].get('資料備註','')}"
            with col:
                st.markdown(f"""
                <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['primary']}; border-radius:12px; padding:13px 15px; margin:8px 0 14px 0; min-height:210px;">
                    <div style="font-size:12px; color:{COLORS['subtext']}; font-weight:800;">#{_safe_text(rank)}｜{_safe_text(code)}</div>
                    <div style="font-size:18px; font-weight:900; color:{COLORS['text']}; margin:3px 0 8px 0;">{_safe_text(name)}</div>
                    <div style="display:flex; gap:10px; flex-wrap:wrap; font-size:13px; color:{COLORS['text']}; margin-bottom:8px;">
                        <span><b>持股數</b> {_safe_text(hold_cnt)}</span>
                        <span><b>集中度</b> {_safe_text(conc)}%</span>
                    </div>
                    <div style="font-size:13px; line-height:1.55; color:{COLORS['text']};"><b>產業：</b>{_safe_text(industries)}</div>
                    <div style="font-size:13px; line-height:1.55; color:{COLORS['text']}; margin-top:6px;"><b>重倉：</b>{_safe_text(stocks)}</div>
                    <div style="font-size:12px; color:{COLORS['subtext']}; margin-top:8px;">{_safe_text(q_note)}</div>
                </div>
                """, unsafe_allow_html=True)

    incomplete = summary.get("incomplete_holdings", pd.DataFrame())
    if incomplete is not None and not incomplete.empty:
        with st.expander("⚠️ 自動來源不完整名單", expanded=False):
            st.dataframe(incomplete.style.set_properties(**{"text-align": "center"}), use_container_width=True, hide_index=True, height=220)


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
    """V37.9.1：只顯示本機 ETL report，不在頁面載入時打 GitHub API 診斷。"""
    history_status = history_status or get_history_status(holdings, lookback_days=20)
    days = int(history_status.get("days", 0) or 0)
    latest = str(history_status.get("latest", "-") or "-")
    msg = str(history_status.get("message", "") or "")
    snapshot = summary.get("snapshot", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    etf_count = int(snapshot["ETF"].nunique()) if snapshot is not None and not snapshot.empty and "ETF" in snapshot.columns else 0
    changes = summary.get("changes", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    event_count = int(len(changes)) if changes is not None and not changes.empty else 0
    report = _load_local_etl_report()
    run_at = report.get("run_at", "-") if isinstance(report, dict) else "-"
    complete_etfs = report.get("complete_etfs", []) if isinstance(report, dict) else []
    raw_rows = report.get("raw_rows", "-") if isinstance(report, dict) else "-"
    complete_rows = report.get("complete_rows", "-") if isinstance(report, dict) else "-"
    auto_text = str(auto_note or "已讀取本機 ETL 歷史快照；官方抓取交給 GitHub Actions，不在前端即時執行。")
    compact_msg = msg.replace("｜", "；")

    title = f"🧭 主動 ETF 風向狀態｜快照 {days} 日｜最新 {latest}｜涵蓋 {etf_count} 檔｜事件 {event_count} 筆｜ETL {run_at}"
    with st.expander(title, expanded=False):
        st.markdown(f"""
        <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['primary']}; padding:10px 13px; border-radius:10px; margin:4px 0 10px 0;">
            <div style="font-size:14px; color:{COLORS['text']}; line-height:1.65;"><b>狀態：</b>{_safe_text(auto_text)}</div>
            <div style="font-size:12px; color:{COLORS['subtext']}; line-height:1.45; margin-top:3px;">{_safe_text(compact_msg)}</div>
            <div style="font-size:12px; color:{COLORS['subtext']}; line-height:1.45; margin-top:3px;">ETL：raw {raw_rows}｜complete {complete_rows}｜完整 ETF：{_safe_text('、'.join(map(str, complete_etfs)) if complete_etfs else '-')}</div>
        </div>
        """, unsafe_allow_html=True)
        health = report.get("etl_health", []) if isinstance(report, dict) else []
        if health:
            st.markdown("##### 🚦 ETL 健康燈號")
            hdf = pd.DataFrame(health)
            cols = ["ETF代號", "ETF名稱", "投信", "健康燈號", "連續失敗天數", "最後成功日期", "資料過期天數", "需要Playwright", "最後狀態"]
            st.dataframe(hdf[[c for c in cols if c in hdf.columns]], use_container_width=True, hide_index=True, height=260)
        quality = report.get("quality", []) if isinstance(report, dict) else []
        if quality:
            st.markdown("##### 📋 快照完整度")
            st.dataframe(pd.DataFrame(quality), use_container_width=True, hide_index=True, height=260)


def _action_items_html(df, COLORS, title, icon, max_rows=8):
    if df is None or df.empty:
        return f"<div style='color:{COLORS['subtext']}; font-size:13px;'>近 30 天沒有共同{title}。</div>"
    blocks = []
    for i, (_, r) in enumerate(df.head(max_rows).iterrows(), start=1):
        stock = f"{r.get('成分股名稱','')}({r.get('成分股代號','')})"
        etfs = str(r.get('涉及ETF', ''))
        etf_cnt = r.get('ETF數', '-')
        event_cnt = r.get('事件數', '-')
        change = r.get('合計變化', 0)
        try:
            change_txt = f"{float(change):+.2f}%"
        except Exception:
            change_txt = str(change)
        shares = r.get('合計股數變化', '')
        try:
            shares_txt = f"｜{float(shares):+,.0f} 股" if str(shares) not in ['', 'nan', 'None'] else ''
        except Exception:
            shares_txt = ''
        blocks.append(
            f"<div style='border-bottom:1px solid rgba(128,128,128,.18); padding:7px 0;'>"
            f"<div style='font-weight:900; color:{COLORS['text']}; font-size:13.5px;'>{i}. {_safe_text(stock)}</div>"
            f"<div style='color:{COLORS['subtext']}; font-size:12.5px; line-height:1.45;'>{_safe_text(r.get('產業',''))}｜{etf_cnt} 檔 ETF｜{event_cnt} 事件｜{change_txt}{shares_txt}</div>"
            f"<div style='color:{COLORS['subtext']}; font-size:12px; line-height:1.45;'>涉及：{_safe_text(etfs)}</div>"
            f"</div>"
        )
    return "".join(blocks)


def _render_etfedge_like_changes(summary, COLORS, table_style):
    changes = summary.get("changes", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    daily_events = summary.get("daily_events", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    shared_actions = summary.get("shared_actions", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    snapshot = summary.get("snapshot", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    hot_etfs = summary.get("hot_etfs", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()
    meta = summary.get("meta", pd.DataFrame()) if isinstance(summary, dict) else pd.DataFrame()

    st.markdown("##### 📡 主動 ETF 經理人調倉雷達")
    st.caption("共同動作與逐日明細已合併：主畫面固定顯示新增、加碼、減碼、刪除四種動作，不用篩選器，避免每點一次就重跑。")

    if meta is not None and not meta.empty:
        m = meta.iloc[0].to_dict()
        st.caption(f"資料意義：{m.get('資料意義','')}｜門檻：{m.get('事件門檻','')}｜完整度：{m.get('完整度門檻','')}｜事件 {m.get('事件明細','')}")

    if hot_etfs is not None and not hot_etfs.empty:
        hot_txt = "、".join([f"{r['ETF代號']}" for _, r in hot_etfs.head(10).iterrows()])
        st.markdown(f"<div style='font-size:13px; color:{COLORS['subtext']}; margin:4px 0 10px 0;'>🔥 本週追蹤：{_safe_text(hot_txt)}</div>", unsafe_allow_html=True)

    basis = "尚無逐日變化"
    if changes is not None and not changes.empty and "比較基準" in changes.columns:
        basis = str(changes["比較基準"].iloc[0])
    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['primary']}; padding:10px 13px; border-radius:9px; margin:8px 0 12px 0;">
        <b>最新比較基準：</b>{_safe_text(basis)}
    </div>
    """, unsafe_allow_html=True)

    scope = daily_events if daily_events is not None and not daily_events.empty else changes
    counts = {k: 0 for k in ["新增", "加碼", "減碼", "刪除"]}
    if scope is not None and not scope.empty and "狀態" in scope.columns:
        counts = {k: int((scope["狀態"] == k).sum()) for k in counts}

    cc = st.columns(4)
    for col, (label, val) in zip(cc, [("🆕 新增", counts["新增"]), ("➕ 加碼", counts["加碼"]), ("➖ 減碼", counts["減碼"]), ("❌ 刪除", counts["刪除"])]):
        with col:
            st.metric(label, f"{val} 筆")

    if shared_actions is None or shared_actions.empty:
        st.info("近 30 天沒有 2 檔以上主動 ETF 對同一個股出現同步動作；或目前完整快照不足。")
    else:
        action_order = [("新增", "🆕"), ("加碼", "➕"), ("減碼", "➖"), ("刪除", "❌")]
        for row_start in range(0, 4, 2):
            cols = st.columns(2)
            for col, (status, icon) in zip(cols, action_order[row_start:row_start+2]):
                sub = shared_actions[shared_actions["狀態"].astype(str).eq(status)].copy()
                if not sub.empty:
                    sort_col = "合計股數變化" if "合計股數變化" in sub.columns else "合計變化"
                    sub["_sort"] = pd.to_numeric(sub.get(sort_col, 0), errors="coerce").abs().fillna(0)
                    sub = sub.sort_values(["ETF數", "事件數", "_sort"], ascending=[False, False, False])
                with col:
                    card_html = (
                        f"<div style='background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-radius:12px; padding:12px 14px; margin:8px 0 14px 0; min-height:260px;'>"
                        f"<div style='font-size:16px; font-weight:900; color:{COLORS['text']}; margin-bottom:6px;'>{icon} 共同{status} Top 8</div>"
                        + _action_items_html(sub, COLORS, status, icon, max_rows=8)
                        + "</div>"
                    )
                    st.markdown(card_html, unsafe_allow_html=True)

    with st.expander("📋 展開逐日明細 / ETF 快照", expanded=False):
        tab1, tab2, tab3 = st.tabs(["逐日事件", "ETF快照", "熱門Top10"])
        with tab1:
            if daily_events is None or daily_events.empty:
                st.info("目前沒有逐日事件。若持股來源多日未更新，這裡會維持空白。")
            else:
                show_cols = ["事件日期", "比較基準", "資料模式", "ETF代號", "狀態", "成分股代號", "成分股名稱", "產業", "持有股數_舊", "持有股數_新", "股數變化率", "權重_舊", "權重_新", "變化"]
                disp = daily_events[[c for c in show_cols if c in daily_events.columns]].copy().sort_values(["事件日期", "狀態", "變化"], ascending=[False, True, False]).head(240)
                st.dataframe(disp.style.set_properties(**table_style).format({"持有股數_舊": "{:,.0f}", "持有股數_新": "{:,.0f}", "股數變化率": "{:+.1%}", "權重_舊": "{:.2f}%", "權重_新": "{:.2f}%", "變化": "{:+.2f}%"}), use_container_width=True, hide_index=True, height=440)
        with tab2:
            if snapshot is None or snapshot.empty:
                st.info("目前沒有 ETF 快照。")
            else:
                show_cols = ["熱門名次", "ETF", "名稱", "持股數", "前十集中度", "前十大產業", "前十大個股"]
                disp = snapshot[[c for c in show_cols if c in snapshot.columns]].copy()
                st.dataframe(disp.style.set_properties(**table_style).format({"前十集中度": "{:.2f}%"}), use_container_width=True, hide_index=True, height=340)
        with tab3:
            if hot_etfs is None or hot_etfs.empty:
                st.info("目前沒有熱門 ETF 清單。")
            else:
                show_cols = ["熱門名次", "ETF代號", "ETF名稱", "熱門分數", "權重合計", "持股數", "動能分數"]
                disp_hot = hot_etfs[[c for c in show_cols if c in hot_etfs.columns]].copy()
                st.dataframe(disp_hot.style.set_properties(**table_style).format({"熱門分數": "{:.1f}", "權重合計": "{:.1f}", "動能分數": "{:.1f}"}), use_container_width=True, hide_index=True, height=260)


def _render_manager_visuals(summary, holdings, COLORS, table_style, history_status=None, auto_note=""):
    history_status = history_status or get_history_status(holdings, lookback_days=20)

    _render_industry_donut_cards(summary, COLORS, top_n=10)
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
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
    st.caption("V37.9.1 速度瘦身：前端只讀 GitHub Actions 產出的 history / CSV，不再即時爬官方或第三方來源。")

    holdings = pd.DataFrame()
    auto_note = ""

    # 使用者若在側邊欄指定 CSV，優先讀側邊欄 CSV；否則讀 GitHub Actions 產出的本機 history。
    if etf_holdings_url:
        holdings = load_active_etf_holdings(etf_holdings_url)
        if not holdings.empty:
            auto_note = "已使用側邊欄 CSV 備援資料。"
    else:
        holdings = _load_local_active_etf_history("data/active_etf_holdings_history.csv")
        if not holdings.empty:
            auto_note = "已使用 GitHub Actions / 官方公告 ETL 產出的本機歷史快照。"

    summary = summarize_active_etf_holdings(holdings, industry_map, name_map, top_n=10, lookback_days=20) if not holdings.empty else None
    history_status = get_history_status(holdings, lookback_days=20) if not holdings.empty else None

    if holdings.empty or summary is None or summary.get("snapshot", pd.DataFrame()).empty:
        st.info("目前沒有可用的主動 ETF history。ETF 動能排行仍可正常使用；官方持股更新請交給 GitHub Actions，不在前端即時抓取。")
    else:
        _render_manager_visuals(summary, holdings, COLORS, table_style, history_status=history_status, auto_note=auto_note)
