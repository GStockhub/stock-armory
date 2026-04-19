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
