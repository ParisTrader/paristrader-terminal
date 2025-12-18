"""
Refresh the 1-year annualized volatility (VOLATILITY_360D) and 1-day average return (MU_1D) for the sector ETF list.
Both metrics are calculated based on the last 252 trading days of daily closing prices.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
PROGRESS_BAR_WIDTH = 120


def _print_progress(message: str) -> None:
    sys.stdout.write("\r" + message.ljust(PROGRESS_BAR_WIDTH))
    sys.stdout.flush()


def _clear_progress() -> None:
    sys.stdout.write("\r" + " " * PROGRESS_BAR_WIDTH + "\r")
    sys.stdout.flush()


VOL_COLUMN = "VOLATILITY_360D"
MIN_TRADING_DAYS = 200
TRADING_DAYS_PER_YEAR = 252


def _clean_ticker(value: object) -> Optional[str]:
    """Clean a ticker according to the fixed rules."""
    ticker = str(value).strip()
    if not ticker or ticker.lower() == "nan":
        return None
    return ticker


def _download_price_series(ticker: str) -> pd.Series:
    """
    Download the last 252 trading days of daily prices for a single ticker.
    Prefer Adj Close; fall back to Close when needed.
    Note: We download ~400 calendar days to ensure we get at least 252 trading days,
    then take the last 252 trading days.
    """
    # 下载约400个自然日的数据，确保包含至少252个交易日
    # （一年约252个交易日，但自然日约365天，所以400天足够）
    data = yf.download(
        ticker,
        period="400d",      # 下载约400个自然日，确保包含至少252个交易日
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if data.empty:
        raise ValueError(f"{ticker}: yfinance 返回数据为空。")

    price_col = None
    if "Adj Close" in data.columns:
        price_col = data["Adj Close"].copy()
    elif "Close" in data.columns:
        price_col = data["Close"].copy()

    if price_col is None or price_col.dropna().empty:
        raise ValueError(f"{ticker}: 缺少可用的 Adj Close/Close 列。")

    price_col = price_col.dropna()
    if isinstance(price_col, pd.DataFrame):
        if price_col.shape[1] != 1:
            raise ValueError(f"{ticker}: 收盘价列形状异常：{price_col.shape}")
        price_col = price_col.iloc[:, 0]

    # 取最后252个交易日（去除NaN后，按日期排序，取最后252个）
    price_col = price_col.sort_index()
    if len(price_col) < TRADING_DAYS_PER_YEAR:
        raise ValueError(
            f"{ticker}: 可用交易日数量 {len(price_col)} < {TRADING_DAYS_PER_YEAR}，"
            "无法计算基于252个交易日的波动率。"
        )
    
    # 取最后252个交易日
    price_col = price_col.tail(TRADING_DAYS_PER_YEAR)

    return price_col.squeeze()


def _compute_vol_and_mu(prices: pd.Series) -> tuple[float, float]:
    """
    根据近 252 个交易日的价格序列计算：
    - 1 年期年化波动率（百分数）
    - 1 日平均收益 μ（百分数）
    """
    returns = prices.pct_change().dropna()
    if returns.empty:
        raise ValueError("收益率序列为空，无法计算波动率和均值。")

    # 日收益率样本标准差（小数）
    daily_std = returns.std(ddof=1)
    # 年化波动率（百分数）
    annualized_vol_pct = daily_std * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0

    # 日均收益 μ（小数 → 百分数）
    mu_daily_dec = returns.mean()
    mu_daily_pct = mu_daily_dec * 100.0

    return annualized_vol_pct, mu_daily_pct


def update_volatility_360d_column(excel_path: str, sheet_name: str | None = None) -> pd.DataFrame:
    """
    Read ETF tickers from column C (the third column) of the Excel file, calculate the 1-year annualized
    volatility (VOLATILITY_360D) and 1-day average return (MU_1D) based on the last 252 trading days,
    and write both columns back to the Excel file.
    Returns the updated DataFrame.
    """
    if sheet_name is None:
        sheet_to_read = 0
    else:
        sheet_to_read = sheet_name

    df = pd.read_excel(excel_path, sheet_name=sheet_to_read)
    if df.shape[1] < 3:
        raise ValueError("Excel 至少需要包含前三列，C 列应为 ETF Ticker。")

    ticker_series = df.iloc[:, 2]

    pairs: list[tuple[int, str]] = []
    for idx, raw_value in ticker_series.items():
        ticker = _clean_ticker(raw_value)
        if ticker is None:
            print(f"[阶段 1/2] 行 {idx}: ticker 为空或非法，跳过。", flush=True)
            continue
        pairs.append((idx, ticker))

    total = len(pairs)
    if total == 0:
        print("[阶段 1/2] 未找到任何有效 ticker，波动率计算跳过。", flush=True)
        return df

    print(f"[阶段 1/2] 共 {total} 个标的需要计算波动率和日均收益。", flush=True)

    vol_series = pd.Series(np.nan, index=df.index, name="VOLATILITY_360D")
    mu_series = pd.Series(np.nan, index=df.index, name="MU_1D")
    done = 0

    for idx, ticker in pairs:
        done += 1
        percent = done * 100.0 / total
        progress_msg = f"[阶段 1/2] 进度 {percent:5.1f}% ({done}/{total})：正在处理 {ticker} ..."
        _print_progress(progress_msg)
        try:
            price_series = _download_price_series(ticker)
            if price_series.size < MIN_TRADING_DAYS:
                _clear_progress()
                print(
                    f"{ticker}: 有效交易日 {price_series.size} < {MIN_TRADING_DAYS}，写入 NaN。",
                    flush=True,
                )
                continue

            vol_percent, mu_daily_pct = _compute_vol_and_mu(price_series)
            vol_series.at[idx] = vol_percent
            mu_series.at[idx] = mu_daily_pct
        except Exception as exc:
            _clear_progress()
            print(f"{ticker}: 计算失败 -> {exc}", flush=True)

    # 写回 VOLATILITY_360D
    if VOL_COLUMN in df.columns:
        df.loc[:, VOL_COLUMN] = vol_series
    else:
        df[VOL_COLUMN] = vol_series

    # 写回 MU_1D（日均收益 μ，百分数）
    if "MU_1D" in df.columns:
        df.loc[:, "MU_1D"] = mu_series
    else:
        df["MU_1D"] = mu_series

    output_path = Path(excel_path)
    df.to_excel(output_path, index=False)
    _clear_progress()
    print(f"[阶段 1/2] 已将结果保存至 {output_path.resolve()}", flush=True)

    return df


if __name__ == "__main__":
    UPDATED_FILE = "sector_etf_stock_list.xlsx"
    updated_df = update_volatility_360d_column(UPDATED_FILE)
    print("前 5 行结果预览：")
    preview_cols = [col for col in updated_df.columns if col in ["VOLATILITY_360D", "MU_1D"] or updated_df.columns.get_loc(col) < 3]
    print(updated_df[preview_cols].head())

