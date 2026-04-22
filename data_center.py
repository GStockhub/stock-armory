@st.cache_data(ttl=14400, show_spinner=False)
def get_macro_dashboard():
    score = 5.0
    macro_data = []
    overheat_flag = False

    # 🔥 主指數 + ETF備援（重點）
    indices = {
        "^TWII": ("台股加權", "0050.TW"),
        "^IXIC": ("那斯達克", "QQQ"),
        "^GSPC": ("標普500", "SPY"),
        "^VIX": ("恐慌指數", "VIXY"),
        "TWD=X": ("美元/台幣(匯率)", "TWD=X"),
    }

    for main_sym, (name, fallback) in indices.items():
        display_name = name
        hist = pd.DataFrame()

        # 🔹 第一層：yfinance 主抓
        try:
            hist = yf.download(main_sym, period="3mo", progress=False)
        except:
            pass

        # 🔹 第二層：fallback ETF
        if hist is None or hist.empty:
            try:
                hist = yf.download(fallback, period="3mo", progress=False)
                if not hist.empty:
                    display_name = f"{name}(ETF備援)"
            except:
                pass

        # 🔴 第三層：完全失敗 → 顯示斷線但不中斷系統
        if hist is None or hist.empty:
            macro_data.append({
                "戰區": display_name,
                "現值": "抓取失敗",
                "月線": "-",
                "狀態": "⚪ 斷線"
            })
            continue

        try:
            close = hist["Close"]
            last = float(close.iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])

            bias = ((last - ma20) / ma20) * 100 if ma20 > 0 else 0

            # ===== 狀態判斷 =====
            if "恐慌" in name:
                if last > 25:
                    status = "🔴 恐慌"
                    score -= 2
                elif last > 18:
                    status = "🟡 警戒"
                else:
                    status = "🟢 安定"
                    score += 1

            elif "匯率" in name:
                if last > ma20:
                    status = "🔴 貶值"
                    score -= 1
                else:
                    status = "🟢 升值"
                    score += 1

            else:
                if last > ma20:
                    status = "🟢 多頭"
                    score += 1
                else:
                    status = "🔴 空頭"
                    score -= 1

                # 🔥 台股過熱判定
                if "台股" in name and bias > 5:
                    overheat_flag = True
                    score -= 2
                    status = "🔥 過熱"

            macro_data.append({
                "戰區": display_name,
                "現值": f"{last:.2f}",
                "月線": f"{ma20:.2f}",
                "狀態": status
            })

        except:
            macro_data.append({
                "戰區": display_name,
                "現值": "計算失敗",
                "月線": "-",
                "狀態": "⚪ 斷線"
            })

    return max(1, min(10, int(score))), pd.DataFrame(macro_data), overheat_flag
