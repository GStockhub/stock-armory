import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import yfinance as yf

# =========================
# 👑 台灣專屬：民國年校正模組
# =========================
def parse_tw_date(d_str):
    try:
        d_str = str(d_str).strip().replace('/', '-').replace('.', '-')
        parts = d_str.split('-')
        if len(parts) == 3:
            y = int(parts[0])
            if y < 200: y += 1911  # 民國年自動轉西元
            return pd.to_datetime(f"{y}-{parts[1]}-{parts[2]}")
        return pd.to_datetime(d_str)
    except:
        return pd.NaT

# =========================
# FinMind 主引擎
# =========================
def get_finmind_data(sid, start_date, fm_token):
    if not fm_token:
        return pd.DataFrame()
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": sid,
            "start_date": start_date,
            "token": fm_token.strip()
        }
        res = requests.get(url, params=params, timeout=10, verify=False).json()

        if res.get("data") and len(res["data"]) > 0:
            df = pd.DataFrame(res["data"])
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)

            df['High'] = df.get('max', df.get('high', df['close']))
            df['Close'] = df['close']

            df = df[['High', 'Close']].dropna()
            df = df.sort_index()
            return df
    except:
        pass
    return pd.DataFrame()


# =========================
# YF 備援引擎
# =========================
def get_yf_data(sid, start_date):
    suffixes = [".TW", ".TWO"]
    for suf in suffixes:
        try:
            df = yf.Ticker(f"{sid}{suf}").history(start=start_date)
            if not df.empty:
                df.index = pd.to_datetime(df.index.date)
                df['High'] = df.get('High', df['Close'])
                df = df[['High', 'Close']].dropna()
                df = df.sort_index()
                return df
        except:
            continue
    return pd.DataFrame()


# =========================
# 主函數
# =========================
def render_aar_tab(aar_sheet_url, fee_discount, fm_token):

    if not aar_sheet_url:
        st.info("請輸入交易日誌 CSV")
        return

    try:
        df = pd.read_csv(aar_sheet_url)
        df.columns = df.columns.str.strip()

        global_start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")

        cache = {}
        results = []
        total_pnl = 0

        fm_ok, yf_ok, fail = 0, 0, 0

        with st.spinner("AI 覆盤分析中..."):

            for _, row in df.iterrows():
                try:
                    sid = str(row['代號']).strip()
                    if sid == "" or sid == "nan":
                        continue

                    # 👑 套用民國年修正，不再變成西元 113 年
                    b_date = parse_tw_date(row['買進日期'])
                    b_price = float(row['買進價'])
                    shares = float(row['張數'])

                    tag = str(row.get('心理標籤', '')).strip()

                    fee_rate = 0.001425 * fee_discount
                    tax_rate = 0.001 if sid.startswith('00') else 0.003

                except:
                    continue

                # ========= 抓資料（快取） =========
                if sid not in cache:

                    hist = get_finmind_data(sid, global_start, fm_token)

                    if not hist.empty:
                        fm_ok += 1
                    else:
                        hist = get_yf_data(sid, global_start)
                        if not hist.empty:
                            yf_ok += 1
                        else:
                            fail += 1

                    cache[sid] = hist
                    time.sleep(0.2)

                hist = cache[sid]

                # ========= 預設 =========
                diagnosis = "⚠️ 無資料"
                s_price = b_price
                s_date = None  # 👑 新增變數供持有天數計算

                # ========= 未平倉 =========
                if pd.isna(row.get('賣出日期')) or str(row.get('賣出價', '')).strip() == "":
                    if not hist.empty:
                        s_price = float(hist['Close'].iloc[-1])
                        diagnosis = f"⚪ 未平倉 | 現價 {s_price:.1f}"
                    else:
                        diagnosis = "⚪ 未平倉 | 無報價"

                # ========= 已平倉 =========
                else:
                    # 👑 套用民國年修正
                    s_date = parse_tw_date(row['賣出日期'])
                    s_price = float(row['賣出價'])

                    if hist.empty:
                        diagnosis = "⚠️ 無K線資料"
                    else:
                        hist = hist.sort_index()

                        # 👑 核心修正：不要用 in index
                        future_data = hist[hist.index > s_date]

                        if future_data.empty:
                            if (datetime.now() - s_date).days <= 3:
                                diagnosis = "⏳ 剛賣出"
                            else:
                                diagnosis = "⚠️ 無後續資料"
                        else:
                            max_high = future_data['High'].max()

                            if pd.isna(max_high):
                                diagnosis = "⚠️ 價格異常"
                            else:
                                if '恐高' in tag or '耐心' in tag:
                                    if max_high > s_price * 1.02:
                                        missed = (max_high - s_price) * shares * 1000
                                        diagnosis = f"⚠️ 賣飛！後高{max_high:.1f} 少賺 {missed:,.0f}"
                                    else:
                                        diagnosis = "✅ 賣點合理"

                                elif '恐慌' in tag:
                                    if max_high > b_price:
                                        diagnosis = "🩸 被洗出場"
                                    else:
                                        diagnosis = "🛡️ 止損正確"

                                elif '紀律' in tag:
                                    diagnosis = "👑 紀律執行"

                                else:
                                    diagnosis = f"📊 後高 {max_high:.1f}"

                # ========= 損益 (台灣券商整數化修正) =========
                buy_fee = int((b_price * shares * 1000) * fee_rate)
                buy_cost = (b_price * shares * 1000) + buy_fee
                
                sell_fee = int((s_price * shares * 1000) * fee_rate)
                sell_tax = int((s_price * shares * 1000) * tax_rate)
                sell_rev = (s_price * shares * 1000) - sell_fee - sell_tax

                pnl = sell_rev - buy_cost
                roi = (pnl / buy_cost) * 100 if buy_cost > 0 else 0

                total_pnl += pnl

                # 👑 修復持有天數：已賣出用賣出日減，未賣出才用今天減
                if s_date is not None:
                    held_days = (s_date - b_date).days
                else:
                    held_days = (datetime.now() - b_date).days

                results.append({
                    "代號": sid,
                    "持有天數": held_days,
                    "淨利": pnl,
                    "報酬%": roi,
                    "心魔": tag[:10],
                    "AI診斷": diagnosis
                })

        # ========= 顯示 =========
        if results:
            res = pd.DataFrame(results)

            st.metric("總淨利", f"{total_pnl:,.0f} 元")

            st.write(f"FinMind成功: {fm_ok} | YF成功: {yf_ok} | 失敗: {fail}")

            st.dataframe(
                res.style.format({
                    "淨利": "{:,.0f}",
                    "報酬%": "{:.2f}%"
                }).map(
                    lambda x: "color:#EF4444" if x > 0 else "color:#10B981", # 配合台灣紅漲綠跌習慣
                    subset=["淨利", "報酬%"]
                ),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("沒有資料")

    except Exception as e:
        st.error(f"系統錯誤: {e}")
