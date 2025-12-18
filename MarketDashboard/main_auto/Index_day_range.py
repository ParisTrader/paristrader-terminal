import argparse
import html
import io
import platform
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import requests
import yfinance as yf

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '8523931731:AAEtoq7TfO-sr9BIAUe-G9FvETj0_g7NMIc'
CHAT_ID = '-1003261897616'
TOPIC_ID = 4725

# Mode configuration (mode1 saves locally, mode2 sends to Telegram)
DEFAULT_MODE = 'mode1'

# 定義要分析的代號
TICKERS = {
    '^HSI': 'Hang Seng Index (HSI)',
    '^GSPC': 'S&P 500 (SPX)',
    '^NDX': 'Nasdaq 100 (NDX)',
    'GC=F': 'Gold Futures (Gold)'
}


def send_to_telegram(image_buffer, caption):
    """Sends the image stored in the buffer to the specific Telegram Topic."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    image_buffer.seek(0)
    files = {'photo': ('chart.png', image_buffer, 'image/png')}
    data = {'chat_id': CHAT_ID, 'message_thread_id': TOPIC_ID, 'caption': caption}

    try:
        response = requests.post(url, files=files, data=data)
        if response.status_code != 200:
            print(f" -> Failed to send to Telegram. Error: {response.text}")
    except Exception as e:
        print(f" -> Error sending to Telegram: {e}")


def get_true_range_data(ticker):
    """
    獲取數據邏輯：
    - 黃金期貨 (GC=F): 下載 1小時 (60m) 數據並重新合併為日線，以包含完整 24小時波動。
    - 指數: 下載日線數據 (1d)。
    """
    # 1. 黃金期貨特殊處理 (抓取全天候數據)
    if ticker == 'GC=F':
        print(f"   -> Fetching 1-hour intraday data for {ticker} to capture full 24h range...")
        # Yahoo Intraday 限制約 60 天
        df_hourly = yf.download(ticker, period="59d", interval="60m", progress=False, auto_adjust=True)

        if df_hourly.empty:
            return pd.DataFrame()

        if isinstance(df_hourly.columns, pd.MultiIndex):
            df_hourly.columns = df_hourly.columns.get_level_values(0)

        # 建立日期欄位進行分組 (忽略時間)
        df_hourly['DateStr'] = df_hourly.index.date

        # 聚合：找出每個日曆日的最高 High 和最低 Low
        daily_df = df_hourly.groupby('DateStr').agg({
            'High': 'max',
            'Low': 'min',
            'Close': 'last'
        })

        # 轉回 DatetimeIndex 格式以便繪圖
        daily_df.index = pd.to_datetime(daily_df.index)
        daily_df.sort_index(inplace=True)
        return daily_df

    # 2. 一般指數處理 (日線)
    else:
        df = yf.download(ticker, period="60d", interval="1d", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df


def generate_and_send_chart(ticker, nice_name, mode):
    # 設定字體 (支援中文顯示)
    system_name = platform.system()
    if system_name == "Windows":
        plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei']
    elif system_name == "Darwin":
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang HK']
    else:
        plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
    plt.rcParams['axes.unicode_minus'] = False

    print(f"\nProcessing {nice_name} ({ticker})...")

    # --- 獲取數據 ---
    raw_df = get_true_range_data(ticker)

    if raw_df.empty:
        print(f"No data found for {ticker}.")
        return

    # --- 計算指標 ---
    raw_df['Range'] = raw_df['High'] - raw_df['Low']

    # 5日移動平均 (趨勢線)
    raw_df['SMA_5'] = raw_df['Range'].rolling(window=5).mean()

    # 只取最後 30 筆交易日進行繪圖
    df = raw_df.iloc[-30:].copy()

    # 計算 30日平均 (基準線)
    avg_volatility = df['Range'].mean()
    current_vol = df['Range'].iloc[-1]

    # 判斷狀態 (Active / Quiet)
    if current_vol > avg_volatility:
        status_text = "Status: ACTIVE (Volatile)"
        status_color = '#c0392b'  # 紅色
        caption_status = "⚠️ Active/Volatile"
    else:
        status_text = "Status: QUIET"
        status_color = '#7f8c8d'  # 灰色
        caption_status = "✅ Quiet"

    # --- 繪圖開始 ---
    fig, ax = plt.subplots(figsize=(13, 7))

    # 柱狀圖顏色邏輯
    bar_colors = ['#bdc3c7' if r < avg_volatility else '#e74c3c' for r in df['Range']]

    # 畫柱狀圖
    bars = ax.bar(df.index, df['Range'], color=bar_colors, alpha=0.85)

    # 畫基準線 (藍色虛線)
    ax.axhline(y=avg_volatility, color='blue', linestyle='--', linewidth=2, alpha=0.8)

    # 畫趨勢線 (黑色實線)
    ax.plot(df.index, df['SMA_5'], color='black', linewidth=2.5, marker='o', markersize=4, zorder=5)

    # 標示數值
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2., height + (height * 0.02),
                f'{int(height)}',
                ha='center', va='bottom', fontsize=8, color='black')

    # 標題與標籤
    ax.set_title(f'{nice_name} Volatility (波幅趨勢) - Last 30 Days', fontsize=16, weight='bold')
    ax.set_ylabel('True Range (High - Low)', fontsize=12)
    ax.grid(True, axis='y', linestyle='--', alpha=0.3)

    # X軸日期格式
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    # 圖例 (Legend)
    legend_elements = [
        mpatches.Patch(color='#e74c3c', label='Above Avg (Active)'),
        mpatches.Patch(color='#bdc3c7', label='Below Avg (Quiet)'),
        plt.Line2D([0], [0], color='blue', lw=2, linestyle='--', label=f'30-Day Avg ({int(avg_volatility)} pts)'),
        plt.Line2D([0], [0], color='black', lw=2.5, marker='o', label='5-Day Trend')
    ]
    ax.legend(handles=legend_elements, loc='upper left', framealpha=0.9)

    # --- 右上角狀態框 ---
    # 使用 transAxes 座標系 (0,0 為左下, 1,1 為右上)
    ax.text(0.98, 0.95, status_text, transform=ax.transAxes,
            fontsize=14, weight='bold', color='white', ha='right', va='top',
            bbox=dict(boxstyle="round,pad=0.4", facecolor=status_color, edgecolor='none', alpha=0.9))

    # --- 加入水印 (Watermark) ---
    # 放在狀態框的下方 (y=0.88 左右)
    ax.text(0.98, 0.88, 't.me/AlgoParisTrader', transform=ax.transAxes,
            fontsize=12, color='grey', alpha=0.6, ha='right', va='top', style='italic', weight='bold')

    plt.tight_layout()

    # --- 儲存並發送 ---
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)

    caption = f"📊 *{nice_name}* Volatility Report\n" \
              f"📅 Date: {df.index[-1].strftime('%Y-%m-%d')}\n" \
              f"📉 Current Range: {int(current_vol)}\n" \
              f"📏 30-Day Avg: {int(avg_volatility)}\n" \
              f"📢 {caption_status}\n" \
              f"🔗 t.me/AlgoParisTrader"

    if mode == 'mode1':
        output_dir = Path(__file__).parent / 'output'
        output_dir.mkdir(exist_ok=True)

        safe_ticker = (
            ticker.replace('^', '')
            .replace('/', '_')
            .replace('=', '-')
        )
        output_filename = f"{safe_ticker}_{df.index[-1].strftime('%Y%m%d')}.png"
        output_path = output_dir / output_filename

        buf.seek(0)
        with open(output_path, 'wb') as image_file:
            image_file.write(buf.read())

        print(f" -> Chart saved to {output_path}")
        return {
            'image_path': output_path,
            'caption': caption,
            'nice_name': nice_name,
            'ticker': ticker,
        }
    else:
        send_to_telegram(buf, caption)
        return None


def generate_html_report(entries):
    if not entries:
        print("No charts generated; skipping HTML report.")
        return

    output_dir = Path(__file__).parent / 'output'
    output_dir.mkdir(exist_ok=True)
    html_path = output_dir / 'index.html'

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='UTF-8' />",
        f"<title>Volatility Report - {timestamp}</title>",
        "<style>",
        "body {font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 24px;}",
        "h1 {text-align: center;}",
        ".timestamp {text-align: center; color: #666; margin-bottom: 32px;}",
        ".container {display: flex; flex-direction: column; gap: 24px; max-width: 1000px; margin: 0 auto;}",
        ".card {background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.08);}",
        ".card h2 {margin-top: 0;}",
        ".card img {width: 100%; height: auto; border-radius: 8px; margin-top: 12px;}",
        ".caption {margin-top: 16px; line-height: 1.5; color: #2c3e50;}",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Volatility Report</h1>",
        f"<p class='timestamp'>Generated at {timestamp}</p>",
        "<div class='container'>",
    ]

    for entry in entries:
        rel_path = entry['image_path'].name
        safe_title = html.escape(f"{entry['nice_name']} ({entry['ticker']})")
        safe_caption = html.escape(entry['caption']).replace('\n', '<br>')
        card_html = (
            "<div class='card'>"
            f"<h2>{safe_title}</h2>"
            f"<img src=\"{rel_path}\" alt=\"{safe_title}\">"
            f"<p class='caption'>{safe_caption}</p>"
            "</div>"
        )
        html_parts.append(card_html)

    html_parts.extend(["</div>", "</body>", "</html>"])

    html_content = ''.join(html_parts)
    html_path.write_text(html_content, encoding='utf-8')
    print(f" -> HTML report saved to {html_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate volatility reports.")
    parser.add_argument(
        '--mode',
        choices=['mode1', 'mode2'],
        default=None,
        help="mode1: save images to ./output; mode2: send to Telegram",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_mode = args.mode or DEFAULT_MODE
    print(f"Starting Analysis Job in {run_mode} ...")

    mode1_entries = []
    for ticker, name in TICKERS.items():
        try:
            result = generate_and_send_chart(ticker, name, run_mode)
            if result:
                mode1_entries.append(result)
        except Exception as e:
            print(f"Error processing {name}: {e}")

    if run_mode == 'mode1':
        generate_html_report(mode1_entries)

    print("\nAll jobs finished.")