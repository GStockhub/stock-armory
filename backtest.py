def run_backtest(df):
    position = None
    trades = []

    for i in range(20, len(df)):
        row = df.iloc[i]

        data = {
            "price": row["Close"],
            "ma5": row["MA5"],
            "ma10": row["MA10"],
            "ma20": row["MA20"],
            "bias": (row["Close"] - row["MA20"]) / row["MA20"] * 100,
            "volume": row["Volume"] / 1000,
            "trust_streak": row.get("trust_streak", 0)
        }

        # ======================
        # 沒持股 → 找進場
        # ======================
        if position is None:
            if check_entry(data):
                position = {
                    "entry_price": data["price"],
                    "highest_price": data["price"]
                }
            continue

        # ======================
        # 有持股 → 檢查出場
        # ======================
        exit_signal = check_exit(position, data)

        if exit_signal:
            pnl = (data["price"] - position["entry_price"]) / position["entry_price"]
            trades.append(pnl)
            position = None

    return trades
