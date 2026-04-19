def get_theme(name="dark_quant"):
    
    if name == "dark_quant":  # 👑 ① 暗黑量化神殿（主推）
        return """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Roboto+Mono:wght@400;600&display=swap');

        .stApp { background-color: #121417; }

        h1, h2, h3, h4, h5, h6, p, div, span, label, li {
            color: #E5E7EB !important;
            font-family: 'Inter', sans-serif;
        }

        table, [data-testid="stDataFrame"] {
            font-family: 'Roboto Mono', monospace !important;
        }

        /* 色彩 */
        .highlight-gold { color: #C9A227 !important; font-weight: 600; }
        .highlight-cyan { color: #3A7CA5 !important; font-weight: 600; }
        .highlight-red { color: #C53030 !important; font-weight: 600; }
        .highlight-green { color: #2F855A !important; font-weight: 600; }

        /* Tabs */
        .stTabs [data-baseweb="tab"] {
            background-color: #1C1F23;
            border: 1px solid #2A2F35;
            color: #9CA3AF;
        }
        .stTabs [aria-selected="true"] {
            color: #C9A227 !important;
            border-bottom: 2px solid #C9A227 !important;
        }

        /* 卡片 */
        .tier-card {
            background-color: #1C1F23;
            border: 1px solid #2A2F35;
            border-radius: 8px;
            padding: 20px;
        }

        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: #0F1113;
        }

        /* Scroll */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-thumb { background: #2A2F35; }

        /* Button */
        .stButton > button {
            background-color: #1C1F23 !important;
            color: #C9A227 !important;
            border: 1px solid #2A2F35 !important;
        }
        </style>
        """

    elif name == "minimal":  # 🧘 ③ 極簡冷靜
        return """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Roboto+Mono:wght@400;600&display=swap');

        .stApp { background-color: #16181C; }

        h1, h2, h3, h4, h5, h6, p, div, span, label, li {
            color: #E2E8F0 !important;
            font-family: 'Inter', sans-serif;
        }

        table, [data-testid="stDataFrame"] {
            font-family: 'Roboto Mono', monospace !important;
        }

        .highlight-gold { color: #60A5FA !important; font-weight: 600; }
        .highlight-cyan { color: #93C5FD !important; }
        .highlight-red { color: #F87171 !important; }
        .highlight-green { color: #34D399 !important; }

        .stTabs [data-baseweb="tab"] {
            background-color: #20242A;
            border: 1px solid #2D3238;
            color: #9CA3AF;
        }
        .stTabs [aria-selected="true"] {
            color: #60A5FA !important;
        }

        .tier-card {
            background-color: #20242A;
            border: 1px solid #2D3238;
            border-radius: 8px;
            padding: 20px;
        }

        [data-testid="stSidebar"] {
            background-color: #14161A;
        }

        .stButton > button {
            background-color: #20242A !important;
            color: #60A5FA !important;
            border: 1px solid #2D3238 !important;
        }
        </style>
        """

    elif name == "gold_pro":  # 🪙 ④ 奢華黑金
        return """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Roboto+Mono:wght@400;600&display=swap');

        .stApp { background-color: #111111; }

        h1, h2, h3, h4, h5, h6, p, div, span, label, li {
            color: #F5F5F5 !important;
            font-family: 'Inter', sans-serif;
        }

        table, [data-testid="stDataFrame"] {
            font-family: 'Roboto Mono', monospace !important;
        }

        .highlight-gold { color: #B8962E !important; font-weight: 700; }
        .highlight-cyan { color: #E6C76B !important; }
        .highlight-red { color: #E53E3E !important; }
        .highlight-green { color: #38A169 !important; }

        .stTabs [data-baseweb="tab"] {
            background-color: #1E1E1E;
            border: 1px solid #2C2C2C;
            color: #A0AEC0;
        }
        .stTabs [aria-selected="true"] {
            color: #B8962E !important;
            border-bottom: 2px solid #B8962E !important;
        }

        .tier-card {
            background-color: #1E1E1E;
            border: 1px solid #2C2C2C;
            border-radius: 8px;
            padding: 20px;
        }

        [data-testid="stSidebar"] {
            background-color: #0D0D0D;
        }

        .stButton > button {
            background-color: #1E1E1E !important;
            color: #B8962E !important;
            border: 1px solid #2C2C2C !important;
        }
        </style>
        """

    else:
        return ""
