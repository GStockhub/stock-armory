@st.cache_data(ttl=14400, show_spinner=False)
def fetch_chips_data(fm_token=None):
    chip_dict = {}
    date_ptr = datetime.now()
    attempts = 0
    session = get_retry_session()

    while len(chip_dict) < 5 and attempts < 20:
        if date_ptr.weekday() < 5:
            d_str = date_ptr.strftime("%Y%m%d")
            fm_d_str = date_ptr.strftime("%Y-%m-%d")
            success = False

            # =========================
            # 先抓 FinMind（主來源）
            # =========================
            if fm_token and str(fm_token).strip():
                try:
                    fm_url = "https://api.finmindtrade.com/api/v4/data"
                    params = {
                        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
                        "start_date": fm_d_str,
                        "end_date": fm_d_str,
                        "token": str(fm_token).strip()
                    }

                    r = session.get(
                        fm_url,
                        params=params,
                        timeout=12,
                        verify=False
                    )

                    if r.status_code == 200:
                        res = r.json()

                        if res.get("msg") == "success" and res.get("data"):
                            df = pd.DataFrame(res["data"])

                            if (
                                not df.empty
                                and "stock_id" in df.columns
                                and "name" in df.columns
                                and "buy" in df.columns
                                and "sell" in df.columns
                            ):
                                df["buy"] = pd.to_numeric(
                                    df["buy"], errors="coerce"
                                ).fillna(0)

                                df["sell"] = pd.to_numeric(
                                    df["sell"], errors="coerce"
                                ).fillna(0)

                                df["net"] = (
                                    (df["buy"] - df["sell"]) / 1000
                                )

                                pivot_df = df.pivot_table(
                                    index="stock_id",
                                    columns="name",
                                    values="net",
                                    aggfunc="sum"
                                ).fillna(0)

                                clean = pd.DataFrame()
                                clean["代號"] = pivot_df.index.astype(str)
                                clean["名稱"] = clean["代號"]

                                trust_cols = [
                                    c for c in pivot_df.columns
                                    if (
                                        "Investment_Trust" in str(c)
                                        or "投信" in str(c)
                                    )
                                ]

                                foreign_cols = [
                                    c for c in pivot_df.columns
                                    if (
                                        "Foreign" in str(c)
                                        or "外資" in str(c)
                                    )
                                ]

                                dealer_cols = [
                                    c for c in pivot_df.columns
                                    if (
                                        "Dealer" in str(c)
                                        or "自營" in str(c)
                                    )
                                ]

                                clean["投信(張)"] = (
                                    pivot_df[trust_cols].sum(axis=1).values
                                    if trust_cols else 0
                                )

                                clean["外資(張)"] = (
                                    pivot_df[foreign_cols].sum(axis=1).values
                                    if foreign_cols else 0
                                )

                                clean["自營(張)"] = (
                                    pivot_df[dealer_cols].sum(axis=1).values
                                    if dealer_cols else 0
                                )

                                clean["三大法人合計"] = (
                                    clean["投信(張)"]
                                    + clean["外資(張)"]
                                    + clean["自營(張)"]
                                )

                                chip_dict[d_str] = clean
                                success = True

                except Exception as e:
                    print(f"FinMind chip failed {fm_d_str}: {e}")

            # =========================
            # FinMind失敗 → 改抓TWSE備援
            # =========================
            if not success:
                try:
                    twse_url = (
                        f"https://www.twse.com.tw/rwd/zh/fund/T86"
                        f"?date={d_str}"
                        f"&selectType=ALLBUT0999"
                        f"&response=json"
                    )

                    r = session.get(
                        twse_url,
                        timeout=12,
                        verify=False
                    )

                    if r.status_code == 200:
                        res = r.json()

                        if (
                            res.get("stat") == "OK"
                            and res.get("data")
                        ):
                            df = pd.DataFrame(
                                res["data"],
                                columns=res["fields"]
                            )

                            code_col = [
                                c for c in df.columns
                                if (
                                    "證券代號" in c
                                    or "代號" in c
                                )
                            ][0]

                            name_col = [
                                c for c in df.columns
                                if (
                                    "證券名稱" in c
                                    or "名稱" in c
                                )
                            ][0]

                            trust_cols = [
                                c for c in df.columns
                                if (
                                    "投信" in c
                                    and "買賣超" in c
                                )
                            ]

                            foreign_cols = [
                                c for c in df.columns
                                if (
                                    "外資" in c
                                    and "買賣超" in c
                                )
                            ]

                            dealer_cols = [
                                c for c in df.columns
                                if (
                                    "自營" in c
                                    and "買賣超" in c
                                )
                            ]

                            def parse_col(col_name):
                                return pd.to_numeric(
                                    df[col_name]
                                    .astype(str)
                                    .str.replace(",", "", regex=False),
                                    errors="coerce"
                                ).fillna(0) / 1000

                            clean = pd.DataFrame()

                            clean["代號"] = (
                                df[code_col]
                                .astype(str)
                                .str.strip()
                            )

                            clean["名稱"] = (
                                df[name_col]
                                .astype(str)
                                .str.strip()
                            )

                            clean["投信(張)"] = (
                                sum(parse_col(c) for c in trust_cols)
                                if trust_cols else 0
                            )

                            clean["外資(張)"] = (
                                sum(parse_col(c) for c in foreign_cols)
                                if foreign_cols else 0
                            )

                            clean["自營(張)"] = (
                                sum(parse_col(c) for c in dealer_cols)
                                if dealer_cols else 0
                            )

                            clean["三大法人合計"] = (
                                clean["投信(張)"]
                                + clean["外資(張)"]
                                + clean["自營(張)"]
                            )

                            chip_dict[d_str] = clean

                except Exception as e:
                    print(f"TWSE chip failed {d_str}: {e}")

        date_ptr -= timedelta(days=1)
        attempts += 1
        time.sleep(0.15)

    return chip_dict
