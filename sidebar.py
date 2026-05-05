import streamlit as st
import theme


def _detect_mobile_by_context():
    """Best-effort mobile detection. Falls back to manual toggle if headers are unavailable."""
    try:
        ua = str(st.context.headers.get("user-agent", "")).lower()
        return any(k in ua for k in ["iphone", "android", "mobile", "ipad"])
    except Exception:
        return False


def _compact_divider():
    st.markdown("<div class='side-divider'></div>", unsafe_allow_html=True)


def render_sidebar(auth_status="guest_auth"):
    with st.sidebar:
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] .block-container { padding-top: .85rem; padding-bottom: .75rem; }
            [data-testid="stSidebar"] h3 { margin: 0 0 .42rem 0 !important; }
            [data-testid="stSidebar"] h4 { margin: .18rem 0 .30rem 0 !important; }
            [data-testid="stSidebar"] p, [data-testid="stSidebar"] label { line-height: 1.22 !important; }
            [data-testid="stSidebar"] div[data-testid="stRadio"] { margin-top: -.25rem; }
            [data-testid="stSidebar"] div[data-testid="stRadio"] label { padding-top: 0px !important; padding-bottom: 0px !important; }
            [data-testid="stSidebar"] div[data-testid="stExpander"] { margin: .36rem 0 .42rem 0 !important; }
            [data-testid="stSidebar"] div[data-testid="stAlert"] { padding: .42rem .55rem !important; margin: .30rem 0 !important; }
            [data-testid="stSidebar"] button { min-height: 2.15rem !important; }
            .side-divider { height:1px; background:rgba(128,128,128,.20); margin:.58rem 0 .50rem 0; }
            .side-note-card { border-left:4px solid #A68A75; background:rgba(128,128,128,.07); padding:.48rem .60rem; border-radius:6px; font-size:12.5px; line-height:1.42; margin:.32rem 0 .12rem 0; }
            .side-status-card { border-left:4px solid #20A05D; background:rgba(128,128,128,.07); padding:.45rem .60rem; border-radius:6px; font-size:12.5px; line-height:1.42; margin:.42rem 0 .45rem 0; }
            .side-caption-tight { font-size:12px; opacity:.78; margin:.28rem 0 .25rem 0; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### ⚙️ 操盤控制台")

        # 先讀取 secrets，但顯示區塊依使用者指定順序放在下方。
        if auth_status == "admin_auth":
            default_sheet_url = st.secrets.get("sheet_url", "")
            default_aar_url = st.secrets.get("aar_sheet_url", "")
            default_etf_holdings_url = st.secrets.get("active_etf_holdings_url", "")
            github_token = st.secrets.get("github_token", "")
            github_repo = st.secrets.get("github_repo", "")
            github_branch = st.secrets.get("github_branch", "")
            github_history_path = st.secrets.get("github_etf_history_path", "")
            github_history_ready = bool(github_token and github_repo and github_branch and github_history_path)
            required_secret_count = sum(bool(x) for x in [default_sheet_url, default_aar_url, github_history_ready])
        else:
            default_sheet_url = ""
            default_aar_url = ""
            default_etf_holdings_url = ""
            github_history_ready = False
            required_secret_count = 0

        # ===================================================
        # 📱 手機快查模式：第一順位
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
            help="手機快查只載入沙盤推演與快速兵工廠；網址加 ?quick=1 可固定進入。",
        )
        st.caption("快查：只跑沙盤與快速兵工廠" if mobile_quick_mode else "完整：載入 ETF / 法人 / AAR / 回測")

        _compact_divider()

        # ===================================================
        # 🎚️ 今日作戰模式：第二順位
        # ===================================================
        st.markdown("#### 🎚️ 今日操作節奏")
        operation_mode = st.radio(
            "選擇今日操作節奏",
            ["保守模式", "標準模式", "進攻模式"],
            index=1,
            horizontal=False,
            help="保守：提高門檻、減少買量；標準：維持原本節奏；進攻：略放寬B級與買量，但仍遵守停損。",
        )
        mode_note = {
            "保守模式": "🛡️ 保守：只打高把握標的，建議買量減少30%",
            "標準模式": "⚖️ 標準：短波段模型正常執行",
            "進攻模式": "⚔️ 進攻：B級備選更積極，買量最多提高15%",
        }.get(operation_mode, "⚖️ 標準：短波段模型正常執行")
        st.markdown(f"<div class='side-note-card'>{mode_note}</div>", unsafe_allow_html=True)

        _compact_divider()

        # ===================================================
        # 🔧 CSV 網址設定：第三順位
        # ===================================================
        with st.expander("🔧 CSV 網址設定", expanded=False):
            manual_sheet_url = st.text_input("【持股部位】CSV 網址", value="", placeholder="貼上您的持股 CSV 網址")
            manual_aar_url = st.text_input("【交易日誌】CSV 網址", value="", placeholder="貼上您的 AAR CSV 網址")
            manual_etf_url = st.text_input(
                "【主動ETF持股快照】CSV 網址",
                value="",
                placeholder="可選；欄位需含 日期、ETF代號、成分股代號、權重",
            )

        sheet_url = manual_sheet_url.strip() if manual_sheet_url.strip() else default_sheet_url
        aar_sheet_url = manual_aar_url.strip() if manual_aar_url.strip() else default_aar_url
        etf_holdings_url = manual_etf_url.strip() if manual_etf_url.strip() else default_etf_holdings_url

        _compact_divider()

        # ===================================================
        # 🎨 介面主題：第四順位
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
            label_visibility="collapsed",
        )

        try:
            COLORS = theme.apply_custom_theme(theme_choice)
            if not isinstance(COLORS, dict):
                raise TypeError("舊版 theme.py")
        except Exception:
            COLORS = {
                "bg": "#0D1117",
                "card": "#161B22",
                "border": "#30363D",
                "text": "#C9D1D9",
                "subtext": "#8B949E",
                "primary": "#58A6FF",
                "accent": "#79C0FF",
                "green": "#3FB950",
                "red": "#FF7B72",
            }
            st.error("⚠️ 偵測到雲端 theme.py 尚未更新，目前使用備用色碼。")

        _compact_divider()

        # ===================================================
        # 🧹 清空快取：第五順位
        # ===================================================
        if st.button("🔄 清空情報快取", use_container_width=True, help="資料異常、ETF/法人抓不到時再使用。"):
            st.cache_data.clear()
            st.success("快取已清除，請重新載入。")

        _compact_divider()

        # ===================================================
        # 🔗 資料連線：第六順位
        # ===================================================
        st.markdown("#### 🔗 資料連線")
        if auth_status == "admin_auth":
            backup_msg = "ETF備援CSV：已設定" if default_etf_holdings_url else "ETF備援CSV：未設定（選填）"
            st.caption(f"必要 secrets：{required_secret_count}/3（持股/AAR/GitHub歷史庫）")
            st.caption(backup_msg)
        else:
            st.caption("友軍模式：可手動貼 CSV")

        # app.py 會把資料健康燈號塞進這個 placeholder
        health_slot = st.empty()

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
            "health_slot": health_slot,
        }
