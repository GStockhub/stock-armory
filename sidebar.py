import streamlit as st
import theme


def _detect_mobile_by_context():
    """Best-effort mobile detection. Falls back to manual toggle if headers are unavailable."""
    try:
        ua = str(st.context.headers.get("user-agent", "")).lower()
        return any(k in ua for k in ["iphone", "android", "mobile", "ipad"])
    except Exception:
        return False


def render_sidebar(auth_status="guest_auth"):
    with st.sidebar:
        st.markdown("### ⚙️ 操盤控制台")

        # ===================================================
        # 🎚️ 作戰模式
        # ===================================================
        st.markdown("#### 🎚️ 今日作戰模式")
        operation_mode = st.radio(
            "選擇今日操作節奏",
            ["保守模式", "標準模式", "進攻模式"],
            index=1,
            horizontal=False,
            help="保守：提高門檻、減少買量；標準：維持原本節奏；進攻：略放寬B級與買量，但仍遵守停損。"
        )
        if operation_mode == "保守模式":
            st.warning("🛡️ 保守：只打高把握標的，建議買量減少30%")
        elif operation_mode == "進攻模式":
            st.info("⚔️ 進攻：B級備選更積極，建議買量最多提高15%")
        else:
            st.success("⚖️ 標準：短波段模型正常執行")

        st.markdown("---")

        # ===================================================
        # 📱 手機快查模式：自動偵測 + 手動備援 + URL 永久入口
        # ===================================================
        query_quick = False
        try:
            query_quick = str(st.query_params.get("quick", "")).lower() in ["1", "true", "yes", "mobile"]
        except Exception:
            query_quick = False
        auto_mobile = _detect_mobile_by_context()
        default_quick = bool(query_quick or auto_mobile)
        mobile_quick_mode = st.toggle(
            "📱 手機快查模式",
            value=default_quick,
            help="手機快查只載入沙盤推演與快速兵工廠，避免盤中手機重開時整套系統重跑。可在網址加 ?quick=1 固定進入。"
        )
        if mobile_quick_mode:
            st.caption("目前為快查模式：只載入沙盤與快速兵工廠。")
        else:
            st.caption("完整模式：載入ETF、法人、持股、AAR與回測。")

        st.markdown("---")

        # ===================================================
        # 🔗 資料連線
        # ===================================================
        st.markdown("#### 🔗 資料連線")
        if auth_status == "admin_auth":
            default_sheet_url = st.secrets.get("sheet_url", "")
            default_aar_url = st.secrets.get("aar_sheet_url", "")
            default_etf_holdings_url = st.secrets.get("active_etf_holdings_url", "")
            if default_sheet_url or default_aar_url or default_etf_holdings_url:
                st.success("✅ 已讀取 secrets 內的資料連線", icon="🔗")
        else:
            default_sheet_url = ""
            default_aar_url = ""
            default_etf_holdings_url = ""
            st.info("💡 友軍請手動貼上 CSV 網址", icon="👋")

        with st.expander("🔧 CSV 網址設定", expanded=False):
            manual_sheet_url = st.text_input("【持股部位】CSV 網址", value="", placeholder="貼上您的持股 CSV 網址")
            manual_aar_url = st.text_input("【交易日誌】CSV 網址", value="", placeholder="貼上您的 AAR CSV 網址")
            manual_etf_url = st.text_input("【主動ETF持股快照】CSV 網址", value="", placeholder="可選；欄位需含 日期、ETF代號、成分股代號、權重")

        sheet_url = manual_sheet_url.strip() if manual_sheet_url.strip() else default_sheet_url
        aar_sheet_url = manual_aar_url.strip() if manual_aar_url.strip() else default_aar_url
        etf_holdings_url = manual_etf_url.strip() if manual_etf_url.strip() else default_etf_holdings_url

        # 資料健康燈號由 app.py 在資料讀取後補進 sidebar，避免 Sidebar 自己重抓資料。
        st.markdown("---")

        # ===================================================
        # 🎨 介面主題
        # ===================================================
        st.markdown("#### 🎨 介面主題")
        theme_options = {
            "milktea_light": "☀️ 奶茶極簡",
            "gold": "👑 皇家黑金",
            "navy": "🦈 鯊魚淺藍",
            "gray": "🧘 極簡炭灰",
            "milktea_tech": "☕ 奶茶科技",
        }
        theme_choice = st.selectbox(
            "主題色系",
            list(theme_options.keys()),
            index=0,
            format_func=lambda x: theme_options.get(x),
        )

        try:
            COLORS = theme.apply_custom_theme(theme_choice)
            if not isinstance(COLORS, dict):
                raise TypeError("舊版 theme.py")
        except Exception:
            COLORS = {
                "bg": "#0D1117", "card": "#161B22", "border": "#30363D",
                "text": "#C9D1D9", "subtext": "#8B949E", "primary": "#58A6FF",
                "accent": "#79C0FF", "green": "#3FB950", "red": "#FF7B72",
            }
            st.error("⚠️ 偵測到雲端 theme.py 尚未更新，目前使用備用色碼。")

        st.markdown("---")
        if st.button("🔄 一鍵清空情報快取", use_container_width=True):
            st.cache_data.clear()
            st.success("快取已清除，請重新載入。")

        return {
            "COLORS": COLORS,
            "sheet_url": sheet_url,
            "aar_sheet_url": aar_sheet_url,
            "etf_holdings_url": etf_holdings_url,
            "total_capital": 200000.0,
            "risk_amount": 10000.0,
            "fee_discount": 1.0,
            "operation_mode": operation_mode,
            "mobile_quick_mode": mobile_quick_mode,
        }
