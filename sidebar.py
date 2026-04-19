import streamlit as st
import theme  

def render_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ 紀律設定")
        st.markdown("---")
        
        # 1. 👑 拔除囉唆括號，清爽俐落！
        theme_options = {
            "navy": "🦈 鯊魚海軍藍",
            "gold": "👑 黑金專業",
            "gray": "🧘 極簡炭灰",
            "milktea_tech": "☕ 奶茶科技",
            "milktea_light": "☀️ 奶茶極簡"
        }
        
        theme_choice = st.selectbox(
            "🎨 戰情室佈景主題", 
            list(theme_options.keys()), 
            index=0, 
            format_func=lambda x: theme_options.get(x)
        )
        
        try:
            COLORS = theme.apply_custom_theme(theme_choice)
            if not isinstance(COLORS, dict): raise TypeError("舊版 theme.py")
        except Exception as e:
            COLORS = {
                "bg": "#0D1117", "card": "#161B22", "border": "#30363D",
                "text": "#C9D1D9", "subtext": "#8B949E", "primary": "#58A6FF",
                "accent": "#79C0FF", "green": "#3FB950", "red": "#FF7B72"
            }
            st.error("⚠️ 偵測到雲端 `theme.py` 尚未更新！目前使用緊急備用色碼。")

        # 2. 📝 輸入欄位
        sheet_url = st.text_input("輸入【持股部位】CSV 網址：", value="", placeholder="貼上持股分頁網址")
        aar_sheet_url = st.text_input("輸入【交易日誌】CSV 網址：", value="", placeholder="貼上日誌分頁網址(供AAR使用)")
        
        st.markdown("---")
        st.markdown("#### 💰 資金控管")
        total_capital = st.number_input("作戰本金 (元)", value=200000, step=10000)
        risk_tolerance_pct = st.slider("單筆最大虧損容忍 (%)", min_value=1.0, max_value=10.0, value=5.0, step=0.5)
        risk_amount = total_capital * (risk_tolerance_pct / 100)
        
        st.info(f"🛡️ **單筆保命底線：{risk_amount:,.0f} 元**\n\n*(依此反推單筆最多買進張數)*")
        
        st.markdown("---")
        st.markdown("#### ⚖️ 真實稅費參數")
        fee_discount = st.slider("券商手續費折數 (無折扣=1.0, 五折=0.5)", min_value=0.1, max_value=1.0, value=1.0, step=0.05)
        
        st.markdown("---")
        st.markdown("#### 🛡️ 總曝險與預備金")
        max_market_cap = total_capital * 0.60
        
        st.markdown(f"""
        <div style="background-color: {COLORS['card']}; padding: 15px; border-radius: 8px; border-left: 5px solid {COLORS['primary']}; margin-bottom: 15px;">
            <div style="margin-bottom: 12px; text-align: left;">
                ⚔️ <b style="color: {COLORS['text']};">最高資金 (60%)：</b><br>
                <span style="font-size: 18px; font-weight: bold; color: {COLORS['primary']};">{max_market_cap:,.0f} 元</span>
            </div>
            <div style="text-align: left;">
                🛡️ <b style="color: {COLORS['text']};">預備部隊 (40%)：</b><br>
                <span style="font-size: 18px; font-weight: bold; color: {COLORS['accent']};">{total_capital - max_market_cap:,.0f} 元</span><br>
                <span style="font-size: 14px; color: {COLORS['subtext']};">*(極端避險與股災專用)*</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🔄 一鍵清空情報快取"):
            st.cache_data.clear()
            st.success("快取已清除！請重新載入。")
            
        return {
            "COLORS": COLORS,
            "sheet_url": sheet_url,
            "aar_sheet_url": aar_sheet_url,
            "total_capital": total_capital,
            "risk_amount": risk_amount,
            "fee_discount": fee_discount
        }
