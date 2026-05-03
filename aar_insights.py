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
    grp["勝率"] = grp["勝率"].map(lambda x: f"{x:.0f}%")
    grp["平均報酬"] = grp["平均報酬"].map(lambda x: f"{x:+.2f}%")
    grp["淨利"] = grp["淨利"].map(lambda x: f"{x:,.0f}")
    return grp


def render_context_insights(res_df, COLORS):
    """AAR 進階：產業 × 戰術 × 心魔。只做行為覆盤，不參與選股評分。"""
    if res_df is None or res_df.empty:
        return
    df = res_df.copy()
    if "賣出日" in df.columns:
        df = df[df["賣出日"].astype(str) != "-"].copy()
    if df.empty or len(df) < 5:
        st.info("AAR 產業 × 戰術 × 心魔分析至少需要 5 筆平倉資料。")
        return

    st.markdown("### 🧬 AAR 產業 × 戰術 × 心魔分析")
    st.caption("這區不是拿來篩選股票，而是找出你在哪種產業、戰術與心理情境最容易賺錢或犯錯。")

    c1, c2, c3 = st.columns(3)
    industry_df = _build_group(df, "產業")
    tactic_df = _build_group(df, "戰術推定")
    demon_df = _build_group(df, "心魔分類")

    with c1:
        st.markdown("#### 🏭 產業績效")
        if not industry_df.empty:
            st.dataframe(industry_df.rename(columns={"產業":"產業/類型"}).head(8), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("#### ⚔️ 戰術績效")
        if not tactic_df.empty:
            st.dataframe(tactic_df.rename(columns={"戰術推定":"戰術"}).head(8), use_container_width=True, hide_index=True)
    with c3:
        st.markdown("#### 👤 心魔績效")
        if not demon_df.empty:
            st.dataframe(demon_df.rename(columns={"心魔分類":"心魔"}).head(8), use_container_width=True, hide_index=True)

    # 組合診斷：找出最賺與最傷的情境
    work = df.copy()
    work["淨利_num"] = _num(work["淨利"])
    combo = work.groupby(["產業", "戰術推定", "心魔分類"], dropna=False).agg(
        筆數=("代號", "count"),
        淨利=("淨利_num", "sum"),
        代表股票=("名稱", _dominant_text),
    ).reset_index()
    combo = combo[combo["筆數"] >= 1].sort_values("淨利", ascending=False)

    best = combo.head(1)
    worst = combo.tail(1)
    best_txt = "樣本不足"
    worst_txt = "樣本不足"
    if not best.empty:
        r = best.iloc[0]
        best_txt = f"最順：{r['產業']} / {r['戰術推定']} / {r['心魔分類']}，累計 {r['淨利']:,.0f} 元，代表：{r['代表股票']}。"
    if not worst.empty:
        r = worst.iloc[0]
        worst_txt = f"最傷：{r['產業']} / {r['戰術推定']} / {r['心魔分類']}，累計 {r['淨利']:,.0f} 元，代表：{r['代表股票']}。"

    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['primary']}; border-radius:10px; padding:12px 14px; margin:10px 0 14px 0;">
        <div style="font-weight:800; margin-bottom:6px; color:{COLORS['text']};">🧭 情境診斷</div>
        <div style="font-size:13px; line-height:1.55; color:{COLORS['text']};">{best_txt}</div>
        <div style="font-size:13px; line-height:1.55; color:{COLORS['text']}; margin-top:4px;">{worst_txt}</div>
        <div style="font-size:12px; color:{COLORS['subtext']}; margin-top:6px;">提醒：樣本少時只當方向參考；不要因為單次結果就封印某產業。</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("🔎 查看產業 × 戰術 × 心魔明細", expanded=False):
        detail = combo.copy()
        detail["淨利"] = detail["淨利"].map(lambda x: f"{x:,.0f}")
        st.dataframe(detail.head(30), use_container_width=True, hide_index=True)
