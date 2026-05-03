import pandas as pd
import numpy as np


def to_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(str(value).replace(',', '').replace('%', '').strip())
    except Exception:
        return default


def to_int(value, default=0):
    try:
        return int(float(str(value).replace(',', '').strip()))
    except Exception:
        return default


def text(value):
    return '' if value is None or pd.isna(value) else str(value)


def calc_refined_safety_score(row):
    """把舊安全指數升級成觀察用分數，不影響S/A/B/C主選股邏輯。"""
    base = to_float(row.get('安全指數', 5), 5)
    price = to_float(row.get('現價', 0), 0)
    m5 = to_float(row.get('M5', price), price)
    m10 = to_float(row.get('M10', price), price)
    m20 = to_float(row.get('M20', price), price)
    bias = to_float(row.get('乖離(%)', row.get('乖離', 0)), 0)
    rsi = to_float(row.get('RSI', 50), 50)
    phase = text(row.get('生命週期', ''))
    sell_streak = to_int(row.get('投信連賣', 0), 0)
    buy_streak = to_int(row.get('連買', 0), 0)

    score = base
    if price > 0 and m5 > 0 and price < m5:
        score -= 0.8
    if price > 0 and m10 > 0 and price < m10:
        score -= 1.4
    if price > 0 and m20 > 0 and price < m20:
        score -= 1.8
    if bias > 8:
        score -= 1.0
    elif 0 <= bias <= 5:
        score += 0.4
    if rsi > 80:
        score -= 1.0
    elif 50 <= rsi <= 70:
        score += 0.3
    if sell_streak >= 3:
        score -= min(2.0, 0.45 * sell_streak)
    if 3 <= buy_streak <= 7:
        score += 0.7
    elif buy_streak >= 11:
        score -= 0.8
    if '第三段' in phase:
        score -= 1.5
    return max(1, min(10, int(round(score))))


def get_institution_state(row):
    """把投信連買/連賣與三大法人合計壓成單一法人狀態。"""
    buy_streak = to_int(row.get('連買', 0), 0)
    sell_streak = to_int(row.get('投信連賣', 0), 0)
    trust = to_float(row.get('投信(張)', 0), 0)
    foreign = to_float(row.get('外資(張)', 0), 0)
    total = to_float(row.get('三大法人合計', 0), 0)

    if sell_streak >= 5:
        return '🔴 法人撤退'
    if sell_streak >= 3:
        return '🟠 連賣警戒'
    if buy_streak >= 14:
        return '🟠 出貨警戒'
    if 11 <= buy_streak <= 13:
        return '🟠 建倉末段'
    if 8 <= buy_streak <= 10:
        return '🟡 建倉偏熱'
    if 3 <= buy_streak <= 7 and total > 0:
        return '🟢 建倉主段'
    if 2 <= buy_streak <= 3 and total > 0:
        return '🟢 建倉初段'
    if buy_streak == 1 and trust > 0 and foreign > 0:
        return '🟢 土洋合擊'
    if total > 0 and trust > 0:
        return '⚪ 法人偏買'
    return '⚪ 無明確方向'


def get_decision_label(row, holding=False):
    """五段式決策標籤：可進攻 / 等回踩 / 續抱 / 降級觀察 / 禁買出場。"""
    price = to_float(row.get('現價', 0), 0)
    m5 = to_float(row.get('M5', price), price)
    m10 = to_float(row.get('M10', price), price)
    bias = to_float(row.get('乖離(%)', row.get('乖離', 0)), 0)
    rsi = to_float(row.get('RSI', 50), 50)
    total = to_float(row.get('三大法人合計', 0), 0)
    buy_streak = to_int(row.get('連買', 0), 0)
    sell_streak = to_int(row.get('投信連賣', 0), 0)
    phase = text(row.get('生命週期', ''))
    tactic = text(row.get('戰術型態', ''))

    if price <= 0:
        return '⚪ 資料不足'
    if (m10 > 0 and price < m10) or ('爆量出貨' in phase) or (sell_streak >= 3 and m5 > 0 and price < m5):
        return '🔴 禁買/出場'
    if holding and m5 > 0 and price >= m5 and sell_streak < 3:
        return '🔵 續抱'
    if (m5 > 0 and price < m5) or sell_streak >= 3 or '提高警覺' in phase or '高機率末升' in phase:
        return '🟠 降級觀察'
    if bias > 7 or rsi > 75 or '建倉偏熱' in get_institution_state(row):
        return '🟡 等回踩'
    if m5 > 0 and price >= m5 and (total > 0 or buy_streak >= 2 or '🚀' in tactic or '🔥' in tactic or '🛡️' in tactic):
        return '🟢 可進攻'
    return '⚪ 觀察'


def get_next_action(row, holding=False):
    label = get_decision_label(row, holding=holding)
    price = to_float(row.get('現價', 0), 0)
    m5 = to_float(row.get('M5', price), price)
    m10 = to_float(row.get('M10', price), price)
    rsi = to_float(row.get('RSI', 50), 50)
    bias = to_float(row.get('乖離(%)', row.get('乖離', 0)), 0)
    sell_streak = to_int(row.get('投信連賣', 0), 0)

    if '可進攻' in label:
        return '依計畫；跳空>4.5%不追'
    if '等回踩' in label:
        if rsi > 75 or bias > 7:
            return '等M5/M10，不追高'
        return '等回踩確認'
    if '續抱' in label:
        return '續抱；跌破M5再處理'
    if '降級' in label:
        if sell_streak >= 3:
            return '法人轉賣，暫不新買'
        if price < m5:
            return '等站回M5，否則看M10'
        return '縮小倉位觀察'
    if '禁買' in label:
        return '不買；持股減碼/停損'
    return '只觀察，不主動出手'


def is_institution_observation(row, main_codes=None):
    main_codes = set(main_codes or [])
    sid = text(row.get('代號', '')).strip()
    if sid in main_codes:
        return False
    refined = to_int(row.get('改版安全指數', row.get('安全指數', 0)), 0)
    total = to_float(row.get('三大法人合計', 0), 0)
    state = get_institution_state(row)
    phase = text(row.get('生命週期', ''))
    decision = get_decision_label(row)
    if refined < 7 or total <= 0:
        return False
    if '撤退' in state or '連賣警戒' in state or '出貨警戒' in state:
        return False
    if '第三段' in phase or '禁買' in decision:
        return False
    return any(k in state for k in ['建倉初段', '建倉主段', '建倉偏熱', '土洋合擊', '法人偏買'])
