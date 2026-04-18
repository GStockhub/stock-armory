# ==============================================================================
# 【v25.2 AAR 核武：FinMind 優先 + yf 備援 + 智能解析】
# ==============================================================================

def get_finmind_data(sid, start_date, fm_token):
    """FinMind 優先抓取（600req/hr）"""
    if not fm_token or fm_token == "":
        return pd.DataFrame()
    
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": sid,
            "start_date": start_date,
            "token": fm_token.strip()
        }
        res = requests.get(url, params=params, timeout=8, verify=False).json()
        
        if res.get("msg") == "success" and res.get("data"):
            df = pd.DataFrame(res["data"])
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # 欄位標準化
            df['High'] = df.get('max', df.get('high', df['close']))
            df['Close'] = df['close']
            return df[['High', 'Close']]
    except:
        pass
    return pd.DataFrame()

def robust_yf_fallback(sid, start_date):
    """yf 備援（日期絕對清理）"""
    suffixes = [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            df = ticker.history(start=start_date)
            if not df.empty:
                # 👑 絕對日期清理：只留 YYYY-MM-DD 00:00:00
                df.index = pd.to_datetime(df.index.date)
                df['High'] = df.get('High', df['Close'])
                return df[['High', 'Close']]
        except:
            continue
    return pd.DataFrame()

def render_aar_tab(aar_sheet_url, fee_discount, fm_token):
    if not aar_sheet_url:
        st.info("請輸入【交易日誌】CSV 網址")
        return
    
    try:
        aar_df = pd.read_csv(aar_sheet_url)
        aar_df.columns = aar_df.columns.str.strip()
        
        global_start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")  # 2年
        results, total_pnl = [], 0
        cache = {}  # 股票快取
        fm_success, yf_success, fail_count = 0, 0, 0
        
        st.info(f"🔑 FinMind Token 狀態：{'✅ 有效' if fm_token else '❌ 未設定（限速300/hr）'}")
        
        with st.spinner('🕵️ 雙重資料源解析中...'):
            for _, row in aar_df.iterrows():
                sid = str(row['代號']).strip()
                if sid in ['nan', '']: continue
                
                # 基本資料
                b_date = pd.to_datetime(row['買進日期']).date()
                b_price, shares = float(row['買進價']), float(row['張數'])
                tag = str(row.get('心理標籤', '')).strip()
                fee_rate = 0.001425 * fee_discount
                tax_rate = 0.001 if sid.startswith('00') else 0.003
                
                # 快取資料
                if sid not in cache:
                    # 1. FinMind 優先
                    hist_fm = get_finmind_data(sid, global_start, fm_token)
                    if not hist_fm.empty:
                        cache[sid] = hist_fm
                        fm_success += 1
                    else:
                        # 2. yf 備援
                        hist_yf = robust_yf_fallback(sid, global_start)
                        if not hist_yf.empty:
                            cache[sid] = hist_yf
                            yf_success += 1
                        else:
                            fail_count += 1
                            cache[sid] = pd.DataFrame()
                
                hist = cache[sid]
                
                # 賣出價/診斷
                s_price = float(row.get('賣出價', b_price))
                diagnosis = "✅ 已結案"
                
                if pd.isna(row.get('賣出日期')) or str(row.get('賣出價', '')).strip() == "":
                    # 未平倉
                    if not hist.empty:
                        s_price = float(hist['Close'].iloc[-1])
                        diagnosis = f"⚪ 未平倉 | 現價：{s_price:.1f}"
                    else:
                        diagnosis = "⚪ 未平倉 | 無報價"
                else:
                    s_date = pd.to_datetime(row['賣出日期']).date()
                    if not hist.empty and s_date in hist.index:
                        future_mask = hist.index > s_date
                        future_data = hist[future_mask]
                        
                        if len(future_data) > 0:
                            max_high = future_data['High'].max()
                            if '恐高' in tag or '耐心' in tag:
                                if max_high > s_price * 1.02:
                                    missed = (max_high - s_price) * shares * 1000
                                    diagnosis = f"⚠️ 賣早了！後高{int(max_high)}，少+{missed:,.0f}"
                                else:
                                    diagnosis = "✅ 時機正確"
                            elif '恐慌' in tag:
                                diagnosis = "🩸 被洗出局" if max_high > b_price else "🛡️ 正確止損"
                            else:
                                diagnosis = f"後高：{int(max_high)}"
                        else:
                            diagnosis = "⏳ 剛賣出"
                    else:
                        diagnosis = "⚠️ 無後續K線"
                
                # 稅後損益
                buy_cost = (b_price * shares * 1000) * (1 + fee_rate)
                sell_rev = (s_price * shares * 1000) * (1 - fee_rate - tax_rate)
                pnl = sell_rev - buy_cost
                roi = (pnl / buy_cost) * 100 if buy_cost > 0 else 0
                total_pnl += pnl
                
                results.append({
                    '代號': sid, '天數': (datetime.now().date() - b_date).days,
                    '淨利': pnl, '報酬%': roi, '心魔': tag[:15],
                    '診斷': diagnosis
                })
        
        # 顯示結果
        if results:
            df_results = pd.DataFrame(results)
            p_color = "#10B981" if total_pnl > 0 else "#EF4444"
            
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("總淨利", f"{total_pnl:,.0f}元", delta=f"{total_pnl/len(results):,.0f}平均")
            with col2: st.metric("成功率", f"{(fm_success+yf_success)/(fm_success+yf_success+fail_count)*100:.0f}%")
            with col3: st.metric("阻擋筆數", fail_count)
            
            st.dataframe(df_results.style.format({
                '淨利': '{:,.0f}', '報酬%': '{:.1f}%'
            }).map(lambda x: 'color: #10B981; font-weight: bold' if x > 0 else 'color: #EF4444' 
                   if x < 0 else '', subset=['淨利', '報酬%']), hide_index=True)
        else:
            st.warning("無有效紀錄")
            
    except Exception as e:
        st.error(f"❌ 錯誤：{str(e)[:100]}")
