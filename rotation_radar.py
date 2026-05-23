"""rotation_radar.py

產業輪動雷達。
從 app.py 拆出，降低主程式體積；邏輯維持 V36 樣本數/可信度校正。
"""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st


def build_industry_rotation_table(source_df, twse_ind_map, macro_df=None):
    """依產業聚合熱度與輪動升溫訊號。"""
    if source_df is None or source_df.empty or "代號" not in source_df.columns:
        return pd.DataFrame()
    df = source_df.copy()
    if "產業" not in df.columns:
        df["產業"] = df["代號"].astype(str).map(lambda x: twse_ind_map.get(x, "未分類"))
    df["產業"] = df["產業"].replace("", "未分類").fillna("未分類")
    for c in ["日漲幅(%)", "3日漲幅(%)", "5日漲幅(%)", "vol_ratio", "安全指數", "三大法人合計", "投信(張)", "現價", "M5", "M10", "乖離(%)"]:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df = df[~df["代號"].astype(str).str.startswith("00")].copy()
    if df.empty:
        return pd.DataFrame()
    rows = []
    for ind, g in df.groupby("產業"):
        sample_n = int(len(g))
        if sample_n < 2:
            continue
        avg_day = float(g["日漲幅(%)"].mean())
        avg_3d = float(g["3日漲幅(%)"].mean())
        avg_5d = float(g["5日漲幅(%)"].mean())
        up_ratio = float((g["日漲幅(%)"] > 0).mean())
        avg_vol = float(g["vol_ratio"].replace([np.inf, -np.inf], np.nan).fillna(1).clip(0, 5).mean())
        strong_count = int(((g["現價"] > g["M5"]) & (g["M5"] >= g["M10"]) & (g["vol_ratio"] >= 1.2)).sum())
        breakout_count = int((g["戰術型態"].astype(str).str.contains("爆量|多頭", na=False)).sum()) if "戰術型態" in g.columns else strong_count
        inst = float(g["三大法人合計"].sum())
        trust = float(g["投信(張)"].sum())

        hot_raw = 0
        hot_raw += min(max(avg_day, -2), 4) * 8
        hot_raw += up_ratio * 22
        hot_raw += min(avg_vol, 3) * 12
        hot_raw += min(strong_count, 5) * 5
        hot_raw += min(breakout_count, 4) * 5
        if inst > 0: hot_raw += 6
        if trust > 0: hot_raw += 5

        if sample_n >= 10:
            confidence, confidence_note, sample_weight = "高", "樣本充足", 1.00
        elif sample_n >= 5:
            confidence, confidence_note, sample_weight = "中", "樣本普通", 0.90
        elif sample_n >= 3:
            confidence, confidence_note, sample_weight = "低", "樣本偏少，降權觀察", 0.76
        else:
            confidence, confidence_note, sample_weight = "低", "樣本過少，只列觀察", 0.62

        hot_score = max(0, min(100, hot_raw * sample_weight))
        rotation_delta = (avg_3d - avg_5d) + max(avg_day, 0) + max(avg_vol - 1, 0) * 2 + up_ratio * 3
        if avg_day >= 0 and avg_vol >= 1.2 and up_ratio >= 0.5:
            rotation_delta += 3

        if sample_n < 3 and hot_score >= 55:
            state, advice = "🟡 潛伏觀察", "樣本太少，不升主戰場；只加入雷達"
        elif hot_score >= 75 and rotation_delta >= 0 and sample_n >= 5:
            state, advice = "🔥 主戰場", "只做龍頭回測，不追第三根"
        elif 45 <= hot_score < 75 and rotation_delta >= 4 and up_ratio >= 0.5:
            state, advice = "🟠 資金升溫", "可找族群強股小倉試單"
        elif hot_score < 55 and rotation_delta >= 5 and avg_vol >= 1.2:
            state, advice = "🟡 潛伏觀察", "加入雷達，等突破確認"
        elif hot_score >= 55 and rotation_delta <= -3:
            state, advice = "⚠️ 退潮警戒", "反彈不追，持股偏降碼"
        else:
            state, advice = "⚪ 普通", "不優先"

        leaders = g.sort_values(["安全指數", "vol_ratio"], ascending=[False, False]).head(3)
        leader_txt = "、".join((leaders["名稱"].astype(str) + "(" + leaders["代號"].astype(str) + ")").tolist())
        reasons = []
        if avg_day > 0: reasons.append(f"均漲{avg_day:.2f}%")
        if up_ratio >= 0.6: reasons.append(f"上漲家數{up_ratio*100:.0f}%")
        if avg_vol >= 1.2: reasons.append(f"量比{avg_vol:.2f}x")
        if strong_count >= 2: reasons.append(f"強勢{strong_count}檔")
        if inst > 0: reasons.append("法人買超")
        if confidence != "高": reasons.append(confidence_note)
        rows.append({
            "產業": ind, "輪動狀態": state, "可信度": confidence, "樣本數": sample_n,
            "今日熱度": int(round(hot_score, 0)), "5日升溫": round(rotation_delta, 1),
            "平均漲幅%": round(avg_day, 2), "3日均幅%": round(avg_3d, 2), "5日均幅%": round(avg_5d, 2),
            "上漲家數%": round(up_ratio * 100, 1), "平均量比": round(avg_vol, 2), "強勢股數": int(strong_count),
            "法人合計": int(round(inst, 0)), "代表股": leader_txt, "熱度原因": "、".join(reasons) if reasons else "尚未明顯發動", "操作建議": advice,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    state_order = {"🔥 主戰場": 0, "🟠 資金升溫": 1, "🟡 潛伏觀察": 2, "⚠️ 退潮警戒": 3, "⚪ 普通": 4}
    out["_ord"] = out["輪動狀態"].map(state_order).fillna(9)
    return out.sort_values(["_ord", "今日熱度", "5日升溫"], ascending=[True, False, False]).drop(columns=["_ord"])


def render_industry_rotation_radar(colors, table_style, twse_ind_map, today_df=None, macro_df=None):
    st.markdown("#### 🔥 <span class='highlight-primary'>產業輪動雷達</span>", unsafe_allow_html=True)
    st.caption("用個股引擎已掃出的價量、均線與法人資料，判斷每日/近5日誰是主戰場、誰正在升溫、誰可能退潮。")
    frames = []
    chip_intel = st.session_state.get("eod_intel_df", None)
    if chip_intel is not None and isinstance(chip_intel, pd.DataFrame) and not chip_intel.empty:
        base = chip_intel.copy()
        if today_df is not None and not today_df.empty:
            chip_cols = [c for c in ["代號", "三大法人合計", "投信(張)", "外資(張)"] if c in today_df.columns]
            base = pd.merge(base, today_df[chip_cols], on="代號", how="left")
        frames.append(base)
    for key in ["eod_master_list", "eod_special_watch", "eod_rank_sorted"]:
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            frames.append(df.copy())
    if not frames:
        st.info("尚未有足夠掃描資料。請先到【個股游擊】按一次「重新掃描明日清單」，情報局就會整理產業輪動。")
        return
    pool = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["代號"], keep="first")
    table = build_industry_rotation_table(pool, twse_ind_map, macro_df)
    if table.empty:
        st.info("產業輪動資料不足，可能是今日掃描樣本太少或價量欄位不足。")
        return
    hot = table[table["輪動狀態"].isin(["🔥 主戰場", "🟠 資金升溫", "🟡 潛伏觀察"])].head(10)
    if not hot.empty:
        status_order = ["🔥 主戰場", "🟠 資金升溫", "🟡 潛伏觀察", "⚠️ 退潮警戒", "⚪ 普通"]
        group_blocks = []
        for state in status_order:
            g = hot[hot["輪動狀態"] == state]
            if g.empty:
                continue
            color = colors["red"] if "主戰場" in state else (colors["accent"] if "升溫" in state else colors["primary"])
            items = []
            for _, r in g.head(6).iterrows():
                reps = str(r.get("代表股", ""))
                if len(reps) > 34:
                    reps = reps[:34] + "…"
                items.append(
                    f"<span style='display:inline-block; margin:3px 6px 3px 0; padding:5px 8px; border-radius:999px; background:{colors['bg']}; border:1px solid {colors['border']}; color:{colors['text']}; font-size:12.5px;'>"
                    f"<b>{html.escape(str(r['產業']))}</b>｜熱度 {float(r['今日熱度']):.0f}｜升溫 {float(r['5日升溫']):+.1f}｜可信 {html.escape(str(r.get('可信度', '-')))}"
                    f"</span>"
                )
            rep_line = html.escape(str(g.iloc[0].get("代表股", "")))
            if len(rep_line) > 80:
                rep_line = rep_line[:80] + "…"
            group_blocks.append(f"""
            <div style="margin:8px 0 10px 0;">
                <div style="font-size:14px; font-weight:900; color:{color}; margin-bottom:4px;">{html.escape(state)}｜{len(g)} 個產業</div>
                <div>{''.join(items)}</div>
                <div style="font-size:12px; color:{colors['subtext']}; line-height:1.45; margin-top:4px;"><b>代表股：</b>{rep_line}</div>
            </div>
            """)
        blocks_html = "".join(group_blocks)
        st.markdown(f"""
        <div style="background:{colors['card']}; border:1px solid {colors['border']}; border-left:5px solid {colors['primary']}; border-radius:12px; padding:12px 14px; margin:8px 0 14px 0;">
            <div style="font-size:16px; font-weight:900; color:{colors['text']}; margin-bottom:4px;">🧭 今日輪動總覽</div>
            <div style="font-size:12.5px; color:{colors['subtext']}; margin-bottom:8px;">把同一種輪動狀態合併顯示；細節看下方表格即可。</div>
            {blocks_html}
        </div>
        """, unsafe_allow_html=True)
    show_cols = ["產業", "輪動狀態", "可信度", "樣本數", "今日熱度", "5日升溫", "平均漲幅%", "上漲家數%", "平均量比", "強勢股數", "法人合計", "代表股", "操作建議"]
    view_df = table[[c for c in show_cols if c in table.columns]].copy()
    fmt_map = {
        "今日熱度": "{:.0f}", "5日升溫": "{:+.1f}", "平均漲幅%": "{:+.2f}",
        "上漲家數%": "{:.1f}", "平均量比": "{:.2f}", "強勢股數": "{:.0f}",
        "樣本數": "{:.0f}", "法人合計": "{:,.0f}",
    }
    styled_rotation = view_df.style.set_properties(**table_style).format({k: v for k, v in fmt_map.items() if k in view_df.columns}, na_rep="-")
    st.dataframe(styled_rotation, use_container_width=True, hide_index=True, height=420)
