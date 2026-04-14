import yfinance as yf
import pandas as pd

from strategy_v2 import check_entry, check_exit
from backtest import run_backtest

# 抓一檔你熟的股票
stock_id = "2330"

df = yf.Ticker(f"{stock_id}.TW").history(period="1y")

# 加均線
df["MA5"] = df["Close"].rolling(5).mean()
df["MA10"] = df["Close"].rolling(10).mean()
df["MA20"] = df["Close"].rolling(20).mean()

# 假資料（先模擬投信）
df["trust_streak"] = 3

# 跑回測
trades = run_backtest(df)

# 統計結果
if trades:
    avg = sum(trades) / len(trades)
    win_rate = len([t for t in trades if t > 0]) / len(trades)

    print("交易次數:", len(trades))
    print("勝率:", round(win_rate * 100, 2), "%")
    print("平均報酬:", round(avg * 100, 2), "%")
else:
    print("沒有交易")
