import pandas as pd
import streamlit as st


def _num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _dominant_text(values, default="-"):
    vals = [str(v).strip() for v in values if str(v).strip() and str(v).strip() not in ["nan", "None", "-"]]
    if not vals:
        return default
    return pd.Series(vals).mode().iloc[0]


def normalize_demon(user_demon="", system_demon=""):
    raw = str(user_demon or system_demon or "").strip()
    raw = raw.replace("👤", "").replace("🕊️", "").replace("😨", "").replace("⚓", "").replace("🛡️", "").strip()
    raw = raw.split("(")[0].split("（")[0].strip()
    if not raw:
        return "未標註"
    if "恐高" in raw or "賣飛" in raw:
        return "恐高早退"
    if "失去耐心" in raw or "耐心" in raw:
        return "失去耐心"
    if "凹單" in raw or "死抱" in raw:
        return "凹單死抱"
    if "恐慌" in raw:
        return "恐慌殺低"
    if "紀律" in raw or "停損" in raw:
        return "紀律停損"
    return raw


def infer_tactic(roi, held_days, demon_label, detail="", grade=""):
    demon = str(demon_label)
    detail = str(detail)
    grade = str(grade)
    try:
        roi = float(roi)
    except Exception:
        roi = 0.0
    try:
        held_days = int(float(held_days))
    except Exception:
        held_days = 0

    if "凹單" in demon or (roi <= -5 and held_days >= 3):
        return "破線未砍/救援"
    if "恐高" in demon or "賣飛" in demon or "潛在+" in detail:
        return "強股提早下車"
    if "失去耐心" in demon:
        return "盤整耐心不足"
    if held_days <= 2:
        return "隔日短打"
    if 3 <= held_days <= 5:
        return "短線波段"
    if held_days >= 6:
        return "延長持有"
    if "S級" in grade:
        return "完美停利"
    return "一般交易"


def _build_group(df, key):
    if df is None or df.empty or key not in df.columns:
        return pd.DataFrame()
    work = df.copy()
    work["淨利_num"] = _num(work["淨利"])
    work["報酬率_num"] = _num(work["報酬率(%)"])
    grp = work.groupby(key, dropna=False).agg(
        筆數=("代號", "count"),
        勝率=("報酬率_num", lambda x: (x > 0).mean() * 100 if len(x) else 0),
        淨利=("淨利_num", "sum"),
        平均報酬=("報酬率_num", "mean"),
        主要心魔=("心魔分類", _dominant_text),
    ).reset_index()
    grp = grp.sort_values(["淨利", "勝率"], ascending=[False, False])
    return grp


def _best_worst_text(group_df, key_name):
    if group_df is None or group_df.empty:
        return "樣本不足", "樣本不足", "-", "先累積更多交易紀錄"
    best = group_df.sort_values(["淨利", "勝率"], ascending=[False, False]).iloc[0]
    worst = group_df.sort_values(["淨利", "勝率"], ascending=[True, True]).iloc[0]
    main_demon = worst.get("主要心魔", "-")
    if "凹單" in str(main_demon):
        advice = "破線就走，救援單不要拖成大虧"
    elif "恐高" in str(main_demon):
        advice = "+5.5%～6% 出半，剩餘守 M5"
    elif "耐心" in str(main_demon):
        advice = "未破 M5/M10 前，不因盤整就亂跑"
    else:
        advice = "維持 SOP，避免因單筆結果過度修正"
    best_txt = f"{best.get(key_name, '-')}: {best.get('淨利', 0):,.0f} 元 / 勝率 {best.get('勝率', 0):.0f}%"
    worst_txt = f"{worst.get(key_name, '-')}: {worst.get('淨利', 0):,.0f} 元 / 勝率 {worst.get('勝率', 0):.0f}%"
    return best_txt, worst_txt, main_demon, advice


def _format_group(df, key_name):
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy().rename(columns={key_name: "分類"})
    # 詳細表只保留績效數據，主要心魔已經在上方情境總表呈現，避免三張明細表重複顯示。
    if "主要心魔" in out.columns:
        out = out.drop(columns=["主要心魔"])
    out["勝率"] = out["勝率"].map(lambda x: f"{x:.0f}%")
    out["平均報酬"] = out["平均報酬"].map(lambda x: f"{x:+.2f}%")
    out["淨利"] = out["淨利"].map(lambda x: f"{x:,.0f}")
    return out


def render_context_insights(res_df, COLORS):
    """AAR 進階：產業 × 戰術 × 心魔。只做情境歸因，不取代上方戰術糾錯中心。"""
    if res_df is None or res_df.empty:
        return
    df = res_df.copy()
    if "賣出日" in df.columns:
        df = df[df["賣出日"].astype(str) != "-"].copy()
    if df.empty or len(df) < 5:
        st.info("AAR 產業 × 戰術 × 心魔分析至少需要 5 筆平倉資料。")
        return

    st.caption("此區是情境歸因表；真正的下一次修正指令以上方「AAR 戰術糾錯中心」為準。")

    industry_df = _build_group(df, "產業")
    tactic_df = _build_group(df, "戰術推定")
    demon_df = _build_group(df, "心魔分類")

    b1, w1, d1, a1 = _best_worst_text(industry_df, "產業")
    b2, w2, d2, a2 = _best_worst_text(tactic_df, "戰術推定")
    b3, w3, d3, a3 = _best_worst_text(demon_df, "心魔分類")
    summary = pd.DataFrame([
        {"維度": "產業", "最順": b1, "最傷": w1, "主要問題": d1, "建議": a1},
        {"維度": "戰術", "最順": b2, "最傷": w2, "主要問題": d2, "建議": a2},
        {"維度": "心魔", "最順": b3, "最傷": w3, "主要問題": d3, "建議": a3},
    ])
    st.dataframe(summary, use_container_width=True, hide_index=True, height=150)

    work = df.copy()
    work["淨利_num"] = _num(work["淨利"])
    combo = work.groupby(["產業", "戰術推定", "心魔分類"], dropna=False).agg(
        筆數=("代號", "count"),
        淨利=("淨利_num", "sum"),
        代表股票=("名稱", _dominant_text),
    ).reset_index().sort_values("淨利", ascending=False)
    with st.expander("🔎 查看產業 / 戰術 / 心魔詳細表", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("##### 產業績效")
            st.dataframe(_format_group(industry_df, "產業").head(12), use_container_width=True, hide_index=True)
        with c2:
            st.markdown("##### 戰術績效")
            st.dataframe(_format_group(tactic_df, "戰術推定").head(12), use_container_width=True, hide_index=True)
        with c3:
            st.markdown("##### 心魔績效")
            st.dataframe(_format_group(demon_df, "心魔分類").head(12), use_container_width=True, hide_index=True)
        st.markdown("##### 組合情境明細")
        detail = combo.copy()
        detail["淨利"] = detail["淨利"].map(lambda x: f"{x:,.0f}")
        st.dataframe(detail.head(30), use_container_width=True, hide_index=True)
