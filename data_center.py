# 🚀 更改了 TTL 來強制打破 Streamlit 的壞資料快取！
@st.cache_data(ttl=14400, show_spinner=False)
def fetch_chips_data(fm_token=None):
    chip_dict = {}
    date_ptr = datetime.now()
    attempts = 0
    session = get_retry_session()

    # 🛡️ 採用 GPT 的神級戰術：不抓滿 5 天有效資料，絕不退兵 (最多嘗試 20 天)
    while len(chip_dict) < 5 and attempts < 20:
        if date_ptr.weekday() < 5:  # 只抓平日 (週一到週五)
            fm_d_str = date_ptr.strftime("%Y-%m-%d")
            
            try:
                fm_url = "https://api.finmindtrade.com/api/v4/data"
                params = {
                    "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
                    "start_date": fm_d_str,
                    "end_date": fm_d_str,
                }
                if fm_token and str(fm_token).strip():
                    params["token"] = str(fm_token).strip()

                r = session.get(fm_url, params=params, timeout=15, verify=False)
                
                if r.status_code == 200:
                    res = r.json()
                    
                    if res.get("msg") == "success" and res.get("data"):
                        df = pd.DataFrame(res["data"])
                        
                        # 🛡️ 結合 GPT 的終極防護：極度嚴格檢查所有必要欄位
                        if (not df.empty and 
                            "stock_id" in df.columns and 
                            "name" in df.columns and 
                            "buy" in df.columns and 
                            "sell" in df.columns):
                            
                            df["buy"] = pd.to_numeric(df["buy"], errors="coerce").fillna(0)
                            df["sell"] = pd.to_numeric(df["sell"], errors="coerce").fillna(0)
                            df["net"] = (df["buy"] - df["sell"]) / 1000
                            
                            pivoted = df.pivot_table(
                                index="stock_id", 
                                columns="name", 
                                values="net", 
                                aggfunc="sum"
                            ).fillna(0)
                            
                            # 確保三大法人的欄位一定存在，避免後續加總崩潰
                            for col in ["Foreign_Investor", "Investment_Trust", "Dealer_self"]:
                                if col not in pivoted.columns:
                                    pivoted[col] = 0

                            pivoted["三大法人合計"] = pivoted["Foreign_Investor"] + pivoted["Investment_Trust"] + pivoted["Dealer_self"]
                            
                            pivoted = pivoted.rename(columns={
                                "Foreign_Investor": "外資(張)", 
                                "Investment_Trust": "投信(張)", 
                                "Dealer_self": "自營(張)"
                            }).reset_index().rename(columns={"stock_id": "代號"})
                            
                            pivoted["代號"] = pivoted["代號"].astype(str)
                            
                            # 只有真正成功處理完，才加入字典
                            chip_dict[fm_d_str] = pivoted
                        else:
                            print(f"[{fm_d_str}] 資料欄位殘缺 (可能是假日或 FinMind 異常)，直接跳過。")
                            
            except Exception as e:
                print(f"FinMind chip failed for {fm_d_str}: {e}")

        # 時間往前推一天，繼續嘗試
        date_ptr -= timedelta(days=1)
        attempts += 1
        time.sleep(0.2)  # 稍微等待避免被鎖 IP

    return chip_dict
