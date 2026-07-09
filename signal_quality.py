# -*- coding: utf-8 -*-
"""
signal_quality.py — 訊號品質儀表板（戰績分析室）

把 signal_tracker 累積的隔日/3日/5日結果變成可行動的回饋：

1. 沙盤加值驗證   : 「原始 S/A/B」vs「S/A/B + 沙盤通過」命中率對照
                    —— 這是訊號追蹤室建立時的核心假設，在此正式驗證。
2. 滾動品質趨勢   : 每週各評級 5 日達標率走勢，看訊號是否劣化。
3. 分數有效性檢查 : 分數高低分組 vs 實際達標率，確認排序邏輯是否有效。
4. 產業命中分布   : 哪些產業的訊號值得信、哪些是雜訊來源。
5. 門檻校準建議   : 依近期表現給出保守/標準/進攻模式的調整方向。

設計原則：所有結論都標示樣本數；樣本 < MIN_SAMPLE 一律標記「樣本不足」，
不做過度推論 —— 寧可說「還不知道」也不給假信心。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

TRACKED = ["S級", "A級", "B級"]
HIT_THRESHOLD = 3.0      # 與 signal_tracker 是否達標定義一致：3/5 日內最高漲幅 >= 3%
MIN_SAMPLE = 10          # 低於此樣本數的結論一律標記樣本不足
PASS_STATUS = "通過"      # 沙盤狀態的通過標記（_sandbox_assessment 定義）


# ---------------------------------------------------------
# 資料準備
# ---------------------------------------------------------

def _prep(history: pd.DataFrame) -> pd.DataFrame:
    """取出已驗證（有 3 日或 5 日結果）的 S/A/B 樣本。"""
    if history is None or history.empty:
        return pd.DataFrame()
    df = history[history["類型"].isin(TRACKED)].copy()
    if df.empty:
        return df
    for c in ["隔日漲跌%", "3日最高漲幅%", "5日最高漲幅%", "分數", "沙盤勝率", "沙盤乖離"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df["3日最高漲幅%"].notna() | df["5日最高漲幅%"].notna()].copy()
    if df.empty:
        return df
    best = df[["3日最高漲幅%", "5日最高漲幅%"]].max(axis=1, skipna=True)
    df["_hit"] = (best >= HIT_THRESHOLD).astype(float)
    df["_d1_win"] = np.where(df["隔日漲跌%"].notna(), (df["隔日漲跌%"] > 0).astype(float), np.nan)
    df["_fail"] = np.where(df["隔日漲跌%"].notna(), (df["隔日漲跌%"] <= -2).astype(float), np.nan)
    df["_dt"] = pd.to_datetime(df["日期"], errors="coerce")
    df["_pass"] = df.get("沙盤狀態", "").astype(str).str.strip().eq(PASS_STATUS)
    return df


def _rate(series) -> float:
    s = pd.to_numeric(pd.Series(series), errors="coerce").dropna()
    return float(s.mean() * 100) if len(s) else np.nan


def _fmt_rate(v, n) -> str:
    if pd.isna(v) or n == 0:
        return "—"
    mark = "" if n >= MIN_SAMPLE else " ⚠️"
    return f"{v:.0f}%（n={n}{mark}）"


# ---------------------------------------------------------
# 1. 沙盤加值驗證
# ---------------------------------------------------------

def _sandbox_value_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for typ in TRACKED:
        g = df[df["類型"] == typ]
        if g.empty:
            continue
        for label, sub in [("原始訊號", g), ("＋沙盤通過", g[g["_pass"]])]:
            n = len(sub)
            rows.append({
                "類型": typ,
                "樣本": label,
                "n": n,
                "5日達標率%": round(_rate(sub["_hit"]), 1) if n else np.nan,
                "隔日勝率%": round(_rate(sub["_d1_win"]), 1) if n else np.nan,
                "隔日重挫率%": round(_rate(sub["_fail"]), 1) if n else np.nan,
                "平均5日高點%": round(float(pd.to_numeric(sub["5日最高漲幅%"], errors="coerce").mean()), 2) if n else np.nan,
            })
    return pd.DataFrame(rows)


def _sandbox_verdict(tbl: pd.DataFrame) -> list:
    """比對每個評級 原始 vs 沙盤通過 的達標率，產生文字結論。"""
    verdicts = []
    for typ in TRACKED:
        raw = tbl[(tbl["類型"] == typ) & (tbl["樣本"] == "原始訊號")]
        flt = tbl[(tbl["類型"] == typ) & (tbl["樣本"] == "＋沙盤通過")]
        if raw.empty or flt.empty:
            continue
        r, f = raw.iloc[0], flt.iloc[0]
        if f["n"] < MIN_SAMPLE:
            verdicts.append(f"**{typ}**：沙盤通過樣本僅 {int(f['n'])} 筆，尚不足以下結論，繼續累積。")
            continue
        diff = (f["5日達標率%"] or 0) - (r["5日達標率%"] or 0)
        if diff >= 8:
            verdicts.append(f"**{typ}**：沙盤過濾有效 ✅ 達標率 {r['5日達標率%']:.0f}% → {f['5日達標率%']:.0f}%（+{diff:.0f}pp），建議只打沙盤通過的球。")
        elif diff <= -8:
            verdicts.append(f"**{typ}**：沙盤反而過濾掉好球 ⚠️ 達標率 {r['5日達標率%']:.0f}% → {f['5日達標率%']:.0f}%，沙盤條件可能過嚴，值得檢視「乖離偏高」是否誤殺強勢股。")
        else:
            verdicts.append(f"**{typ}**：沙盤過濾效果中性（{diff:+.0f}pp），主要價值在避開隔日重挫（{r['隔日重挫率%']:.0f}% vs {f['隔日重挫率%']:.0f}%）。")
    return verdicts


# ---------------------------------------------------------
# 2. 滾動品質趨勢（週）
# ---------------------------------------------------------

def _weekly_trend(df: pd.DataFrame) -> pd.DataFrame:
    if df["_dt"].isna().all():
        return pd.DataFrame()
    work = df.dropna(subset=["_dt"]).copy()
    work["週"] = work["_dt"].dt.to_period("W").dt.start_time.dt.strftime("%m/%d")
    piv = work.pivot_table(index="週", columns="類型", values="_hit", aggfunc="mean") * 100
    cnt = work.pivot_table(index="週", columns="類型", values="_hit", aggfunc="count")
    # 該週樣本 < 3 的格子視為雜訊，遮蔽
    piv = piv.where(cnt >= 3)
    return piv.round(1)


# ---------------------------------------------------------
# 3. 分數有效性
# ---------------------------------------------------------

def _score_effectiveness(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for typ in TRACKED:
        g = df[(df["類型"] == typ) & df["分數"].notna()]
        if len(g) < MIN_SAMPLE:
            continue
        try:
            g = g.copy()
            g["_bucket"] = pd.qcut(g["分數"], q=min(3, g["分數"].nunique()), labels=None, duplicates="drop")
        except Exception:
            continue
        for b, sub in g.groupby("_bucket", observed=True):
            rows.append({
                "類型": typ,
                "分數區間": f"{b.left:.0f}–{b.right:.0f}",
                "n": len(sub),
                "5日達標率%": round(_rate(sub["_hit"]), 1),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------
# 4. 產業命中分布
# ---------------------------------------------------------

def _industry_table(df: pd.DataFrame, min_n: int = 3) -> pd.DataFrame:
    g = df[df["產業"].astype(str).str.strip().ne("")]
    if g.empty:
        return pd.DataFrame()
    agg = g.groupby("產業").agg(n=("_hit", "count"), 達標率=("_hit", "mean"), 平均5日高點=("5日最高漲幅%", "mean")).reset_index()
    agg = agg[agg["n"] >= min_n].copy()
    if agg.empty:
        return pd.DataFrame()
    agg["達標率"] = (agg["達標率"] * 100).round(1)
    agg["平均5日高點"] = agg["平均5日高點"].round(2)
    return agg.sort_values(["達標率", "n"], ascending=[False, False]).reset_index(drop=True)


# ---------------------------------------------------------
# 5. 門檻校準建議
# ---------------------------------------------------------

def _threshold_advice(df: pd.DataFrame, operation_mode: str = "") -> list:
    advice = []
    recent_cut = df["_dt"].max() - pd.Timedelta(days=30) if df["_dt"].notna().any() else None
    for typ in TRACKED:
        g = df[df["類型"] == typ]
        n = len(g)
        if n < MIN_SAMPLE:
            advice.append(f"**{typ}**：已驗證樣本 {n} 筆（<{MIN_SAMPLE}），先累積數據，暫不調整門檻。")
            continue
        overall = _rate(g["_hit"])
        recent = g[g["_dt"] >= recent_cut] if recent_cut is not None else g
        recent_rate = _rate(recent["_hit"]) if len(recent) >= 5 else np.nan
        line = f"**{typ}**：整體達標率 {overall:.0f}%（n={n}）"
        if pd.notna(recent_rate):
            trend = recent_rate - overall
            line += f"，近 30 天 {recent_rate:.0f}%"
            if trend <= -10:
                line += " —— 品質下滑 📉，建議暫時切到保守模式（提高該級門檻），或優先只做沙盤通過樣本。"
            elif trend >= 10:
                line += " —— 品質上升 📈，若已在保守模式可考慮回到標準模式。"
            else:
                line += "，穩定。"
        advice.append(line)
    if operation_mode:
        advice.append(f"（目前操作模式：{operation_mode}。以上建議請搭配大盤環境判讀，過熱訊號優先於命中率。）")
    return advice


# ---------------------------------------------------------
# 主渲染入口
# ---------------------------------------------------------

def render_quality_dashboard(history: pd.DataFrame, COLORS: dict, table_style: dict, operation_mode: str = ""):
    st.markdown("### 🎖️ <span class='highlight-primary'>戰績分析室</span>", unsafe_allow_html=True)
    st.caption(f"把命中結果變成回饋：驗證沙盤價值、監控訊號品質、校準模式門檻。達標定義：3/5 日內最高漲幅 ≥ {HIT_THRESHOLD:.0f}%；樣本 < {MIN_SAMPLE} 標記 ⚠️。")

    df = _prep(history)
    if df.empty:
        st.info("尚無已驗證的 S/A/B 樣本。請先保存每日快照，並在幾個交易日後按「更新命中結果」。")
        return

    # ---- 1. 沙盤加值驗證 ----
    st.markdown("#### 🔬 沙盤第二道體檢，到底有沒有用？")
    tbl = _sandbox_value_table(df)
    if not tbl.empty:
        st.dataframe(
            tbl.style.format({
                "5日達標率%": "{:.1f}%", "隔日勝率%": "{:.1f}%",
                "隔日重挫率%": "{:.1f}%", "平均5日高點%": "{:+.2f}%",
            }, na_rep="—").set_properties(**table_style),
            use_container_width=True, hide_index=True,
        )
        for v in _sandbox_verdict(tbl):
            st.markdown(f"- {v}")

    # ---- 2. 週趨勢 ----
    trend = _weekly_trend(df)
    if not trend.empty and trend.notna().any().any():
        st.markdown("#### 📈 每週 5 日達標率走勢")
        st.line_chart(trend, height=220)
        st.caption("單週樣本 < 3 的點不顯示，避免被單筆結果誤導。")

    # ---- 3+4. 分數有效性 / 產業分布 ----
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### 🧮 分數越高，真的越準嗎？")
        eff = _score_effectiveness(df)
        if eff.empty:
            st.caption("樣本尚不足以分組檢驗（每級至少需 10 筆）。")
        else:
            st.dataframe(
                eff.style.format({"5日達標率%": "{:.1f}%"}).set_properties(**table_style),
                use_container_width=True, hide_index=True,
            )
            st.caption("若高分組達標率沒有明顯高於低分組，代表分數排序在近期市場失效，選股時應加重籌碼/產業判斷。")
    with col_b:
        st.markdown("#### 🏭 產業命中分布")
        ind = _industry_table(df)
        if ind.empty:
            st.caption("各產業樣本皆 < 3 筆，暫不顯示。")
        else:
            st.dataframe(
                ind.style.format({"達標率": "{:.1f}%", "平均5日高點": "{:+.2f}%"}).set_properties(**table_style),
                use_container_width=True, hide_index=True, height=min(300, 45 + 35 * len(ind)),
            )

    # ---- 5. 門檻校準 ----
    st.markdown("#### 🎛️ 模式門檻校準建議")
    for a in _threshold_advice(df, operation_mode):
        st.markdown(f"- {a}")
