# -*- coding: utf-8 -*-
"""
param_scan.py — 回測參數掃描室

用歷史資料回答一個問題：「我的 SOP 參數，真的是最優解嗎？」

掃描維度（一次掃一個，避免組合爆炸與過擬合）：
1. 進場分數門檻   min_entry_score : 對應保守/標準/進攻模式的門檻哲學
2. 分級組合       allowed_tiers   : 只打 S？S+A？還是 S/A/B 全收？
3. 出半獲利點     take_half_pct   : 5.5% 出半是不是最甜的位置
4. 最長持有天數   max_hold_bars   : 3-5 天波段的時間停損該設多長

誠實原則：
- 結果附「過擬合警語」——歷史最優 ≠ 未來最優，參數差距在雜訊範圍內就不值得改。
- 顯示每組交易筆數；筆數太少的「高報酬」直接標記不可信。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from backtest_engine import BacktestConfig, run_portfolio_backtest

MIN_TRADES_CREDIBLE = 8   # 交易筆數低於此值的結果標記為樣本不足

SCAN_PRESETS = {
    "進場分數門檻": {
        "field": "min_entry_score",
        "values": [0, 55, 62, 68, 72],
        "fmt": lambda v: "不過濾" if v == 0 else f"≥{v:g}分",
        "note": "門檻越高＝越像保守模式。看拉高門檻是犧牲了報酬還是濾掉了雜訊。",
    },
    "分級組合": {
        "field": "allowed_tiers",
        "values": [("S",), ("S", "A"), ("S", "A", "B")],
        "fmt": lambda v: "+".join(v),
        "note": "驗證「只打最有把握的球」在歷史上是否真的比較賺。",
    },
    "出半獲利點": {
        "field": "take_half_pct",
        "values": [4.5, 5.5, 6.5, 8.0],
        "fmt": lambda v: f"+{v:g}%出半",
        "note": "目前 SOP 是 +5.5% 出半；看提早落袋 vs 讓利潤跑的取捨。",
    },
    "最長持有天數": {
        "field": "max_hold_bars",
        "values": [7, 10, 13],
        "fmt": lambda v: f"{v}根K",
        "note": "時間停損：波段拖太久通常代表訊號失效，看幾天是甜蜜點。",
    },
}


def run_param_scan(
    symbols: List[str],
    preset_name: str,
    name_map: Optional[Dict[str, str]] = None,
    fm_token: Optional[str] = None,
    period: str = "1y",
    base_config: Optional[BacktestConfig] = None,
    progress_cb=None,
) -> pd.DataFrame:
    """對單一參數維度跑掃描，回傳彙總比較表。

    價格資料由 backtest_engine.load_backtest_data 的 st.cache_data 快取，
    同一批股票掃 N 組參數只會下載一次。
    """
    preset = SCAN_PRESETS[preset_name]
    base = base_config or BacktestConfig()
    rows = []
    values = preset["values"]
    for i, v in enumerate(values):
        cfg = replace(base, **{preset["field"]: v})
        res = run_portfolio_backtest(symbols, name_map=name_map, fm_token=fm_token, period=period, config=cfg)
        label = preset["fmt"](v)
        if not res.get("ok"):
            rows.append({"參數": label, "狀態": res.get("message", "失敗"), "交易筆數": 0})
        else:
            s = res["summary"]
            n_trades = int(s.get("交易筆數", 0))
            rows.append({
                "參數": label,
                "總報酬%": round(float(s.get("總報酬(%)", np.nan)), 2),
                "最大回撤%": round(float(s.get("最大回撤(%)", np.nan)), 2),
                "勝率%": round(float(s.get("勝率(%)", np.nan)), 1),
                "平均單筆%": round(float(s.get("平均單筆報酬(%)", np.nan)), 2),
                "平均持有天": round(float(s.get("平均持有天數", np.nan)), 1),
                "交易筆數": n_trades,
                "可信度": "✅" if n_trades >= MIN_TRADES_CREDIBLE else "⚠️ 樣本不足",
            })
        if progress_cb:
            progress_cb((i + 1) / len(values))
    return pd.DataFrame(rows)


def _default_scan_symbols(max_n: int = 12) -> List[str]:
    """預設掃描池：優先用今日 S/A/B 主清單，退而求其次用近期訊號紀錄常客。"""
    master = st.session_state.get("eod_master_list", pd.DataFrame())
    if isinstance(master, pd.DataFrame) and not master.empty and "代號" in master.columns:
        codes = [str(c).strip() for c in master["代號"].astype(str).tolist() if str(c).strip()]
        return list(dict.fromkeys(codes))[:max_n]
    try:
        import signal_tracker
        hist, _ = signal_tracker.load_signal_history()
        if hist is not None and not hist.empty:
            top = hist[hist["類型"].isin(["S級", "A級", "B級"])]["代號"].value_counts().head(max_n)
            return [str(c) for c in top.index.tolist()]
    except Exception:
        pass
    return []


def render_param_scan_panel(COLORS: dict, table_style: dict, fm_token: str, name_map: Optional[Dict[str, str]] = None):
    with st.expander("🧪 參數掃描室：驗證 SOP 參數是否為歷史最優", expanded=False):
        st.caption("用同一批股票、同一段歷史，只改一個參數，比較資金曲線結果。一次掃一個維度，避免過擬合。")

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            preset_name = st.selectbox("掃描維度", list(SCAN_PRESETS.keys()), key="pscan_preset")
        with c2:
            default_syms = ",".join(_default_scan_symbols())
            syms_text = st.text_input("掃描股票池（逗號分隔）", value=default_syms, key="pscan_syms",
                                      placeholder="例：2330,2317,3443（留空無法掃描）")
        with c3:
            period = st.selectbox("回測期間", ["6mo", "1y", "2y"], index=1, key="pscan_period")

        st.caption(f"💡 {SCAN_PRESETS[preset_name]['note']}")
        run_btn = st.button("🚀 執行參數掃描", type="primary", use_container_width=True, key="pscan_run")

        if run_btn:
            symbols = [s.strip() for s in str(syms_text).replace("，", ",").split(",") if s.strip()]
            if len(symbols) < 3:
                st.warning("至少需要 3 檔股票才有比較意義；建議 8–15 檔。")
                return
            prog = st.progress(0.0, text="掃描中…（首輪需下載歷史價，之後各組共用快取）")
            result = run_param_scan(
                symbols, preset_name, name_map=name_map, fm_token=fm_token,
                period=period, progress_cb=lambda p: prog.progress(p, text=f"掃描中… {p*100:.0f}%"),
            )
            prog.empty()
            st.session_state["pscan_result"] = result
            st.session_state["pscan_result_label"] = f"{preset_name}｜{len(symbols)} 檔｜{period}"

        result = st.session_state.get("pscan_result")
        if isinstance(result, pd.DataFrame) and not result.empty:
            st.markdown(f"**掃描結果**（{st.session_state.get('pscan_result_label','')}）")
            if "總報酬%" in result.columns:
                view = result.sort_values("總報酬%", ascending=False, na_position="last")
                st.dataframe(
                    view.style.format({
                        "總報酬%": "{:+.2f}%", "最大回撤%": "{:.2f}%",
                        "勝率%": "{:.1f}%", "平均單筆%": "{:+.2f}%", "平均持有天": "{:.1f}",
                    }, na_rep="—").set_properties(**table_style),
                    use_container_width=True, hide_index=True,
                )
                credible = view[view["交易筆數"] >= MIN_TRADES_CREDIBLE]
                if not credible.empty:
                    best = credible.iloc[0]
                    st.markdown(f"- 歷史最優（可信樣本內）：**{best['參數']}** —— 總報酬 {best['總報酬%']:+.2f}%、勝率 {best['勝率%']:.1f}%、最大回撤 {best['最大回撤%']:.2f}%。")
                    spread = credible["總報酬%"].max() - credible["總報酬%"].min()
                    if spread < 3:
                        st.markdown("- 各組差距 < 3pp，**在雜訊範圍內** —— 現行參數沒有明顯劣勢，不建議為此改 SOP。")
            else:
                st.dataframe(result, use_container_width=True, hide_index=True)
            st.caption("⚠️ 過擬合警語：歷史最優 ≠ 未來最優。參數只有在「不同期間、不同股票池都穩定領先」時才值得採用；單次掃描的冠軍請當參考，不要當聖旨。")
