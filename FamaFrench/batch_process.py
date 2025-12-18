import pandas as pd
import yfinance as yf
import statsmodels.api as sm
from statsmodels.regression.rolling import RollingOLS
import requests
import zipfile
import io
import numpy as np
import os
from datetime import datetime, timedelta

# ==========================================
# 1. 基礎設置與股票清單
# ==========================================

OUTPUT_FILE = "stock_factor_data1.csv"
INPUT_FILE = "stock_list.csv"


def load_stock_list():
    """從同目錄下的 stock_list.csv 讀取股票清單"""
    # 獲取目前腳本所在的資料夾路徑
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, INPUT_FILE)

    print(f"正在讀取股票清單: {file_path}")

    if not os.path.exists(file_path):
        print(f"錯誤: 找不到檔案 {INPUT_FILE}。請確保它與腳本在同一個資料夾。")
        return []

    try:
        # 修改點：header=0 代表第一行是標題，數據從第二行開始
        df = pd.read_csv(file_path, header=0, usecols=[0], dtype=str)

        # 修改點：使用 iloc[:, 0] 選取第一欄，不論標題叫什麼名字
        # 清洗數據: 轉字串 -> 去除前後空白 -> 轉大寫 -> 移除 NaN
        stock_list = df.iloc[:, 0].astype(str).str.strip().str.upper().dropna().tolist()

        # 移除可能的空字串 (例如 excel 裡看似空白的格子)
        stock_list = [x for x in stock_list if x and x != 'NAN']

        print(f"成功載入 {len(stock_list)} 支股票 (已略過標題行)。")
        return stock_list
    except Exception as e:
        print(f"讀取 CSV 發生錯誤: {e}")
        return []


# ==========================================
# 2. 核心功能函式
# ==========================================

def get_fama_french_daily():
    print("正在更新 Fama-French 因子數據...")
    ff5_url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
    mom_url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip"

    def fetch_and_clean(url, skip_rows):
        try:
            r = requests.get(url)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            csv_name = [n for n in z.namelist() if n.endswith('.csv')][0]
            df = pd.read_csv(z.open(csv_name), skiprows=skip_rows)
            df = df.rename(columns={"Unnamed: 0": "Date"})
            df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d', errors='coerce')
            df = df.dropna(subset=['Date']).set_index('Date')
            return df
        except Exception as e:
            print(f"下載失敗: {url} - {e}")
            return pd.DataFrame()

    df_ff5 = fetch_and_clean(ff5_url, 3)
    df_mom = fetch_and_clean(mom_url, 13)

    if df_ff5.empty or df_mom.empty:
        return None

    factors = df_ff5.join(df_mom, how='inner')
    factors.columns = [c.strip() for c in factors.columns]
    factors = factors / 100.0
    return factors


def get_stock_data_safe(ticker, start_date):
    """防彈版單一股票下載"""
    try:
        # 強制 auto_adjust=False 抓取原始數據
        df = yf.download(ticker, start=start_date, progress=False, auto_adjust=False)
        if df.empty: return None

        # 暴力搜尋價格欄位
        target_col = None
        cols = df.columns.values
        for col in cols:
            if isinstance(col, tuple) and 'Adj Close' in col:
                target_col = col;
                break
            elif 'Adj Close' == col:
                target_col = col;
                break

        if target_col is None:  # Fallback to Close
            for col in cols:
                if isinstance(col, tuple) and 'Close' in col:
                    target_col = col;
                    break
                elif 'Close' == col:
                    target_col = col;
                    break

        if target_col is None: return None

        stock = df[target_col]
        if isinstance(stock, pd.DataFrame): stock = stock.iloc[:, 0]
        return stock
    except Exception as e:
        print(f"Error downloading {ticker}: {e}")
        return None


def calculate_scores(betas):
    """計算 0-10 分數"""
    scores = {}
    scores['Score_Beta'] = np.clip(5 + (betas['Mkt-RF'] - 1) * 5, 0, 10)
    scores['Score_Size'] = np.clip(5 + betas['SMB'] * 4, 0, 10)  # High = Small Cap
    scores['Score_Value'] = np.clip(5 + betas['HML'] * 4, 0, 10)  # High = Value
    scores['Score_Mom'] = np.clip(5 + betas['Mom'] * 4, 0, 10)
    scores['Score_Quality'] = np.clip(5 + betas['RMW'] * 4, 0, 10)
    return scores


def assign_baskets(scores, raw_betas):
    """
    根據分數將股票歸類到不同的籃子 (Factor Baskets)。
    這是一個字串標籤生成器。
    """
    tags = []

    # --- Beta 標籤 ---
    if scores['Score_Beta'] >= 7.5:
        tags.append("Aggressive (High Beta)")
    elif scores['Score_Beta'] <= 3.0:
        tags.append("Defensive (Low Vol)")

    # --- Size 標籤 ---
    if scores['Score_Size'] >= 7.0:
        tags.append("Small Cap")
    elif scores['Score_Size'] <= 3.0:
        tags.append("Large Cap")

    # --- Style (Value/Growth) 標籤 ---
    if scores['Score_Value'] >= 7.0:
        tags.append("Deep Value")
    elif scores['Score_Value'] <= 3.0:
        tags.append("High Growth")

    # --- Momentum 標籤 ---
    if scores['Score_Mom'] >= 7.5:
        tags.append("High Momentum")
    elif scores['Score_Mom'] <= 2.5:
        tags.append("Falling Knife")

    # --- Quality 標籤 ---
    if scores['Score_Quality'] >= 7.0:
        tags.append("High Quality")
    elif scores['Score_Quality'] <= 3.0:
        tags.append("Speculative/Junk")

    return "; ".join(tags)  # 用分號隔開，方便 CSV 讀取


# ==========================================
# 3. 執行批次處理
# ==========================================

def main():
    # 0. 載入股票清單
    stock_list = load_stock_list()
    if not stock_list: return

    # 1. 準備因子數據
    factors = get_fama_french_daily()
    if factors is None: return

    results = []
    total_stocks = len(stock_list)
    # 抓取範圍：擴大到 5 年，確保有足夠數據跑 Rolling
    start_date = factors.index[-1] - timedelta(days=5 * 365)

    print(f"開始處理 {total_stocks} 支股票 (含 Rolling Analysis)...")
    print("-" * 50)

    for i, ticker in enumerate(stock_list):
        print(f"[{i + 1}/{total_stocks}] Processing {ticker}...", end=" ")

        # 抓取數據
        stock_price = get_stock_data_safe(ticker, start_date)

        # 改進 1: 只要有 6 個月 (約126天) 數據就允許處理
        if stock_price is None or len(stock_price) < 126:
            print("Skipped (上市時間太短)")
            continue

        stock_ret = stock_price.pct_change().dropna()
        common_idx = stock_ret.index.intersection(factors.index)

        # 改進 2: 放寬重疊門檻至 126 天
        if len(common_idx) < 126:
            print(f"Skipped (重疊數據不足: {len(common_idx)}天)")
            continue

        # --- A. 靜態回歸 (Static Regression) ---
        # 使用最近 3 年 (或所有可用數據)
        window_size = min(len(common_idx), 756)
        idx_static = common_idx[-window_size:]

        try:
            y = stock_ret.loc[idx_static] - factors.loc[idx_static, 'RF']
            X = factors.loc[idx_static, ['Mkt-RF', 'SMB', 'HML', 'Mom', 'RMW']]
            X = sm.add_constant(X)

            model = sm.OLS(y, X).fit()
            betas = model.params
            scores = calculate_scores(betas)
            baskets = assign_baskets(scores, betas)

            # --- B. 滾動回歸 (Rolling Window Analysis) ---
            # 計算 Rolling 12-Month (252 days) Beta
            roll_window = 252

            # 如果數據總長度不夠跑 Rolling (少於1年)，就填入空值或單點
            beta_trend_str = ""
            if len(common_idx) > roll_window:
                # 為了效能，我們只對 Mkt-RF 做 Rolling (CAPM Beta Trend)
                # 這樣比較快，也比較符合一般對 "Beta 走勢" 的定義
                y_roll = stock_ret.loc[common_idx] - factors.loc[common_idx, 'RF']
                X_roll = sm.add_constant(factors.loc[common_idx, 'Mkt-RF'])

                rols = RollingOLS(y_roll, X_roll, window=roll_window)
                rres = rols.fit()

                # 取出 Beta (Mkt-RF) 序列
                rolling_beta_series = rres.params['Mkt-RF'].dropna()

                # 數據減量 (Downsampling): 每月取樣一次，取最後 24 個月
                # 這樣 CSV 不會太大，但前端能畫出 2 年走勢
                monthly_trend = rolling_beta_series.resample('ME').last().tail(24)

                # 轉成字串 "1.2,1.15,1.3..."
                beta_trend_str = ",".join([f"{x:.2f}" for x in monthly_trend.values])
            else:
                # 數據不足，直接用靜態 Beta 當作唯一的一點
                beta_trend_str = f"{betas['Mkt-RF']:.2f}"

            # 整理結果
            row = {
                'Ticker': ticker,
                'Last_Date': idx_static[-1].strftime('%Y-%m-%d'),
                # 分數
                'Score_Beta': round(scores['Score_Beta'], 2),
                'Score_Size': round(scores['Score_Size'], 2),
                'Score_Value': round(scores['Score_Value'], 2),
                'Score_Mom': round(scores['Score_Mom'], 2),
                'Score_Quality': round(scores['Score_Quality'], 2),
                # 原始係數
                'Beta_Raw': round(betas['Mkt-RF'], 3),
                'SMB_Raw': round(betas['SMB'], 3),
                'HML_Raw': round(betas['HML'], 3),
                'Mom_Raw': round(betas['Mom'], 3),
                'RMW_Raw': round(betas['RMW'], 3),
                'Baskets': baskets,
                # 新增: Beta 歷史走勢
                'Beta_Trend': beta_trend_str
            }
            results.append(row)
            print("Done.")

        except Exception as e:
            print(f"Failed ({e})")

    # 4. 存檔
    if results:
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILE)
        df_results = pd.DataFrame(results)
        df_results.to_csv(output_path, index=False, encoding='utf-8-sig')
        print("-" * 50)
        print(f"處理完成！數據已儲存至: {output_path}")
        print(f"成功處理: {len(df_results)} / {total_stocks}")
    else:
        print("沒有產生任何結果。")


if __name__ == "__main__":
    main()