# -*- coding: utf-8 -*-
"""
net_utils.py — 共用網路與快取工具（安全性優化版）

集中管理原本散落在 chips_provider / active_etf_holdings / fundamental_engine /
active_etf_official_sources / active_etf_source_probe / data_center 的重複程式碼：

1. build_session()      : 共用 requests.Session（含 retry 與台灣常用 headers）
2. smart_get()          : 先用 SSL 驗證連線；僅在該主機憑證驗證失敗時，
                          才針對「該主機」降級為不驗證，並記錄警告。
                          取代原本全面 verify=False 的做法。
3. maybe_cache_data()   : Streamlit 環境下套 st.cache_data，
                          GitHub Actions / CLI 環境下自動略過。

環境變數：
- ALLOW_INSECURE_SSL=1  : 完全恢復舊行為（所有請求不驗證憑證）。
                          僅供除錯用，不建議常態開啟。
"""

import os
import warnings
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None

try:
    import urllib3
except Exception:  # pragma: no cover
    urllib3 = None

try:
    import streamlit as st
except Exception:  # pragma: no cover - GitHub Actions / CLI 環境
    st = None


ALLOW_INSECURE_SSL = str(os.environ.get("ALLOW_INSECURE_SSL", "")).strip() in {"1", "true", "TRUE", "yes"}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 記錄哪些主機憑證驗證失敗過（本 process 生命週期內只警告一次、只降級該主機）
_INSECURE_HOSTS = set()


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def build_session(with_retry: bool = True, extra_headers: Optional[dict] = None) -> requests.Session:
    """建立共用 Session。with_retry=True 時對 429/5xx 自動重試 3 次。"""
    s = requests.Session()
    if with_retry and Retry is not None:
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
    s.headers.update(DEFAULT_HEADERS)
    if extra_headers:
        s.headers.update(extra_headers)
    return s


def smart_get(url: str, session: Optional[requests.Session] = None, timeout: int = 20, **kwargs) -> requests.Response:
    """安全優先的 GET：

    1. 預設 verify=True 正常驗證憑證。
    2. 若該主機憑證驗證失敗（部分政府/投信網站憑證鏈不完整），
       僅針對該主機降級 verify=False 重試一次，並發出一次性警告。
    3. ALLOW_INSECURE_SSL=1 時恢復舊有全域不驗證行為。
    """
    sess = session or build_session()
    host = _host_of(url)

    if ALLOW_INSECURE_SSL or host in _INSECURE_HOSTS:
        if urllib3 is not None:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return sess.get(url, timeout=timeout, verify=False, **kwargs)

    try:
        return sess.get(url, timeout=timeout, verify=True, **kwargs)
    except requests.exceptions.SSLError:
        _INSECURE_HOSTS.add(host)
        warnings.warn(f"[net_utils] {host} 憑證驗證失敗，該主機已降級為不驗證連線（僅本次執行期間）。")
        if urllib3 is not None:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return sess.get(url, timeout=timeout, verify=False, **kwargs)


def maybe_cache_data(ttl=1800, show_spinner=False):
    """Streamlit 環境下套 st.cache_data；CLI / GitHub Actions 環境自動跳過。"""
    def deco(fn):
        if st is not None:
            try:
                return st.cache_data(ttl=ttl, show_spinner=show_spinner)(fn)
            except Exception:
                return fn
        return fn
    return deco
