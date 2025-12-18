# -*- coding: utf-8 -*-
"""
從 Yahoo Finance 獲取 USD/HKD 匯率
目標 URL: https://finance.yahoo.com/quote/HKD%3DX/
"""

import yfinance as yf
import pandas as pd
import time
import datetime as dt

MAX_RETRIES = 5

def get_usdhkd_rate():
    """
    獲取 USD/HKD 即時匯率
    :return: (rate, timestamp_str) or (None, None)
    """
    # Yahoo Finance 上的 ticker 為 HKD=X
    ticker_symbol = "HKD=X"
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] 正在獲取 {ticker_symbol} 匯率...")
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # 初始化 Ticker
            ticker = yf.Ticker(ticker_symbol)
            
            # 獲取歷史數據 (1天) 來拿最新收盤價/即時價
            # period='1d' 甚至 '5d' 都可以，取最後一筆
            hist = ticker.history(period="5d")
            
            if hist.empty:
                raise Exception("Yahoo Finance 返回數據為空 (Empty DataFrame)")
                
            # 取最後一筆 Close
            rate = hist['Close'].iloc[-1]
            
            # 嘗試獲取時間，若 index 是 datetime 則格式化
            last_time = hist.index[-1]
            if isinstance(last_time, (dt.datetime, pd.Timestamp)):
                date_str = last_time.strftime('%Y-%m-%d %H:%M:%S')
            else:
                date_str = str(last_time)
            
            print(f"   -> 成功: 1 USD = {rate:.4f} HKD (資料時間: {date_str})")
            return rate, date_str
            
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"   -> [最終失敗] 無法獲取匯率: {e}")
                break
            
            wait_s = min(5, 2 ** attempt)
            print(f"   -> 嘗試失敗 ({e})，{wait_s}秒後重試 ({attempt}/{MAX_RETRIES})...")
            time.sleep(wait_s)
            
    return None, None

if __name__ == "__main__":
    rate, ts = get_usdhkd_rate()
    if rate is not None:
        print(f"\n=== 結果 ===\n匯率: {rate}\n時間: {ts}")
    else:
        print("\n=== 結果 ===\n獲取失敗")

