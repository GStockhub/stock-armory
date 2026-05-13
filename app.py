import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
from datetime import datetime
import time
import ssl
import html
from streamlit_cookies_controller import CookieController

from data_center import load_industry_map, get_macro_dashboard, fetch_chips_data, read_remote_csv, convert_gsheet_url
from quant_engine import run_sandbox_sim, level2_quant_engine
from decision_logic import get_institution_state, get_decision_label, get_next_action, calc_refined_safety_score, is_institution_observation
from backtest_engine import BacktestConfig, run_portfolio_backtest

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError: pass
else: ssl._create_default_https_context = _create_unverified_https_context

from manual import QUICK_MANUAL_TEXT, MANUAL_TEXT, HISTORY_TEXT
import aar
import sidebar
import etf_ui
import mobile_ui
import rotation_radar
import signal_tracker
from fundamental_engine import get_fundamental_badge

st.set_page_config(page_title="我要賺大錢", page_icon="💰️", layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------
# 🔒 專屬門禁與 API Token
# ---------------------------------------------------------
ADMIN_PWD = st.secrets.get("admin_pwd", "0989")
GUEST_PWD = st.secrets.get("guest_pwd", "1023")
FM_TOKEN = st.secrets.get("fm_token", "")

try:
    controller = CookieController()
    try:
        auth_status = controller.get("v3_auth_token")
    except Exception:
        auth_status = st.session_state.get("v3_auth_token", None)
except Exception:
    controller = None
    auth_status = st.session_state.get("v3_auth_token", None)

if auth_status not in ["admin_auth", "guest_auth"]:
    st.markdown("<h1 style='text-align: center; margin-top: 100px;'>🔒 終極戰情室 v35.2 - 軍事管制區</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("請輸入通行密碼：", type="password", placeholder="輸入密碼後按下 Enter 或點擊解鎖")
        if st.button("🔓 驗證並解鎖", use_container_width=True) or pwd:
            if pwd == ADMIN_PWD:
                st.session_state["v3_auth_token"] = "admin_auth"
                try:
                    if controller is not None: controller.set("v3_auth_token", "admin_auth", max_age=2592000)
                except Exception: pass
                st.success("✅ 統帥確認：...正在為您開啟專屬戰情室...")
                time.sleep(1.2)
                st.rerun()
            elif pwd == GUEST_PWD:
                st.session_state["v3_auth_token"] = "guest_auth"
                try:
                    if controller is not None: controller.set("v3_auth_token", "guest_auth", max_age=2592000)
                except Exception: pass
                st.success("✅ 友軍確認：...正在開啟系統...")
                time.sleep(1.2)
                st.rerun()
            elif pwd != "":
                st.error("❌ 密碼錯誤！防禦系統已啟動。")
    st.stop()

# UI 共用樣式已固化於 theme.py，由 sidebar.render_sidebar() 套用。
configs = sidebar.render_sidebar(auth_status)
COLORS = configs["COLORS"]
sheet_url = str(configs["sheet_url"]).strip()
aar_sheet_url = str(configs["aar_sheet_url"]).strip()
etf_holdings_url = str(configs.get("etf_holdings_url", "")).strip()
mobile_quick_mode = bool(configs.get("mobile_quick_mode", False))

try: total_capital = float(configs.get("total_capital", 100000))
except: total_capital = 100000.0
try: risk_amount = float(configs.get("risk_amount", 1000))
except: risk_amount = 1000.0
try: fee_discount = float(configs.get("fee_discount", 1.0))
except: fee_discount = 1.0
operation_mode = configs.get("operation_mode", "標準模式")
MODE_PROFILE = {
    "保守模式": {"s": 92, "a": 72, "b": 55, "size": 0.70, "label": "🛡️ 保守模式", "note": "提高分數門檻、建議買量打7折，只打最有把握的球。"},
    "標準模式": {"s": 88, "a": 65, "b": 45, "size": 1.00, "label": "⚖️ 標準模式", "note": "維持V35.1 ETF主體倉 + 個股游擊節奏。"},
    "進攻模式": {"s": 84, "a": 60, "b": 40, "size": 1.15, "label": "⚔️ 進攻模式", "note": "略放寬B級觀察與買量，但仍受總曝險與停損控制。"},
}.get(operation_mode, {"s": 88, "a": 65, "b": 45, "size": 1.00, "label": "⚖️ 標準模式", "note": "維持V35.1 ETF主體倉 + 個股游擊節奏。"})

table_style = {"text-align": "center", "background-color": COLORS["card"], "color": COLORS["text"], "border-color": COLORS["border"]}

st.markdown(f"<h1 style='text-align: center;' class='highlight-primary'>💰️讓我賺大錢</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;' class='text-sub'>—— V37.10.3 ETF Import同步修正版｜分層抓取 ✕ 防推送衝突</p>", unsafe_allow_html=True)

TWSE_IND_MAP, TWSE_NAME_MAP = load_industry_map()

# =========================================================
# 📱 手機快查模式：避免手機重開時載入完整主系統
# =========================================================


MACRO_SCORE, MACRO_DF, OVERHEAT_FLAG = get_macro_dashboard()

def risk_color(val):
    try:
        v = float(val)
        if v >= 88: return f'color: {COLORS["green"]}; font-weight: bold;'
        elif v < 45: return f'color: {COLORS["red"]}; font-weight: bold;'
        return f'color: {COLORS["primary"]}; font-weight: bold;'
    except: return ""

def format_lots(shares):
    lots = int(shares) / 1000
    if lots <= 0: return "0"
    return f"{lots:.1f}".rstrip("0").rstrip(".")

def render_data_health_panel():
    health = []
    health.append(("產業地圖", len(TWSE_NAME_MAP) > 0, f"{len(TWSE_NAME_MAP):,} 筆" if TWSE_NAME_MAP else "未讀取"))
    health.append(("大盤儀表", not MACRO_DF.empty, f"{len(MACRO_DF)} 項" if not MACRO_DF.empty else "無資料"))
    health.append(("法人籌碼", chip_data_available or not today_df.empty, f"近 {len(chip_db)} 日｜{chips_data_source}" if chip_data_available else f"技術備援｜{len(today_df)} 檔候選"))
    health.append(("持股CSV", (auth_status != "admin_auth") or holding_read_ok, f"{holding_rows} 筆" if holding_read_ok else ("友軍隱藏" if auth_status != "admin_auth" else ("未設定" if not sheet_url else "讀取失敗/空表"))))
    health.append(("AAR日誌", aar_read_ok, f"{aar_rows} 筆" if aar_read_ok else ("未設定" if not aar_sheet_url else "讀取失敗/空表")))
    health.append(("FinMind Token", bool(str(FM_TOKEN).strip()), "已設定" if str(FM_TOKEN).strip() else "未設定"))

    cols = st.columns(3)
    for idx, (name, ok, msg) in enumerate(health):
        color = COLORS["green"] if ok else COLORS["red"]
        icon = "✅" if ok else "⚠️"
        with cols[idx % 3]:
            st.markdown(f"""
            <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:4px solid {color}; padding:10px 12px; border-radius:8px; margin-bottom:8px;">
                <div style="font-size:13px; color:{COLORS['subtext']};">{icon} {name}</div>
                <div style="font-size:16px; font-weight:700; color:{COLORS['text']};">{msg}</div>
            </div>
            """, unsafe_allow_html=True)


def render_data_status_bar():
    status_items = [
        len(TWSE_NAME_MAP) > 0,
        not MACRO_DF.empty,
        (len(chip_db) > 0) or (isinstance(today_df, pd.DataFrame) and not today_df.empty),
        holding_read_ok or not sheet_url,
        aar_read_ok or not aar_sheet_url,
        bool(str(FM_TOKEN).strip()),
    ]
    ok_count = sum(bool(x) for x in status_items)
    total_count = len(status_items)
    color = COLORS["green"] if ok_count >= 5 else (COLORS["accent"] if ok_count >= 4 else COLORS["red"])
    msg = "全部正常" if ok_count == total_count else "部分異常，請打開健康燈號查看"
    html_block = f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {color}; padding:8px 12px; border-radius:8px; margin:8px 0 14px 0; font-size:13px;">
        <b style="color:{COLORS['text']};">🧭 資料狀態：{ok_count}/{total_count} 正常</b>
        <span style="color:{COLORS['subtext']}; margin-left:8px;">{msg}</span>
    </div>
    """
    st.markdown(html_block, unsafe_allow_html=True)


def _row_text(row, possible_keys, exclude_keys=None, default=""):
    exclude_keys = exclude_keys or []
    for col in row.index:
        c = str(col).strip()
        if any(x in c for x in exclude_keys):
            continue
        if c in possible_keys or any(k in c for k in possible_keys):
            val = row[col]
            if pd.notna(val) and str(val).strip() not in ["", "nan", "NaN", "None"]:
                return str(val).strip()
    return default


def _to_float_safe(v, default=0.0):
    try:
        raw = str(v).replace(",", "").strip()
        if raw in ["", "nan", "NaN", "None"]:
            return default
        import re
        m = re.search(r"-?\d+\.?\d*", raw)
        return float(m.group(0)) if m else default
    except Exception:
        return default


def build_rescue_residual_map(aar_df, current_codes):
    """從 AAR 交易日誌找出：同代號近期/歷史已有認賠紀錄，但目前仍持有的救援殘倉。"""
    rescue = {}
    if aar_df is None or aar_df.empty or not current_codes:
        return rescue

    df = aar_df.copy()
    df.columns = df.columns.str.replace("\ufeff", "", regex=False).str.strip()
    current_codes = {str(x).strip() for x in current_codes if str(x).strip()}

    for _, row in df.iterrows():
        sid = _row_text(row, ["代號", "股票代號", "證券代號", "股票代碼", "stock_id"])
        sid = str(sid).strip()
        if not sid or sid not in current_codes:
            continue

        buy_price = _to_float_safe(_row_text(row, ["買進價", "成本價", "成本", "買價", "均價"], exclude_keys=["賣", "平"]))
        sell_price = _to_float_safe(_row_text(row, ["賣出價", "賣價", "平倉價"]))
        shares = _to_float_safe(_row_text(row, ["張數", "庫存張數", "庫存", "股數", "數量"]), 0.0)
        sell_date = _row_text(row, ["賣出日期", "賣出日", "平倉日"])
        label = _row_text(row, ["心理標籤", "心魔", "標籤", "心理狀態"])

        if buy_price <= 0 or sell_price <= 0 or shares <= 0 or not sell_date:
            continue

        raw_pnl = (sell_price - buy_price) * shares * 1000
        loss_pct = (sell_price - buy_price) / buy_price * 100 if buy_price > 0 else 0
        label_hit = any(k in label for k in ["凹單", "認賠", "停損", "砍", "虧"])

        if raw_pnl < 0 or loss_pct < -2 or label_hit:
            item = rescue.setdefault(sid, {
                "count": 0,
                "loss_sum": 0.0,
                "worst_pct": 0.0,
                "last_date": "",
                "labels": set(),
            })
            item["count"] += 1
            item["loss_sum"] += raw_pnl
            item["worst_pct"] = min(item["worst_pct"], loss_pct)
            item["last_date"] = sell_date or item["last_date"]
            if label:
                item["labels"].add(label.split("(")[0].strip())

    for sid, item in rescue.items():
        item["labels"] = "、".join(sorted(item["labels"])) if item["labels"] else "已認賠/停損"
    return rescue


def render_battle_summary(master_list, rank_sorted):
    attack_df = master_list[master_list["評級"].isin(["S", "A"])] if not master_list.empty else pd.DataFrame()
    b_df = master_list[master_list["評級"].eq("B")] if not master_list.empty else pd.DataFrame()
    top_names = "、".join((attack_df["名稱"].astype(str) + "(" + attack_df["代號"].astype(str) + ")").head(3).tolist()) if not attack_df.empty else "今日無主攻標的"
    caution_cnt = 0
    if rank_sorted is not None and not rank_sorted.empty:
        caution_cnt = int(((rank_sorted.get("RSI", 50) > 75) | (rank_sorted.get("乖離(%)", 0) > 8) | (rank_sorted.get("生命週期", "").astype(str).str.contains("第三段", na=False))).sum())
    market_msg = "可小量作戰" if MACRO_SCORE > 5 and not OVERHEAT_FLAG else "防守優先、降低倉位"
    st.markdown("#### 🧭 今日作戰摘要")
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        (MODE_PROFILE["label"], MODE_PROFILE["note"], COLORS["primary"]),
        (f"可出手 {len(attack_df)} 檔", top_names, COLORS["green"] if len(attack_df) else COLORS["accent"]),
        (f"B級備選 {len(b_df)} 檔", "只回踩低接，不追高", COLORS["accent"]),
        (f"禁追/警戒 {caution_cnt} 檔", market_msg, COLORS["red"] if caution_cnt else COLORS["green"]),
    ]
    for col, (title, sub, color) in zip([c1, c2, c3, c4], cards):
        with col:
            st.markdown(f"""
            <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {color}; border-radius:10px; padding:12px 14px; min-height:86px;">
                <div style="font-size:16px; font-weight:800; color:{COLORS['text']}; margin-bottom:6px;">{title}</div>
                <div style="font-size:12.5px; line-height:1.35; color:{COLORS['subtext']};">{sub}</div>
            </div>
            """, unsafe_allow_html=True)


def _macro_to_float(val):
    try:
        return float(str(val).replace("%", "").replace(",", "").strip())
    except Exception:
        return np.nan


def build_macro_brief(macro_df, macro_score, overheat_flag):
    """把國際大盤表格翻成一句可執行的明日策略。"""
    if macro_df is None or macro_df.empty:
        return {
            "title": "資料不足：大盤狀態暫時無法判讀",
            "body": "目前大盤資料未成功讀取。明日先以保守模式處理，只看既有持股與高把握 S/A，避免因資料斷線誤判行情。",
            "strategy": "建議：降低倉位，不追高；等資料恢復後再恢復正常掃描。",
            "risk": "風險提醒：請先檢查 Yahoo / 大盤儀表資料健康燈號。",
            "color": COLORS["accent"],
            "icon": "⚪"
        }

    dfm = macro_df.copy()
    if "名稱" not in dfm.columns:
        return {
            "title": "資料格式異常：大盤欄位無法判讀",
            "body": "目前大盤表格缺少【名稱】欄位，無法產生完整綜合結論。",
            "strategy": "建議：先以系統分級與個股技術面為主，降低操作金額。",
            "risk": "風險提醒：請檢查 data_center.py 的 get_macro_dashboard 回傳欄位。",
            "color": COLORS["accent"],
            "icon": "⚪"
        }

    def find_row(keyword):
        hit = dfm[dfm["名稱"].astype(str).str.contains(keyword, na=False)]
        return hit.iloc[0] if not hit.empty else None

    tw = find_row("台股")
    nas = find_row("那斯")
    spx = find_row("標普")
    vix = find_row("恐慌")
    fx = find_row("美元")

    def bias_of(row):
        if row is None or "乖離(%)" not in row.index:
            return np.nan
        return _macro_to_float(row["乖離(%)"])

    def status_of(row):
        if row is None or "狀態" not in row.index:
            return ""
        return str(row["狀態"])

    tw_bias = bias_of(tw)
    tw_status = status_of(tw)
    nas_status = status_of(nas)
    spx_status = status_of(spx)
    vix_status = status_of(vix)
    fx_status = status_of(fx)

    equity_bulls = sum("多頭" in x for x in [tw_status, nas_status, spx_status])
    vix_ok = ("安定" in vix_status) or ("月線下" in vix_status)
    fx_bad = ("貶值" in fx_status) or ("資金外逃" in fx_status)
    hot = bool(overheat_flag) or (pd.notna(tw_bias) and tw_bias >= 5)

    risk_items = []
    if hot:
        risk_items.append(f"台股乖離偏高{f'({tw_bias:.2f}%)'if pd.notna(tw_bias) else ''}，短線拉回風險增加")
    if fx_bad:
        risk_items.append("美元/台幣偏強，資金面需留意")
    if not vix_ok:
        risk_items.append("VIX 未明顯安定，盤中波動可能放大")
    if equity_bulls <= 1:
        risk_items.append("主要股市站上月線數量不足，趨勢保護偏弱")

    if macro_score <= 3:
        title = "偏空防守：不開新倉"
        body = "趨勢或資金面不利，先保本金。"
        strategy = "新倉暫停；只處理持股停損/減碼。"
        color, icon = COLORS["red"], "🔴"
    elif hot:
        title = "偏多過熱：小量，不追高"
        body = "趨勢仍有支撐，但台股乖離偏高，早盤追高容易被倒貨。"
        strategy = "S/A 小量；B等13:00後確認；跳空>4.5% 不追。"
        color, icon = COLORS["accent"], "🔥"
    elif macro_score >= 7 and equity_bulls >= 2 and vix_ok:
        title = "偏多可作戰：優先 S/A"
        body = "主要股市站上月線，VIX 安定，可正常短波段。"
        strategy = "S/A 依計畫；B 只做回踩；禁追價與停損照表。"
        color, icon = COLORS["green"], "🟢"
    elif macro_score >= 5:
        title = "中性偏多：精選少做"
        body = "盤勢不差，但優勢不夠大。"
        strategy = "只選前 2～4 檔；S/A 優先；B 等回踩。"
        color, icon = COLORS["primary"], "🟡"
    else:
        title = "中性偏弱：少做多看"
        body = "安全墊不足，容易買到反彈不是主升。"
        strategy = "只看 S 級與持股；A/B 觀察；破 M10 不凹。"
        color, icon = COLORS["red"], "🟠"

    risk = "；".join(risk_items) if risk_items else "目前未見明顯系統性風險，但仍需遵守禁追價與停損線。"
    return {"title": title, "body": body, "strategy": strategy, "risk": risk, "color": color, "icon": icon}


def render_macro_brief(macro_df, macro_score, overheat_flag):
    brief = build_macro_brief(macro_df, macro_score, overheat_flag)
    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:6px solid {brief['color']}; border-radius:10px; padding:14px 16px; margin-bottom:14px;">
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
            <span style="font-size:22px;">{brief['icon']}</span>
            <span style="font-size:18px; font-weight:800; color:{COLORS['text']};">綜合判斷：{brief['title']}</span>
        </div>
        <div style="font-size:14px; line-height:1.65; color:{COLORS['text']}; margin-bottom:6px;">{brief['body']}</div>
        <div style="font-size:14px; line-height:1.65; color:{COLORS['text']};"><b>策略：</b>{brief['strategy']}</div>
        <div style="font-size:13px; line-height:1.55; color:{COLORS['subtext']}; margin-top:6px;"><b>風險提醒：</b>{brief['risk']}</div>
    </div>
    """, unsafe_allow_html=True)


def render_top_status_panel():
    """市場警戒燈 + 大盤綜合判斷。資料健康移到 Sidebar，不佔主畫面。"""
    if MACRO_SCORE <= 3:
        market_title = f"🔴 紅色警戒 ({MACRO_SCORE}/10)"
        market_msg = "市場偏弱，保留現金，不主動開新倉。"
        main_color = COLORS["red"]
    elif MACRO_SCORE <= 5:
        market_title = f"🟡 黃色警戒 ({MACRO_SCORE}/10)"
        market_msg = "大盤偏弱，資金減半操作。"
        main_color = COLORS["accent"]
    else:
        market_title = f"🟢 可作戰 ({MACRO_SCORE}/10)"
        market_msg = "盤勢允許短波段，但仍依禁追與停損。"
        main_color = COLORS["green"]

    heat_title = "🔥 高檔過熱" if OVERHEAT_FLAG else "✅ 過熱未觸發"
    heat_msg = "大盤乖離 >5%，新倉限縮，嚴禁早盤追高。" if OVERHEAT_FLAG else "尚未觸發大盤過熱限制。"
    heat_color = COLORS["red"] if OVERHEAT_FLAG else COLORS["green"]
    brief = build_macro_brief(MACRO_DF, MACRO_SCORE, OVERHEAT_FLAG)

    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:6px solid {main_color}; border-radius:10px; padding:14px 16px; margin:8px 0 16px 0;">
        <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:stretch;">
            <div style="flex:1 1 250px; min-width:230px;">
                <div style="font-size:17px; font-weight:900; color:{COLORS['text']};">{market_title}</div>
                <div style="font-size:13px; color:{COLORS['subtext']}; margin-top:4px; line-height:1.5;">{market_msg}</div>
            </div>
            <div style="flex:1 1 250px; min-width:230px; border-left:1px solid {COLORS['border']}; padding-left:12px;">
                <div style="font-size:17px; font-weight:900; color:{heat_color};">{heat_title}</div>
                <div style="font-size:13px; color:{COLORS['subtext']}; margin-top:4px; line-height:1.5;">{heat_msg}</div>
            </div>
        </div>
        <div style="margin-top:11px; padding-top:10px; border-top:1px dashed {COLORS['border']}; color:{COLORS['text']}; line-height:1.62; font-size:13.5px;">
            <b>{brief['icon']} 綜合判斷：{brief['title']}</b><br>
            {brief['body']}<br>
            <b>明日指令：</b>{brief['strategy']}<br>
            <span style="color:{COLORS['subtext']};"><b>風險提醒：</b>{brief['risk']}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


with st.spinner("情報兵正在部署防線..."):
    chip_db = fetch_chips_data(FM_TOKEN)

m_df = pd.DataFrame()
today_df = pd.DataFrame()
top_80_chips = []
holding_rows = 0
holding_read_ok = False
aar_rows = 0
aar_read_ok = False
aar_probe_df = pd.DataFrame()
rescue_residual_map = {}

def _build_technical_fallback_chips(max_rows=350):
    """V37.2：法人籌碼 / 快取異常時，建立技術面候選池，避免個股游擊與情報局整區空白。"""
    fallback_rows = []
    for code, name in list(TWSE_NAME_MAP.items()):
        code = str(code).strip()
        ind = str(TWSE_IND_MAP.get(code, ""))
        if not code.isdigit() or len(code) != 4 or code.startswith("00"):
            continue
        if any(x in ind for x in ["金融", "保險", "存託憑證"]):
            continue
        fallback_rows.append({
            "代號": code,
            "名稱": name,
            "外資(張)": 0.0,
            "投信(張)": 0.0,
            "自營(張)": 0.0,
            "三大法人合計": 0.0,
            "連買": 0,
            "投信連賣": 0,
            "法人狀態": "⚪ 法人資料暫缺",
        })
        if len(fallback_rows) >= int(max_rows):
            break
    return pd.DataFrame(fallback_rows)


def _ensure_today_candidates(reason=""):
    """V37.3：在頁籤渲染前再次保底，避免 today_df 在初始化後仍為空。"""
    global today_df, top_80_chips, dates, chip_data_available, chips_data_source
    if isinstance(today_df, pd.DataFrame) and not today_df.empty and "代號" in today_df.columns:
        return
    today_df = _build_technical_fallback_chips(max_rows=350)
    dates = ["TECH"]
    top_80_chips = today_df["代號"].astype(str).head(120).tolist() if not today_df.empty else []
    chip_data_available = False
    chips_data_source = "技術備援"
    if reason:
        st.warning(f"⚠️ 已啟用技術備援候選池：{reason}｜候選 {len(today_df)} 檔")


def _debug_data_chain_box(extra=None):
    """V37.4：精簡資料鏈診斷；只有掃描失敗時才在主畫面顯示。"""
    extra = extra or {}
    try:
        eod_df = st.session_state.get("eod_intel_df", pd.DataFrame())
        eod_rows = 0 if eod_df is None else (len(eod_df) if isinstance(eod_df, pd.DataFrame) else -1)
    except Exception:
        eod_rows = -1
    diag = {
        "大盤分": MACRO_SCORE,
        "候選池": len(today_df) if isinstance(today_df, pd.DataFrame) else -1,
        "籌碼日": len(chip_db) if isinstance(chip_db, dict) else -1,
        "來源": chips_data_source,
        "掃描檔": eod_rows,
    }
    diag.update(extra)
    with st.expander("🩺 資料鏈診斷", expanded=False):
        st.dataframe(pd.DataFrame([diag]), use_container_width=True, hide_index=True)


def _run_level2_rescue(calc_list, label="主掃描"):
    """V37.3：level2 若被快取成空或批次失敗，清 cache 後用較小候選池再試一次。"""
    calc_list = tuple(str(x).strip() for x in calc_list if str(x).strip() and not str(x).startswith("00"))
    if not calc_list:
        return pd.DataFrame(), "calc_list 空"
    try:
        df = level2_quant_engine(calc_list, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, FM_TOKEN)
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df, f"{label} 成功：{len(df)} 檔"
    except Exception as e:
        first_err = str(e)
    else:
        first_err = "第一次回傳空表或 None"

    # Streamlit cache 可能把限流期間的空結果暫存；強制清一次再縮小樣本。
    try:
        level2_quant_engine.clear()
    except Exception:
        pass

    # 縮小候選池，降低 Yahoo / FinMind 壓力；優先用前 60 檔。
    small_list = calc_list[:60]
    try:
        df2 = level2_quant_engine(small_list, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, FM_TOKEN)
        if isinstance(df2, pd.DataFrame) and not df2.empty:
            return df2, f"{label} 第一次失敗；縮小重試成功：{len(df2)} 檔"
        return pd.DataFrame(), f"{label} 仍無技術資料：{first_err}"
    except Exception as e:
        return pd.DataFrame(), f"{label} 重試失敗：{first_err}｜{e}"


chip_data_available = len(chip_db) >= 1
chips_data_source = st.session_state.get("chips_data_source", "即時")

if chip_data_available:
    dates = sorted(list(chip_db.keys()), reverse=True)
    today_df = chip_db[dates[0]].copy()

    for i, d in enumerate(dates):
        today_df = pd.merge(today_df, chip_db[d][["代號", "投信(張)"]].rename(columns={"投信(張)": f"D{i}"}), on="代號", how="left").fillna(0)

    def get_streak(r):
        s = 0
        for i in range(len(dates)):
            if r.get(f"D{i}", 0) > 0: s += 1
            else: break
        return s

    def get_sell_streak(r):
        s = 0
        for i in range(len(dates)):
            if r.get(f"D{i}", 0) < 0: s += 1
            else: break
        return s

    today_df["連買"] = today_df.apply(get_streak, axis=1)
    today_df["投信連賣"] = today_df.apply(get_sell_streak, axis=1)
    today_df["法人狀態"] = today_df.apply(get_institution_state, axis=1)
    top_80_chips = today_df.sort_values("投信(張)", ascending=False).head(80)["代號"].tolist()

    # V37.2：防止 chip_db 有 key 但最新 DataFrame 為空，導致 S/A/B 與情報局整區無資料。
    if today_df.empty or "代號" not in today_df.columns:
        st.toast("法人籌碼快取格式異常；啟用技術面備援，避免個股游擊與情報局空白。", icon="⚠️")
        today_df = _build_technical_fallback_chips(max_rows=350)
        dates = ["TECH"]
        top_80_chips = today_df["代號"].head(120).tolist() if not today_df.empty else []
        chip_data_available = False
        chips_data_source = "技術備援"
else:
    st.toast("籌碼連線失敗；啟用技術面備援，S/A/B 仍可掃描但法人欄位暫缺。", icon="⚠️")
    today_df = _build_technical_fallback_chips(max_rows=350)
    dates = ["TECH"]
    top_80_chips = today_df["代號"].head(120).tolist() if not today_df.empty else []
    chip_data_available = False
    chips_data_source = "技術備援"

if sheet_url and auth_status == "admin_auth":
    try:
        sheet_df = read_remote_csv(sheet_url, dtype=str)
        holding_rows = len(sheet_df)
        holding_read_ok = not sheet_df.empty
        code_col = next((c for c in sheet_df.columns if any(k in c for k in ["代號", "代碼"])), None)
        if code_col: sheet_df = sheet_df.rename(columns={code_col: "代號"})
            
        h_df = sheet_df[sheet_df["分類"] == "持股"].copy() if "分類" in sheet_df.columns else sheet_df.copy()
        if not h_df.empty and "代號" in h_df.columns:
            h_df["代號"] = h_df["代號"].astype(str).str.strip()
            # 🚀 統帥優化：持股情報直接調用最強的 level2_quant_engine 統一獲取 MACD/RSI/BBAND
            h_intel = level2_quant_engine(tuple(h_df["代號"].tolist()), TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, FM_TOKEN)
            if h_intel is not None and not h_intel.empty:
                m_df = pd.merge(h_df, h_intel, on="代號", how="left")
                if "名稱_x" in m_df.columns: m_df = m_df.rename(columns={"名稱_x": "名稱"}).drop(columns=["名稱_y"], errors='ignore')
                else: m_df["名稱"] = m_df["代號"].map(TWSE_NAME_MAP).fillna("未知")
    except Exception as e: st.error(f"❌ 讀取持股部位失敗：{e}")

if aar_sheet_url:
    try:
        aar_probe_df = read_remote_csv(aar_sheet_url, dtype=str)
        aar_rows = len(aar_probe_df)
        aar_read_ok = not aar_probe_df.empty
    except Exception:
        aar_probe_df = pd.DataFrame()
        aar_rows = 0
        aar_read_ok = False

if not m_df.empty and "代號" in m_df.columns:
    rescue_residual_map = build_rescue_residual_map(aar_probe_df, m_df["代號"].astype(str).tolist())

# 資料健康燈號移至 Sidebar，主畫面不再佔用 S/A/B 空間。
_eod_cached = st.session_state.get("eod_intel_df", pd.DataFrame())
_eod_rows = len(_eod_cached) if isinstance(_eod_cached, pd.DataFrame) else 0
status_items = [
    ("產業", len(TWSE_NAME_MAP) > 0),
    ("大盤", not MACRO_DF.empty),
    ("法人/候選", chip_data_available or (isinstance(today_df, pd.DataFrame) and not today_df.empty)),
    ("SAB", (_eod_rows > 0) or (isinstance(today_df, pd.DataFrame) and not today_df.empty)),
    ("持股", (auth_status != "admin_auth") or holding_read_ok or not sheet_url),
    ("AAR", aar_read_ok or not aar_sheet_url),
    ("Token", bool(str(FM_TOKEN).strip())),
]
ok_count = sum(ok for _, ok in status_items)
color = COLORS["green"] if ok_count >= 5 else (COLORS["accent"] if ok_count >= 4 else COLORS["red"])
health_html = f"""
<div class="side-status-card" style="border-left-color:{color};">
    <b>🧭 資料狀態：{ok_count}/{len(status_items)} 正常</b><br>
    <span style="font-size:12px; opacity:.75;">{'全部正常' if ok_count == len(status_items) else '部分異常，請展開查看'}</span>
</div>
"""
health_slot = configs.get("health_slot") if isinstance(configs, dict) else None
try:
    if health_slot is not None:
        with health_slot.container():
            st.markdown(health_html, unsafe_allow_html=True)
            with st.expander("資料連線", expanded=False):
                st.markdown("｜".join([f"{'✅' if ok else '⚠️'} {name}" for name, ok in status_items]))
                st.caption(f"候選 {len(today_df) if isinstance(today_df, pd.DataFrame) else 0}｜籌碼日 {len(chip_db) if isinstance(chip_db, dict) else 0}｜SAB掃描 {_eod_rows}｜來源 {chips_data_source}")
    else:
        with st.sidebar:
            st.markdown(health_html, unsafe_allow_html=True)
except Exception:
    with st.sidebar:
        st.markdown(health_html, unsafe_allow_html=True)

render_top_status_panel()

# =========================================================
# 🔥 主流曝險警報 + 輪動建議
# =========================================================
def _theme_from_industry(industry, code="", name=""):
    code = str(code or "").strip().upper()
    text = f"{industry or ''} {name or ''} {code}"
    if code == "0050":
        return "長期存錢倉"
    if code.startswith("00"):
        if any(k in text for k in ["科技", "AI", "半導體", "電子"]):
            return "科技ETF"
        if any(k in text for k in ["高息", "股息", "動能高息"]):
            return "高息ETF"
        return "ETF"
    rules = [("半導體", "半導體"), ("電子零組件", "電子零組件/PCB"), ("電腦及週邊", "AI伺服器/電腦週邊"), ("通信網路", "網通/通信"), ("其他電子", "設備/散熱/其他電子"), ("電機機械", "電機機械"), ("生技", "生技醫療"), ("金融", "金融"), ("航運", "航運"), ("觀光", "觀光/內需"), ("貿易百貨", "內需消費"), ("食品", "食品/內需"), ("化學", "化工"), ("塑膠", "塑化"), ("鋼鐵", "鋼鐵")]
    for key, theme in rules:
        if key in text:
            return theme
    if "電子" in text:
        return "科技/電子"
    return str(industry or "未分類") or "未分類"

def _theme_group(theme):
    t = str(theme)
    if any(k in t for k in ["半導體", "電子", "AI", "電腦", "網通", "科技", "設備", "PCB"]):
        return "科技電子"
    if "ETF" in t:
        return "ETF"
    return t

def _row_position_value(row):
    def pick(keys):
        for col in row.index:
            if any(k in str(col) for k in keys):
                v = row[col]
                if pd.notna(v) and str(v).strip() not in ["", "nan", "None"]:
                    try:
                        return float(str(v).replace(",", ""))
                    except Exception:
                        pass
        return 0.0
    price = pick(["現價", "市價"])
    qty = pick(["庫存張數", "張數", "庫存", "股數", "數量"])
    return max(0.0, price * qty * 1000)

def _build_rotation_suggestions(dominant_group, COLORS):
    frames = []
    for key in ["eod_master_list", "eod_special_watch", "eod_rank_sorted"]:
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            frames.append(df.copy())
    if not frames:
        return []
    pool = pd.concat(frames, ignore_index=True)
    if "代號" not in pool.columns:
        return []
    pool = pool.drop_duplicates(subset=["代號"], keep="first").copy()
    pool = pool[~pool["代號"].astype(str).str.startswith("00")].copy()
    if pool.empty:
        return []
    if "Quant_Score" not in pool.columns:
        pool["Quant_Score"] = pd.to_numeric(pool.get("量化評分", 0), errors="coerce").fillna(0)
    rows = []
    for _, rr in pool.iterrows():
        code = str(rr.get("代號", "")).strip()
        name = str(rr.get("名稱", TWSE_NAME_MAP.get(code, code))).strip()
        ind = str(rr.get("產業", TWSE_IND_MAP.get(code, "未分類"))).strip()
        theme = _theme_from_industry(ind, code, name)
        group = _theme_group(theme)
        if group == dominant_group or theme in ["長期存錢倉", "未分類"]:
            continue
        score = float(pd.to_numeric(pd.Series([rr.get("Quant_Score", 0)]), errors="coerce").fillna(0).iloc[0])
        rows.append({"theme": theme, "score": score, "code": code})
    if not rows:
        return []
    x = pd.DataFrame(rows)
    g = x.groupby("theme").agg(count=("code", "count"), avg_score=("score", "mean"), best_score=("score", "max"), examples=("code", lambda s: "、".join(list(s.astype(str).head(3))))).reset_index()
    g["rotation_score"] = g["count"] * 10 + g["avg_score"]
    g = g.sort_values(["rotation_score", "best_score"], ascending=False).head(3)
    return [f"{r['theme']}（{int(r['count'])} 檔，均分 {r['avg_score']:.0f}，例：{r['examples']}）" for _, r in g.iterrows()]

def render_mainstream_exposure_alert(hold_df, COLORS, industry_map, name_map):
    if hold_df is None or hold_df.empty:
        return
    exposure, total_value = [], 0.0
    for _, r in hold_df.iterrows():
        code = str(r.get("代號", "")).strip().upper()
        if not code or code == "0050":
            continue
        name = str(r.get("名稱", name_map.get(code, code))).strip()
        value = _row_position_value(r)
        if value <= 0:
            continue
        ind = str(r.get("產業", industry_map.get(code, ""))).strip()
        theme = _theme_from_industry(ind, code, name)
        group = _theme_group(theme)
        exposure.append({"code": code, "name": name, "value": value, "theme": theme, "group": group})
        total_value += value
    if not exposure or total_value <= 0:
        return
    exp_df = pd.DataFrame(exposure)
    grp = exp_df.groupby("group").agg(value=("value", "sum"), count=("code", "count"), themes=("theme", lambda s: "、".join(pd.Series(s).dropna().astype(str).unique()[:4]))).reset_index()
    grp["pct"] = grp["value"] / total_value * 100
    grp = grp.sort_values("pct", ascending=False)
    top = grp.iloc[0]
    pct = float(top["pct"]); dominant_group = str(top["group"])
    color = COLORS["red"] if pct >= 75 else (COLORS["accent"] if pct >= 60 else COLORS["primary"])
    if pct >= 75:
        status = "⚠️ 主流曝險偏高"; command = "可抱強勢倉，但今日不建議再加同方向；若大盤跌破 M5，優先處理新倉與弱倉。"
    elif pct >= 60:
        status = "🟡 主流曝險集中"; command = "短波段可接受集中，但新倉需縮量；避免同族群連續加碼。"
    else:
        status = "🟢 曝險尚可"; command = "目前作戰倉未過度集中；仍以 S/A/B 與 ETF 動能決定是否出手。"
    suggestions = _build_rotation_suggestions(dominant_group, COLORS)
    sug_text = "<br>".join([f"{i+1}. {x}" for i, x in enumerate(suggestions)]) if suggestions else "目前沒有足夠強的替代族群；不為了分散而買弱勢股，寧可留現金。"
    chips = "".join([f"<span style='display:inline-block; padding:4px 8px; border-radius:999px; background:{COLORS['bg']}; border:1px solid {COLORS['border']}; margin:2px 4px 2px 0; font-size:12px;'>{html.escape(str(r['group']))} {float(r['pct']):.0f}%</span>" for _, r in grp.head(4).iterrows()])
    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {color}; border-radius:10px; padding:12px 14px; margin:8px 0 14px 0;">
        <div style="font-size:17px; font-weight:900; color:{color};">🔥 {status}｜{html.escape(dominant_group)} {pct:.0f}%</div>
        <div style="font-size:13px; color:{COLORS['subtext']}; margin-top:4px;">作戰倉估算，不含 0050 長期存錢倉。主要集中：{html.escape(str(top['themes']))}</div>
        <div style="margin-top:8px;">{chips}</div>
        <div style="font-size:13.5px; line-height:1.65; margin-top:8px; color:{COLORS['text']};"><b>策略：</b>{html.escape(command)}<br><b>輪動觀察：</b><br>{sug_text}</div>
    </div>
    """, unsafe_allow_html=True)

@st.fragment
def render_sandbox_panel():
    st.markdown("### 🔮 <span class='highlight-primary'>沙盤推演</span>", unsafe_allow_html=True)
    col_s1, col_s2 = st.columns([1, 3])
    with col_s1:
        sim_id = st.text_input("股票代號", placeholder="例: 2330 或 0050", label_visibility="collapsed", key="sandbox_stock_id")
        sim_btn = st.button("⚡執行體檢", use_container_width=True, key="sandbox_btn")
        if st.button("🧹 清除結果", use_container_width=True, key="sandbox_clear_btn"):
            st.session_state.pop("sandbox_last_result", None)
            st.session_state.pop("sandbox_last_id", None)

    with col_s2:
        if sim_btn and sim_id:
            with st.spinner("🧠 正在呼叫量化引擎掃描..."):
                res = run_sandbox_sim(str(sim_id).strip(), TWSE_NAME_MAP, FM_TOKEN)
                st.session_state["sandbox_last_result"] = res
                st.session_state["sandbox_last_id"] = str(sim_id).strip()

        res = st.session_state.get("sandbox_last_result")
        if res:
            grade_color, grade_text, advice = mobile_ui._get_sandbox_grade(res, COLORS)
            badge = mobile_ui._get_fundamental_badge_safe(res, FM_TOKEN, get_fundamental_badge)
            st.markdown(mobile_ui._render_sandbox_merged_html(res, badge, grade_color, grade_text, advice, COLORS), unsafe_allow_html=True)
        elif sim_btn:
            st.error("❌ 查無此股票或歷史資料不足，請確認代碼是否正確。")

        else:
            st.info("輸入代號後執行體檢；結果會暫存在本頁，不會因切換分頁立刻消失。")


def _fmt_money0(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return str(x)



if mobile_quick_mode:
    mobile_ui.render_mobile_battle_room(
        COLORS, TWSE_NAME_MAP, FM_TOKEN, run_sandbox_sim, get_fundamental_badge,
        auth_status, m_df, fee_discount
    )
    st.stop()


t_rank, t_etf, t_chip, t_cmd, t_book = st.tabs(["🎯 個股游擊", "📈 ETF 主體倉", "📡 情報局", "🏦 總司令部", "📖 兵工廠與軍史館"])

with t_rank:
    _ensure_today_candidates("進入個股游擊時 today_df 仍為空")
    render_sandbox_panel()
    st.markdown("<hr style='margin: 10px 0 25px 0; border-color: " + COLORS["border"] + ";'>", unsafe_allow_html=True)
    st.markdown("### 🎯 <span class='highlight-primary'>明日作戰部隊</span>", unsafe_allow_html=True)
    scan_col1, scan_col2 = st.columns([1, 3])
    with scan_col1:
        force_eod_scan = st.button("🔄 重新掃描明日清單", use_container_width=True, key="force_eod_scan")
    with scan_col2:
        last_scan = st.session_state.get("eod_last_scan_time", "尚未掃描")
        st.caption(f"最後掃描時間：{last_scan}")

    with st.expander("🌍 國際大盤數值"):
        if not MACRO_DF.empty:
            disp_macro = MACRO_DF.copy()
            if "現價" in disp_macro.columns: disp_macro["現價"] = pd.to_numeric(disp_macro["現價"], errors='coerce').apply(lambda x: f"{x:.2f}")
            if "月線(M20)" in disp_macro.columns: disp_macro["月線(M20)"] = pd.to_numeric(disp_macro["月線(M20)"], errors='coerce').apply(lambda x: f"{x:.2f}")
            if "乖離(%)" in disp_macro.columns: disp_macro["乖離(%)"] = pd.to_numeric(disp_macro["乖離(%)"].astype(str).str.replace('%',''), errors='coerce').apply(lambda x: f"{x:.2f}%")
            
            styled_macro = disp_macro.style.set_properties(**table_style).map(
                lambda x: f'color: {COLORS["green"]};' if "多頭" in str(x) or "安定" in str(x) or "升值" in str(x) 
                else (f'color: {COLORS["red"]};' if "空頭" in str(x) or "恐慌" in str(x) or "貶值" in str(x) else ""), 
                subset=["狀態"]
            )
            st.dataframe(styled_macro, use_container_width=True, hide_index=True)

    if not today_df.empty:
        st.caption(f"大盤燈號：{MACRO_SCORE}/10，只作風險提醒，不再阻斷 S/A/B 掃描；是否進場由你自行判斷。")
        if chip_data_available:
            calc_list = tuple(x for x in set(today_df[today_df["連買"] >= 1]["代號"].tolist() + top_80_chips) if not str(x).startswith("00"))
        else:
            st.info("⚠️ 法人籌碼暫缺，已啟用技術面備援掃描；法人狀態、連買天數僅供暫缺標示，不作籌碼判斷。")
            calc_list = tuple(x for x in top_80_chips if not str(x).startswith("00"))
        scan_key = f"{dates[0] if 'dates' in locals() and dates else 'nodate'}_{MACRO_SCORE}_{operation_mode}_{len(calc_list)}_{chips_data_source}"
        needs_eod_scan = force_eod_scan or st.session_state.get("eod_scan_key") != scan_key or "eod_intel_df" not in st.session_state
        if needs_eod_scan:
            intel_df, scan_msg = _run_level2_rescue(calc_list, "S/A/B 技術掃描")
            st.session_state["eod_intel_df"] = intel_df
            st.session_state["eod_scan_msg"] = scan_msg
            st.session_state["eod_scan_key"] = scan_key
            st.session_state["eod_last_scan_time"] = datetime.now().strftime("%H:%M:%S")
        else:
            intel_df = st.session_state.get("eod_intel_df")
            scan_msg = st.session_state.get("eod_scan_msg", "沿用快取掃描結果")

        st.caption(f"技術掃描狀態：{scan_msg}")
        if intel_df is None or getattr(intel_df, "empty", True):
            st.error("🚨 S/A/B 技術掃描目前沒有產出資料。這代表批次價格資料鏈失敗或被限流；沙盤單檔仍可使用。", icon="💀")
            _debug_data_chain_box({"calc_list": len(calc_list), "scan_msg": scan_msg})
        else:
            final_rank = pd.merge(today_df, intel_df, on="代號", suffixes=("_chip", "_intel"))
            final_rank = final_rank[~final_rank["代號"].astype(str).str.startswith("00")].copy()
            if "名稱_chip" in final_rank.columns: final_rank = final_rank.rename(columns={"名稱_chip": "名稱"})
            elif "名稱_x" in final_rank.columns: final_rank = final_rank.rename(columns={"名稱_x": "名稱"})
            if "名稱_intel" in final_rank.columns: final_rank = final_rank.drop(columns=["名稱_intel"])
            if "名稱_y" in final_rank.columns: final_rank = final_rank.drop(columns=["名稱_y"])

            def determine_phase(row):
                vol_ratio = row.get("vol_ratio", 0)
                close_pos = row.get("close_position", 1)
                streak = row["連買"]
                if vol_ratio > 1.8 and close_pos < 0.4: return "💀 第三段 (爆量出貨)"
                elif streak >= 14: return "💀 第三段 (高機率末升)"
                elif streak >= 11: return "⚠️ 第三段 (提高警覺)"
                elif "🚀" in row["戰術型態"] or "🔥" in row["戰術型態"]: return "🔥 第一段 (主升起漲)"
                elif "🛡️" in row["戰術型態"]: return "🛡️ 第二段 (均線回踩)"
                else: return "⏳ 觀望醞釀"

            final_rank["生命週期"] = final_rank.apply(determine_phase, axis=1)
            final_rank["法人狀態"] = final_rank.apply(get_institution_state, axis=1)

            def calculate_quant_score(row):
                score = 50
                if row["勝率(%)"] > 50: score += (row["勝率(%)"] - 50) * 0.5
                elif row["勝率(%)"] < 50: score -= (50 - row["勝率(%)"]) * 0.5

                streak = row["連買"]
                if 3 <= streak <= 7: score += 20
                elif 8 <= streak <= 10: score += 10
                elif streak >= 14: score -= 15

                score += row["均報(%)"] * 10 + row["安全指數"] * 2

                vol_ratio = row.get("vol_ratio", 0)
                close_pos = row.get("close_position", 1)
                
                if vol_ratio > 1.8 and close_pos > 0.7: score += 15
                elif vol_ratio > 1.8 and close_pos < 0.4: score -= 25

                t = row["戰術型態"]
                if "🔥" in t: score += 25
                elif "🚀" in t: score += 15
                elif "🛡️" in t: score += 10
                elif "⚠️" in t: score -= 15

                phase = row["生命週期"]
                if "第一段" in phase: score += 20
                elif "第二段" in phase:
                    score += 8
                    if close_pos > 0.6: score += 10
                elif "爆量出貨" in phase: score -= 35
                elif "高機率末升" in phase: score -= 30
                elif "提高警覺" in phase: score -= 15

                if row["乖離(%)"] > 8: score -= (row["乖離(%)"] - 5) * 3
                if MACRO_SCORE <= 5:
                    score -= 15
                    if row["乖離(%)"] > 5: score -= 20

                vol_m20 = row.get("vol_ma20", 2000)
                atr_pct = row.get("atr_percent", 3.0)
                ind = str(row.get("產業", ""))
                name = str(row.get("名稱", ""))
                
                if vol_m20 < 1500: score -= 30  
                if atr_pct < 2.0: score -= 30  
                if "金融" in ind or "保險" in ind or name in ["中華電", "台灣大", "遠傳"]: score -= 20

                return round(score, 1)

            final_rank["Quant_Score"] = final_rank.apply(calculate_quant_score, axis=1)
            final_rank["安全指數"] = final_rank.apply(calc_refined_safety_score, axis=1)
            final_rank["決策標籤"] = final_rank.apply(get_decision_label, axis=1)
            final_rank["建議"] = final_rank.apply(get_next_action, axis=1)
            rank_sorted = final_rank.sort_values("Quant_Score", ascending=False).reset_index(drop=True)
            is_phase_3 = rank_sorted["生命週期"].str.contains("第三段", na=False)
            
            s_mask = (rank_sorted["Quant_Score"] >= MODE_PROFILE["s"]) & (rank_sorted["基本達標"] == True) & (~is_phase_3)
            a_mask = (~s_mask) & (rank_sorted["Quant_Score"] >= MODE_PROFILE["a"]) & (rank_sorted["基本達標"] == True)
            b_mask = (~s_mask) & (~a_mask) & (rank_sorted["Quant_Score"] >= MODE_PROFILE["b"])
            c_mask = (~s_mask) & (~a_mask) & (~b_mask)

            s_all = rank_sorted[s_mask].copy()
            a_all = rank_sorted[a_mask].copy()
            b_all = rank_sorted[b_mask].copy()
            s_all["評級"], a_all["評級"], b_all["評級"] = "S", "A", "B"

            # v35：個股游擊主畫面只保留 S/A/B Top 10，避免 C 級雜訊干擾執行。
            master_list = pd.concat([s_all, a_all, b_all]).sort_values("Quant_Score", ascending=False).reset_index(drop=True)
            master_list = master_list[master_list["現價"] > master_list["停損價"]].head(10).copy()

            # V37.1：S/A/B 顯示保護。
            # 若嚴格條件剛好讓主清單為空，但 rank_sorted 仍有可觀察標的，
            # 就用「保守 B 級觀察」補出清單，避免畫面看起來像 SAB 標籤整個消失。
            # 這不是放寬買進，而是讓你仍看得到候選股與分數，實際進場仍需沙盤體檢。
            if master_list.empty and not rank_sorted.empty:
                fallback_pool = rank_sorted.copy()
                fallback_pool["安全指數"] = fallback_pool.apply(calc_refined_safety_score, axis=1)
                fallback_pool["決策標籤"] = fallback_pool.apply(get_decision_label, axis=1)
                fallback_pool["建議"] = fallback_pool.apply(get_next_action, axis=1)
                fallback_pool["法人狀態"] = fallback_pool.apply(get_institution_state, axis=1)
                fallback_mask = (
                    (pd.to_numeric(fallback_pool["Quant_Score"], errors="coerce").fillna(0) >= MODE_PROFILE["b"] - 10)
                    & (pd.to_numeric(fallback_pool["現價"], errors="coerce").fillna(0) > pd.to_numeric(fallback_pool["停損價"], errors="coerce").fillna(0))
                    & (~fallback_pool["生命週期"].astype(str).str.contains("爆量出貨|高機率末升", na=False))
                    & (~fallback_pool["決策標籤"].astype(str).str.contains("禁買|出場", na=False))
                )
                master_list = fallback_pool[fallback_mask].sort_values(["Quant_Score", "安全指數"], ascending=[False, False]).head(10).copy()
                if not master_list.empty:
                    def _fallback_grade(row):
                        score = float(row.get("Quant_Score", 0) or 0)
                        basic_ok = bool(row.get("基本達標", False))
                        if basic_ok and score >= MODE_PROFILE["s"]:
                            return "S"
                        if basic_ok and score >= MODE_PROFILE["a"]:
                            return "A"
                        return "B"
                    master_list["評級"] = master_list.apply(_fallback_grade, axis=1)
                    master_list["建議"] = master_list["建議"].astype(str).apply(
                        lambda x: ("保守觀察｜" + x) if "保守觀察" not in x else x
                    )
                    st.warning("⚠️ 嚴格 S/A/B 條件暫時沒有主攻標的；已啟用保守觀察清單。這些標的需再用沙盤體檢，不代表直接買進。")

            master_list["名次"] = range(1, len(master_list) + 1) if not master_list.empty else []

            main_codes_now = set(master_list["代號"].astype(str).tolist()) if not master_list.empty else set()
            st.session_state["eod_main_codes"] = main_codes_now
            st.session_state["eod_master_list"] = master_list.copy()
            st.session_state["eod_rank_sorted"] = rank_sorted.copy()

            # v35：特殊關注 Top 3。不是買進名單，只抓接近達標、線型修復、法人未撤退的候補股。
            special_pool = rank_sorted[~rank_sorted["代號"].astype(str).isin(main_codes_now)].copy()
            if not special_pool.empty:
                special_pool["安全指數"] = special_pool.apply(calc_refined_safety_score, axis=1)
                special_pool["決策標籤"] = special_pool.apply(get_decision_label, axis=1)
                special_pool["建議"] = special_pool.apply(get_next_action, axis=1)
                special_pool["法人狀態"] = special_pool.apply(get_institution_state, axis=1)
                special_mask = (
                    (~special_pool["生命週期"].astype(str).str.contains("爆量出貨|高機率末升", na=False))
                    & (~special_pool["法人狀態"].astype(str).str.contains("撤退", na=False))
                    & (~special_pool["決策標籤"].astype(str).str.contains("禁買|出場", na=False))
                    & (special_pool["安全指數"] >= 6)
                    & (special_pool["Quant_Score"] >= MODE_PROFILE["b"] - 12)
                    & (special_pool["現價"] > special_pool["停損價"])
                )
                special_watch = special_pool[special_mask].sort_values(["Quant_Score", "安全指數"], ascending=[False, False]).head(3).copy()
                special_watch["評級"] = "特殊關注"
                special_watch["名次"] = range(1, len(special_watch) + 1)
            else:
                special_watch = pd.DataFrame()
            st.session_state["eod_special_watch"] = special_watch.copy() if isinstance(special_watch, pd.DataFrame) else pd.DataFrame()

            if master_list.empty:
                st.warning("今日沒有通過 S/A/B 條件的標的。這通常不是壞掉，而是分數、基本達標、停損線、乖離或資料源限流造成清單被過濾。")
                diag_cols = ["代號", "名稱", "Quant_Score", "基本達標", "現價", "停損價", "生命週期", "戰術型態", "決策標籤"]
                diag_cols = [c for c in diag_cols if c in rank_sorted.columns]
                if diag_cols:
                    with st.expander("🔎 查看未入選診斷 Top 20", expanded=False):
                        st.dataframe(rank_sorted[diag_cols].head(20), use_container_width=True, hide_index=True)

            if not master_list.empty:
                def calc_suggested_lots(row):
                    if row["原始風險差額"] > 0:
                        suggested_shares = min(risk_amount / row["原始風險差額"], (total_capital * 0.15) / row["現價"])
                    else: suggested_shares = 0
                    if MACRO_SCORE <= 5 or OVERHEAT_FLAG: suggested_shares *= 0.5
                    suggested_shares *= MODE_PROFILE["size"]
                    if row["現價"] > 3000: suggested_shares *= 0.5
                    return format_lots(suggested_shares)

                master_list["建議買量(張)"] = master_list.apply(calc_suggested_lots, axis=1)
                master_list["法人狀態"] = master_list.apply(get_institution_state, axis=1)
                master_list["安全指數"] = master_list.apply(calc_refined_safety_score, axis=1)
                master_list["決策標籤"] = master_list.apply(get_decision_label, axis=1)
                master_list["建議"] = master_list.apply(get_next_action, axis=1)

                ui_s = master_list[master_list["評級"] == "S"]
                ui_a = master_list[master_list["評級"] == "A"]
                ui_b = master_list[master_list["評級"] == "B"]
                ui_c = master_list[master_list["評級"] == "C"]

                # ===================================================
                # 📱 明日清單下載：手機盤中快速查看
                # ===================================================
                def build_mobile_list(df_src):
                    rows = []
                    for _, rr in df_src.iterrows():
                        tactic = str(rr.get("戰術型態", ""))
                        price = float(rr.get("現價", 0) or 0)
                        m5 = float(rr.get("M5", price) or price)
                        m10 = float(rr.get("M10", price) or price)
                        stop = float(rr.get("停損價", 0) or 0)
                        if "🛡️" in tactic:
                            low_p, high_p = sorted([m10, m5])
                            entry_zone = f"{low_p:.2f}~{high_p:.2f}"
                            note = "回踩單：靠近M5/M10才買"
                        else:
                            entry_zone = f"{price:.2f}~{price * 1.03:.2f}"
                            note = "突破單：+4.5%內才考慮"
                        if float(rr.get("RSI", 50) or 50) > 75:
                            note += "；RSI過熱，不追"
                        if float(rr.get("乖離(%)", 0) or 0) > 8:
                            note += "；乖離過大等回檔"
                        if "第三段" in str(rr.get("生命週期", "")):
                            note += "；末升警戒"
                        rows.append({
                            "評級": rr.get("評級", ""),
                            "代號": rr.get("代號", ""),
                            "名稱": rr.get("名稱", ""),
                            "決策標籤": rr.get("決策標籤", ""),
                            "建議": rr.get("建議", ""),
                            "法人狀態": rr.get("法人狀態", ""),
                            "現價": round(price, 2),
                            "建議進場": entry_zone,
                            "禁追價(+4.5%)": round(price * 1.045, 2),
                            "停損價": round(stop, 2),
                            "建議買量(張)": rr.get("建議買量(張)", ""),
                            "戰術型態": rr.get("戰術型態", ""),
                            "生命週期": rr.get("生命週期", ""),
                            "量化分數": rr.get("Quant_Score", ""),
                            "備註": note,
                        })
                    return pd.DataFrame(rows)

                def build_full_list(df_src):
                    cols = [
                        "名次", "評級", "代號", "名稱", "決策標籤", "建議", "法人狀態", "產業", "生命週期", "戰術型態",
                        "Quant_Score", "勝率(%)", "均報(%)", "安全指數", "安全指數", "現價", "M5", "M10", "M20",
                        "乖離(%)", "RSI", "MACD_Hist", "BB_Upper", "停損價", "停利價",
                        "建議買量(張)", "連買", "投信連賣", "外資(張)", "投信(張)", "自營(張)", "三大法人合計"
                    ]
                    keep = [c for c in cols if c in df_src.columns]
                    out = df_src[keep].copy()
                    if "Quant_Score" in out.columns:
                        out = out.rename(columns={"Quant_Score": "量化分數", "停損價": "ATR停損"})
                    return out

                mobile_csv = build_mobile_list(master_list).to_csv(index=False).encode("utf-8-sig")
                full_csv = build_full_list(master_list).to_csv(index=False).encode("utf-8-sig")
                
                st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
                
                dl1, dl2 = st.columns(2)
                with dl1:
                    st.download_button(
                        "📱 下載簡表 CSV",
                        data=mobile_csv,
                        file_name=f"Mobile_Tactical_List_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
                with dl2:
                    st.download_button(
                        "📊 下載完整 CSV",
                        data=full_csv,
                        file_name=f"Full_Tactical_List_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

                st.markdown("#### 🥇 <span class='highlight-primary'>【S/A級】主力狙擊區</span>", unsafe_allow_html=True)
                
                if ui_s.empty and ui_a.empty: 
                    st.info("今日無 S/A 主攻標的；不追高，等下一輪訊號。")
                else:
                    def render_tier_cards(tier_df, badge_class, badge_name, border_color):
                        cols = st.columns(3)
                        for idx, (_, r) in enumerate(tier_df.iterrows()):
                            if idx >= 3: break
                            with cols[idx]:
                                badges = ""
                                if r.get("MACD_Cross"): badges += f"<span style='background-color: rgba(241, 196, 15, 0.15); color: #F1C40F; padding: 2px 6px; border-radius: 4px; font-size: 11px; border: 1px solid #F1C40F;'>✅ MACD 共振</span>"
                                if r.get("RSI", 50) > 75: badges += f"<span style='background-color: rgba(255, 75, 75, 0.15); color: #FF4B4B; padding: 2px 6px; border-radius: 4px; font-size: 11px; border: 1px solid #FF4B4B;'>⚠️ RSI {r.get('RSI',0):.0f} 禁追高</span>"
                                elif 50 <= r.get("RSI", 50) <= 70: badges += f"<span style='background-color: rgba(63, 185, 80, 0.15); color: #3FB950; padding: 2px 6px; border-radius: 4px; font-size: 11px; border: 1px solid #3FB950;'>🟢 RSI 健康</span>"
                                if r["現價"] > r.get("BB_Upper", 9999) * 1.02: badges += f"<span style='background-color: rgba(230, 126, 34, 0.15); color: #E67E22; padding: 2px 6px; border-radius: 4px; font-size: 11px; border: 1px solid #E67E22;'>🌋 乖離上軌</span>"

                                card_html = f'<div class="tier-card" style="background-color: {COLORS["card"]}; border-top: 4px solid {border_color}; border-left: 1px solid {COLORS["border"]}; border-right: 1px solid {COLORS["border"]}; border-bottom: 1px solid {COLORS["border"]}; height: 100%; display: flex; flex-direction: column;">'
                                
                                # 🚀 終極修復：確保標籤與標題和諧共處
                                card_html += f'<div style="display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; width: 100%;">'
                                
                                # 🛡️ 標籤裝甲：flex: 0 0 auto 絕對禁止縮放，且給予固定寬度或讓他自己決定內容寬度
                                card_html += f'<div style="flex: 0 0 auto; padding-top: 3px;"><span class="tier-badge {badge_class}" style="display:inline-block; padding:2px 7px; border-radius:5px; font-size:12px; font-weight:900; color:{border_color}; border:1px solid {border_color}; background:rgba(255,255,255,0.05); white-space:nowrap;">{badge_name}</span></div>'
                                
                                # 📜 標題自適應：flex: 1 1 auto 填滿剩餘空間，加上 min-width: 0 允許內部文字被壓縮與換行
                                card_html += f'<div style="flex: 1 1 auto; min-width: 0;">'
                                # 使用 clamp 設定字體大小，當空間被壓縮時，字體可以縮小到 13px
                                card_html += f'<h3 style="color: {border_color}; margin: 0; font-size: clamp(13px, 1.1vw + 10px, 19px); line-height: 1.25; word-wrap: break-word;">{r["名稱"]} <span style="white-space: nowrap;">({r["代號"]})</span></h3>'
                                card_html += f'</div>'
                                card_html += f'</div>'
                                
                                card_html += f'<div style="min-height: 22px; margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 4px;">{badges}</div>'
                                
                                card_html += f'<div style="margin-top: auto;">'
                                card_html += f'<p style="color: #A0A0A0; margin: 0 0 8px 0; font-size: 12px;">{r["產業"]} | 投信連買 {r["連買"]} 天</p>'
                                card_html += f'<div style="background-color: {COLORS["bg"]}; padding: 10px; border-radius: 6px; margin-bottom: 10px; border-left: 3px solid {COLORS["green"]};">'
                                card_html += f'<div class="info-row"><span class="info-label" style="font-weight:bold; color: {COLORS["text"]};">🎯 量化評分</span><span class="info-value" style="font-size: 16px; color: {COLORS["text"]}; font-weight:bold;">{r["Quant_Score"]} 分</span></div>'
                                card_html += f'<div style="color: {COLORS["text"]}; font-size: 12px; font-weight: bold; margin-top: 4px;">{r["戰術型態"]} | <span style="color:{COLORS["accent"]}">{r["生命週期"]}</span></div>'
                                card_html += f'<div style="color:{COLORS["subtext"]}; font-size:12px; margin-top:4px;">{r.get("決策標籤", "")} ｜ {r.get("法人狀態", "")}</div></div>'
                                card_html += f'<div style="width: 100%;">'
                                card_html += f'<div class="info-row"><span class="info-label" style="color: {COLORS["text"]}; opacity: 0.8;">📊 歷史勝率</span><span class="info-value"><span style="color: {COLORS["green"]}; font-weight:bold;">{r["勝率(%)"]:.1f}%</span> <span style="color: {COLORS["subtext"]}; font-size:11px;">(均報 +{r["均報(%)"]:.2f}%)</span></span></div>'
                                card_html += f'<div class="info-row"><span class="info-label" style="color: {COLORS["text"]}; opacity: 0.8;">💰 現價</span><span class="info-value"><span style="color: {COLORS["primary"]};">{r["現價"]:.2f}</span> <span style="color: {COLORS["subtext"]}; font-size:11px;">(乖離 {r["乖離(%)"]:.1f}%)</span></span></div>'
                                card_html += f'<div class="info-row"><span class="info-label" style="color: {COLORS["text"]}; opacity: 0.8;">🚨 ATR 停損</span><span class="info-value" style="color: {COLORS["red"]};">{r["停損價"]:.2f}</span></div>'
                                card_html += f'<div class="info-row" style="border-top: 1px dashed #555; padding-top: 6px; margin-top: 6px;"><span class="info-label" style="color: {COLORS["text"]}; font-weight:bold;">⚖️ AI建議買量</span><span class="info-value" style="color: {COLORS["accent"]}; font-weight: bold;">{r["建議買量(張)"]} 張</span></div>'
                                card_html += '</div></div></div>'
                                st.markdown(card_html.replace('\n', ''), unsafe_allow_html=True)
                    
                    if not ui_s.empty: render_tier_cards(ui_s, "badge-s", "🥇 S級", COLORS["primary"])
                    if not ui_a.empty: render_tier_cards(ui_a, "badge-a", "🥈 A級", COLORS["accent"])

              # 確保這行與上面的 if not ui_a.empty: 對齊 (通常是 16 個半形空格)
                st.markdown("#### ⚔️ <span class='highlight-primary'>【B級】穩健波段 </span>", unsafe_allow_html=True)

                if ui_b.empty:
                    st.info("今日無 B 級備選。")
                else:
                    def build_tactical_summary(row):
                        tags = []
                        if row.get("MACD_Cross"):
                            tags.append("✅MACD")
                        rsi_v = float(row.get("RSI", 50) or 50)
                        if rsi_v > 75:
                            tags.append(f"⚠️RSI{rsi_v:.0f}")
                        elif 50 <= rsi_v <= 70:
                            tags.append("🟢RSI")
                        try:
                            if float(row.get("現價", 0) or 0) > float(row.get("BB_Upper", 999999) or 999999) * 1.02:
                                tags.append("🌋BB上軌")
                        except Exception:
                            pass
                        parts = [
                            f"{row.get('決策標籤','')}｜{row.get('法人狀態','')}",
                            f"{row.get('生命週期','')}｜{row.get('戰術型態','')}",
                            " ".join(tags),
                            f"{row.get('建議','')}"
                        ]
                        return " ｜ ".join([str(x).strip() for x in parts if str(x).strip()])

                    disp_b = ui_b.copy()
                    if "名次" in disp_b.columns:
                        disp_b = disp_b.sort_values("名次", ascending=True)
                    elif "Quant_Score" in disp_b.columns:
                        disp_b = disp_b.sort_values("Quant_Score", ascending=False)

                    disp_b["戰術摘要"] = disp_b.apply(build_tactical_summary, axis=1)
                    b_cols = ["代號", "名稱", "戰術摘要", "勝率(%)", "現價", "停損價", "建議買量(張)", "連買", "Quant_Score"]
                    b_cols = [c for c in b_cols if c in disp_b.columns]
                    disp_b = disp_b[b_cols].copy().rename(columns={"Quant_Score": "量化評分", "停損價": "ATR停損"})
                    if "量化評分" in disp_b.columns:
                        disp_b["量化評分"] = disp_b["量化評分"].apply(lambda x: f"{float(x):.0f}")
                    if "勝率(%)" in disp_b.columns:
                        disp_b["勝率(%)"] = disp_b["勝率(%)"].apply(lambda x: f"{float(x):.1f}%")
                    for cc in ["現價", "ATR停損"]:
                        if cc in disp_b.columns:
                            disp_b[cc] = disp_b[cc].apply(lambda x: f"{float(x):.2f}")

                    # B級不再用 dataframe，改用 HTML 表格：戰術摘要可換行，其餘欄位壓縮。
                    # 這樣不會再被 Streamlit dataframe 固定欄寬截斷。
                    import html as _html

                    def _b_cell(v):
                        return _html.escape(str(v if v is not None else ""))

                    b_rows = []
                    for _, br in disp_b.iterrows():
                        b_rows.append(f"""
                        <tr>
                            <td class="b-code">{_b_cell(br.get('代號', ''))}</td>
                            <td class="b-name">{_b_cell(br.get('名稱', ''))}</td>
                            <td class="b-summary">{_b_cell(br.get('戰術摘要', ''))}</td>
                            <td class="b-small">{_b_cell(br.get('勝率(%)', ''))}</td>
                            <td class="b-small">{_b_cell(br.get('現價', ''))}</td>
                            <td class="b-small">{_b_cell(br.get('ATR停損', ''))}</td>
                            <td class="b-mini">{_b_cell(br.get('建議買量(張)', ''))}</td>
                            <td class="b-mini">{_b_cell(br.get('連買', ''))}</td>
                            <td class="b-score">{_b_cell(br.get('量化評分', ''))}</td>
                        </tr>
                        """)

                    # 用 components.html 渲染完整 HTML，避免 st.markdown 將 <tr>/<td> 當成程式碼區塊顯示。
                    components.html(f"""
                    <style>
                    .b-table-wrap {{
                        width: 100%;
                        border: 1px solid {COLORS['border']};
                        border-radius: 9px;
                        overflow-x: auto;
                        overflow-y: hidden;
                        -webkit-overflow-scrolling: touch;
                        background: {COLORS['card']};
                        margin: 6px 0 16px 0;
                    }}
                    .b-table {{
                        width: 100%;
                        min-width: 960px;
                        border-collapse: collapse;
                        table-layout: auto;
                        font-size: 13px;
                    }}
                    .b-table col.b-col-code {{ width: 56px; }}
                    .b-table col.b-col-name {{ width: 92px; }}
                    .b-table col.b-col-summary {{ width: auto; }}
                    .b-table col.b-col-small {{ width: 62px; }}
                    .b-table col.b-col-mini {{ width: 46px; }}
                    .b-table col.b-col-score {{ width: 54px; }}
                    .b-table th {{
                        background: rgba(128,128,128,.07);
                        color: {COLORS['subtext']} !important;
                        font-weight: 800;
                        padding: 8px 6px;
                        border-bottom: 1px solid {COLORS['border']};
                        white-space: nowrap;
                        text-align: left;
                    }}
                    .b-table td {{
                        color: {COLORS['text']} !important;
                        padding: 8px 6px;
                        border-bottom: 1px solid rgba(128,128,128,.18);
                        vertical-align: top;
                    }}
                    .b-table tr:last-child td {{ border-bottom: none; }}
                    .b-code {{ white-space: nowrap; font-weight: 700; }}
                    .b-name {{ white-space: nowrap; font-weight: 700; }}
                    .b-summary {{
                        white-space: normal;
                        overflow-wrap: anywhere;
                        word-break: break-word;
                        line-height: 1.55;
                        font-weight: 650;
                    }}
                    .b-small {{ white-space: nowrap; text-align: right; font-size: 12.5px; }}
                    .b-mini {{ white-space: nowrap; text-align: center; font-size: 12.5px; }}
                    .b-score {{ white-space: nowrap; text-align: right; font-weight: 900; color: {COLORS['green']} !important; }}
                    @media (max-width: 900px) {{
                        .b-table {{ min-width: 900px; font-size: 12px; }}
                        .b-table col.b-col-code {{ width: 50px; }}
                        .b-table col.b-col-name {{ width: 78px; }}
                        .b-table col.b-col-small {{ width: 54px; }}
                        .b-table col.b-col-mini {{ width: 38px; }}
                        .b-table col.b-col-score {{ width: 48px; }}
                    }}
                    </style>
                    <div class="b-table-wrap">
                        <table class="b-table">
                            <colgroup>
                                <col class="b-col-code">
                                <col class="b-col-name">
                                <col class="b-col-summary">
                                <col class="b-col-small">
                                <col class="b-col-small">
                                <col class="b-col-small">
                                <col class="b-col-mini">
                                <col class="b-col-mini">
                                <col class="b-col-score">
                            </colgroup>
                            <thead>
                                <tr>
                                    <th class="b-code">代號</th>
                                    <th class="b-name">名稱</th>
                                    <th class="b-summary">戰術摘要</th>
                                    <th class="b-small">勝率</th>
                                    <th class="b-small">現價</th>
                                    <th class="b-small">ATR</th>
                                    <th class="b-mini">買量</th>
                                    <th class="b-mini">連買</th>
                                    <th class="b-score">評分</th>
                                </tr>
                            </thead>
                            <tbody>{''.join(b_rows)}</tbody>
                        </table>
                    </div>
                    """, height=min(420, max(170, 74 + len(b_rows) * 46)), scrolling=True)

                st.markdown("#### 🔎 <span class='highlight-primary'>特殊關注 Top 3</span>", unsafe_allow_html=True)
                st.caption("這裡不是買進清單，而是尚未進 S/A/B、但線型與籌碼接近可觀察區的候補股；隔天轉強再丟沙盤。")
                if special_watch.empty:
                    st.info("今日無特殊關注候補股；代表主清單以外暫時不需要分心。")
                else:
                    cols_sp = st.columns(3)
                    for idx, (_, rr) in enumerate(special_watch.iterrows()):
                        with cols_sp[idx % 3]:
                            reason_bits = []
                            if float(rr.get("安全指數", 0) or 0) >= 7:
                                reason_bits.append("安全指數達標")
                            if "建倉" in str(rr.get("法人狀態", "")) or "偏買" in str(rr.get("法人狀態", "")):
                                reason_bits.append(str(rr.get("法人狀態", "")))
                            if float(rr.get("乖離(%)", 0) or 0) <= 8:
                                reason_bits.append("乖離未過熱")
                            reason = "、".join(reason_bits[:3]) if reason_bits else "接近達標，待轉強確認"
                            st.markdown(f"""
                            <div class="tier-card" style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {COLORS['accent']}; border-radius:10px; padding:12px 14px; min-height:150px;">
                                <div style="font-size:13px; color:{COLORS['subtext']}; font-weight:700;">候補 #{idx+1}</div>
                                <div style="font-size:19px; font-weight:900; color:{COLORS['accent']}; line-height:1.25; margin:4px 0 6px 0;">{rr.get('名稱','')} ({rr.get('代號','')})</div>
                                <div style="font-size:13px; color:{COLORS['text']}; margin-bottom:6px;"><b>分數：</b>{float(rr.get('Quant_Score',0) or 0):.1f}｜<b>安全：</b>{rr.get('安全指數','')}</div>
                                <div style="font-size:13px; color:{COLORS['text']}; margin-bottom:6px; line-height:1.45;"><b>戰術摘要：</b>{rr.get('決策標籤','')}｜{rr.get('法人狀態','')}<br>{rr.get('生命週期','')}｜{rr.get('戰術型態','')}</div>
                                <div style="font-size:12.5px; color:{COLORS['subtext']}; line-height:1.45;"><b>關注理由：</b>{reason}<br><b>升級條件：</b>{rr.get('建議','站回M5/M10且量能正常')}</div>
                            </div>
                            """, unsafe_allow_html=True)


with t_etf:
    etf_ui.render_etf_tab(COLORS, FM_TOKEN, TWSE_IND_MAP, TWSE_NAME_MAP, etf_holdings_url, table_style)

with t_chip:
    _ensure_today_candidates("進入情報局時 today_df 仍為空")
    if (st.session_state.get("eod_intel_df") is None or getattr(st.session_state.get("eod_intel_df"), "empty", True)) and not today_df.empty:
        _chip_calc = tuple(today_df["代號"].astype(str).head(80).tolist())
        _chip_intel, _chip_msg = _run_level2_rescue(_chip_calc, "情報局技術補掃描")
        if isinstance(_chip_intel, pd.DataFrame) and not _chip_intel.empty:
            st.session_state["eod_intel_df"] = _chip_intel
            st.session_state["eod_scan_msg"] = _chip_msg
    rotation_radar.render_industry_rotation_radar(COLORS, table_style, TWSE_IND_MAP, today_df, MACRO_DF)
    st.markdown("<hr style='margin: 14px 0 22px 0; border-color: " + COLORS["border"] + ";'>", unsafe_allow_html=True)
    if not today_df.empty:
        st.markdown("#### 🛳️ <span class='highlight-accent'>法人建倉觀察雷達</span>", unsafe_allow_html=True)
        st.caption("只保留：安全指數≥7、三大法人合計買超、法人偏建倉，並排除已進入 S/A/B 主清單的標的。")
        main_chips = today_df.copy()
        chip_intel = st.session_state.get("eod_intel_df", None)
        if chip_intel is not None and not getattr(chip_intel, "empty", True):
            intel_cols = [c for c in ["代號", "安全指數", "現價", "M5", "M10", "M20", "RSI", "乖離(%)"] if c in chip_intel.columns]
            main_chips = pd.merge(main_chips, chip_intel[intel_cols], on="代號", how="left")
        else:
            main_chips["安全指數"] = "-"
        main_chips["法人狀態"] = main_chips.apply(get_institution_state, axis=1)
        main_chips["安全指數"] = main_chips.apply(calc_refined_safety_score, axis=1)
        main_chips["決策標籤"] = main_chips.apply(get_decision_label, axis=1)
        main_chips["建議"] = main_chips.apply(get_next_action, axis=1)
        main_codes = st.session_state.get("eod_main_codes", set())
        obs_mask = main_chips.apply(lambda r: is_institution_observation(r, main_codes), axis=1)
        obs_df = main_chips[obs_mask].sort_values(["安全指數", "三大法人合計"], ascending=[False, False]).head(20).copy()
        if obs_df.empty:
            st.info("目前沒有符合條件的法人建倉觀察標的；代表主清單以外暫時不需要分心。")
        else:
            obs_df["法人戰術摘要"] = obs_df.apply(lambda r: f"{r.get('法人狀態','')}｜{r.get('決策標籤','')}\n｜{r.get('建議','')}", axis=1)
            view_cols = ["代號", "名稱", "法人戰術摘要", "連買", "安全指數", "外資(張)", "投信(張)", "自營(張)", "三大法人合計"]
            obs_df = obs_df[[c for c in view_cols if c in obs_df.columns]].copy()
            styled_obs = obs_df.style.set_properties(**table_style).format({"外資(張)": "{:,.0f}", "投信(張)": "{:,.0f}", "自營(張)": "{:,.0f}", "三大法人合計": "{:,.0f}"}).map(risk_color, subset=["安全指數"])
            st.dataframe(styled_obs, height=430, use_container_width=True, hide_index=True)
    else:
        st.info("法人籌碼暫時無法取得；情報局會在技術備援候選池建立後恢復。沙盤、ETF、司令部仍可使用。")

with t_cmd:
    cmd_hold_tab, cmd_aar_tab, cmd_bt_tab = st.tabs(["🛡️ 持股風控", "📊 AAR 戰術教練", "🧪 訊號追蹤室"])
    with cmd_hold_tab:
        st.markdown("### 🏦 <span class='highlight-primary'>司令部：戰備資金精算</span>", unsafe_allow_html=True)

        if auth_status != "admin_auth":
            st.info("友軍模式不顯示個人持股、成本與損益；沙盤推演、情報局、ETF、AAR 與回測仍可使用。")
        elif not sheet_url:
            st.info("請在左側邊欄輸入您的【持股部位】CSV 網址以啟用風控檢查。")
        else:
            if not m_df.empty:
                total_pnl = 0
                active_fee_rate = 0.001425 * fee_discount
            
                def get_cmd_val(row_data, possible_keys, default=0.0):
                    for col in row_data.index:
                        if any(k in str(col) for k in possible_keys):
                            val = row_data[col]
                            if pd.notna(val) and str(val).strip() != '':
                                try: return float(str(val).replace(',', '').strip())
                                except: pass
                    return default

                total_float_pnl = 0
                for _, r in m_df.iterrows():
                    try:
                        p_now_r = float(r.get('現價', 0) or 0)
                        p_cost_r = float(str(r.get("成本價", r.get("成本", r.get("買進價", 0)))).replace(",", "") or 0)
                        qty_r = float(str(r.get("庫存張數", r.get("張數", r.get("庫存", 0)))).replace(",", "") or 0)
                        if p_now_r > 0 and qty_r > 0:
                            buy_r = p_cost_r * qty_r * 1000 * (1 + active_fee_rate)
                            sell_r = p_now_r * qty_r * 1000 * (1 - active_fee_rate - 0.003)
                            total_float_pnl += (sell_r - buy_r)
                    except: pass

                float_loss_pct = (total_float_pnl / total_capital * 100) if total_capital > 0 else 0
                if float_loss_pct <= -2.0:
                    st.error(f"🔒 **風控鎖倉警報**：當前持倉總浮虧已達 **{float_loss_pct:.1f}%**（超過本金 2% 底線）依律停止進場，專注處理虧損部位。", icon="🚨")
                elif float_loss_pct <= -1.0:
                    st.warning(f"⚠️ **組合風控預警**：持倉總浮虧 {float_loss_pct:.1f}%，接近 2% 底線，請謹慎評估是否繼續加倉。")

                if rescue_residual_map:
                    rescue_names = []
                    for code, info in rescue_residual_map.items():
                        rescue_names.append(f"{TWSE_NAME_MAP.get(code, code)}({code})")
                    st.warning(f"**救援殘倉模式啟動：{len(rescue_residual_map)} 檔**｜{ '、'.join(rescue_names[:5]) }。這些是已在 AAR 出現認賠/停損紀錄但目前仍持有的標的；反彈減碼優先，站回結構前不加碼。", icon="🚑")

                render_mainstream_exposure_alert(m_df, COLORS, TWSE_IND_MAP, TWSE_NAME_MAP)

                html_cards = '<div style="display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px;">'
                for _, r in m_df.iterrows():
                    try:
                        p_now_raw = r.get('現價', 0)
                        p_now = float(p_now_raw) if pd.notna(p_now_raw) and str(p_now_raw).strip() != '' else 0.0
                        p_cost = get_cmd_val(r, ["成本價", "成本", "買進價", "成交均價", "建倉成本", "買價"])
                        qty = get_cmd_val(r, ["庫存張數", "張數", "庫存", "股數", "數量"])
                        sid_hold = str(r.get("代號", "")).strip()
                        rescue_info = rescue_residual_map.get(sid_hold, {}) if isinstance(rescue_residual_map, dict) else {}
                        is_rescue_residual = bool(rescue_info)

                        buy_date_raw = ""
                        for col in r.index:
                            if any(k in str(col) for k in ["買進日期", "買進日", "建倉日", "日期"]) and "賣" not in str(col):
                                v = r[col]
                                if pd.notna(v) and str(v).strip() not in ["", "nan"]:
                                    buy_date_raw = str(v).strip()
                                    break

                        held_days_now = 0
                        timer_color = COLORS["subtext"]
                        timer_warning = ""
                        if buy_date_raw:
                            try:
                                raw_d = buy_date_raw.replace("/", "-").replace(".", "-")
                                parts_d = raw_d.split("-")
                                if len(parts_d) == 2: buy_dt = pd.to_datetime(f"{datetime.now().year}-{parts_d[0]}-{parts_d[1]}", errors="coerce")
                                elif len(parts_d) == 3:
                                    y_d = int(parts_d[0])
                                    if y_d < 1911: y_d += 1911
                                    buy_dt = pd.to_datetime(f"{y_d}-{parts_d[1]}-{parts_d[2]}", errors="coerce")
                                else: buy_dt = pd.NaT
                                if pd.notna(buy_dt):
                                    held_days_now = (pd.Timestamp(datetime.now()) - buy_dt).days
                                    if held_days_now > 5:
                                        timer_color = COLORS["red"]
                                        timer_warning = f" ⚠️ 已持 {held_days_now} 天！超出甜蜜點"
                                    else: timer_warning = f" (已持 {held_days_now} 天)"
                            except: pass

                        if p_now > 0 and qty > 0:
                            buy_cost_total = (p_cost * qty * 1000) + int((p_cost * qty * 1000) * active_fee_rate)
                            sell_revenue_net = (p_now * qty * 1000) - int((p_now * qty * 1000) * active_fee_rate) - int((p_now * qty * 1000) * 0.003)
                            pnl = sell_revenue_net - buy_cost_total
                            ret = (pnl / buy_cost_total) * 100 if buy_cost_total > 0 else 0
                            total_pnl += pnl
                        else: pnl, ret = 0, 0.0
                    
                        m5, m10 = float(r.get('M5', 0)) if pd.notna(r.get('M5', 0)) else 0.0, float(r.get('M10', 0)) if pd.notna(r.get('M10', 0)) else 0.0
                        atr = float(r.get('ATR', p_now * 0.03))
                        dynamic_sl = float(r.get('停損價', p_cost - 1.5 * atr))
                    
                        # 🚀 統帥優化：AAR 續抱信心雷達 (BBAND, RSI, MACD 綜合判定)
                        rsi_val = float(r.get('RSI', 50))
                        bb_upper = float(r.get('BB_Upper', 99999))
                        macd_hist = float(r.get('MACD_Hist', 0))

                        conf_level = "中"
                        conf_color = COLORS.get('accent', '#79C0FF')
                        conf_text = "動能降溫震盪中，請嚴守 M5 與 ATR 防線，不破不賣。"

                        if p_now < m5 and (rsi_val > 80 or p_now < m10):
                            conf_level = "低"
                            conf_color = COLORS.get('red', '#FF7B72')
                            conf_text = "高檔轉弱警報！請嚴格執行紀律，立刻減碼或停損，收回資金！"
                        elif p_now >= m5 and (p_now >= bb_upper * 0.98 or (70 <= rsi_val <= 80)):
                            conf_level = "高"
                            conf_color = COLORS.get('primary', '#58A6FF')
                            conf_text = "主升段極速狂飆中！動能極強，請將軍死抱，砍單者軍法處置！"

                        glow_class = "glow-s-tier" if conf_level == "高" else ""
                        border_col = conf_color
                        ret_col = COLORS['red'] if pnl > 0 else (COLORS['green'] if pnl < 0 else COLORS['text'])
                    
                        if p_now == 0.0 or m10 == 0.0: struct, coach, border_col, glow_class = "⚪ 訊號不足", "無法取得完整均線數據，請手動確認走勢。", COLORS['border'], ""
                        else:
                            struct = f"📈 趨勢：現價 > M5" if p_now > m5 else (f"📉 跌破M5" if p_now >= dynamic_sl else f"💀 貫穿防線")
                            coach = f"<strong style='color:{conf_color}; font-size:14px;'>🛡️ 續抱信心【{conf_level}】</strong><br>{conf_text}"

                        if p_now == 0.0 or m10 == 0.0:
                            next_action = "手動確認資料"
                        elif p_now < dynamic_sl or p_now < m10:
                            next_action = "破防：減碼/停損"
                        elif p_now < m5:
                            next_action = "等站回M5，站不回看M10"
                        elif ret >= 5.5 and conf_level == "高":
                            next_action = "可先出半，剩下守M5"
                        elif conf_level == "高":
                            next_action = "續抱，跌破M5再處理"
                        else:
                            next_action = "守M5/ATR，不追不攤"

                        if is_rescue_residual:
                            rescue_loss = abs(float(rescue_info.get("loss_sum", 0)))
                            rescue_count = int(rescue_info.get("count", 0))
                            rescue_worst = float(rescue_info.get("worst_pct", 0))
                            rescue_note = f"AAR 已急救 {rescue_count} 次，已認賠約 {rescue_loss:,.0f} 元，最差單筆 {rescue_worst:.1f}%。"
                            glow_class = ""
                            if p_now == 0.0 or m10 == 0.0:
                                conf_level = "救援"
                                conf_color = COLORS.get('accent', '#79C0FF')
                                struct = "🚑 救援殘倉｜資料待確認"
                                next_action = "先確認報價/均線，不加碼"
                            elif ret <= -10:
                                conf_level = "急救"
                                conf_color = COLORS.get('red', '#FF7B72')
                                border_col = conf_color
                                struct = "🚨 救援殘倉｜深虧破口"
                                next_action = "反彈減碼優先，不再凹"
                            elif ret <= -5:
                                conf_level = "救援"
                                conf_color = COLORS.get('red', '#FF7B72')
                                border_col = conf_color
                                struct = "🚑 救援殘倉｜風險未解除"
                                next_action = "反彈減碼；站回M10前不加碼"
                            elif p_now < m5:
                                conf_level = "觀察"
                                conf_color = COLORS.get('accent', '#79C0FF')
                                border_col = conf_color
                                struct = "🚑 救援殘倉｜跌破M5"
                                next_action = "站不回M5就二次處理"
                            else:
                                conf_level = "修復中"
                                conf_color = COLORS.get('primary', '#58A6FF')
                                border_col = conf_color
                                struct = "🚑 救援殘倉｜修復中"
                                next_action = "守M5/M10；先不加碼"
                            coach = f"<strong style='color:{conf_color}; font-size:14px;'>🚑 救援殘倉【{conf_level}】</strong><br>{rescue_note}<br>原則：反彈減碼優先，站回成本區前不加碼；再破 M5/M10 執行二次處理。"

                        name_display = r['名稱'] if '名稱' in r else r.get('代號','')
                        display_p_now = f"{p_now:.2f}" if p_now > 0 else "抓取中"
                        timer_html = f"<span style='color:{timer_color}; font-size:12px;'>{timer_warning}</span>" if timer_warning else ""
                        rescue_badge = f" <span style='font-size:12px; color:{COLORS['red']}; font-weight:700;'>🚑救援殘倉</span>" if is_rescue_residual else ""
                    
                        html_cards += f"<div class='holding-card {glow_class}' style='border-left: 5px solid {border_col}; padding: 10px 15px; background-color: {COLORS['card']}; border-radius: 4px; margin-bottom: 8px;'><div class='rwd-flex-header' style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;'><div class='rwd-flex-title' style='display: flex; align-items: baseline; gap: 15px;'><h3 style='margin: 0; font-size: 20px; font-weight: bold; color: {COLORS['text']};'>{name_display} ({r['代號']}){rescue_badge}</h3><div style='font-size: 13.5px; color: {COLORS['subtext']};'>現價: <strong style='color:{COLORS['text']}'>{display_p_now}</strong> | 成本: {p_cost:.2f} {timer_html}</div></div><div class='rwd-flex-profit' style='text-align: right;'><span style='font-size: 16px; font-weight: bold; color: {ret_col};'>{ret:.2f}%</span><span style='font-size: 16px; font-weight: bold; color: {ret_col}; margin-left: 10px;'>{pnl:,.0f} 元</span></div></div><div class='rwd-flex-info' style='background-color: {COLORS['bg']}; padding: 6px 12px; border-radius: 6px; font-size: 13.5px; display: flex; gap: 20px;'><div style='white-space: nowrap;'><span style='color:{COLORS['subtext']}'>📊 結構：</span><span style='color:{COLORS['text']}; font-weight:500;'>{struct}</span></div><div><span style='color:{COLORS['subtext']}'>💡 教練：</span><span style='color:{COLORS['text']}'>{coach}</span></div><div style='white-space: nowrap;'><span style='color:{COLORS['subtext']}'>🎯 建議：</span><span style='color:{conf_color}; font-weight:700;'>{next_action}</span></div></div></div>"
                    except Exception as e: continue
                html_cards += '</div>'
            
                p_color = COLORS["red"] if total_pnl > 0 else COLORS["green"]
                st.markdown(f"#### 💰 目前總淨損益：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
                st.markdown(html_cards, unsafe_allow_html=True)
            else:
                st.info("💡 目前尚無有效持股資料，或現價抓取失敗。")

    with cmd_aar_tab:
        st.markdown("### 📊 <span class='highlight-primary'>AAR 戰術覆盤室</span>", unsafe_allow_html=True)
        aar.render_aar_tab(aar_sheet_url, fee_discount, FM_TOKEN, COLORS)

    with cmd_bt_tab:
        signal_tracker.render_signal_tracker_tab(
            COLORS=COLORS,
            table_style=table_style,
            fm_token=FM_TOKEN,
            twse_ind_map=TWSE_IND_MAP,
            macro_score=MACRO_SCORE,
            overheat_flag=OVERHEAT_FLAG,
            operation_mode=operation_mode,
        )

with t_book:
    st.markdown("### 📖 <span class='highlight-primary'>游擊兵工廠與軍史館</span>", unsafe_allow_html=True)
    quick_tab, full_tab, hist_tab = st.tabs(["⚡ 快速版", "📚 完整兵工廠", "🏛️ 軍史館"])
    with quick_tab:
        st.markdown(QUICK_MANUAL_TEXT, unsafe_allow_html=True)
    with full_tab:
        st.markdown(MANUAL_TEXT, unsafe_allow_html=True)
    with hist_tab:
        st.markdown(HISTORY_TEXT, unsafe_allow_html=True)

st.divider()
st.markdown("<p style='text-align: center;' class='text-sub'>© 游擊隊軍火部 - v35.0 </p>", unsafe_allow_html=True)
