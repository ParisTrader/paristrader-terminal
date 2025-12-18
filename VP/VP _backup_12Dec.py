"""
成交量分布图（Volume Profile）仪表板生成脚本

功能概述：
1. 通过 yfinance 拉取多个期货与股票标的的 1 分钟行情，自动处理盘前/盘后数据并限制在最新可用区间内。
2. 合并最近 N 个交易日（含跨日周日数据），去重时间戳并剔除周六记录，确保样本连续且干净。
3. 以 GC 为参考统一分箱粒度与显示范围，对各标的计算 Volume Profile 直方图。
4. 识别成交量峰值、计算 POC（Point of Control）与价值区域，并根据现价限制可视窗口，保证重点信息可见。
5. 输出 Plotly 图形与峰值表格数据，构建带纵向滑块的交互式 HTML 仪表板，可在多个标的间切换并同步滚动价格区间。
6. 打印处理的日期区间与各标的的最新时间戳，最终生成 `volume_profile_dashboard.html` 文件。

主要功能模块：
- `fetch_1m_batch`：分段抓取 1 分钟行情并过滤无效时段。
- `process_ticker`：整理单个标的的日历范围、交易日筛选及数据清洗。
- `get_bin_size`：依据标的 tick 大小计算统一粒度的分箱宽度。
- `plot_volume_profile`：生成 Volume Profile、峰值列表和滑块所需的窗口元数据。
- 主流程：按 GC → 其他标的顺序处理结果，构建 HTML、绑定 Plotly 图表与表格联动。

技术特点：
- GC 参考标的驱动的分箱与展示区间对齐机制。
- 峰值识别：局部极值筛选 → 窗口去重 → 强度阈值 → 上下平衡。
- 纵向滑块控制的价格窗口 + 表格自动高亮现价与峰值并居中显示。
- 输出阶段转换为北京时间，便于国内时区回溯数据 freshness。
"""

import yfinance as yf
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, timezone
import json
import warnings
import io
import time
import re
import math
from contextlib import redirect_stdout, redirect_stderr
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os

today = datetime.now().date()
us_cal = USFederalHolidayCalendar()
N_DAYS = 20
LOOKBACK_NATURAL_DAYS = 40

warnings.filterwarnings(
    "ignore",
    message=r".*no price data found.*",
    category=UserWarning,
    module="yfinance"
)

end_date = today + timedelta(days=1)
start_date = (today - timedelta(days=LOOKBACK_NATURAL_DAYS))

# Yahoo 1m only supports roughly the most recent 30 days; clamp the start date to this range
earliest_1m_date = (datetime.now() - timedelta(days=29)).date()
if start_date < earliest_1m_date:
    start_date = earliest_1m_date

def fetch_1m_batch(ticker, start, end):
    try:
        with io.StringIO() as buf_out, io.StringIO() as buf_err:
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                df = ticker.history(start=start, end=end, interval="1m")

        if df.empty:
            return pd.DataFrame()

        # 保持 UTC 时区，不转换为纽约时区，不移除时区信息
        if df.index.tzinfo is None:
            # 如果数据没有时区信息，假设是UTC并添加时区信息
            df.index = df.index.tz_localize('UTC')
        else:
            # 如果有时区信息，转换为UTC并保留时区信息
            df.index = df.index.tz_convert('UTC')

        return df.dropna()
    except Exception:
        return pd.DataFrame()

CRYPTO_SYMBOL_MAP = {
    'BTC-USD': 'BTCUSDT',
    'ETH-USD': 'ETHUSDT',
}

CRYPTO_DISPLAY_NAMES = {
    'BTC-USD': 'BTCUSD',
    'ETH-USD': 'ETHUSD',
}

DERIBIT_SYMBOL_MAP = {
    'BTC-USD': 'BTC-PERPETUAL',
    'ETH-USD': 'ETH-PERPETUAL',
}

BINANCE_ENDPOINTS = [
    "https://api.binance.com",
    "https://data.binance.com",
    "https://data-api.binance.vision",
]

BINANCE_PROXY_ADDRESS = os.getenv("BINANCE_PROXY_ADDRESS", "").strip()
BINANCE_PROXY_TYPE = os.getenv("BINANCE_PROXY_TYPE", "http").strip().lower()

_binance_session = requests.Session()
_binance_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )
})

_binance_retry = Retry(
    total=5,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)

_binance_session.mount("https://", HTTPAdapter(max_retries=_binance_retry))

if BINANCE_PROXY_ADDRESS:
    proxy_prefix = "socks5" if BINANCE_PROXY_TYPE.startswith("socks5") else BINANCE_PROXY_TYPE or "http"
    proxy_uri = f"{proxy_prefix}://{BINANCE_PROXY_ADDRESS}"
    _binance_session.proxies.update({
        "http": proxy_uri,
        "https": proxy_uri,
    })


def fetch_binance_klines(symbol_code, start_dt, end_dt, interval="1m"):
    """Fetch 1m klines for the given symbol from Binance."""
    pair = CRYPTO_SYMBOL_MAP.get(symbol_code)
    if pair is None:
        return pd.DataFrame()

    limit = 1000
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    current_ms = start_ms
    rows = []

    while current_ms < end_ms:
        params = {
            "symbol": pair,
            "interval": interval,
            "limit": limit,
            "startTime": current_ms,
            "endTime": min(current_ms + limit * 60 * 1000 - 1, end_ms),
        }

        data = None
        last_exc = None
        for base_url in BINANCE_ENDPOINTS:
            try:
                resp = _binance_session.get(f"{base_url}/api/v3/klines", params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.HTTPError as http_exc:
                status_code = getattr(http_exc.response, "status_code", None)
                if status_code == 451 and not BINANCE_PROXY_ADDRESS:
                    warnings.warn(
                        "Binance returned HTTP 451 (geo-block). "
                        "Configure a proxy via BINANCE_PROXY_ADDRESS if access is restricted."
                    )
                last_exc = http_exc
            except Exception as exc:
                last_exc = exc

        if data is None:
            warnings.warn(f"Binance klines request failed for {symbol_code}: {last_exc}")
            break

        if not data:
            break

        for entry in data:
            rows.append({
                "OpenTime": int(entry[0]),
                "Open": float(entry[1]),
                "High": float(entry[2]),
                "Low": float(entry[3]),
                "Close": float(entry[4]),
                "Volume": float(entry[5]),
                "CloseTime": int(entry[6]),
            })

        last_close = int(data[-1][6])
        next_start = last_close + 1
        if next_start <= current_ms:
            break
        current_ms = next_start

        if len(data) < limit:
            break

        time.sleep(0.2)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["OpenTime"]).sort_values("OpenTime")
    df["OpenTime"] = pd.to_datetime(df["OpenTime"], unit="ms", utc=True)
    df.set_index("OpenTime", inplace=True)
    df.index = df.index.tz_convert('America/New_York').tz_localize(None)

    return df[["Open", "High", "Low", "Close", "Volume"]]


DERIBIT_BASE_URL = "https://www.deribit.com/api/v2"

_deribit_session = requests.Session()
_deribit_retry = Retry(
    total=5,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
_deribit_session.mount("https://", HTTPAdapter(max_retries=_deribit_retry))


def fetch_deribit_chart(symbol_code, start_dt, end_dt, resolution="1"):
    instrument_name = DERIBIT_SYMBOL_MAP.get(symbol_code)
    if not instrument_name:
        return pd.DataFrame()

    params = {
        "instrument_name": instrument_name,
        "start_timestamp": int(start_dt.timestamp() * 1000),
        "end_timestamp": int(end_dt.timestamp() * 1000),
        "resolution": resolution,
    }

    try:
        resp = _deribit_session.get(f"{DERIBIT_BASE_URL}/public/get_tradingview_chart_data", params=params, timeout=15)
        resp.raise_for_status()
        result = resp.json().get("result", {})
    except Exception as exc:
        warnings.warn(f"Deribit chart request failed for {symbol_code}: {exc}")
        return pd.DataFrame()

    ticks = result.get("ticks")
    if not ticks:
        return pd.DataFrame()

    columns = ["open", "high", "low", "close", "volume"]
    data_dict = {}
    for col in columns:
        arr = result.get(col)
        if arr is None or len(arr) != len(ticks):
            return pd.DataFrame()
        data_dict[col.title()] = arr

    df = pd.DataFrame(data_dict, index=pd.to_datetime(ticks, unit="ms", utc=True))
    df = df.astype(float)
    df.index = df.index.tz_convert('America/New_York').tz_localize(None)
    df.rename(columns={"Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume"}, inplace=True)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_crypto_1m(symbol_code, start_date, end_date):
    """Fetch 1m OHLCV data for crypto symbols using Binance klines."""
    try:
        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)

        df_binance = fetch_binance_klines(symbol_code, start_dt, end_dt, interval="1m")
        if not df_binance.empty:
            return df_binance

        df_deribit = fetch_deribit_chart(symbol_code, start_dt, end_dt, resolution="1")
        if not df_deribit.empty:
            return df_deribit

        warnings.warn(f"No crypto data retrieved for {symbol_code} from available sources.")
        return pd.DataFrame()
    except Exception as exc:
        warnings.warn(f"Failed to fetch crypto data for {symbol_code}: {exc}")
        return pd.DataFrame()

def load_hsi_from_excel(contract_code, excel_path="data/hsi_data.xlsx", N_DAYS=20):
    """
    从 Excel 文件读取 HSI 合约数据并转换为标准格式。
    
    Args:
        contract_code: 合约代码，如 'HSI2511' 或 'HSI2512'
        excel_path: Excel 文件路径
        N_DAYS: 需要的交易日数量
    
    Returns:
        tuple: (data_20d, name, data_20d_dates) 或 None
            - data_20d: DataFrame with 'Close' and 'Volume' columns, indexed by datetime
            - name: 标的名称
            - data_20d_dates: 交易日列表
    """
    try:
        # 读取 Excel 工作表
        df = pd.read_excel(excel_path, sheet_name=contract_code)
        
        if df.empty:
            return None
        
        # 确保必要的列存在
        required_cols = ['timestamp', 'close_price', 'minute_volume']
        if not all(col in df.columns for col in required_cols):
            print(f"Warning: {contract_code} sheet missing required columns. Found: {df.columns.tolist()}")
            return None
        
        # 将 timestamp 转换为 datetime 并设置为索引
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # 重命名列以匹配标准格式
        df = df.rename(columns={
            'close_price': 'Close',
            'minute_volume': 'Volume'
        })
        
        # 设置索引
        df = df.set_index('timestamp')
        
        # 去重时间戳
        duplicate_timestamps = df.index.duplicated()
        if duplicate_timestamps.any():
            # 保留最后一个
            df = df[~df.index.duplicated(keep='last')]
        
        # 移除周末数据（周六、周日）
        not_weekend_mask = df.index.weekday < 5
        df = df[not_weekend_mask].copy()
        
        if df.empty:
            return None
        
        # 获取所有交易日
        all_dates = sorted(pd.Series(df.index.date).unique())
        all_trading_dates = [d for d in all_dates]  # 移除 d <= today 限制，允许未来日期
        
        # 选择最近 N_DAYS 个交易日
        if len(all_trading_dates) <= N_DAYS:
            selected_trading_days = all_trading_dates
        else:
            selected_trading_days = all_trading_dates[-N_DAYS:]
        
        if not selected_trading_days:
            return None
        
        natural_start = min(selected_trading_days)
        natural_end = max(selected_trading_days)
        
        # 包含范围内的周日数据
        sundays_in_range = [
            d for d in all_dates
            if pd.Timestamp(d).weekday() == 6 and natural_start <= d <= natural_end
        ]
        selected_dates_set = set(selected_trading_days) | set(sundays_in_range)
        
        # 筛选数据
        mask = pd.Series([date in selected_dates_set for date in df.index.date], index=df.index)
        data_20d = df[['Close', 'Volume']][mask].copy()
        
        if data_20d.empty:
            return None
        
        data_20d_dates = sorted(pd.Series(data_20d.index.date).unique())
        name = contract_code
        
        return data_20d, name, data_20d_dates
        
    except Exception as e:
        print(f"Error loading {contract_code} from Excel: {e}")
        return None


def process_ticker(ticker_symbol, start_date, end_date, N_DAYS):
    """Process the volume profile for a single symbol."""
    is_crypto = ticker_symbol in CRYPTO_SYMBOL_MAP
    name = CRYPTO_DISPLAY_NAMES.get(ticker_symbol, ticker_symbol.split('=')[0])

    if is_crypto:
        all_data = fetch_crypto_1m(ticker_symbol, start_date, end_date)
    else:
        ticker = yf.Ticker(ticker_symbol)
        all_data = pd.DataFrame()
        current = start_date
        while current < end_date:
            batch_end = min(current + timedelta(days=7), end_date)
            batch = fetch_1m_batch(ticker, current, batch_end)
            if not batch.empty:
                all_data = pd.concat([all_data, batch])
            current = batch_end

    if all_data is None or all_data.empty:
        return None

    all_data = all_data.sort_index()
    all_data.index = pd.to_datetime(all_data.index)

    duplicate_timestamps = all_data.index.duplicated()
    if duplicate_timestamps.any():
        all_data = all_data[~duplicate_timestamps]

    if not is_crypto:
        not_saturday_mask = all_data.index.weekday != 5
        all_data = all_data[not_saturday_mask].copy()

    all_dates = sorted(pd.Series(all_data.index.date).unique())

    if is_crypto:
        all_trading_dates = [d for d in all_dates]  # 移除 d <= today 限制，允许未来日期
    else:
        all_trading_dates = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]  # 移除 d <= today 限制，允许未来日期

    if len(all_trading_dates) <= N_DAYS:
        selected_trading_days = all_trading_dates
    else:
        selected_trading_days = all_trading_dates[-N_DAYS:]

    if not selected_trading_days:
        return None

    natural_start = min(selected_trading_days)
    natural_end = max(selected_trading_days)

    if is_crypto:
        selected_dates_set = set(selected_trading_days)
    else:
        sundays_in_range = [
            d for d in all_dates
            if pd.Timestamp(d).weekday() == 6 and natural_start <= d <= natural_end
        ]
        selected_dates_set = set(selected_trading_days) | set(sundays_in_range)

    mask = pd.Series([date in selected_dates_set for date in all_data.index.date], index=all_data.index)
    data_20d = all_data[mask].copy()
    if data_20d.empty:
        return None

    data_20d_dates = sorted(pd.Series(data_20d.index.date).unique())

    return data_20d, name, data_20d_dates


def get_bin_size(ticker_name):
    """
    Compute an appropriate bin width based on the symbol name.
    True normalization: maintain the same relative granularity (identical ticks per bin) across symbols.
    
    Using GC as the reference:
    - GC bin width is 1.5 with a tick size of 0.1
    - GC relative granularity = 1.5 / 0.1 = 15 ticks per bin
    
    Other instruments keep the same relative granularity (15 ticks per bin):
    - bin width = tick_size × 15
    
    Tick sizes:
    - GC (gold futures): 0.1 USD/oz → bin_size = 1.5
    - SI (silver futures): 0.005 USD/oz → bin_size = 0.075
    - ES (E-mini S&P 500): 0.25 index points → bin_size = 3.75
    - NQ (E-mini Nasdaq 100): 0.25 index points → bin_size = 3.75
    - TSLA: 0.01 USD → bin_size = 0.15
    - AAPL: 0.01 USD → bin_size = 0.15
    - NVDA: 0.01 USD → bin_size = 0.15
    """
    GC_BIN_SIZE = 1.5
    GC_TICK_SIZE = 0.1
    GC_TICKS_PER_BIN = GC_BIN_SIZE / GC_TICK_SIZE
    
    tick_sizes = {
        'GC': 0.1,      # 黄金期货: 0.1 USD/oz
        'SI': 0.005,    # 白银期货: 0.005 USD/oz
        'ES': 0.25,
        'NQ': 0.25,
        'TSLA': 0.01,
        'AAPL': 0.01,
        'NVDA': 0.01,
        'CRS': 0.01,
        'BTCUSD': 1.0,
        'ETHUSD': 0.5,
        'HSI2511': 1.0,  # 恒生指数期货: 1.0 点
        'HSI2512': 1.0,  # 恒生指数期货: 1.0 点
    }
    
    tick_size = tick_sizes.get(ticker_name, GC_TICK_SIZE)
    bin_size = tick_size * GC_TICKS_PER_BIN
    
    return bin_size

def plot_volume_profile(data_20d, name, N_DAYS, gc_reference=None):
    """
    Plot a volume profile chart and return metadata for dynamic scrolling windows.
    """
    prices = data_20d['Close'].values
    volumes = data_20d['Volume'].values
    bin_size = get_bin_size(name)

    p_min = np.floor(prices.min() / bin_size) * bin_size
    p_max = np.ceil(prices.max() / bin_size) * bin_size
    price_bins = np.arange(p_min, p_max + bin_size, bin_size)

    hist, bin_edges = np.histogram(prices, bins=price_bins, weights=volumes)
    profile_price = (bin_edges[:-1] + bin_edges[1:]) / 2
    profile_vol = hist.astype(float)

    total_vol = profile_vol.sum()
    poc_idx = np.argmax(profile_vol)
    current_price = float(data_20d['Close'].iloc[-1])

    def find_local_maxima(prices_arr, vols_arr):
        candidates = []
        n = len(vols_arr)
        if n < 3:
            return candidates
        for i in range(1, n - 1):
            if vols_arr[i] >= vols_arr[i - 1] and vols_arr[i] >= vols_arr[i + 1]:
                candidates.append({
                    'idx': i,
                    'price': float(prices_arr[i]),
                    'volume': float(vols_arr[i])
                })
        return candidates

    def dedup_within_window(candidates, spot_price, window_size=6):
        if not candidates:
            return []
        candidates_sorted = sorted(candidates, key=lambda x: x['idx'])
        
        def sel_key(p):
            return (
                p['volume'],
                -abs(p['price'] - spot_price),
                p['price']
            )
        
        kept = []
        for candidate in candidates_sorted:
            conflicts = [peak for peak in kept if abs(candidate['idx'] - peak['idx']) < window_size]
            
            if not conflicts:
                kept.append(candidate)
            else:
                all_candidates = [candidate] + conflicts
                best = max(all_candidates, key=sel_key)
                
                for conflict_peak in conflicts:
                    kept.remove(conflict_peak)
                
                if best not in kept:
                    kept.append(best)
        
        kept = sorted(kept, key=lambda x: x['idx'])
        return kept

    def apply_strength_threshold(peaks, ratio=0.3):
        if not peaks:
            return []
        vmax = max(p['volume'] for p in peaks)
        thresh = ratio * vmax
        return [p for p in peaks if p['volume'] >= thresh]

    def balance_up_down(peaks, spot_price, max_allowed_diff: int = 10, x_target: int | None = None, y_target: int | None = None):
        peaks_up = [p for p in peaks if p['price'] > spot_price]
        peaks_dn = [p for p in peaks if p['price'] < spot_price]

        def removal_key_up(p):
            return (p['volume'], abs(p['price'] - spot_price), p['price'])

        def removal_key_dn(p):
            return (p['volume'], abs(p['price'] - spot_price), -p['price'])

        def remove_one(side: str):
            nonlocal peaks_up, peaks_dn
            if side == 'up' and peaks_up:
                victim = sorted(peaks_up, key=removal_key_up)[0]
                peaks_up.remove(victim)
            elif side == 'dn' and peaks_dn:
                victim = sorted(peaks_dn, key=removal_key_dn)[0]
                peaks_dn.remove(victim)

        if x_target is not None and len(peaks_up) > x_target:
            while len(peaks_up) > x_target:
                remove_one('up')
        if y_target is not None and len(peaks_dn) > y_target:
            while len(peaks_dn) > y_target:
                remove_one('dn')

        while abs(len(peaks_up) - len(peaks_dn)) > max_allowed_diff:
            if len(peaks_up) > len(peaks_dn):
                remove_one('up')
            else:
                remove_one('dn')
        return peaks_up, peaks_dn

    def has_near_peak(peaks_side, side, spot_idx, near_bins=40):
        """
        检查指定侧在spot近邻区内是否有峰
        
        Args:
            peaks_side: 一侧的峰列表
            side: 'up' 或 'dn'
            spot_idx: spot的分箱索引
            near_bins: 近邻区分箱数（默认40）
        
        Returns:
            bool: 如果近邻区有峰返回True，否则返回False
        """
        if side == 'up':
            return any(0 < (p['idx'] - spot_idx) <= near_bins for p in peaks_side)
        else:  # side == 'dn'
            return any(0 < (spot_idx - p['idx']) <= near_bins for p in peaks_side)

    def score_and_filter_peaks_side(peaks_side, spot_idx,
                                     max_dist_bins=40,
                                     alpha=1.0,
                                     lambda_=math.log(3.0),
                                     gamma=2.0,
                                     score_ratio=0.4,
                                     top_k=None,
                                     verbose=False):
        """
        对同一侧的峰集合进行综合得分计算和过滤
        
        Args:
            peaks_side: 一侧的峰列表（每个峰至少包含 'idx', 'price', 'volume'）
            spot_idx: spot的分箱索引
            max_dist_bins: 距离归一化的分箱上限（默认40）
            alpha: 成交量权重指数（默认1.0）
            lambda_: 距离衰减强度（默认log(3.0)）
            gamma: 距离的非线性指数（默认2.0）
            score_ratio: 得分阈值比例，仅保留得分 >= score_ratio * 该侧最高得分 的峰（默认0.4）
            top_k: 如果指定，选择得分最高的 top_k 个峰（优先于 score_ratio）
        
        Returns:
            list: 过滤后的峰列表（已移除临时的 'score' 字段）
        """
        if not peaks_side:
            return []

        # 计算该侧的最大成交量（用于归一化）
        vmax = max(p['volume'] for p in peaks_side)
        if vmax <= 0:
            # 若全部 volume 非正，则直接返回原峰集合
            return peaks_side

        # 为每个峰计算得分
        scored = []
        for p in peaks_side:
            # 1. 成交量归一化
            v_norm = p['volume'] / vmax

            # 2. 计算与spot的距离并归一化
            d = abs(p['idx'] - spot_idx)
            # 当距离 < max_dist_bins 时，归一化到 [0, 1)
            # 当距离 >= max_dist_bins 时，d_norm 继续增长，使惩罚随距离递增
            if d < max_dist_bins:
                d_norm = d / max_dist_bins
            else:
                # 距离 >= 40 bins 时，d_norm 从 1.0 开始递增
                # 使用分段函数：d_norm = 1.0 + (d - max_dist_bins) / max_dist_bins
                # 这样可以确保距离越远，d_norm 越大，惩罚越重
                d_norm = 1.0 + (d - max_dist_bins) / max_dist_bins

            # 3. 计算距离权重（指数 + 非线性增强）
            w = math.exp(-lambda_ * (d_norm ** gamma))

            # 4. 综合得分
            score = (v_norm ** alpha) * w

            # 复制峰字典并添加得分
            q = dict(p)
            q['score'] = float(score)
            q['v_norm'] = v_norm
            q['d'] = d
            q['w'] = w
            scored.append(q)

        # 找出最高得分并设置阈值
        s_max = max(q['score'] for q in scored)
        thresh = score_ratio * s_max

        # 按得分排序以便调试
        scored_sorted = sorted(scored, key=lambda x: x['score'], reverse=True)
        
        # 过滤逻辑：优先使用 top_k，否则使用阈值过滤
        if top_k is not None and top_k > 0:
            # 选择得分最高的 top_k 个峰
            filtered = scored_sorted[:top_k]
        else:
            # 使用阈值过滤：仅保留得分 >= 阈值的峰
            filtered = [q for q in scored if q['score'] >= thresh]
        
        # 调试日志：仅在 verbose=True 时输出
        # （已移除详细日志输出）
        
        # 移除临时的调试字段，避免影响后续逻辑
        for q in filtered:
            q.pop('score', None)
            q.pop('v_norm', None)
            q.pop('d', None)
            q.pop('w', None)
        
        return filtered

    def red_gradient_color(volume, vmax_peak):
        rgb = (204, 0, 0)
        hex_str = '#CC0000'
        return rgb, hex_str

    # --- Diagnostics: trace a specific peak through the pipeline (optional) ---
    TRACE_ENABLED = (name == 'BTC-USD')  # 仅对BTC跟踪
    TRACE_PEAK_PRICE = 99862.0
    TRACE_PEAK_VOL = 957.0
    trace_last_stage = None
    def is_target_peak(p, price_tol):
        return abs(p.get('price', -1e18) - TRACE_PEAK_PRICE) <= price_tol
    def trace_stage(peaks, stage, price_tol):
        nonlocal trace_last_stage
        if not TRACE_ENABLED:
            return
        existed = any(is_target_peak(p, price_tol) for p in peaks)
        if existed:
            trace_last_stage = stage
            print(f"[TRACE BTC] present after {stage}")
        else:
            print(f"[TRACE BTC] not present after {stage}")
    # --- End diagnostics setup ---

    candidate_peaks = find_local_maxima(profile_price, profile_vol)
    trace_stage(candidate_peaks, "local_maxima", bin_size/2)
    deduped_peaks = dedup_within_window(candidate_peaks, spot_price=current_price, window_size=6)
    if TRACE_ENABLED and any(is_target_peak(p, bin_size/2) for p in candidate_peaks) and not any(is_target_peak(p, bin_size/2) for p in deduped_peaks):
        print("[TRACE BTC] filtered by dedup_within_window")
    filtered_peaks = apply_strength_threshold(deduped_peaks, ratio=0.4)
    if TRACE_ENABLED and any(is_target_peak(p, bin_size/2) for p in deduped_peaks) and not any(is_target_peak(p, bin_size/2) for p in filtered_peaks):
        print("[TRACE BTC] filtered by strength_threshold")

    if not filtered_peaks:
        filtered_peaks = deduped_peaks
    if not filtered_peaks and len(profile_vol) >= 3:
        closest_idx = int(np.argmin(np.abs(profile_price - current_price)))
        filtered_peaks = [{
            'idx': closest_idx,
            'price': float(profile_price[closest_idx]),
            'volume': float(profile_vol[closest_idx])
        }]

    # 第一次上下侧平衡：用于综合判断是否需要重筛
    initial_peaks_up, initial_peaks_dn = balance_up_down(filtered_peaks, spot_price=current_price, max_allowed_diff=10)
    if TRACE_ENABLED:
        existed_before_balance = any(is_target_peak(p, bin_size/2) for p in filtered_peaks)
        existed_after_balance = any(is_target_peak(p, bin_size/2) for p in (initial_peaks_up + initial_peaks_dn))
        if existed_before_balance and not existed_after_balance:
            print("[TRACE BTC] filtered by initial balance_up_down")
    N_up_initial = len(initial_peaks_up)
    N_dn_initial = len(initial_peaks_dn)
    # 基于第一次平衡后的集合判断近邻是否缺峰
    spot_idx = int(np.argmin(np.abs(profile_price - current_price)))
    has_near_up = has_near_peak(initial_peaks_up, 'up', spot_idx, near_bins=40)
    has_near_dn = has_near_peak(initial_peaks_dn, 'dn', spot_idx, near_bins=40)
    need_rescore = (not has_near_up) or (not has_near_dn)
    if not need_rescore:
        # 不重筛：第一次平衡即为最终峰
        peaks_up, peaks_dn = initial_peaks_up, initial_peaks_dn
    else:
        # 需要重筛：回到 raw 峰（基于 filtered_peaks 划分）
        raw_up = [p for p in filtered_peaks if p['price'] > current_price]
        raw_dn = [p for p in filtered_peaks if p['price'] < current_price]
        # 还原距离惩罚为原参数：lambda=log(3.0), gamma=2.0
        lambda_base = math.log(3.0)
        gamma_base = 2.0
        # 仅对“峰数较多的一侧”做 top-k 筛选；少侧不变
        N_up_raw = len(raw_up)
        N_dn_raw = len(raw_dn)
        bigger_side = 'up' if N_up_raw >= N_dn_raw else 'dn'
        smaller_count = min(N_up_raw, N_dn_raw)
        target_big = smaller_count + 10
        if bigger_side == 'up' and N_up_raw > 0:
            rescored_up = score_and_filter_peaks_side(
                raw_up, spot_idx,
                max_dist_bins=40,
                alpha=1.0,
                lambda_=lambda_base,
                gamma=gamma_base,
                score_ratio=0.0,
                top_k=min(target_big, N_up_raw),
                verbose=False,
            )
            rescored_dn = raw_dn
        elif bigger_side == 'dn' and N_dn_raw > 0:
            rescored_dn = score_and_filter_peaks_side(
                raw_dn, spot_idx,
                max_dist_bins=40,
                alpha=1.0,
                lambda_=lambda_base,
                gamma=gamma_base,
                score_ratio=0.0,
                top_k=min(target_big, N_dn_raw),
                verbose=False,
            )
            rescored_up = raw_up
        else:
            # 边界：任一侧为空，直接合并原始
            rescored_up, rescored_dn = raw_up, raw_dn
        if TRACE_ENABLED:
            existed_before_rescore = any(is_target_peak(p, bin_size/2) for p in (raw_up + raw_dn))
            existed_after_rescore = any(is_target_peak(p, bin_size/2) for p in (rescored_up + rescored_dn))
            if existed_before_rescore and not existed_after_rescore:
                print("[TRACE BTC] filtered by rescore scoring (raw_up/raw_dn top-k bigger side)")
        peaks_for_balance = rescored_up + rescored_dn
        # 第二次上下侧平衡：最终峰
        peaks_up, peaks_dn = balance_up_down(peaks_for_balance, spot_price=current_price, max_allowed_diff=10)
    
    # 最终统计（不输出日志）
    N_up_final = len(peaks_up)
    N_dn_final = len(peaks_dn)

    final_peaks = sorted(peaks_up + peaks_dn, key=lambda p: p['price'], reverse=True)

    if final_peaks:
        vmax_peak = max(p['volume'] for p in final_peaks)
    else:
        vmax_peak = 0.0
    for p in final_peaks:
        p['rgb'], p['hex'] = red_gradient_color(p['volume'], vmax_peak)

    target = total_vol
    low_idx = high_idx = poc_idx
    current_vol = profile_vol[poc_idx]
    while current_vol < target and (low_idx > 0 or high_idx < len(profile_vol)-1):
        vol_below = profile_vol[low_idx-1] if low_idx > 0 else 0
        vol_above = profile_vol[high_idx+1] if high_idx < len(profile_vol)-1 else 0
        if vol_below >= vol_above and low_idx > 0:
            low_idx -= 1
            current_vol += profile_vol[low_idx]
        elif high_idx < len(profile_vol)-1:
            high_idx += 1
            current_vol += profile_vol[high_idx]
        else:
            break
    val_price = profile_price[low_idx]
    vah_price = profile_price[high_idx]

    max_offset_bins = 450
    spot_idx = int(np.argmin(np.abs(profile_price - current_price)))
    min_allowed_idx = max(spot_idx - max_offset_bins, 0)
    max_allowed_idx = min(spot_idx + max_offset_bins, len(profile_price) - 1)

    allowed_indices = np.arange(min_allowed_idx, max_allowed_idx + 1)
    allowed_mask = np.zeros(profile_price.shape, dtype=bool)
    allowed_mask[allowed_indices] = True

    display_lower_bound = float(profile_price[min_allowed_idx])
    display_upper_bound = float(profile_price[max_allowed_idx])

    before_window_clip = final_peaks[:]
    final_peaks = [p for p in final_peaks if display_lower_bound <= p['price'] <= display_upper_bound]
    if TRACE_ENABLED and any(is_target_peak(p, bin_size/2) for p in before_window_clip) and not any(is_target_peak(p, bin_size/2) for p in final_peaks):
        print("[TRACE BTC] filtered by display window clamp (allowed price range)")
    peak_idx_to_color = {peak['idx']: peak['hex'] for peak in final_peaks}

    subset_prices = profile_price[allowed_mask]
    subset_vols = profile_vol[allowed_mask]
    subset_original_indices = np.where(allowed_mask)[0]

    window_bins_target = 100
    window_bins = min(window_bins_target, len(subset_prices))
    if window_bins == 0 and len(subset_prices) > 0:
        window_bins = len(subset_prices)
    half_window = window_bins // 2 if window_bins > 0 else 0

    initial_low_idx = max(spot_idx - half_window, min_allowed_idx)
    initial_high_idx = initial_low_idx + window_bins - 1 if window_bins > 0 else min_allowed_idx
    if window_bins > 0 and initial_high_idx > max_allowed_idx:
        initial_high_idx = max_allowed_idx
        initial_low_idx = max(initial_high_idx - window_bins + 1, min_allowed_idx)

    if window_bins <= 0 or len(subset_prices) == 0:
        initial_lower_bound = display_lower_bound
        initial_upper_bound = display_upper_bound
    else:
        initial_lower_bound = float(profile_price[initial_low_idx])
        initial_upper_bound = float(profile_price[initial_high_idx])

    initial_offset = max(initial_low_idx - min_allowed_idx, 0)
    max_offset = max(len(subset_prices) - window_bins, 0) if window_bins > 0 else 0
    allowed_prices = [float(p) for p in subset_prices.tolist()]

    value_area_color = "#FFD700"
    normal_color = "white"

    records = []
    for local_idx, price_val in enumerate(subset_prices):
        original_idx = int(subset_original_indices[local_idx])
        volume_val = float(subset_vols[local_idx])
        
        if original_idx in peak_idx_to_color:
            color = peak_idx_to_color[original_idx]
            is_peak = True
        elif val_price <= price_val <= vah_price:
            color = value_area_color
            is_peak = False
        else:
            color = normal_color
            is_peak = False

        hover_text = f"Price: ${price_val:.2f}<br>Volume: {volume_val:,.0f}"

        records.append({
            'Price': float(price_val),
            'Volume': volume_val,
            'Color': color,
            'HoverText': hover_text,
            'IsPeak': is_peak
        })

    records_sorted = sorted(records, key=lambda r: r['Price'], reverse=True)
    profile_df = pd.DataFrame(records_sorted)

    volumes_sorted = profile_df['Volume'].tolist()
    prices_sorted = profile_df['Price'].tolist()
    colors_sorted = profile_df['Color'].tolist()
    hovers_sorted = profile_df['HoverText'].tolist()

    max_vol = subset_vols.max() if len(subset_vols) else 0.0
    mid_price = (display_lower_bound + display_upper_bound) / 2 if len(subset_prices) else current_price
    tick_spacing = max(1, int(mid_price * 0.002 + 0.5))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=volumes_sorted,
        y=prices_sorted,
        orientation='h',
        marker=dict(color=colors_sorted, line=dict(width=0)),
        hovertext=hovers_sorted,
        hovertemplate='%{hovertext}<extra></extra>',
        name='Volume Profile',
        showlegend=False,
        width=bin_size
    ))

    fig.add_trace(go.Scatter(
        x=[0, max_vol * 1.35 * 0.9],
        y=[current_price, current_price],
        mode="lines",
        line=dict(color="#00FF99", dash="dash"),
        showlegend=False,
        hoverinfo="skip"
    ))
    fig.add_trace(go.Scatter(
        x=[max_vol * 1.35 * 0.9],
        y=[current_price],
        mode="text",
        text=["SPOT"],
        textposition="middle right",
        textfont=dict(color="#00FF99"),
        showlegend=False,
        hoverinfo="skip"
    ))

    initial_range = {
        'upper': initial_upper_bound,
        'lower': initial_lower_bound
    }
    scroll_range = {
        'upper': display_upper_bound,
        'lower': display_lower_bound
    }

    fig.update_layout(
        title=f'{name} – {N_DAYS} Day Volume Profile<br>Spot Price ${current_price:.2f}',
        xaxis_title='Volume',
        yaxis_title='Price ($)',
        plot_bgcolor='black',
        paper_bgcolor='black',
        font=dict(color='white', size=11),
        margin=dict(l=140, r=60, t=100, b=100),
        xaxis=dict(
            gridcolor='rgba(255,255,255,0.1)',
            showgrid=False,
            range=[0, max_vol * 1.35 if max_vol > 0 else 1.0],
            zeroline=False
        ),
        yaxis=dict(
            gridcolor='rgba(255,255,255,0.1)',
            showgrid=False,
            range=[initial_range['lower'], initial_range['upper']],
            dtick=tick_spacing,
            tickformat='d',
            autorange=False,
            fixedrange=True
        ),
        width=1700
    )

    return {
        'fig': fig,
        'profile_df': profile_df,
        'spot_price': current_price,
        'initial_range': initial_range,
        'scroll_range': scroll_range,
        'bin_size': bin_size,
        'max_volume': max_vol,
        'display_bin_count': len(subset_prices),
        'final_peaks': final_peaks,
        'window_bins': window_bins,
        'initial_offset': initial_offset,
        'max_offset': max_offset,
        'allowed_prices': allowed_prices,
        'rescore_triggered': need_rescore,  # 记录是否触发重筛
        'up_peaks_raw': N_up_initial,       # 第一次平衡后的上侧峰数（用于日志）
        'dn_peaks_raw': N_dn_initial        # 第一次平衡后的下侧峰数（用于日志）
    }


def js_safe_name(name: str) -> str:
    return re.sub(r'[^0-9A-Za-z_]', '_', name)

# "GC=F"
def generate_dashboard(HSI_output=True):
    ticker_symbols = ["NQ=F","GC=F", "ES=F", "NIY=F","SI=F", "BTC-USD", "ETH-USD", "TSLA", "AAPL", "NVDA"]
    symbol_payloads = []
    ticker_info = []  # Store each symbol name and bin count
    date_range = None  # Track the processed date window
    latest_data_info = []  # Store the latest timestamp per symbol
    
    # 处理进度信号
    # 计算总标的数量（可选择是否包含HSI）
    hsi_contracts = ['HSI2511', 'HSI2512']
    total_symbols = len(ticker_symbols) + (len(hsi_contracts) if HSI_output else 0)
    processed_count = 0
    
    print(f"\n处理进度: **0%**", end="", flush=True)
    
    # Process GC first to derive the reference configuration
    gc_reference = None
    gc_ticker = "GC=F"
    
    # First locate and process GC
    for ticker_symbol in ticker_symbols:
            if ticker_symbol == gc_ticker:
                result = process_ticker(ticker_symbol, start_date, end_date, N_DAYS)
                if result is not None:
                    data_20d, name, data_20d_dates = result
                    if date_range is None:
                        date_range = [data_20d_dates[0], data_20d_dates[-1]]
                    else:
                        date_range[0] = min(date_range[0], data_20d_dates[0])
                        date_range[1] = max(date_range[1], data_20d_dates[-1])
    
                    plot_result = plot_volume_profile(data_20d, name, N_DAYS, gc_reference=None)
                    fig = plot_result['fig']
                    spot_price = plot_result['spot_price']
                    profile_records = [
                        {
                            'Price': float(record['Price']),
                            'Volume': float(record['Volume']),
                            'Color': record['Color'],
                            'HoverText': record['HoverText'],
                            'IsPeak': bool(record['IsPeak'])
                        }
                        for record in plot_result['profile_df'].to_dict(orient='records')
                    ]
                    initial_range = plot_result['initial_range']
                    scroll_range = plot_result['scroll_range']
                    bin_size = plot_result['bin_size']
                    num_bins = plot_result['display_bin_count']
                    gc_display_range = scroll_range['upper'] - scroll_range['lower']
                    gc_reference = {
                        'price': spot_price,
                        'bin_size': bin_size,
                        'display_range': gc_display_range
                    }
                    latest_timestamp = data_20d.index.max()
                    latest_data_info.append((name, latest_timestamp))
                    symbol_payloads.append({
                        'name': name,
                        'fig': fig,
                        'profile_records': profile_records,
                        'spot_price': spot_price,
                        'initial_range': initial_range,
                        'scroll_range': scroll_range,
                        'bin_size': bin_size,
                        'window_bins': plot_result['window_bins'],
                        'initial_offset': plot_result['initial_offset'],
                        'max_offset': plot_result['max_offset'],
                        'allowed_prices': plot_result['allowed_prices'],
                        'rescore_triggered': plot_result.get('rescore_triggered', False),
                        'up_peaks_raw': plot_result.get('up_peaks_raw', None),
                        'dn_peaks_raw': plot_result.get('dn_peaks_raw', None)
                    })
                    ticker_info.append((name, num_bins))
                    processed_count += 1
                    percentage = int(processed_count * 100 / total_symbols)
                    # 使用 \r 回到行首，\033[K 清除到行尾，实现同一位置更新
                    print(f"\r处理进度: **{percentage}%**", end="", flush=True)
                break
    
    # Process the remaining symbols
    for ticker_symbol in ticker_symbols:
        if ticker_symbol == gc_ticker:
            continue  # GC is already handled
        
        result = process_ticker(ticker_symbol, start_date, end_date, N_DAYS)
        if result is None:
            continue
        
        data_20d, name, data_20d_dates = result
        if date_range is None:
            date_range = [data_20d_dates[0], data_20d_dates[-1]]
        else:
            date_range[0] = min(date_range[0], data_20d_dates[0])
            date_range[1] = max(date_range[1], data_20d_dates[-1])
        
        plot_result = plot_volume_profile(data_20d, name, N_DAYS, gc_reference=gc_reference)
        fig = plot_result['fig']
        spot_price = plot_result['spot_price']
        profile_records = [
            {
                'Price': float(record['Price']),
                'Volume': float(record['Volume']),
                'Color': record['Color'],
                'HoverText': record['HoverText'],
                'IsPeak': bool(record['IsPeak'])
            }
            for record in plot_result['profile_df'].to_dict(orient='records')
        ]
        initial_range = plot_result['initial_range']
        scroll_range = plot_result['scroll_range']
        bin_size = plot_result['bin_size']
        num_bins = plot_result['display_bin_count']
        win_height = plot_result['window_bins']
        win_offset = plot_result['initial_offset']
        max_offset = plot_result['max_offset']
        allowed = plot_result['allowed_prices']
        
        latest_timestamp = data_20d.index.max()
        latest_data_info.append((name, latest_timestamp))
        symbol_payloads.append({
            'name': name,
            'fig': fig,
            'profile_records': profile_records,
            'spot_price': spot_price,
            'initial_range': initial_range,
            'scroll_range': scroll_range,
            'bin_size': bin_size,
            'window_bins': plot_result['window_bins'],
            'initial_offset': plot_result['initial_offset'],
            'max_offset': plot_result['max_offset'],
            'allowed_prices': plot_result['allowed_prices'],
            'rescore_triggered': plot_result.get('rescore_triggered', False),
            'up_peaks_raw': plot_result.get('up_peaks_raw', None),
            'dn_peaks_raw': plot_result.get('dn_peaks_raw', None)
        })
        ticker_info.append((name, num_bins))
        processed_count += 1
        percentage = int(processed_count * 100 / total_symbols)
        # 使用 \r 回到行首，实现同一位置更新
        print(f"\r处理进度: **{percentage}%**", end="", flush=True)
    
    # Process HSI contracts from Excel（可开关）
    if HSI_output:
        hsi_contracts = ['HSI2511', 'HSI2512']
        for contract_code in hsi_contracts:
            result = load_hsi_from_excel(contract_code, excel_path="data/hsi_data.xlsx", N_DAYS=N_DAYS)
            if result is None:
                continue
            
            data_20d, name, data_20d_dates = result
            if date_range is None:
                date_range = [data_20d_dates[0], data_20d_dates[-1]]
            else:
                date_range[0] = min(date_range[0], data_20d_dates[0])
                date_range[1] = max(date_range[1], data_20d_dates[-1])
            
            plot_result = plot_volume_profile(data_20d, name, N_DAYS, gc_reference=gc_reference)
            fig = plot_result['fig']
            spot_price = plot_result['spot_price']
            profile_records = [
                {
                    'Price': float(record['Price']),
                    'Volume': float(record['Volume']),
                    'Color': record['Color'],
                    'HoverText': record['HoverText'],
                    'IsPeak': bool(record['IsPeak'])
                }
                for record in plot_result['profile_df'].to_dict(orient='records')
            ]
            initial_range = plot_result['initial_range']
            scroll_range = plot_result['scroll_range']
            bin_size = plot_result['bin_size']
            num_bins = plot_result['display_bin_count']
            win_height = plot_result['window_bins']
            win_offset = plot_result['initial_offset']
            max_offset = plot_result['max_offset']
            allowed = plot_result['allowed_prices']
            
            latest_timestamp = data_20d.index.max()
            latest_data_info.append((name, latest_timestamp))
            symbol_payloads.append({
                'name': name,
                'fig': fig,
                'profile_records': profile_records,
                'spot_price': spot_price,
                'initial_range': initial_range,
                'scroll_range': scroll_range,
                'bin_size': bin_size,
                'window_bins': plot_result['window_bins'],
                'initial_offset': plot_result['initial_offset'],
                'max_offset': plot_result['max_offset'],
                'allowed_prices': plot_result['allowed_prices'],
                'rescore_triggered': plot_result.get('rescore_triggered', False),
                'up_peaks_raw': plot_result.get('up_peaks_raw', None),
                'dn_peaks_raw': plot_result.get('dn_peaks_raw', None)
            })
            ticker_info.append((name, num_bins))
            processed_count += 1
            percentage = int(processed_count * 100 / total_symbols) if total_symbols > 0 else 100
            # 使用 \r 回到行首，实现同一位置更新
            print(f"\r处理进度: **{percentage}%**", end="", flush=True)
    
    # Print summary information - 简化输出
    print()  # 换行，结束进度显示
    print("="*60)
    for name, num_bins in ticker_info:
        # 查找对应的重筛信息
        rescore_status = "未触发"
        up_raw = None
        dn_raw = None
        for payload in symbol_payloads:
            if payload['name'] == name and 'rescore_triggered' in payload:
                rescore_status = "已触发" if payload['rescore_triggered'] else "未触发"
                up_raw = payload.get('up_peaks_raw', None)
                dn_raw = payload.get('dn_peaks_raw', None)
                break
        if up_raw is not None and dn_raw is not None:
            print(f"{name}: {int(num_bins)} bins, 上下峰数: {up_raw}/{dn_raw}, 综合得分重筛: {rescore_status}")
        else:
            print(f"{name}: {int(num_bins)} bins, 综合得分重筛: {rescore_status}")
    print("="*60)
    
    if latest_data_info:
        print("\nLatest data timestamps:")
        for name, latest_ts in latest_data_info:
            latest_ts = pd.Timestamp(latest_ts)
            # HSI标的使用UTC时区，其他标的使用中国标准时间
            if name in ['HSI2511', 'HSI2512']:
                # HSI标的：使用UTC时区
                if latest_ts.tzinfo is None:
                    latest_ts_utc = latest_ts.tz_localize('UTC')
                else:
                    latest_ts_utc = latest_ts.tz_convert('UTC')
                utc_str = latest_ts_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
                print(f"  {name}: {utc_str}")
            else:
                # 其他标的：使用中国标准时间
                if latest_ts.tzinfo is None:
                    latest_ts_eastern = latest_ts.tz_localize('America/New_York')
                else:
                    latest_ts_eastern = latest_ts.tz_convert('America/New_York')
                latest_ts_china = latest_ts_eastern.tz_convert('Asia/Shanghai')
                china_str = latest_ts_china.strftime("%Y-%m-%d %H:%M:%S %Z")
                print(f"  {name}: {china_str}")
    
    # 检查是否有有效数据，如果没有则返回 None
    if not symbol_payloads:
        print("\n警告: 没有获取到任何有效数据，跳过生成 HTML 文件")
        return None
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Volume Profile Dashboard</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {
                background-color: #000000;
                color: #ffffff;
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 16px;
                box-sizing: border-box;
                overflow-x: hidden;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                min-height: 100vh;
            }
            main {
                flex: 1;
                display: flex;
                flex-direction: column;
                min-height: 0;
                gap: 12px;
            }
            .tabs {
                display: flex;
                justify-content: center;
                margin-bottom: 20px;
                border-bottom: 2px solid #333;
            }
            .tab-button {
                background-color: #222222;
                color: #ffffff;
                border: none;
                padding: 12px 30px;
                margin: 0 5px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                transition: all 0.3s;
            }
            .tab-button:hover {
                background-color: #333333;
            }
            .tab-button.active {
                background-color: #444444;
                border-bottom: 3px solid #00FF99;
            }
            .content-panel {
                display: none;
                flex: 1 1 auto;
                min-height: 0;
            }
            .content-panel.active {
                display: flex;
                flex-direction: column;
                flex: 1 1 auto;
                min-height: 0;
            }
            .content-wrapper {
                display: flex;
                flex-wrap: wrap;
                gap: 16px;
                align-items: stretch;
                flex: 1;
                min-height: 0;
                justify-content: space-between;
                padding: 0 12px;
            }
            .chart-container {
                flex: 1 1 520px;
                max-width: 100%;
                background-color: #000000;
                min-width: 0;
                min-height: 0;
            }
            .chart-wrapper {
                display: flex;
                flex: 1 1 520px;
                gap: 12px;
                align-items: stretch;
                height: 100%;
                min-height: 0;
                min-width: 0;
            }
            .slider-container {
                flex: 0 0 56px;
                min-width: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 10px 0;
            }
            .price-slider {
                -webkit-appearance: none;
                appearance: none;
                width: 260px;
                height: 6px;
                background: #444444;
                border-radius: 3px;
                outline: none;
                transform: rotate(-90deg);
            }
            .price-slider::-webkit-slider-thumb {
                -webkit-appearance: none;
                appearance: none;
                width: 16px;
                height: 16px;
                border-radius: 50%;
                background: #00FF99;
                cursor: pointer;
                border: none;
            }
            .price-slider::-moz-range-thumb {
                width: 16px;
                height: 16px;
                border-radius: 50%;
                background: #00FF99;
                cursor: pointer;
                border: none;
            }
            .price-slider:disabled {
                opacity: 0.35;
                cursor: not-allowed;
            }
            .table-container {
                flex: 1 1 clamp(220px, 24%, 360px);
                max-width: clamp(220px, 24%, 360px);
                background-color: #000000;
                height: 100%;
                max-height: 100%;
                overflow-y: auto;
                position: relative;
                margin-left: 0;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                background-color: #111111;
                table-layout: fixed;
            }
            th, td {
                border: 1px solid #ffffff;
                padding: 8px 12px;
                text-align: center;
                font-size: 14px;
            }
            th {
                background-color: #222222;
                font-weight: bold;
                position: sticky;
                top: 0;
                z-index: 10;
            }
            tr.spot-row {
                background-color: rgba(0, 255, 153, 0.1);
            }
            td.spot-cell {
                color: #00FF99;
                font-weight: bold;
            }
            h2 {
                text-align: center;
                margin: 0 0 10px 0;
                color: #ffffff;
            }
            .chart-div {
                width: 100%;
                height: 100%;
                min-height: 0;
            }
            @media (max-width: 1400px) {
                body {
                    padding: 14px;
                }
                .content-wrapper {
                    flex-direction: column;
                    padding: 0;
                }
                .chart-wrapper {
                    flex: 1 1 auto;
                    min-width: 0;
                }
                .slider-container {
                    flex: 0 0 auto;
                    padding: 16px 0;
                }
                .table-container {
                    flex: 1 1 auto;
                    max-width: 100%;
                    max-height: 360px;
                }
            }
            @media (max-width: 900px) {
                body {
                    padding: 10px;
                }
                .tabs {
                    flex-wrap: wrap;
                    gap: 8px;
                }
                .tab-button {
                    flex: 1 1 120px;
                    min-width: 120px;
                }
                .price-slider {
                    width: 220px;
                }
            }
        </style>
    </head>
    <body>
        <main>
            <h1 style="text-align: center; margin: 0 0 16px 0;">Volume Profile Dashboard</h1>
        
        <div class="tabs">
    """
    
    for idx, payload in enumerate(symbol_payloads):
        name = payload['name']
        active_class = 'active' if idx == 0 else ''
        html_content += f'<button class="tab-button {active_class}" onclick="showTab(\'{name}\', this)">{name}</button>\n'
    
    html_content += """
        </div>
    """
    
    for idx, payload in enumerate(symbol_payloads):
        name = payload['name']
        active_class = 'active' if idx == 0 else ''
        html_content += f'<div id="panel-{name}" class="content-panel {active_class}">\n'
        html_content += f'<h2>{name} Volume Profile</h2>\n'
        html_content += '<div class="content-wrapper">\n'
        html_content += '<div class="chart-wrapper">\n'
        html_content += f'<div class="chart-container">\n'
        html_content += f'<div id="chart-{name}" class="chart-div"></div>\n'
        html_content += '</div>\n'
        html_content += f'<div class="slider-container">\n'
        html_content += f'<input type="range" class="price-slider" id="slider-{name}" orient="vertical">\n'
        html_content += '</div>\n'
        html_content += '</div>\n'
        html_content += f'<div class="table-container" id="table-container-{name}">\n'
        html_content += '<table>\n'
        html_content += '<thead><tr><th>Price</th><th>Volume</th></tr></thead>\n'
        html_content += f'<tbody id="table-body-{name}">\n'
        html_content += '</tbody>\n'
        html_content += '</table>\n'
        html_content += '</div>\n'
        html_content += '</div>\n'
        html_content += '</div>\n'
    
    html_content += '    </main>\n'
    html_content += '<script>\n'
    html_content += """
    var symbolData = {};
    var activeTicker = null;
    var volumeFormatter = new Intl.NumberFormat('en-US');
    var globalWheelListenerRegistered = false;
    
    function updatePeakTable(tickerName, rangeObj) {
        var data = symbolData[tickerName];
        if (!data) return;
    
        var tableBody = document.getElementById('table-body-' + tickerName);
        if (!tableBody) return;
    
        var upper = rangeObj.upper;
        var lower = rangeObj.lower;
    
        var peaks = data.profileRecords
            .filter(function(record) {
                return record.IsPeak && record.Price <= upper && record.Price >= lower;
            })
            .sort(function(a, b) {
                return b.Price - a.Price;
            });
    
        var rows = [];
        var includeSpot = data.spotPrice <= upper && data.spotPrice >= lower;
        var spotInserted = false;
    
        for (var i = 0; i < peaks.length; i++) {
            var peak = peaks[i];
            if (includeSpot && !spotInserted && data.spotPrice >= peak.Price) {
                rows.push({ type: 'spot', price: data.spotPrice });
                spotInserted = true;
            }
            rows.push({ type: 'peak', price: peak.Price, volume: peak.Volume });
        }
    
        if (includeSpot && !spotInserted) {
            rows.push({ type: 'spot', price: data.spotPrice });
        }
    
        tableBody.innerHTML = '';
    
        rows.forEach(function(row) {
            var tr = document.createElement('tr');
            if (row.type === 'spot') {
                tr.classList.add('spot-row');
                tr.id = 'spot-row-' + tickerName;
            }
            var priceTd = document.createElement('td');
            priceTd.textContent = '$' + row.price.toFixed(2);
            var volumeTd = document.createElement('td');
            if (row.type === 'spot') {
                volumeTd.textContent = 'Spot';
                volumeTd.classList.add('spot-cell');
            } else {
                volumeTd.textContent = volumeFormatter.format(Math.round(row.volume));
            }
            tr.appendChild(priceTd);
            tr.appendChild(volumeTd);
            tableBody.appendChild(tr);
        });
    
        symbolData[tickerName].currentRange = { upper: upper, lower: lower };
    }
    
    function scrollSpotIntoView(tickerName) {
        var container = document.getElementById('table-container-' + tickerName);
        var spotRow = document.getElementById('spot-row-' + tickerName);
        if (!container || !spotRow) return;
        var targetScroll = spotRow.offsetTop - (container.clientHeight / 2) + (spotRow.offsetHeight / 2);
        container.scrollTop = targetScroll;
    }

    function computeChartHeight() {
        var main = document.querySelector('main');
        var topOffset = 0;
        if (main) {
            var rect = main.getBoundingClientRect();
            topOffset = rect.top;
        }
        var available = window.innerHeight - topOffset - 160;
        if (!isFinite(available) || available <= 0) {
            available = window.innerHeight * 0.7;
        }
        available = Math.min(available, window.innerHeight - 40);
        return Math.max(available, 480);
    }

    function applyResponsiveHeight(chartDiv) {
        if (!chartDiv) return;
        var targetHeight = computeChartHeight();
        Plotly.relayout(chartDiv, { height: targetHeight });
    }
    
    function showTab(tickerName, buttonElement) {
        var panels = document.getElementsByClassName('content-panel');
        for (var i = 0; i < panels.length; i++) {
            panels[i].classList.remove('active');
        }
        
        var buttons = document.getElementsByClassName('tab-button');
        for (var j = 0; j < buttons.length; j++) {
            buttons[j].classList.remove('active');
        }
    
        var panel = document.getElementById('panel-' + tickerName);
        if (panel) {
            panel.classList.add('active');
        }
        if (buttonElement) {
        buttonElement.classList.add('active');
        }
    
        activeTicker = tickerName;
    
        var data = symbolData[tickerName];
        if (data) {
            setRangeFromOffset(tickerName, data.currentOffset !== undefined ? data.currentOffset : data.initialOffset, { updateSlider: true });
        }
    }
    
    function computeRangeFromOffset(data, offset) {
        if (!data || data.allowedPrices.length === 0) {
            return null;
        }
    
        var windowSize = data.windowSize;
        if (windowSize <= 0 || windowSize > data.allowedPrices.length) {
            return {
                upper: data.allowedPrices[data.allowedPrices.length - 1],
                lower: data.allowedPrices[0],
                startIndex: 0
            };
        }
    
        var maxOffset = Math.max(data.allowedPrices.length - windowSize, 0);
        var start = Math.min(Math.max(offset, 0), maxOffset);
        var end = start + windowSize - 1;
        var lowerPrice = data.allowedPrices[start];
        var upperPrice = data.allowedPrices[end];
    
        return {
            upper: upperPrice,
            lower: lowerPrice,
            startIndex: start
        };
    }
    
    function setRangeFromOffset(tickerName, offset, options) {
        var data = symbolData[tickerName];
        if (!data) return;
    
        var chartDiv = document.getElementById('chart-' + tickerName);
        if (!chartDiv) return;
    
        var slider = document.getElementById('slider-' + tickerName);
        var rangeData = computeRangeFromOffset(data, offset);
        if (!rangeData) {
            if (data.scrollRange) {
                data.currentRange = {
                    upper: data.scrollRange.upper,
                    lower: data.scrollRange.lower
                };
                data.currentOffset = 0;
                updatePeakTable(tickerName, data.currentRange);
                scrollSpotIntoView(tickerName);
            }
            return;
        }
    
        var rangeObj = { upper: rangeData.upper, lower: rangeData.lower };
        var startIndex = rangeData.startIndex || 0;
    
        data.currentRange = rangeObj;
        data.currentOffset = startIndex;
    
        if (options && options.updateSlider && slider) {
            slider.value = startIndex;
        }
    
        Plotly.relayout(chartDiv, { 'yaxis.range': [rangeObj.lower, rangeObj.upper] }).then(function() {
            updatePeakTable(tickerName, rangeObj);
            scrollSpotIntoView(tickerName);
        });
    }
    
    function stepRangeOffset(tickerName, step) {
        var data = symbolData[tickerName];
        if (!data) return;
    
        var slider = document.getElementById('slider-' + tickerName);
        if (slider && slider.disabled) return;
    
        var maxOffset = Math.max(data.maxOffset || 0, 0);
        var currentOffset = data.currentOffset || 0;
        var nextOffset = currentOffset + step;
        if (nextOffset < 0) {
            nextOffset = 0;
        } else if (nextOffset > maxOffset) {
            nextOffset = maxOffset;
            if (maxOffset > 0) {
                nextOffset = maxOffset - 1;
            }
        }
        if (nextOffset === currentOffset) return;
    
        setRangeFromOffset(tickerName, nextOffset, { updateSlider: true });
    }
    
    function attachWheelSync(tickerName) {
        var chartDiv = document.getElementById('chart-' + tickerName);
        var tableContainer = document.getElementById('table-container-' + tickerName);
        var slider = document.getElementById('slider-' + tickerName);
    
        var handler = function(event) {
            var data = symbolData[tickerName];
        if (!data) return;
        if (slider && slider.disabled) return;
        var ctrl = event.ctrlKey;
        event.preventDefault();
        var step = event.deltaY < 0 ? 20 : -20;
        stepRangeOffset(tickerName, ctrl ? step * 5 : step);
        };
    
        if (chartDiv) {
            chartDiv.addEventListener('wheel', handler, { passive: false });
        }
        if (tableContainer) {
            tableContainer.addEventListener('wheel', handler, { passive: false });
        }
    
        if (!globalWheelListenerRegistered) {
            window.addEventListener('wheel', function(event) {
                if (!activeTicker) {
                    return;
                }
                var target = event.target;
                if (target && (target.closest('.chart-wrapper') || target.closest('.table-container'))) {
                    return;
                }
                var activeData = symbolData[activeTicker];
                if (!activeData) {
                    return;
                }
                var activeSlider = document.getElementById('slider-' + activeTicker);
                if (activeSlider && activeSlider.disabled) {
                    return;
                }
                event.preventDefault();
                var ctrl = event.ctrlKey;
                var step = event.deltaY < 0 ? 20 : -20;
                stepRangeOffset(activeTicker, ctrl ? step * 5 : step);
            }, { passive: false });
            globalWheelListenerRegistered = true;
        }
    }
    
    function initializeSlider(tickerName) {
        var data = symbolData[tickerName];
        if (!data) return;
    
        var slider = document.getElementById('slider-' + tickerName);
        if (!slider) return;
    
        var windowSize = data.windowSize;
        var allowedCount = data.allowedPrices.length;
    
        if (windowSize <= 0 || allowedCount === 0) {
            slider.disabled = true;
            slider.value = 0;
            return;
        }
    
        slider.min = 0;
        slider.max = Math.max(data.maxOffset, 0);
        slider.step = 1;
    
        var initialValue = Math.min(Math.max(data.initialOffset, 0), slider.max);
        slider.value = initialValue;
        slider.disabled = slider.max === 0;
    
        slider.addEventListener('input', function(event) {
            var nextOffset = parseInt(event.target.value, 10);
            setRangeFromOffset(tickerName, nextOffset, { updateSlider: false });
        });
    }
    
    function bootstrapPlot(tickerName, figure) {
        var chartDiv = document.getElementById('chart-' + tickerName);
        if (!chartDiv) return;
    
        figure.layout = figure.layout || {};
        figure.layout.dragmode = false;
        figure.layout.height = computeChartHeight();
        if (figure.layout.yaxis) {
            figure.layout.yaxis.fixedrange = true;
        }
    
        Plotly.newPlot(chartDiv, figure.data, figure.layout, {
            scrollZoom: false,
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d', 'zoom2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'pan2d']
        }).then(function() {
            applyResponsiveHeight(chartDiv);
            if (!chartDiv.dataset.heightListenerBound) {
                window.addEventListener('resize', function() {
                    applyResponsiveHeight(chartDiv);
                });
                chartDiv.dataset.heightListenerBound = "true";
            }
            initializeSlider(tickerName);
            var data = symbolData[tickerName];
            if (!data) return;
            setRangeFromOffset(tickerName, data.initialOffset, { updateSlider: true });
            attachWheelSync(tickerName);
        });
    }
    """
    
    if symbol_payloads:
        default_ticker = symbol_payloads[0]['name']
        html_content += f"activeTicker = '{default_ticker}';\n"
    
    for payload in symbol_payloads:
        name = payload['name']
        symbol_js_data = {
            'profileRecords': payload['profile_records'],
            'spotPrice': payload['spot_price'],
            'binSize': payload['bin_size'],
            'initialRange': {
                'upper': float(payload['initial_range']['upper']),
                'lower': float(payload['initial_range']['lower'])
            },
            'scrollRange': {
                'upper': float(payload['scroll_range']['upper']),
                'lower': float(payload['scroll_range']['lower'])
            },
            'windowSize': int(payload['window_bins']) if payload['window_bins'] is not None else 0,
            'initialOffset': int(payload['initial_offset']) if payload['initial_offset'] is not None else 0,
            'maxOffset': int(payload['max_offset']) if payload['max_offset'] is not None else 0,
            'allowedPrices': payload['allowed_prices'],
            'currentOffset': int(payload['initial_offset']) if payload['initial_offset'] is not None else 0,
            'currentRange': {
                'upper': float(payload['initial_range']['upper']),
                'lower': float(payload['initial_range']['lower'])
            }
        }
        symbol_json = json.dumps(symbol_js_data, ensure_ascii=False)
        symbol_json = symbol_json.replace('</script>', '<\\/script>')
        html_content += f"symbolData['{name}'] = {symbol_json};\n"
    
    for payload in symbol_payloads:
        name = payload['name']
        safe_name = js_safe_name(name)
        fig_dict = payload['fig'].to_dict()
        fig_json_str = json.dumps(fig_dict, ensure_ascii=False)
        fig_json_str = fig_json_str.replace('</script>', '<\\/script>')
        html_content += f'var fig_{safe_name} = {fig_json_str};\n'
        html_content += f"bootstrapPlot('{name}', fig_{safe_name});\n"
    
    html_content += '</script>\n'
    html_content += '</body>\n</html>'
    
    with open('volume_profile_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\nGenerated HTML file: volume_profile_dashboard.html")
    return {
        'html_path': 'volume_profile_dashboard.html',
        'symbol_payloads': symbol_payloads,
        'ticker_info': ticker_info,
        'date_range': date_range,
        'latest_data_info': latest_data_info
    }
    
    
def send_to_topic_via_http(file_path, caption, token, chat_id, message_thread_id=None, reply_to_message_id=None):
    """
    Send a document to a specific Telegram chat/topic via HTTP API.
    With retry mechanism: up to 5 retries (6 total attempts).
    """
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    max_attempts = 6  # 初始1次 + 重试5次
    retry_delay = 1.5  # 重试延迟（秒）
    
    data = {
        'chat_id': chat_id,
        'caption': caption,
    }
    if message_thread_id is not None:
        data['message_thread_id'] = message_thread_id
    if reply_to_message_id is not None:
        data['reply_to_message_id'] = reply_to_message_id
    
    for attempt in range(1, max_attempts + 1):
        try:
            with open(file_path, 'rb') as f:
                files = {'document': f}
                response = requests.post(url, files=files, data=data)
            
            if response.status_code == 200:
                extra_context = []
                if message_thread_id is not None:
                    extra_context.append(f"topic {message_thread_id}")
                if reply_to_message_id is not None:
                    extra_context.append(f"reply {reply_to_message_id}")
                context_str = f" ({', '.join(extra_context)})" if extra_context else ""
                print(f"✅ File sent successfully to chat {chat_id}{context_str} (尝试 {attempt}/{max_attempts})")
                return True
            else:
                # 请求失败，记录错误
                error_msg = f"❌ Error sending file (尝试 {attempt}/{max_attempts}): {response.status_code} - {response.text}"
                if attempt < max_attempts:
                    print(error_msg)
                    print(f"⏳ {retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                else:
                    # 最后一次尝试失败
                    print(error_msg)
                    print(f"❌ 所有 {max_attempts} 次尝试均失败，停止重试")
                    return False
                    
        except Exception as e:
            # 异常处理（网络错误、文件读取错误等）
            error_msg = f"❌ Exception during send (尝试 {attempt}/{max_attempts}): {str(e)}"
            if attempt < max_attempts:
                print(error_msg)
                print(f"⏳ {retry_delay}秒后重试...")
                time.sleep(retry_delay)
            else:
                # 最后一次尝试失败
                print(error_msg)
                print(f"❌ 所有 {max_attempts} 次尝试均失败，停止重试")
                return False
    
    # 理论上不会到达这里，但为了安全起见
    return False


def main():
    """
    Generate the dashboard once or push updates every 2 hours to Telegram.
    """
    # Mode selection: 1 = run once, 2 = every 2 hours loop with Telegram push
    mode = 1
    # Whether to include HSI instruments in the generated dashboard
    HSI_output = False

    # Telegram configuration (update as needed)

    tele_token = '8304129187:AAG1GOqYcbzqhhM1uGQemcL0XvxBC5bMG0c'
    chat_id = -1003474306324
    reply_to_message_id = 113

    if mode == 1:
        generate_dashboard(HSI_output=HSI_output)
        print("Mode 1: Dashboard generated once.")
    elif mode == 2:
        print(f"Mode 2: Starting updates every 2 hours to Telegram chat {chat_id}, replying to message {reply_to_message_id}...")
        while True:
            # 检查 UTC 时区是否是星期天
            utc_now = datetime.now(timezone.utc)
            if utc_now.weekday() == 6:  # 6 = Sunday
                log_time = utc_now.strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{log_time} UTC] Sunday detected, skipping this run...")
                time.sleep(7200)
                continue
            
            try:
                result = generate_dashboard(HSI_output=HSI_output)
                
                # 检查返回结果是否有效
                if result is None:
                    log_time = pd.Timestamp.now(tz='Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{log_time}] No valid data available, skipping Telegram send")
                    time.sleep(7200)
                    continue
                
                # 验证结果中是否有有效数据
                if not result.get('symbol_payloads'):
                    log_time = pd.Timestamp.now(tz='Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{log_time}] No symbol data in result, skipping Telegram send")
                    time.sleep(7200)
                    continue
                
                html_path = result['html_path']
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                caption = (
                    "Volume Profile Dashboard\n"
                    f"Updated: {timestamp} (HKT)\n\n"
                    "Open in browser for interactive charts."
                )
                success = send_to_topic_via_http(
                    html_path, caption, tele_token, chat_id,
                    reply_to_message_id=reply_to_message_id
                )
                if success:
                    log_time = pd.Timestamp.now(tz='Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{log_time}] Dashboard sent as reply to message {reply_to_message_id}")
                else:
                    print("Failed to send—check bot permissions or token.")
            except Exception as exc:
                log_time = pd.Timestamp.now(tz='Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{log_time}] Error in loop: {exc}")
                import traceback
                traceback.print_exc()

            time.sleep(7200)
    else:
        print("Invalid mode. Use 1 or 2.")


if __name__ == "__main__":
    main()
