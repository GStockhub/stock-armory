import streamlit as st
import theme  # 讓側邊欄自己去呼叫主題兵工廠

def render_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ 紀律設定")
        st.markdown("---")
        
        # 1. 👑 UI 魔法切換開關 (改為戰術單選鈕，徹底禁止鍵盤輸入)
        theme_choice = st.radio(
            "🎨 戰情室佈景主題", 
            ["ocean", "gold", "gray"], 
            index=0, 
            format_func=lambda x: {"ocean":"🌊 深海藍", "gold":"👑 黑金", "gray":"🧘 極簡灰"}.get(x)
        )
        
        # 🛡️ 終極防彈裝甲：防止 theme.py 沒更新導致系統當機
        try:
            COLORS = theme.apply_custom_theme(theme_choice)
            if not isinstance(COLORS, dict): raise TypeError("舊版 theme.py")
        except Exception as e:
            COLORS = {
                "bg": "#0B132B", "card": "#1C2541", "border": "#2C3A5A",
                "text": "#E0E6F1", "subtext": "#9FB3C8", "primary": "#5BC0BE",
                "accent": "#CDE7F0", "green": "#6FFFB0", "red": "#FF6B6B"
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
        
        # 👑 未來想改 HTML 或加顏色，都在這裡改！
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
            
        # 3. 📤 將所有大腦需要的參數打包送出去
        return {
            "COLORS": COLORS,
            "sheet_url": sheet_url,
            "aar_sheet_url": aar_sheet_url,
            "total_capital": total_capital,
            "risk_amount": risk_amount,
            "fee_discount": fee_discount
        }
