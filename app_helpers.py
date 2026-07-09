# -*- coding: utf-8 -*-
"""
app_helpers.py — 從 app.py 抽出的純工具函式（結構優化）

這些函式不依賴任何全域狀態（COLORS / session_state），
抽出後 app.py 每次 rerun 不需重新定義，也方便其他模組重用與測試。
"""

import re
from datetime import datetime

import numpy as np
import pandas as pd


def format_lots(shares):
    lots = int(shares) / 1000
    if lots <= 0:
        return "0"
    return f"{lots:.1f}".rstrip("0").rstrip(".")


def _row_text(row, possible_keys, exclude_keys=None, default=""):
    exclude_keys = exclude_keys or []
    for col in row.index:
        c = str(col).strip()
        if any(x in c for x in exclude_keys):
            continue
        if c in possible_keys or any(k in c for k in possible_keys):
            val = row[col]
            if pd.notna(val) and str(val).strip() not in ["", "nan", "NaN", "None"]:
                return str(val).strip()
    return default


def _to_float_safe(v, default=0.0):
    try:
        raw = str(v).replace(",", "").strip()
        if raw in ["", "nan", "NaN", "None"]:
            return default
        m = re.search(r"-?\d+\.?\d*", raw)
        return float(m.group(0)) if m else default
    except Exception:
        return default


def _parse_tw_date_safe(v):
    """解析 AAR / 持股表常見日期格式：YYYY-MM-DD、YYYY/MM/DD、民國年、MM-DD。失敗回傳 NaT。"""
    try:
        raw = str(v).strip().replace("/", "-").replace(".", "-")
        if raw in ["", "nan", "NaN", "None"]:
            return pd.NaT
        parts = raw.split("-")
        if len(parts) == 2:
            return pd.to_datetime(f"{datetime.now().year}-{parts[0]}-{parts[1]}", errors="coerce")
        if len(parts) == 3:
            y = int(float(parts[0]))
            if y < 1911:
                y += 1911
            return pd.to_datetime(f"{y}-{parts[1]}-{parts[2]}", errors="coerce")
        return pd.to_datetime(raw, errors="coerce")
    except Exception:
        return pd.NaT


def _clean_stock_code(x):
    """把候選股代號標準化；排除 NaN、0、空字串、ETF。

    這層是為了避免法人快取或 CSV 欄位被 pandas 轉成 NaN/0，
    造成 S/A/B 掃描拿 NaN、0 去抓 K 線，整批顯示無技術資料。
    """
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    s = str(x).strip().upper()
    if not s or s in {"NAN", "NONE", "NULL", "0", "0.0", "-"}:
        return ""
    s = s.replace(".TW", "").replace(".TWO", "")
    if s.endswith(".0"):
        s = s[:-2]
    # 有些來源會把代號存成 2330 台積電，先取第一段。
    s = s.split()[0].strip()
    if s.isdigit() and len(s) == 4 and not s.startswith("00"):
        return s
    return ""


def _valid_stock_codes(values):
    out = []
    seen = set()
    for v in values or []:
        c = _clean_stock_code(v)
        if c and c not in seen:
            out.append(c)
            seen.add(c)
    return out


def _macro_to_float(val):
    try:
        return float(str(val).replace("%", "").replace(",", "").strip())
    except Exception:
        return np.nan
