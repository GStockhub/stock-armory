"""mobile_ui.py

手機模式與快速沙盤 UI。
從 app.py 拆出，讓主程式只負責流程調度。
"""
from __future__ import annotations

import html
import re

import numpy as np
import pandas as pd
import streamlit as st


def _to_float_safe(v, default=0.0):
    try:
        raw = str(v).replace(",", "").strip()
        if raw in ["", "nan", "NaN", "None"]:
            return default
        m = re.search(r"-?\d+\.?\d*", raw)
        return float(m.group(0)) if m else default
    except Exception:
        return default


def _get_sandbox_grade(res, colors):
    p_now, m5, m10 = res["現價"], res["M5"], res["M10"]
    bias, win_rate, sl_price = res["乖離"], res["勝率"], res["停損價"]
    # V38：流動性優先於技術結構 —— 牛皮股再漂亮的型態都不打。
    liq_tier = str(res.get("流動性分級", "") or "")
    if liq_tier in ("地雷級", "不適合短線") or (liq_tier == "可交易" and not bool(res.get("短線可交易", True))):
        avg_lots = res.get("20日均量(張)", 0)
        grade_color, grade_text = colors["red"], "⛔ 流動性不足 (排除)"
        advice = f"20日均量僅 {avg_lots:,.0f} 張（{res.get('流動性狀態','量能不足')}）。牛皮股滑價大、想跑跑不掉，技術面再好也不列入 3-5 天波段。"
        return grade_color, grade_text, advice
    if p_now < m10:
        grade_color, grade_text = colors["red"], "🛑 嚴禁接刀 (D級)"
        advice = f"現價跌破 M10 ({m10:.1f})，短線轉弱。站不回 M5 前不追；若 M10 無止跌，等 M20 觀察。"
    elif p_now < m5:
        grade_color, grade_text = colors["accent"], "⚠️ 等站回 M5"
        advice = f"現價低於 M5 ({m5:.1f})。若 13:00 後站回 M5 且量能正常才觀察；站不回就等 M10。"
    elif bias > 7:
        grade_color, grade_text = colors["accent"], "⚠️ 追高警告 (C級)"
        advice = f"乖離 {bias:.1f}% 偏高。除非小幅突破且量能強，否則等回踩 M5。"
    elif p_now > m5 and win_rate >= 50:
        grade_color, grade_text = colors["primary"], "👑 准許出兵 (S/A級)"
        advice = f"多頭結構且回測勝率 {win_rate:.0f}%。防守底線 {sl_price:.1f}；跳空 >4.5% 不追。"
    else:
        grade_color, grade_text = colors["green"], "⚖️ 穩健觀察 (B級)"
        advice = f"結構普通，勝率 {win_rate:.0f}%。可小量試單，防守底線 {sl_price:.1f}。"
    return grade_color, grade_text, advice


def _get_fundamental_badge_safe(res, fm_token, get_fundamental_badge):
    try:
        return get_fundamental_badge(str(res.get("代號", "")), str(res.get("名稱", "")), fm_token)
    except Exception:
        return {
            "level": "unknown",
            "title": "⚪ 基本面背景：暫無資料",
            "detail": "目前無法取得完整基本面資料，先以 M5 / M10、乖離與整體風險做判斷。",
            "action": "基本面僅作輔助，不取代技術面與資金控管。",
        }


def _render_sandbox_merged_html(res, badge, grade_color, grade_text, advice, colors):
    p_now, m5, m10 = res["現價"], res["M5"], res["M10"]
    bias, win_rate = res["乖離"], res["勝率"]
    level = str((badge or {}).get("level", "neutral"))
    color_map = {
        "good": colors.get("green", "#22C55E"),
        "bad": colors.get("red", "#EF4444"),
        "warn": colors.get("accent", "#D1D5DB"),
        "etf": colors.get("primary", "#58A6FF"),
        "unknown": colors.get("subtext", "#9CA3AF"),
        "neutral": colors.get("primary", "#58A6FF"),
    }
    funda_color = color_map.get(level, colors.get("primary", "#58A6FF"))
    funda_title = html.escape(str((badge or {}).get("title", "⚪ 基本面背景：暫無資料")))
    funda_detail = html.escape(str((badge or {}).get("detail", "")))
    funda_action = html.escape(str((badge or {}).get("action", "")))
    return f"""
    <style>
        .sandbox-merged-card {{
            background-color:{colors['card']};
            border-left:5px solid {grade_color};
            padding:14px 15px;
            border-radius:9px;
            margin-bottom:10px;
        }}
        .sandbox-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:8px; flex-wrap:wrap; }}
        .sandbox-title {{ margin:0; font-size:20px; color:{colors['text']}; line-height:1.25; }}
        .sandbox-grade {{ font-weight:900; color:{grade_color}; font-size:18px; white-space:nowrap; }}
        .sandbox-stats {{ font-size:14px; color:{colors['subtext']}; margin-bottom:9px; line-height:1.7; }}
        .sandbox-advice {{ background-color:{colors['bg']}; padding:9px 10px; border-radius:7px; font-size:14px; color:{colors['text']}; margin-bottom:10px; line-height:1.55; }}
        .funda-zone {{ border-top:1px solid {colors['border']}; padding-top:9px; }}
        .funda-pill {{ display:inline-flex; align-items:center; gap:5px; max-width:100%; padding:4px 9px; border-radius:999px; border:1px solid {funda_color}; background:{colors['bg']}; color:{funda_color}; font-size:13px; font-weight:900; margin-bottom:6px; line-height:1.35; }}
        .funda-detail {{ font-size:13px; color:{colors['text']}; line-height:1.55; }}
        .funda-action {{ font-size:12.5px; color:{colors['subtext']}; line-height:1.5; margin-top:4px; }}
        @media (max-width: 640px) {{
            .sandbox-merged-card {{ padding:11px 12px; border-radius:8px; }}
            .sandbox-head {{ gap:6px; margin-bottom:6px; }}
            .sandbox-title {{ font-size:16px !important; line-height:1.25; }}
            .sandbox-grade {{ font-size:14px !important; white-space:normal; }}
            .sandbox-stats {{ font-size:12.5px !important; line-height:1.55; margin-bottom:7px; }}
            .sandbox-advice {{ font-size:12.5px !important; padding:8px; margin-bottom:8px; }}
            .funda-zone {{ padding-top:8px; }}
            .funda-pill {{ font-size:12px !important; padding:3px 8px; line-height:1.3; }}
            .funda-detail {{ font-size:12px !important; line-height:1.45; }}
            .funda-action {{ font-size:11.5px !important; line-height:1.4; }}
        }}
    </style>
    <div class="sandbox-merged-card">
        <div class="sandbox-head">
            <h4 class="sandbox-title">{html.escape(str(res['名稱']))} ({html.escape(str(res['代號']))})</h4>
            <span class="sandbox-grade">{grade_text}</span>
        </div>
        <div class="sandbox-stats">
            現價 <b style="color:{colors['text']};">{p_now:.2f}</b>｜M5 <b>{m5:.2f}</b>｜M10 <b>{m10:.2f}</b>｜乖離 <b>{bias:.1f}%</b>｜勝率 <b>{win_rate:.0f}%</b>
        </div>
        <div class="sandbox-advice">💡 <b>建議：</b>{html.escape(advice)}</div>
        <div class="funda-zone">
            <div class="funda-pill">🧱 {funda_title}</div>
            <div class="funda-detail">{funda_detail}</div>
            <div class="funda-action"><b>用法：</b>{funda_action}</div>
        </div>
    </div>
    """


def render_quick_sandbox_panel(colors, twse_name_map, fm_token, run_sandbox_sim, get_fundamental_badge):
    st.markdown("### 🔮 <span class='highlight-primary'>沙盤推演</span>", unsafe_allow_html=True)
    sim_id = st.text_input("股票代號", placeholder="例：2330 / 0052 / 3033", key="quick_sandbox_stock_id")
    c1, c2 = st.columns([1, 1])
    with c1:
        sim_btn = st.button("⚡ 執行體檢", use_container_width=True, key="quick_sandbox_btn")
    with c2:
        if st.button("🧹 清除", use_container_width=True, key="quick_sandbox_clear_btn"):
            st.session_state.pop("quick_sandbox_last_result", None)
            st.session_state.pop("quick_sandbox_last_id", None)

    if sim_btn and sim_id:
        with st.spinner("正在查詢，不載入完整主系統..."):
            res = run_sandbox_sim(str(sim_id).strip(), twse_name_map, fm_token)
            st.session_state["quick_sandbox_last_result"] = res
            st.session_state["quick_sandbox_last_id"] = str(sim_id).strip()

    res = st.session_state.get("quick_sandbox_last_result")
    if res:
        grade_color, grade_text, advice = _get_sandbox_grade(res, colors)
        badge = _get_fundamental_badge_safe(res, fm_token, get_fundamental_badge)
        st.markdown(_render_sandbox_merged_html(res, badge, grade_color, grade_text, advice, colors), unsafe_allow_html=True)


def _extract_hold_qty_cost(row):
    qty = 0.0
    cost = 0.0
    for col in row.index:
        c = str(col)
        v = row[col]
        if pd.isna(v) or str(v).strip() in ["", "nan", "None"]:
            continue
        try:
            num = float(str(v).replace(",", "").strip())
        except Exception:
            continue
        if qty <= 0 and any(k in c for k in ["庫存張數", "張數", "庫存", "股數", "數量"]):
            qty = num
        if cost <= 0 and any(k in c for k in ["成本價", "買進均價", "平均成本", "成本", "買價"]):
            cost = num
    return qty, cost


def build_mobile_holdings_view(hold_df, fee_discount, twse_name_map):
    """手機持股摘要，只給 admin 使用；guest 不會讀/顯示個人持股。"""
    if hold_df is None or hold_df.empty:
        return pd.DataFrame(), 0.0
    rows = []
    fee_rate = 0.001425 * fee_discount
    for _, r in hold_df.iterrows():
        code = str(r.get("代號", "")).strip()
        if not code:
            continue
        name = str(r.get("名稱", twse_name_map.get(code, code))).strip()
        qty, cost = _extract_hold_qty_cost(r)
        now = _to_float_safe(r.get("現價", 0), 0.0)
        m5 = _to_float_safe(r.get("M5", 0), 0.0)
        m10 = _to_float_safe(r.get("M10", 0), 0.0)
        stop = _to_float_safe(r.get("停損價", 0), 0.0)
        if now <= 0 or qty <= 0 or cost <= 0:
            pnl, ret = 0.0, 0.0
        else:
            buy_cost_total = (cost * qty * 1000) + int((cost * qty * 1000) * fee_rate)
            sell_net = (now * qty * 1000) - int((now * qty * 1000) * fee_rate) - int((now * qty * 1000) * 0.003)
            pnl = sell_net - buy_cost_total
            ret = (pnl / buy_cost_total) * 100 if buy_cost_total > 0 else 0.0
        if now <= 0:
            status, action, risk_rank = "⚪ 報價待確認", "先手動確認報價", 3
        elif m10 > 0 and now < m10:
            status, action, risk_rank = "🔴 跌破M10", "優先處理/反彈減碼", 1
        elif stop > 0 and now < stop:
            status, action, risk_rank = "🔴 破防線", "減碼/停損", 1
        elif m5 > 0 and now < m5:
            status, action, risk_rank = "🟡 跌破M5", "等站回；站不回降碼", 2
        elif ret >= 5.5:
            status, action, risk_rank = "🟢 有獲利", "可出半，剩下守M5", 4
        else:
            status, action, risk_rank = "🟢 可觀察", "守M5/ATR，不追不攤", 5
        rows.append({
            "代號": code, "名稱": name, "現價": now, "成本": cost, "張數": qty,
            "損益": pnl, "報酬%": ret, "狀態": status, "今日指令": action, "風險排序": risk_rank,
        })
    out = pd.DataFrame(rows)
    total = float(out["損益"].sum()) if not out.empty else 0.0
    if not out.empty:
        out = out.sort_values(["風險排序", "報酬%"], ascending=[True, True])
    return out, total


def render_mobile_holdings_panel(auth_status, m_df, colors, twse_name_map, fee_discount, precomputed=None):
    st.markdown("### 💼 <span class='highlight-primary'>我的持股戰情</span>", unsafe_allow_html=True)
    if auth_status != "admin_auth":
        st.info("友軍模式不顯示個人持股、成本與損益；沙盤推演與其他功能仍可使用。")
        return
    if precomputed is not None:
        hold_view, total_pnl = precomputed
    else:
        hold_view, total_pnl = build_mobile_holdings_view(m_df, fee_discount, twse_name_map)
    if hold_view.empty:
        st.info("目前沒有讀到有效持股資料，請確認 secrets / CSV 網址。")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("總淨損益", f"{total_pnl:,.0f} 元")
    with c2:
        st.metric("持股檔數", f"{len(hold_view)} 檔")
    with c3:
        weakest = hold_view.iloc[0]
        st.metric("最需處理", f"{weakest['名稱']}({weakest['代號']})", f"{weakest['報酬%']:.2f}%")
    cards = ""
    for _, r in hold_view.iterrows():
        col = colors["red"] if float(r["損益"]) > 0 else (colors["green"] if float(r["損益"]) < 0 else colors["text"])
        border = colors["red"] if int(r["風險排序"]) <= 2 else colors["primary"]
        cards += f"""
        <div style="background:{colors['card']}; border:1px solid {colors['border']}; border-left:5px solid {border}; border-radius:10px; padding:11px 12px; margin-bottom:9px;">
            <div style="display:flex; justify-content:space-between; gap:8px; align-items:flex-start;">
                <div><b style="font-size:16px; color:{colors['text']};">{html.escape(str(r['名稱']))} ({html.escape(str(r['代號']))})</b><br>
                <span style="font-size:12.5px; color:{colors['subtext']};">現價 {float(r['現價']):.2f}｜成本 {float(r['成本']):.2f}｜{float(r['張數']):g} 張/股單位</span></div>
                <div style="text-align:right; color:{col}; font-weight:900; white-space:nowrap;">{float(r['報酬%']):+.2f}%<br>{float(r['損益']):+,.0f}</div>
            </div>
            <div style="margin-top:8px; background:{colors['bg']}; border-radius:8px; padding:7px 9px; font-size:13px; color:{colors['text']}; line-height:1.45;">
                <b>{html.escape(str(r['狀態']))}</b>｜{html.escape(str(r['今日指令']))}
            </div>
        </div>
        """
    st.markdown(cards, unsafe_allow_html=True)


def _macro_light(macro_score, overheat_flag):
    """把大盤環境濃縮成一顆紅綠燈。"""
    try:
        score = float(macro_score)
    except Exception:
        score = np.nan
    if overheat_flag:
        return "🟡", "大盤過熱", "指數乖離偏高，只出半量、拉高停損紀律。"
    if np.isnan(score):
        return "⚪", "環境未知", "大盤資料未取得，先以個股結構與停損為準。"
    if score >= 70:
        return "🟢", "環境有利", "多頭環境，按模式正常出兵。"
    if score >= 45:
        return "🟡", "環境中性", "選股不選市，只打 S/A 與沙盤通過的球。"
    return "🔴", "環境不利", "空方環境，今日以觀望與持股防守為主。"


def _today_top_candidates(max_n=3):
    """從訊號追蹤室讀今日已保存的 S/A/B 快照前幾名（不觸發掃描，維持手機模式輕量）。"""
    try:
        import signal_tracker
        from datetime import datetime as _dt
        hist, _ = signal_tracker.load_signal_history()
        if hist is None or hist.empty:
            return pd.DataFrame(), False
        today = _dt.now().strftime("%Y-%m-%d")
        t = hist[(hist["日期"] == today) & (hist["類型"].isin(["S級", "A級", "B級"]))].copy()
        if t.empty:
            return pd.DataFrame(), True
        order = {"S級": 0, "A級": 1, "B級": 2}
        t["_o"] = t["類型"].map(order)
        t["分數"] = pd.to_numeric(t["分數"], errors="coerce")
        return t.sort_values(["_o", "分數"], ascending=[True, False]).head(max_n), True
    except Exception:
        return pd.DataFrame(), False


def render_mobile_command_brief(colors, macro_score, overheat_flag, hold_view, auth_status):
    """三秒決策區：① 大盤紅綠燈 ② 持股警報 ③ 今日候選前三。"""
    icon, title, advice = _macro_light(macro_score, overheat_flag)

    # ① 大盤紅綠燈（最大的一張卡）
    st.markdown(f"""
    <div style="background:{colors['card']}; border:1px solid {colors['border']}; border-radius:14px; padding:14px 16px; margin-bottom:10px; text-align:center;">
        <div style="font-size:34px; line-height:1;">{icon}</div>
        <div style="font-size:17px; font-weight:900; color:{colors['text']}; margin-top:4px;">{title}</div>
        <div style="font-size:13px; color:{colors['subtext']}; margin-top:3px;">{advice}</div>
    </div>
    """, unsafe_allow_html=True)

    # ② 持股警報（admin 才有持股資料）
    if auth_status == "admin_auth" and hold_view is not None and not hold_view.empty:
        alerts = hold_view[hold_view["風險排序"] <= 2]
        if not alerts.empty:
            worst = alerts.iloc[0]
            body = "、".join(f"{r['名稱']}({r['代號']})" for _, r in alerts.head(3).iterrows())
            st.markdown(f"""
            <div style="background:{colors['card']}; border:1px solid {colors['red']}; border-left:6px solid {colors['red']}; border-radius:12px; padding:11px 14px; margin-bottom:10px;">
                <b style="color:{colors['red']};">🚨 持股警報：{len(alerts)} 檔需處理</b>
                <div style="font-size:13.5px; color:{colors['text']}; margin-top:4px;">{html.escape(body)}</div>
                <div style="font-size:12.5px; color:{colors['subtext']}; margin-top:3px;">最優先：{html.escape(str(worst['名稱']))} — {html.escape(str(worst['今日指令']))}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:{colors['card']}; border:1px solid {colors['border']}; border-left:6px solid {colors['green']}; border-radius:12px; padding:10px 14px; margin-bottom:10px;">
                <b style="color:{colors['green']};">✅ 持股防線完整</b>
                <span style="font-size:13px; color:{colors['subtext']};">　{len(hold_view)} 檔皆守在均線之上，照 SOP 續抱。</span>
            </div>
            """, unsafe_allow_html=True)

    # ③ 今日候選前三（讀已保存快照，不觸發掃描）
    cands, loaded = _today_top_candidates(3)
    if not cands.empty:
        chips = ""
        for _, r in cands.iterrows():
            chips += f"""<span style="display:inline-block; background:{colors['bg']}; border:1px solid {colors['border']}; border-radius:99px; padding:4px 11px; margin:2px 4px 2px 0; font-size:13px; color:{colors['text']};"><b>{html.escape(str(r['類型']))}</b>　{html.escape(str(r['名稱']))}({html.escape(str(r['代號']))})</span>"""
        st.markdown(f"""
        <div style="background:{colors['card']}; border:1px solid {colors['border']}; border-radius:12px; padding:10px 14px; margin-bottom:6px;">
            <b style="color:{colors['text']}; font-size:14px;">🎯 今日候選</b><div style="margin-top:6px;">{chips}</div>
            <div style="font-size:12px; color:{colors['subtext']}; margin-top:5px;">想深入哪一檔？把代號貼進下方沙盤體檢。</div>
        </div>
        """, unsafe_allow_html=True)
    elif loaded:
        st.caption("今日尚未保存作戰快照；回到桌面版掃描後按「保存今日作戰快照」，這裡就會出現候選名單。")


def render_mobile_battle_room(colors, twse_name_map, fm_token, run_sandbox_sim, get_fundamental_badge, auth_status, m_df, fee_discount, macro_score=None, overheat_flag=False):
    st.markdown("<h1 style='text-align: center;' class='highlight-primary'>📱 手機模式</h1>", unsafe_allow_html=True)

    # 持股視圖只算一次，決策區與持股面板共用
    hold_view, total_pnl = (pd.DataFrame(), 0.0)
    if auth_status == "admin_auth":
        hold_view, total_pnl = build_mobile_holdings_view(m_df, fee_discount, twse_name_map)

    # ── ① 三秒決策區：先回答「今天能不能出手、有沒有火要滅」 ──
    render_mobile_command_brief(colors, macro_score, overheat_flag, hold_view, auth_status)

    # ── ② 沙盤推演：臨場查單檔 ──
    st.markdown("<hr style='margin: 8px 0 14px 0; border-color: " + colors["border"] + ";'>", unsafe_allow_html=True)
    render_quick_sandbox_panel(colors, twse_name_map, fm_token, run_sandbox_sim, get_fundamental_badge)

    # ── ③ 持股戰情細節 ──
    st.markdown("<hr style='margin: 10px 0 18px 0; border-color: " + colors["border"] + ";'>", unsafe_allow_html=True)
    render_mobile_holdings_panel(auth_status, m_df, colors, twse_name_map, fee_discount,
                                 precomputed=(hold_view, total_pnl) if auth_status == "admin_auth" else None)
