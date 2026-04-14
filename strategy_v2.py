import pandas as pd

# ======================
# 📌 進場條件（更精準）
# ======================
def check_entry(data):
    cond1 = data["trust_streak"] >= 2          # 投信連買
    cond2 = data["price"] > data["ma20"]       # 站上趨勢
    cond3 = data["price"] > data["ma5"]        # 有動能
    cond4 = data["bias"] < 8                   # 還沒過熱
    cond5 = data["volume"] > 1000              # 有量

    return all([cond1, cond2, cond3, cond4, cond5])


# ======================
# 📌 持有邏輯（解決你早賣）
# ======================
def check_hold(position, data):
    # 只要還在 MA10 上 → 不賣
    if data["price"] > data["ma10"]:
        return True
    return False


# ======================
# 📌 出場邏輯（關鍵升級）
# ======================
def check_exit(position, data):
    entry_price = position["entry_price"]
    highest = position["highest_price"]

    current = data["price"]

    # 更新最高價
    highest = max(highest, current)
    position["highest_price"] = highest

    profit = (current - entry_price) / entry_price * 100
    drawdown = (current - highest) / highest * 100

    # ❗ 核心：移動停利
    if profit > 8 and drawdown < -3:
        return "🔥 停利出場"

    # ❗ 防守
    if current < data["ma10"]:
        return "❌ 跌破趨勢"

    return None
