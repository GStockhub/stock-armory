import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
import ssl
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
    st.markdown("<h1 style='text-align: center; margin-top: 100px;'>🔒 終極戰情室 v34.0 - 軍事管制區</h1>", unsafe_allow_html=True)
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

st.markdown("""
<style>
/* 標籤絕對保護區：強制不換行、大小固定，不受標題長度影響 */
.tier-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: bold; white-space: nowrap !important; flex-shrink: 0; }
.badge-s { background-color: rgba(255, 75, 75, 0.1); color: #FF4B4B; border: 1px solid #FF4B4B; }
.badge-a { background-color: rgba(255, 165, 0, 0.1); color: #FFA500; border: 1px solid #FFA500; }

/* 🚀 統帥級卡片重構：強制高度 100%，消除高低落差 */
.tier-card { border-radius: 6px; padding: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; flex-direction: column; box-sizing: border-box; margin-bottom: 12px; height: 100%; }
.info-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; width: 100%; }
.info-label { font-size: 13px; opacity: 0.8; white-space: nowrap; }
.info-value { font-size: 13px; font-weight: 500; text-align: right; white-space: nowrap; }

/* 🚀 長檔名自適應區：字體微縮、自動換行、絕對限制最多兩行 */
.stock-title { 
    margin: 0; 
    font-size: clamp(15px, 1.2rem, 19px); 
    line-height: 1.25; 
    white-space: normal; 
    word-break: break-word; 
    display: -webkit-box;
    -webkit-line-clamp: 2; 
    -webkit-box-orient: vertical;
    overflow: hidden;
}

@media (max-width: 768px) {
    .rwd-flex-header { flex-direction: column !important; align-items: flex-start !important; gap: 8px; }
    .rwd-flex-title { flex-direction: column !important; gap: 4px !important; }
    .rwd-flex-profit { text-align: left !important; width: 100%; border-bottom: 1px dashed gray; padding-bottom: 8px; }
    .rwd-flex-info { flex-direction: column !important; gap: 8px !important; }
    .rwd-flex-info > div { white-space: normal !important; }
}
</style>
""", unsafe_allow_html=True)

configs = sidebar.render_sidebar(auth_status)
COLORS = configs["COLORS"]
sheet_url = str(configs["sheet_url"]).strip()
aar_sheet_url = str(configs["aar_sheet_url"]).strip()

try: total_capital = float(configs.get("total_capital", 100000))
except: total_capital = 100000.0
try: risk_amount = float(configs.get("risk_amount", 1000))
except: risk_amount = 1000.0
try: fee_discount = float(configs.get("fee_discount", 1.0))
except: fee_discount = 1.0
operation_mode = configs.get("operation_mode", "標準模式")
MODE_PROFILE = {
    "保守模式": {"s": 92, "a": 72, "b": 55, "size": 0.70, "label": "🛡️ 保守模式", "note": "提高分數門檻、建議買量打7折，只打最有把握的球。"},
    "標準模式": {"s": 88, "a": 65, "b": 45, "size": 1.00, "label": "⚖️ 標準模式", "note": "維持V34司令官短波段原始節奏。"},
    "進攻模式": {"s": 84, "a": 60, "b": 40, "size": 1.15, "label": "⚔️ 進攻模式", "note": "略放寬B級觀察與買量，但仍受總曝險與停損控制。"},
}.get(operation_mode, {"s": 88, "a": 65, "b": 45, "size": 1.00, "label": "⚖️ 標準模式", "note": "維持V34司令官短波段原始節奏。"})

table_style = {"text-align": "center", "background-color": COLORS["card"], "color": COLORS["text"], "border-color": COLORS["border"]}

st.markdown(f"<h1 style='text-align: center;' class='highlight-primary'>💰️讓我賺大錢 v34.0</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;' class='text-sub'>—— EOD 司令官版 ✕ 快速沙盤 ✕ AAR行為修正 ——</p>", unsafe_allow_html=True)

TWSE_IND_MAP, TWSE_NAME_MAP = load_industry_map()
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
    health.append(("法人籌碼", len(chip_db) > 0, f"近 {len(chip_db)} 日" if len(chip_db) > 0 else "連線失敗"))
    health.append(("持股CSV", holding_read_ok, f"{holding_rows} 筆" if holding_read_ok else ("未設定" if not sheet_url else "讀取失敗/空表")))
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
        len(chip_db) > 0,
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
    """把大盤警戒、過熱警戒、資料狀態濃縮成一張戰情總覽卡，避免首頁堆太多 alert。"""
    status_items = [
        len(TWSE_NAME_MAP) > 0,
        not MACRO_DF.empty,
        len(chip_db) > 0,
        holding_read_ok or not sheet_url,
        aar_read_ok or not aar_sheet_url,
        bool(str(FM_TOKEN).strip()),
    ]
    ok_count = sum(bool(x) for x in status_items)
    total_count = len(status_items)

    if MACRO_SCORE <= 3:
        market_title = f"🔴 紅色警戒 ({MACRO_SCORE}/10)"
        market_msg = "市場偏弱，保留現金，不主動開新倉"
        main_color = COLORS["red"]
    elif MACRO_SCORE <= 5:
        market_title = f"🟡 黃色警戒 ({MACRO_SCORE}/10)"
        market_msg = "大盤偏弱，資金減半操作"
        main_color = COLORS["accent"]
    else:
        market_title = f"🟢 可作戰 ({MACRO_SCORE}/10)"
        market_msg = "盤勢允許短波段，但仍依禁追與停損"
        main_color = COLORS["green"]

    heat_title = "🔥 高檔過熱" if OVERHEAT_FLAG else "✅ 過熱未觸發"
    heat_msg = "大盤乖離 >5%，限縮 AI 建議買量" if OVERHEAT_FLAG else "尚未觸發大盤過熱限制"
    heat_color = COLORS["red"] if OVERHEAT_FLAG else COLORS["green"]

    data_title = f"🧭 資料 {ok_count}/{total_count}"
    data_msg = "全部正常" if ok_count == total_count else "部分異常，展開下方檢查"
    data_color = COLORS["green"] if ok_count >= 5 else (COLORS["accent"] if ok_count >= 4 else COLORS["red"])

    brief = build_macro_brief(MACRO_DF, MACRO_SCORE, OVERHEAT_FLAG)

    st.markdown(f"""
    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:6px solid {main_color}; border-radius:10px; padding:12px 14px; margin:8px 0 14px 0;">
        <div style="display:flex; flex-wrap:wrap; align-items:stretch; gap:10px;">
            <div style="flex:1 1 230px; min-width:220px;">
                <div style="font-size:15px; font-weight:800; color:{COLORS['text']};">{market_title}</div>
                <div style="font-size:12.5px; color:{COLORS['subtext']}; margin-top:3px;">{market_msg}</div>
            </div>
            <div style="flex:1 1 230px; min-width:220px; border-left:1px solid {COLORS['border']}; padding-left:12px;">
                <div style="font-size:15px; font-weight:800; color:{heat_color};">{heat_title}</div>
                <div style="font-size:12.5px; color:{COLORS['subtext']}; margin-top:3px;">{heat_msg}</div>
            </div>
            <div style="flex:1 1 210px; min-width:200px; border-left:1px solid {COLORS['border']}; padding-left:12px;">
                <div style="font-size:15px; font-weight:800; color:{data_color};">{data_title}</div>
                <div style="font-size:12.5px; color:{COLORS['subtext']}; margin-top:3px;">{data_msg}</div>
            </div>
        </div>
        <div style="margin-top:10px; padding-top:9px; border-top:1px dashed {COLORS['border']}; font-size:13px; line-height:1.55; color:{COLORS['text']};">
            <b>明日指令：</b>{brief['strategy']}
            <span style="color:{COLORS['subtext']}; margin-left:8px;">{brief['risk']}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("🔎 資料燈號", expanded=False):
        render_data_health_panel()


with st.spinner("情報兵正在部署防線..."):
    chip_db = fetch_chips_data(FM_TOKEN)

m_df = pd.DataFrame()
today_df = pd.DataFrame()
top_80_chips = []
holding_rows = 0
holding_read_ok = False
aar_rows = 0
aar_read_ok = False

if len(chip_db) >= 1:
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
else:
    st.toast("籌碼連線失敗；沙盤與司令部仍可使用。", icon="⚠️")

if sheet_url:
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
        aar_rows = 0
        aar_read_ok = False

render_top_status_panel()


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
            p_now, m5, m10, bias, win_rate, sl_price = res["現價"], res["M5"], res["M10"], res["乖離"], res["勝率"], res["停損價"]
            if p_now < m10:
                grade_color, grade_text = COLORS["red"], "🛑 嚴禁接刀 (D級)"
                advice = f"現價跌破 M10 ({m10:.1f})，短線轉弱。站不回 M5 前不追；若 M10 無止跌，等 M20 觀察。"
            elif p_now < m5:
                grade_color, grade_text = COLORS["accent"], "⚠️ 等站回 M5"
                advice = f"現價低於 M5 ({m5:.1f})。若 13:00 後站回 M5 且量能正常才觀察；站不回就等 M10。"
            elif bias > 7:
                grade_color, grade_text = COLORS["accent"], "⚠️ 追高警告 (C級)"
                advice = f"乖離 {bias:.1f}% 偏高。除非小幅突破且量能強，否則等回踩 M5。"
            elif p_now > m5 and win_rate >= 50:
                grade_color, grade_text = COLORS["primary"], "👑 准許出兵 (S/A級)"
                advice = f"多頭結構且回測勝率 {win_rate:.0f}%。防守底線 {sl_price:.1f}；跳空 >4.5% 不追。"
            else:
                grade_color, grade_text = COLORS["green"], "⚖️ 穩健觀察 (B級)"
                advice = f"結構普通，勝率 {win_rate:.0f}%。可小量試單，防守底線 {sl_price:.1f}。"

            html_block = f"""
            <div style="background-color:{COLORS['card']}; border-left:5px solid {grade_color}; padding:15px; border-radius:8px; margin-bottom:10px;">
                <div style="display:flex; justify-content:space-between; gap:12px; margin-bottom:8px;">
                    <h4 style="margin:0; font-size:20px; color:{COLORS['text']};">{res['名稱']} ({res['代號']})</h4>
                    <span style="font-weight:bold; color:{grade_color}; font-size:18px; white-space:nowrap;">{grade_text}</span>
                </div>
                <div style="font-size:14px; color:{COLORS['subtext']}; margin-bottom:10px;">
                    現價 <b style="color:{COLORS['text']};">{p_now:.2f}</b>｜M5 <b>{m5:.2f}</b>｜M10 <b>{m10:.2f}</b>｜乖離 <b>{bias:.1f}%</b>｜勝率 <b>{win_rate:.0f}%</b>
                </div>
                <div style="background-color:{COLORS['bg']}; padding:10px; border-radius:6px; font-size:14px; color:{COLORS['text']};">💡 <b>下一步：</b>{advice}</div>
            </div>
            """
            st.markdown(html_block, unsafe_allow_html=True)
        elif sim_btn:
            st.error("❌ 查無此股票或歷史資料不足，請確認代碼是否正確。")
        else:
            st.info("輸入代號後執行體檢；結果會暫存在本頁，不會因切換分頁立刻消失。")

t_rank, t_chip, t_cmd, t_backtest, t_book = st.tabs(["🎯 戰術指揮所 (機率模型)", "📡 情報局 (法人籌碼)", "🏦 總司令部 (風控與AAR)", "📊 司令官回測室", "📖 兵工廠與軍史館"])

with t_rank:
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
        render_macro_brief(MACRO_DF, MACRO_SCORE, OVERHEAT_FLAG)
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

    if not today_df.empty and MACRO_SCORE > 3:
        calc_list = tuple(set(today_df[today_df["連買"] >= 1]["代號"].tolist() + top_80_chips))
        scan_key = f"{dates[0] if 'dates' in locals() and dates else 'nodate'}_{MACRO_SCORE}_{operation_mode}_{len(calc_list)}"
        needs_eod_scan = force_eod_scan or st.session_state.get("eod_scan_key") != scan_key or "eod_intel_df" not in st.session_state
        if needs_eod_scan:
            intel_df = level2_quant_engine(calc_list, TWSE_IND_MAP, TWSE_NAME_MAP, MACRO_SCORE, FM_TOKEN)
            st.session_state["eod_intel_df"] = intel_df
            st.session_state["eod_scan_key"] = scan_key
            st.session_state["eod_last_scan_time"] = datetime.now().strftime("%H:%M:%S")
        else:
            intel_df = st.session_state.get("eod_intel_df")

        if intel_df is None:
            st.error("🚨 **資料斷線警告**：Yahoo與FinMind皆無回應。請稍後重整或確認 API 額度", icon="💀")
        elif not intel_df.empty:
            final_rank = pd.merge(today_df, intel_df, on="代號", suffixes=("_chip", "_intel"))
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
            final_rank["改版安全指數"] = final_rank.apply(calc_refined_safety_score, axis=1)
            final_rank["決策標籤"] = final_rank.apply(get_decision_label, axis=1)
            final_rank["下一步"] = final_rank.apply(get_next_action, axis=1)
            rank_sorted = final_rank.sort_values("Quant_Score", ascending=False).reset_index(drop=True)
            is_phase_3 = rank_sorted["生命週期"].str.contains("第三段", na=False)
            
            s_mask = (rank_sorted["Quant_Score"] >= MODE_PROFILE["s"]) & (rank_sorted["基本達標"] == True) & (~is_phase_3)
            a_mask = (~s_mask) & (rank_sorted["Quant_Score"] >= MODE_PROFILE["a"]) & (rank_sorted["基本達標"] == True)
            b_mask = (~s_mask) & (~a_mask) & (rank_sorted["Quant_Score"] >= MODE_PROFILE["b"])
            c_mask = (~s_mask) & (~a_mask) & (~b_mask)

            s_tier = rank_sorted[s_mask].head(3).copy()
            a_tier = rank_sorted[a_mask].head(3).copy()
            b_tier = rank_sorted[b_mask].head(7).copy()
            c_tier = rank_sorted[c_mask].copy()

            s_tier["評級"], a_tier["評級"], b_tier["評級"], c_tier["評級"] = "S", "A", "B", "C"

            master_list = pd.concat([s_tier, a_tier, b_tier, c_tier]).reset_index(drop=True)
            master_list = master_list[master_list["現價"] > master_list["停損價"]]
            master_list = master_list.head(20)
            master_list["名次"] = range(1, len(master_list) + 1)
            st.session_state["eod_main_codes"] = set(master_list[master_list["評級"].isin(["S", "A", "B"])]["代號"].astype(str).tolist()) if not master_list.empty else set()

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
                master_list["改版安全指數"] = master_list.apply(calc_refined_safety_score, axis=1)
                master_list["決策標籤"] = master_list.apply(get_decision_label, axis=1)
                master_list["下一步"] = master_list.apply(get_next_action, axis=1)

                ui_s = master_list[master_list["評級"] == "S"]
                ui_a = master_list[master_list["評級"] == "A"]
                ui_b = master_list[master_list["評級"] == "B"]
                ui_c = master_list[master_list["評級"] == "C"]
                render_battle_summary(master_list, rank_sorted)

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
                            "下一步": rr.get("下一步", ""),
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
                        "名次", "評級", "代號", "名稱", "決策標籤", "下一步", "法人狀態", "產業", "生命週期", "戰術型態",
                        "Quant_Score", "勝率(%)", "均報(%)", "安全指數", "改版安全指數", "現價", "M5", "M10", "M20",
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
                                card_html += f'<div style="flex: 0 0 auto; padding-top: 3px;"><span class="tier-badge {badge_class}">{badge_name}</span></div>'
                                
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
                show_bc_full = st.toggle(
                    "顯示 B/C 完整欄位",
                    value=False,
                    key="show_bc_full_detail",
                    help="預設精簡，只看決策標籤、下一步、法人狀態與量化評分；打開後才顯示生命週期、戰術型態、勝率、現價等完整資料。"
                )

                if ui_b.empty:
                    st.info("今日無 B 級備選。")
                else:
                    def generate_b_badges(row):
                        b_tags = []
                        if row.get("MACD_Cross"):
                            b_tags.append("✅M")
                        if row.get("RSI", 50) > 75:
                            b_tags.append("⚠️R")
                        elif 50 <= row.get("RSI", 50) <= 70:
                            b_tags.append("🟢R")
                        if row["現價"] > row.get("BB_Upper", 9999) * 1.02:
                            b_tags.append("🌋B")
                        tag_str = " ".join(b_tags)
                        return f"{row['戰術型態']} {tag_str}" if tag_str else row["戰術型態"]

                    disp_b = ui_b.copy()
                    disp_b["戰術型態"] = disp_b.apply(generate_b_badges, axis=1)

                    if show_bc_full:
                        b_cols = ["名次", "代號", "名稱", "決策標籤", "下一步", "法人狀態", "生命週期", "戰術型態", "Quant_Score", "勝率(%)", "現價", "停損價", "建議買量(張)", "連買"]
                    else:
                        b_cols = ["名次", "代號", "名稱", "決策標籤", "下一步", "法人狀態", "Quant_Score"]

                    b_cols = [c for c in b_cols if c in disp_b.columns]
                    disp_b = disp_b[b_cols].copy()
                    disp_b = disp_b.rename(columns={"Quant_Score": "量化評分", "停損價": "ATR停損"})

                    if "現價" in disp_b.columns:
                        disp_b["現價"] = disp_b["現價"].apply(lambda x: f"{x:.2f}")
                    if "ATR停損" in disp_b.columns:
                        disp_b["ATR停損"] = disp_b["ATR停損"].apply(lambda x: f"{x:.2f}")
                    if "量化評分" in disp_b.columns:
                        disp_b["量化評分"] = disp_b["量化評分"].apply(lambda x: f"{x:.1f}")
                    raw_win_rate = disp_b["勝率(%)"].copy() if "勝率(%)" in disp_b.columns else None
                    if "勝率(%)" in disp_b.columns:
                        disp_b["勝率(%)"] = disp_b["勝率(%)"].apply(lambda x: f"{x:.1f}%")

                    styled_b = disp_b.style.set_properties(**table_style).map(risk_color, subset=["量化評分"])
                    if raw_win_rate is not None:
                        styled_b = styled_b.apply(
                            lambda x: [f'color: {COLORS["green"]}; font-weight: bold;' if v > 60 else '' for v in raw_win_rate],
                            subset=["勝率(%)"]
                        )
                    st.dataframe(styled_b, use_container_width=True, hide_index=True)

                st.markdown("#### 📡 <span class='highlight-primary'>【C級】潛伏遺珠</span>", unsafe_allow_html=True)
                if ui_c.empty:
                    st.info("今日無 C 級觀察名單。")
                else:
                    disp_c = ui_c.copy()

                    if show_bc_full:
                        c_cols = ["名次", "代號", "名稱", "決策標籤", "下一步", "法人狀態", "生命週期", "戰術型態", "Quant_Score", "勝率(%)", "現價", "乖離(%)", "連買"]
                    else:
                        c_cols = ["名次", "代號", "名稱", "決策標籤", "下一步", "法人狀態", "Quant_Score"]

                    c_cols = [c for c in c_cols if c in disp_c.columns]
                    disp_c = disp_c[c_cols].copy()
                    disp_c = disp_c.rename(columns={"Quant_Score": "量化評分"})

                    if "現價" in disp_c.columns:
                        disp_c["現價"] = disp_c["現價"].apply(lambda x: f"{x:.2f}")
                    if "量化評分" in disp_c.columns:
                        disp_c["量化評分"] = disp_c["量化評分"].apply(lambda x: f"{x:.1f}")
                    if "乖離(%)" in disp_c.columns:
                        disp_c["乖離(%)"] = disp_c["乖離(%)"].apply(lambda x: f"{x:.1f}%")
                    if "勝率(%)" in disp_c.columns:
                        disp_c["勝率(%)"] = disp_c["勝率(%)"].apply(lambda x: f"{x:.1f}%")

                    styled_c = disp_c.style.set_properties(**table_style).map(risk_color, subset=["量化評分"])
                    st.dataframe(styled_c, use_container_width=True, hide_index=True)

with t_chip:
    if not today_df.empty:
        st.markdown("### 📡 <span class='highlight-primary'>聯合作戰情報：法人動向</span>", unsafe_allow_html=True)
        st.caption("💡 **籌碼流向**：當日全台股外資、投信、自營商買賣超Top 200。")
        surprise_atk = today_df[(today_df['連買'] == 1) & (today_df['投信(張)'] > 0) & (today_df['外資(張)'] > 0)].sort_values('三大法人合計', ascending=False).head(3)
        if not surprise_atk.empty:
            st.markdown("#### 🚨 <span class='highlight-accent'>土洋合擊區</span>", unsafe_allow_html=True)
            st.dataframe(surprise_atk[['代號','名稱','外資(張)','投信(張)','自營(張)','三大法人合計']].style.set_properties(**table_style).format({'外資(張)':'{:,.0f}','投信(張)':'{:,.0f}','自營(張)':'{:,.0f}','三大法人合計':'{:,.0f}'}), use_container_width=True, hide_index=True)
            st.markdown("---")
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
        main_chips["改版安全指數"] = main_chips.apply(calc_refined_safety_score, axis=1)
        main_chips["決策標籤"] = main_chips.apply(get_decision_label, axis=1)
        main_chips["下一步"] = main_chips.apply(get_next_action, axis=1)
        main_codes = st.session_state.get("eod_main_codes", set())
        obs_mask = main_chips.apply(lambda r: is_institution_observation(r, main_codes), axis=1)
        obs_df = main_chips[obs_mask].sort_values(["改版安全指數", "三大法人合計"], ascending=[False, False]).head(20).copy()
        if obs_df.empty:
            st.info("目前沒有符合條件的法人建倉觀察標的；代表主清單以外暫時不需要分心。")
        else:
            view_cols = ["代號", "名稱", "法人狀態", "決策標籤", "下一步", "連買", "投信連賣", "改版安全指數", "外資(張)", "投信(張)", "自營(張)", "三大法人合計"]
            obs_df = obs_df[[c for c in view_cols if c in obs_df.columns]].copy()
            styled_obs = obs_df.style.set_properties(**table_style).format({"外資(張)": "{:,.0f}", "投信(張)": "{:,.0f}", "自營(張)": "{:,.0f}", "三大法人合計": "{:,.0f}"}).map(risk_color, subset=["改版安全指數"])
            st.dataframe(styled_obs, height=430, use_container_width=True, hide_index=True)
    else:
        st.info("籌碼連線中斷，情報局暫停；沙盤與司令部仍可使用。")

with t_cmd:
    st.markdown("### 🏦 <span class='highlight-primary'>司令部：戰備資金精算</span>", unsafe_allow_html=True)

    if not sheet_url:
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

            html_cards = '<div style="display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px;">'
            for _, r in m_df.iterrows():
                try:
                    p_now_raw = r.get('現價', 0)
                    p_now = float(p_now_raw) if pd.notna(p_now_raw) and str(p_now_raw).strip() != '' else 0.0
                    p_cost = get_cmd_val(r, ["成本價", "成本", "買進價", "成交均價", "建倉成本", "買價"])
                    qty = get_cmd_val(r, ["庫存張數", "張數", "庫存", "股數", "數量"])

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

                    name_display = r['名稱'] if '名稱' in r else r.get('代號','')
                    display_p_now = f"{p_now:.2f}" if p_now > 0 else "抓取中"
                    timer_html = f"<span style='color:{timer_color}; font-size:12px;'>{timer_warning}</span>" if timer_warning else ""
                    
                    html_cards += f"<div class='holding-card {glow_class}' style='border-left: 5px solid {border_col}; padding: 10px 15px; background-color: {COLORS['card']}; border-radius: 4px; margin-bottom: 8px;'><div class='rwd-flex-header' style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;'><div class='rwd-flex-title' style='display: flex; align-items: baseline; gap: 15px;'><h3 style='margin: 0; font-size: 20px; font-weight: bold; color: {COLORS['text']};'>{name_display} ({r['代號']})</h3><div style='font-size: 13.5px; color: {COLORS['subtext']};'>現價: <strong style='color:{COLORS['text']}'>{display_p_now}</strong> | 成本: {p_cost:.2f} {timer_html}</div></div><div class='rwd-flex-profit' style='text-align: right;'><span style='font-size: 16px; font-weight: bold; color: {ret_col};'>{ret:.2f}%</span><span style='font-size: 16px; font-weight: bold; color: {ret_col}; margin-left: 10px;'>{pnl:,.0f} 元</span></div></div><div class='rwd-flex-info' style='background-color: {COLORS['bg']}; padding: 6px 12px; border-radius: 6px; font-size: 13.5px; display: flex; gap: 20px;'><div style='white-space: nowrap;'><span style='color:{COLORS['subtext']}'>📊 結構：</span><span style='color:{COLORS['text']}; font-weight:500;'>{struct}</span></div><div><span style='color:{COLORS['subtext']}'>💡 教練：</span><span style='color:{COLORS['text']}'>{coach}</span></div><div style='white-space: nowrap;'><span style='color:{COLORS['subtext']}'>🎯 下一步：</span><span style='color:{conf_color}; font-weight:700;'>{next_action}</span></div></div></div>"
                except Exception as e: continue
            html_cards += '</div>'
            
            p_color = COLORS["red"] if total_pnl > 0 else COLORS["green"]
            st.markdown(f"#### 💰 目前總淨損益：<span style='color:{p_color}; font-size:24px;'>{total_pnl:,.0f} 元</span>", unsafe_allow_html=True)
            st.markdown(html_cards, unsafe_allow_html=True)
        else:
            st.info("💡 目前尚無有效持股資料，或現價抓取失敗。")

    st.markdown("### 📊 <span class='highlight-primary'>AAR 戰術覆盤室</span>", unsafe_allow_html=True)
    aar.render_aar_tab(aar_sheet_url, fee_discount, FM_TOKEN, COLORS)

with t_backtest:
    st.markdown("### 📊 <span class='highlight-primary'>司令官回測室：資金限制版</span>", unsafe_allow_html=True)
    st.caption("用歷史日K模擬：本金、總曝險、整張/零股、跳空不追、+5.5%出半、M5/M10/ATR出場。這是驗證系統期望值，不是預測未來。")

    default_symbols = []
    if "eod_master_list" in st.session_state and isinstance(st.session_state["eod_master_list"], pd.DataFrame) and not st.session_state["eod_master_list"].empty:
        default_symbols = st.session_state["eod_master_list"]["代號"].astype(str).head(20).tolist()
    elif "eod_rank_sorted" in st.session_state and isinstance(st.session_state["eod_rank_sorted"], pd.DataFrame) and not st.session_state["eod_rank_sorted"].empty:
        default_symbols = st.session_state["eod_rank_sorted"]["代號"].astype(str).head(30).tolist()
    elif not today_df.empty and "代號" in today_df.columns:
        default_symbols = today_df.sort_values("三大法人合計", ascending=False).head(30)["代號"].astype(str).tolist()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        bt_capital = st.number_input("回測本金", min_value=50000, max_value=2000000, value=int(total_capital), step=10000)
        bt_period = st.selectbox("歷史期間", ["6mo", "1y", "2y"], index=1)
    with c2:
        bt_total_exp = st.slider("總曝險上限", 0.2, 1.0, 0.60, 0.05)
        bt_single = st.slider("單檔上限", 0.05, 0.30, 0.15, 0.01)
    with c3:
        bt_max_pos = st.slider("最多持股檔數", 1, 8, 4, 1)
        bt_new_per_day = st.slider("每日最多新買", 1, 3, 2, 1)
    with c4:
        bt_slip = st.slider("滑價估計", 0.0, 0.005, 0.0015, 0.0005, format="%.4f")
        bt_odd = st.checkbox("允許零股", value=True)

    default_text = ",".join(default_symbols[:30])
    symbol_text = st.text_area("回測股票池（逗號分隔；預設取目前主清單/法人買超前排）", value=default_text, height=90)
    run_bt = st.button("🚀 執行資金回測", type="primary", use_container_width=True)

    if run_bt:
        symbols = [x.strip() for x in symbol_text.replace("，", ",").replace("\n", ",").split(",") if x.strip()]
        cfg = BacktestConfig(
            initial_capital=float(bt_capital),
            total_exposure_pct=float(bt_total_exp),
            single_position_pct=float(bt_single),
            max_positions=int(bt_max_pos),
            max_new_positions_per_day=int(bt_new_per_day),
            fee_discount=float(fee_discount),
            slippage_pct=float(bt_slip),
            allow_odd_lot=bool(bt_odd),
        )
        with st.spinner("📡 正在執行資金限制回測，請稍候..."):
            result = run_portfolio_backtest(symbols, TWSE_NAME_MAP, FM_TOKEN, period=bt_period, config=cfg)
        st.session_state["commander_backtest_result"] = result

    result = st.session_state.get("commander_backtest_result")
    if result:
        if not result.get("ok"):
            st.warning(result.get("message", "回測無結果"))
        else:
            summary = result["summary"]
            m1, m2, m3, m4 = st.columns(4)
            metrics = [
                ("最終資金", f"{summary['最終資金']:,.0f}", COLORS['primary']),
                ("總報酬", f"{summary['總報酬(%)']:.2f}%", COLORS['green'] if summary['總報酬(%)'] >= 0 else COLORS['red']),
                ("最大回撤", f"{summary['最大回撤(%)']:.2f}%", COLORS['red']),
                ("勝率", f"{summary['勝率(%)']:.1f}%", COLORS['accent']),
            ]
            for col, (title, val, color) in zip([m1, m2, m3, m4], metrics):
                with col:
                    st.markdown(f"""
                    <div style="background:{COLORS['card']}; border:1px solid {COLORS['border']}; border-left:5px solid {color}; border-radius:10px; padding:12px 14px;">
                        <div style="font-size:13px; color:{COLORS['subtext']};">{title}</div>
                        <div style="font-size:24px; font-weight:800; color:{COLORS['text']};">{val}</div>
                    </div>
                    """, unsafe_allow_html=True)
            st.info(f"交易筆數：{summary['交易筆數']}｜平均單筆報酬：{summary['平均單筆報酬(%)']:.2f}%｜平均持有：{summary['平均持有天數']:.1f}天｜回測股票數：{summary['回測股票數']}")
            curve = result.get("equity_curve", pd.DataFrame())
            if not curve.empty:
                st.line_chart(curve.set_index("日期")[["總資產"]])
            tabs_bt = st.tabs(["分級績效", "交易明細"])
            with tabs_bt[0]:
                tier_stats = result.get("tier_stats", pd.DataFrame())
                if not tier_stats.empty:
                    st.dataframe(tier_stats.style.format({"勝率": "{:.1f}%", "平均報酬": "{:.2f}%", "總損益": "{:,.0f}"}), use_container_width=True, hide_index=True)
                else:
                    st.info("尚無足夠分級統計。")
            with tabs_bt[1]:
                trades = result.get("trades", pd.DataFrame())
                if not trades.empty:
                    st.dataframe(trades, use_container_width=True, hide_index=True, height=420)

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
st.markdown("<p style='text-align: center;' class='text-sub'>© 游擊隊軍火部 - v34.0</p>", unsafe_allow_html=True)
