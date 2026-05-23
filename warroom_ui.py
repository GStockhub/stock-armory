# -*- coding: utf-8 -*-
from __future__ import annotations
import html
from typing import Any, Dict, Iterable, List, Tuple


def _safe(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


def render_section_brief(st, COLORS: Dict[str, str], title: str, verdict: str, cards: Iterable[Tuple[str, str, str]] | None = None, note: str = "") -> None:
    """統一所有主區塊的閱讀節奏：先結論，再重點卡，最後才明細。"""
    cards = list(cards or [])[:5]
    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:6px solid {COLORS['primary']}; border-radius:12px; padding:13px 15px; margin:8px 0 14px 0;">
        <div style="font-size:17px; font-weight:900; color:{COLORS['text']}; margin-bottom:5px;">{_safe(title)}</div>
        <div style="font-size:14px; line-height:1.6; color:{COLORS['text']};">{_safe(verdict)}</div>
        {f"<div style='font-size:12.5px; color:{COLORS['subtext']}; line-height:1.45; margin-top:5px;'>{_safe(note)}</div>" if note else ""}
    </div>
    """, unsafe_allow_html=True)
    if cards:
        cols = st.columns(min(len(cards), 4))
        for col, (label, value, sub) in zip(cols, cards):
            with col:
                st.markdown(f"""
                <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-radius:10px; padding:10px 12px; min-height:92px; margin-bottom:10px;">
                    <div style="font-size:12px; font-weight:800; color:{COLORS['subtext']};">{_safe(label)}</div>
                    <div style="font-size:18px; font-weight:900; color:{COLORS['primary']}; margin:3px 0 5px 0; line-height:1.25;">{_safe(value)}</div>
                    <div style="font-size:12.5px; color:{COLORS['text']}; line-height:1.45;">{_safe(sub)}</div>
                </div>
                """, unsafe_allow_html=True)


def render_reading_rule(st, COLORS: Dict[str, str]) -> None:
    st.caption("閱讀順序：先看一句話結論 → 再看重點卡 → 有需要才展開明細。手機只看沙盤與持股；電腦再看完整戰情室。")
