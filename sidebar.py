import streamlit as st
import theme


def render_sidebar(auth_status="guest_auth"):
    with st.sidebar:
        st.markdown("### ⚙️ 操盤控制台")

        # ===================================================
        # 🎚️ 作戰模式：每天最先決定的不是顏色，而是節奏
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
        # 💰 資金控管：每天真正會動到的核心設定
        # ===================================================
        st.markdown("#### 💰 資金控管")
        total_capital = st.number_input("作戰本金 (元)", value=200000, step=10000)
        risk_tolerance_pct = st.slider("單筆最大虧損容忍 (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
        risk_amount = total_capital * (risk_tolerance_pct / 100)
        st.info(f"🛡️ **單筆保命底線：{risk_amount:,.0f} 元**")

        fee_discount = st.slider("券商手續費折數", min_value=0.1, max_value=1.0, value=1.0, step=0.05, help="無折扣=1.0，五折=0.5")

        max_market_cap = total_capital * 0.60
        st.markdown(f"""
        <div style="background-color: rgba(128,128,128,0.08); padding: 12px; border-radius: 8px; border-left: 4px solid #6C7A89; margin-top: 10px;">
            <div style="font-size:13px; opacity:0.8;">最高曝險 60%</div>
            <div style="font-size:18px; font-weight:800;">{max_market_cap:,.0f} 元</div>
            <div style="font-size:12px; opacity:0.75; margin-top:4px;">預備金 40%：{total_capital - max_market_cap:,.0f} 元</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # ===================================================
        # 🔗 資料連線
        # ===================================================
        st.markdown("#### 🔗 資料連線")
        if auth_status == "admin_auth":
            default_sheet_url = st.secrets.get("sheet_url", "")
            default_aar_url = st.secrets.get("aar_sheet_url", "")
            if default_sheet_url:
                st.success("✅持股部位已自動連線", icon="🔗")
            if default_aar_url:
                st.success("✅交易日誌已自動連線", icon="🔗")
        else:
            default_sheet_url = ""
            default_aar_url = ""
            st.info("💡 友軍請手動貼上 CSV 網址", icon="👋")

        with st.expander("🔧 手動輸入 CSV 網址", expanded=not default_sheet_url):
            manual_sheet_url = st.text_input("【持股部位】CSV 網址", value="", placeholder="貼上您的持股 CSV 網址")
            manual_aar_url = st.text_input("【交易日誌】CSV 網址", value="", placeholder="貼上您的 AAR CSV 網址")

        sheet_url = manual_sheet_url.strip() if manual_sheet_url.strip() else default_sheet_url
        aar_sheet_url = manual_aar_url.strip() if manual_aar_url.strip() else default_aar_url

        st.markdown("---")

        # ===================================================
        # 🎨 主題放後面：不是每天操作核心
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
            "total_capital": total_capital,
            "risk_amount": risk_amount,
            "fee_discount": fee_discount,
            "operation_mode": operation_mode,
        }
