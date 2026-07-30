# -*- coding: utf-8 -*-
"""
market_risk_ui.py — 大盤風險燈號面板(唯讀)
--------------------------------------------
同 intel_daily 模式:只讀 GitHub Actions 產出的 data/market_risk_history.csv,
頁面上不打任何外部 API。渲染節奏沿用 warroom_ui:先結論 → 重點卡 → 明細。
"""
from __future__ import annotations

import os

import pandas as pd

from warroom_ui import render_section_brief

RISK_HISTORY_PATH = "data/market_risk_history.csv"

_LIGHT_STYLE = {
    "紅": ("red", "高風險:降低持股、停止加碼,優先處理高槓桿與弱勢部位"),
    "黃": ("primary", "警戒:控制部位、不追價,新倉嚴設停損"),
    "綠": ("green", "常態:依原策略操作"),
}

_DIM_CARDS = [
    ("score_chip", "籌碼|外資期貨", "foreign_tx_net_oi", "外資台指期淨OI {v:+,.0f} 口"),
    ("score_leverage", "槓桿|融資動能", "margin_minus_index_5d_pct", "融資5日增速−指數 {v:+.1f}%"),
    ("score_breadth", "廣度|站上60MA", "pct_above_ma60", "站上60MA {v:.0f}% 檔"),
    ("score_intl", "國際|費半連動", "sox_bias_ma60_pct", "SOX 60MA乖離 {v:+.1f}%"),
]


def _load_history() -> pd.DataFrame:
    try:
        if os.path.exists(RISK_HISTORY_PATH):
            return pd.read_csv(RISK_HISTORY_PATH, dtype={"date": str})
    except Exception as e:
        print(f"market_risk_ui 讀取失敗: {e}")
    return pd.DataFrame()


def render_market_risk_panel(st, COLORS, table_style=None) -> None:
    df = _load_history()
    if df.empty:
        st.info("大盤風險燈號尚無資料:等 update_market_risk workflow 首跑,或手動執行 "
                "`python market_risk_provider.py --backfill 90` 後 commit data/。")
        return

    latest = df.iloc[-1]
    light = str(latest.get("light", "無資料"))
    color_key, advice = _LIGHT_STYLE.get(light, ("subtext", "資料不足,暫不評分"))
    comp = latest.get("composite_risk")
    comp_txt = "—" if comp is None or pd.isna(comp) else f"{float(comp):.0f}"

    cards = []
    for score_key, label, raw_key, fmt in _DIM_CARDS:
        s = latest.get(score_key)
        v = latest.get(raw_key)
        sub = fmt.format(v=float(v)) if v is not None and pd.notna(v) else "今日缺席(來源失敗)"
        cards.append((label, "—" if s is None or pd.isna(s) else f"{float(s):.0f} / 100", sub))

    render_section_brief(
        st, COLORS,
        title=f"🚦 大盤風險燈號:{light} {comp_txt}/100({latest['date']})",
        verdict=advice,
        cards=cards,
        note="分數越高=風險越高。這是狀態偵測不是預測:紅燈的意義是勝率環境變差、控制曝險,"
             "不是明天必跌。權重:籌碼30/槓桿25/廣度25/國際20;缺席維度自動降權。",
    )

    hist = df.dropna(subset=["composite_risk"]) if "composite_risk" in df.columns else pd.DataFrame()
    if len(hist) >= 2:
        chart = hist.tail(120).copy()
        chart["date"] = pd.to_datetime(chart["date"])
        st.line_chart(chart.set_index("date")["composite_risk"], height=180)

    with st.expander("🔎 原始訊號明細(近10日)"):
        show_cols = [c for c in [
            "date", "foreign_tx_net_oi", "margin_minus_index_5d_pct", "pct_above_ma60",
            "adv_dec_ratio", "sox_bias_ma60_pct", "sox_ret_5d_pct", "adr_premium_pct",
            "composite_risk", "light",
        ] if c in df.columns]
        tail = df[show_cols].tail(10).iloc[::-1]
        if table_style:
            st.dataframe(tail.style.set_properties(**table_style), use_container_width=True, hide_index=True)
        else:
            st.dataframe(tail, use_container_width=True, hide_index=True)
