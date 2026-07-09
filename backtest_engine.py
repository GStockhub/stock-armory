import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st

from data_center import safe_download


@dataclass
class BacktestConfig:
    initial_capital: float = 200000.0
    total_exposure_pct: float = 0.60
    single_position_pct: float = 0.15
    max_positions: int = 4
    max_new_positions_per_day: int = 2
    max_hold_bars: int = 10
    gap_limit_pct: float = 4.5
    take_half_pct: float = 5.5
    fee_discount: float = 1.0
    slippage_pct: float = 0.0015
    allow_odd_lot: bool = True
    odd_lot_entry_delay: bool = False
    # 參數掃描用：進場訊號過濾（0 / 全級 = 維持原行為）
    min_entry_score: float = 0.0
    allowed_tiers: Tuple[str, ...] = ("S", "A", "B")


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def _prepare_df(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c not in df.columns:
            df[c] = 0
        df[c] = _num(df[c])
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].replace(0, np.nan).ffill().fillna(1000)
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA10"] = df["Close"].rolling(10).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["VolMA5"] = df["Volume"].rolling(5).mean()
    df["PrevClose"] = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - df["PrevClose"]).abs()
    tr3 = (df["Low"] - df["PrevClose"]).abs()
    df["ATR"] = np.maximum(tr1, np.maximum(tr2, tr3)).rolling(14).mean()
    df["RSI"] = _rsi(df["Close"])
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = macd - signal
    df["ClosePos"] = np.where((df["High"] - df["Low"]) > 0, (df["Close"] - df["Low"]) / (df["High"] - df["Low"]), 0.5)
    df["Bias20"] = (df["Close"] - df["MA20"]) / df["MA20"] * 100
    return df.dropna(subset=["MA5", "MA10", "MA20", "ATR"])


def _signal_score(row: pd.Series) -> Tuple[bool, float, str, str]:
    close = float(row["Close"])
    ma5 = float(row["MA5"])
    ma10 = float(row["MA10"])
    ma20 = float(row["MA20"])
    vol = float(row["Volume"])
    vol5 = float(row["VolMA5"]) if pd.notna(row["VolMA5"]) and row["VolMA5"] > 0 else vol
    rsi = float(row.get("RSI", 50))
    bias = float(row.get("Bias20", 0))
    close_pos = float(row.get("ClosePos", 0.5))

    trend_signal = close > ma5 > ma10 > ma20 and close_pos >= 0.55 and vol >= vol5 * 0.8
    pullback_signal = close >= ma10 and close <= ma5 * 1.015 and close > row["Open"] and vol >= vol5 * 0.65
    if not (trend_signal or pullback_signal):
        return False, 0.0, "", ""

    score = 50.0
    score += 12 if trend_signal else 0
    score += 10 if pullback_signal else 0
    score += min(max((close_pos - 0.5) * 25, -8), 12)
    score += min(max((vol / vol5 - 1) * 10, -8), 12) if vol5 > 0 else 0
    if 50 <= rsi <= 70:
        score += 8
    elif rsi > 75:
        score -= 12
    if bias > 8:
        score -= (bias - 8) * 2.5
    elif 0 <= bias <= 5:
        score += 6
    tactic = "突破" if trend_signal else "回踩"
    tier = "S" if score >= 72 else ("A" if score >= 62 else "B")
    return True, round(score, 2), tier, tactic


def _sell_value(price: float, shares: int, fee_discount: float, slippage_pct: float, sid: str) -> float:
    tax_rate = 0.001 if str(sid).startswith("00") else 0.003
    fee_rate = 0.001425 * fee_discount
    px = price * (1 - slippage_pct)
    gross = px * shares
    return gross * (1 - fee_rate - tax_rate)


def _buy_cost(price: float, shares: int, fee_discount: float, slippage_pct: float) -> float:
    fee_rate = 0.001425 * fee_discount
    px = price * (1 + slippage_pct)
    gross = px * shares
    return gross * (1 + fee_rate)


def _position_size(price: float, equity: float, cash: float, exposure_room: float, cfg: BacktestConfig) -> int:
    budget = min(equity * cfg.single_position_pct, cash, exposure_room)
    if budget <= 0 or price <= 0:
        return 0
    board_lot_cost = price * 1000
    if board_lot_cost <= budget:
        return int(math.floor(budget / board_lot_cost) * 1000)
    if cfg.allow_odd_lot:
        return int(math.floor(budget / price))
    return 0


@st.cache_data(ttl=1800, show_spinner=False)
def load_backtest_data(symbols: Tuple[str, ...], fm_token: Optional[str], period: str = "1y") -> Dict[str, pd.DataFrame]:
    data = {}
    for sid in symbols:
        try:
            raw = safe_download(str(sid), fm_token, period=period)
            if raw is not None and not raw.empty:
                prepared = _prepare_df(raw)
                if len(prepared) >= 35:
                    data[str(sid)] = prepared
        except Exception:
            continue
    return data


def run_portfolio_backtest(
    symbols: List[str],
    name_map: Optional[Dict[str, str]] = None,
    fm_token: Optional[str] = None,
    period: str = "1y",
    config: Optional[BacktestConfig] = None,
):
    cfg = config or BacktestConfig()
    clean_symbols = tuple(dict.fromkeys([str(s).strip() for s in symbols if str(s).strip()]))
    if not clean_symbols:
        return _empty_result("沒有可回測的股票代號。")

    data = load_backtest_data(clean_symbols, fm_token, period=period)
    if not data:
        return _empty_result("歷史報價不足或資料源暫時無法回應。")

    all_dates = sorted(set().union(*[set(df.index) for df in data.values()]))
    if len(all_dates) < 40:
        return _empty_result("共同交易日不足，無法產生有效回測。")

    cash = float(cfg.initial_capital)
    positions = {}
    trades = []
    equity_rows = []
    pending_signals = {}

    for current_date in all_dates:
        # 1) 先處理持股出場與權益估值
        position_value = 0.0
        for sid in list(positions.keys()):
            pos = positions[sid]
            df = data.get(sid)
            if df is None or current_date not in df.index:
                continue
            row = df.loc[current_date]
            close = float(row["Close"])
            high = float(row["High"])
            ma5 = float(row["MA5"])
            ma10 = float(row["MA10"])
            atr = float(row["ATR"])
            stop = max(float(pos["stop"]), ma10, float(pos["entry_price"]) - 1.5 * atr)
            entry = float(pos["entry_price"])
            shares = int(pos["shares"])
            exit_reason = None
            exit_shares = 0
            exit_price = close

            if (not pos["sold_half"]) and high >= entry * (1 + cfg.take_half_pct / 100):
                exit_shares = max(1, shares // 2)
                exit_price = entry * (1 + cfg.take_half_pct / 100)
                cash += _sell_value(exit_price, exit_shares, cfg.fee_discount, cfg.slippage_pct, sid)
                pos["shares"] -= exit_shares
                pos["sold_half"] = True
                pos["realized"] += _sell_value(exit_price, exit_shares, cfg.fee_discount, cfg.slippage_pct, sid)
                trades.append(_trade_row(sid, name_map, pos, current_date, exit_price, exit_shares, "先出半", partial=True))

            shares = int(pos["shares"])
            holding_bars = int(pos.get("holding_bars", 0)) + 1
            pos["holding_bars"] = holding_bars
            if close < ma10 or close < stop:
                exit_reason = "破M10/ATR"
                exit_shares = shares
                exit_price = close
            elif pos["sold_half"] and close < ma5:
                exit_reason = "半倉破M5"
                exit_shares = shares
                exit_price = ma5
            elif holding_bars >= cfg.max_hold_bars:
                exit_reason = "時間到"
                exit_shares = shares
                exit_price = close

            if exit_reason and exit_shares > 0:
                cash += _sell_value(exit_price, exit_shares, cfg.fee_discount, cfg.slippage_pct, sid)
                pos["shares"] -= exit_shares
                trades.append(_trade_row(sid, name_map, pos, current_date, exit_price, exit_shares, exit_reason, partial=False))
                if pos["shares"] <= 0:
                    del positions[sid]
            else:
                position_value += shares * close

        equity = cash + position_value

        # 2) 依照前一日訊號，今天開盤進場
        candidates = pending_signals.pop(current_date, [])
        if candidates:
            candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
            new_count = 0
            current_exposure = sum(int(p["shares"]) * float(p["last_price"]) for p in positions.values())
            exposure_room = max(equity * cfg.total_exposure_pct - current_exposure, 0)
            for sig in candidates:
                if new_count >= cfg.max_new_positions_per_day or len(positions) >= cfg.max_positions:
                    break
                sid = sig["sid"]
                if sid in positions:
                    continue
                df = data[sid]
                if current_date not in df.index:
                    continue
                row = df.loc[current_date]
                open_p = float(row["Open"])
                prev_close = float(sig["prev_close"])
                gap_pct = (open_p - prev_close) / prev_close * 100 if prev_close > 0 else 0
                if gap_pct > cfg.gap_limit_pct:
                    continue
                shares = _position_size(open_p, equity, cash, exposure_room, cfg)
                if shares <= 0:
                    continue
                cost = _buy_cost(open_p, shares, cfg.fee_discount, cfg.slippage_pct)
                if cost > cash:
                    continue
                cash -= cost
                positions[sid] = {
                    "sid": sid,
                    "entry_date": current_date,
                    "entry_price": open_p * (1 + cfg.slippage_pct),
                    "shares": shares,
                    "initial_shares": shares,
                    "cost": cost,
                    "stop": max(float(sig["ma10"]), open_p * 0.97, open_p - 1.5 * float(sig["atr"])),
                    "sold_half": False,
                    "tier": sig["tier"],
                    "tactic": sig["tactic"],
                    "score": sig["score"],
                    "holding_bars": 0,
                    "realized": 0.0,
                    "last_price": open_p,
                }
                exposure_room -= shares * open_p
                new_count += 1

        # 3) 產生明日待執行訊號
        next_idx_signals = []
        for sid, df in data.items():
            if sid in positions or current_date not in df.index:
                continue
            loc = df.index.get_loc(current_date)
            if isinstance(loc, slice) or loc + 1 >= len(df):
                continue
            row = df.iloc[loc]
            ok, score, tier, tactic = _signal_score(row)
            if not ok:
                continue
            if score < float(cfg.min_entry_score) or tier not in cfg.allowed_tiers:
                continue
            next_date = df.index[loc + 1]
            next_idx_signals.append((next_date, {
                "sid": sid,
                "score": score,
                "tier": tier,
                "tactic": tactic,
                "prev_close": float(row["Close"]),
                "ma10": float(row["MA10"]),
                "atr": float(row["ATR"]),
            }))
        for nd, sig in next_idx_signals:
            pending_signals.setdefault(nd, []).append(sig)

        # 4) 更新持股收盤價與 equity curve
        pos_value = 0.0
        for sid, pos in positions.items():
            df = data.get(sid)
            if df is not None and current_date in df.index:
                pos["last_price"] = float(df.loc[current_date, "Close"])
            pos_value += int(pos["shares"]) * float(pos.get("last_price", pos["entry_price"]))
        equity_rows.append({"日期": current_date, "現金": cash, "持股市值": pos_value, "總資產": cash + pos_value, "持股檔數": len(positions)})

    # 強制平倉未結束持股，讓統計完整
    final_date = all_dates[-1]
    for sid, pos in list(positions.items()):
        df = data.get(sid)
        if df is not None and final_date in df.index:
            price = float(df.loc[final_date, "Close"])
            trades.append(_trade_row(sid, name_map, pos, final_date, price, int(pos["shares"]), "期末平倉", partial=False))
    trades_df = pd.DataFrame(trades)
    curve_df = pd.DataFrame(equity_rows)
    if not curve_df.empty:
        curve_df["日期"] = pd.to_datetime(curve_df["日期"])

    return _summary_result(cfg.initial_capital, curve_df, trades_df, len(data))


def _trade_row(sid, name_map, pos, exit_date, exit_price, shares, reason, partial=False):
    entry_cost_per_share = pos["cost"] / max(int(pos["initial_shares"]), 1)
    pnl = (exit_price * shares) - (entry_cost_per_share * shares)
    ret = pnl / (entry_cost_per_share * shares) * 100 if entry_cost_per_share > 0 else 0
    return {
        "代號": sid,
        "名稱": (name_map or {}).get(sid, sid),
        "進場日": pd.to_datetime(pos["entry_date"]).strftime("%Y-%m-%d"),
        "出場日": pd.to_datetime(exit_date).strftime("%Y-%m-%d"),
        "分級": pos.get("tier", ""),
        "戰術": pos.get("tactic", ""),
        "進場價": round(float(pos["entry_price"]), 2),
        "出場價": round(float(exit_price), 2),
        "股數": int(shares),
        "報酬率(%)": round(ret, 2),
        "估算損益": round(pnl, 0),
        "出場原因": reason,
        "部分出場": "是" if partial else "否",
    }


def _empty_result(msg: str):
    return {
        "ok": False,
        "message": msg,
        "summary": {},
        "equity_curve": pd.DataFrame(),
        "trades": pd.DataFrame(),
        "tier_stats": pd.DataFrame(),
    }


def _summary_result(initial_capital: float, curve_df: pd.DataFrame, trades_df: pd.DataFrame, universe_count: int):
    if curve_df.empty:
        return _empty_result("沒有產生有效資金曲線。")
    final_equity = float(curve_df["總資產"].iloc[-1])
    total_return = (final_equity / initial_capital - 1) * 100
    rolling_max = curve_df["總資產"].cummax()
    drawdown = (curve_df["總資產"] / rolling_max - 1) * 100
    max_dd = float(drawdown.min()) if not drawdown.empty else 0.0
    closed = trades_df[trades_df["部分出場"] == "否"].copy() if not trades_df.empty else pd.DataFrame()
    win_rate = (closed["報酬率(%)"] > 0).mean() * 100 if not closed.empty else 0.0
    avg_ret = closed["報酬率(%)"].mean() if not closed.empty else 0.0
    avg_hold = 0
    if not closed.empty:
        avg_hold = (pd.to_datetime(closed["出場日"]) - pd.to_datetime(closed["進場日"])).dt.days.mean()
    tier_stats = pd.DataFrame()
    if not closed.empty and "分級" in closed.columns:
        tier_stats = closed.groupby("分級").agg(
            筆數=("代號", "count"),
            勝率=("報酬率(%)", lambda x: (x > 0).mean() * 100),
            平均報酬=("報酬率(%)", "mean"),
            總損益=("估算損益", "sum"),
        ).reset_index()
    return {
        "ok": True,
        "message": "回測完成。此為以歷史日K與資金限制模擬的近似結果，仍不等於未來報酬。",
        "summary": {
            "初始本金": initial_capital,
            "最終資金": final_equity,
            "總報酬(%)": total_return,
            "最大回撤(%)": max_dd,
            "勝率(%)": win_rate,
            "平均單筆報酬(%)": avg_ret,
            "平均持有天數": avg_hold,
            "交易筆數": int(len(closed)),
            "回測股票數": int(universe_count),
        },
        "equity_curve": curve_df,
        "trades": trades_df,
        "tier_stats": tier_stats,
    }
