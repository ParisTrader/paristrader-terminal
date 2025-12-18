import argparse
import base64
import html
import io
import os
import platform
import time

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import requests
import yfinance as yf

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '8523931731:AAEtoq7TfO-sr9BIAUe-G9FvETj0_g7NMIc'
CHAT_ID = '-1003261897616'
TOPIC_ID = 4725
TARGET_TIMEZONE = 'Asia/Hong_Kong'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
DEFAULT_HTML_OUTPUT = os.path.join(OUTPUT_DIR, 'intraday_volatility.html')
MODE_CHOICES = ('mode1', 'mode2')
DEFAULT_MODE = 'mode2'
# Optional manual override; set to 'mode1' or 'mode2' to ignore CLI flag
MODE_OVERRIDE = 'mode1'

TARGETS = [
    {'symbol': 'GC=F', 'name': 'Gold (GC Futures)', 'desc': '24h Global Market'},
    {'symbol': 'NQ=F', 'name': 'Nasdaq 100 (NQ Futures)', 'desc': 'US Tech Giants'},
    {'symbol': '^HSI', 'name': 'Hang Seng Index (Spot)', 'desc': 'HK Market (Day Only)'}
]


def send_to_telegram(image_buffer, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    image_buffer.seek(0)
    files = {'photo': ('chart.png', image_buffer, 'image/png')}
    data = {'chat_id': CHAT_ID, 'message_thread_id': TOPIC_ID, 'caption': caption}
    try:
        response = requests.post(url, files=files, data=data)
        if response.status_code == 200:
            print(" -> Sent to Telegram successfully.")
        else:
            print(f" -> Failed. Telegram Response: {response.text}")
    except Exception as e:
        print(f" -> Error sending: {e}")


def save_html_report(sections, output_path=DEFAULT_HTML_OUTPUT):
    """
    Build a lightweight HTML file so users can review the same charts/captions without Telegram.
    """
    if not sections:
        print("No sections to include in the HTML report.")
        return

    generated_at = time.strftime('%Y-%m-%d %H:%M:%S')
    section_html = []
    for entry in sections:
        caption_html = html.escape(entry['caption']).replace('\n', '<br>')
        desc_html = html.escape(entry.get('desc', ''))
        section_html.append(
            f"""
            <section class="card">
                <h2>{html.escape(entry['name'])}</h2>
                <p class="desc">{desc_html}</p>
                <img src="data:image/png;base64,{entry['image_base64']}" alt="{html.escape(entry['name'])} chart">
                <div class="caption">{caption_html}</div>
            </section>
            """
        )

    document = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Intraday Volatility Guide</title>
        <style>
            body {{
                font-family: Arial, "Microsoft JhengHei", sans-serif;
                background: #f4f6f8;
                margin: 0;
                padding: 20px;
                color: #2c3e50;
            }}
            h1 {{
                text-align: center;
            }}
            .meta {{
                text-align: center;
                margin-bottom: 20px;
                color: #7f8c8d;
            }}
            .card {{
                background: #fff;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 24px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
            }}
            .card img {{
                width: 100%;
                border-radius: 6px;
                margin: 16px 0;
            }}
            .caption {{
                font-size: 0.95rem;
                line-height: 1.6;
            }}
            .desc {{
                font-style: italic;
                color: #7f8c8d;
            }}
        </style>
    </head>
    <body>
        <h1>Intraday Volatility Guide</h1>
        <div class="meta">Generated at {generated_at} | Timezone: {TARGET_TIMEZONE}</div>
        {''.join(section_html)}
    </body>
    </html>"""

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as html_file:
        html_file.write(document)

    print(f"\nHTML report saved to {output_path}")


def plot_intraday_zones(target, mode='mode2', html_sections=None):
    ticker_symbol = target['symbol']
    nice_name = target['name']

    # 1. Setup Fonts
    system_name = platform.system()
    if system_name == "Windows":
        plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei']
    elif system_name == "Darwin":
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS']
    else:
        plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
    plt.rcParams['axes.unicode_minus'] = False

    print(f"\nProcessing {nice_name} ({ticker_symbol})...")

    # 2. Download Data
    try:
        # 下載 59 天的 15 分鐘數據
        df = yf.download(ticker_symbol, period="59d", interval="15m", progress=False, auto_adjust=True)
    except Exception as e:
        print(f"Error downloading {ticker_symbol}: {e}")
        return

    if df.empty:
        print(f"No data found for {ticker_symbol}. (Yahoo API issue)")
        return

    # Fix MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 3. Timezone Conversion
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')

    df.index = df.index.tz_convert(TARGET_TIMEZONE)

    # --- FIX: REMOVE VOLUME FILTER ---
    # 不要用 Volume > 0 過濾，因為 ^HSI 的 Volume 常常是 0
    # 我們改用簡單的dropna，確保 High/Low 都有數值即可
    df = df.dropna(subset=['High', 'Low'])

    # 額外檢查：如果 High == Low (數據不動)，也可以視為無效並濾除
    # 但對於 15分K 來說，偶爾 High=Low 是可能的，所以我們只濾除極端值
    df = df[df['High'] > 0]

    # 5. Calculate Range
    df['Range'] = df['High'] - df['Low']

    # 6. Group by Time
    df['TimeStr'] = df.index.strftime('%H:%M')
    intraday_vol = df.groupby('TimeStr')['Range'].mean()

    # Double check data validity
    if intraday_vol.empty or intraday_vol.sum() == 0:
        print(f"Data invalid for {ticker_symbol} (all ranges are 0 or empty).")
        return

    # --- COLOR LOGIC ---
    threshold_grey = intraday_vol.quantile(0.50)
    threshold_red = intraday_vol.quantile(0.80)

    colors = []
    for val in intraday_vol.values:
        if val >= threshold_red:
            colors.append('#c0392b')  # Red
        elif val <= threshold_grey:
            colors.append('#95a5a6')  # Grey
        else:
            colors.append('#f39c12')  # Orange

    # 7. Plotting
    fig, ax = plt.subplots(figsize=(14, 7))
    bars = ax.bar(intraday_vol.index, intraday_vol.values, color=colors, alpha=0.9, width=0.8)

    # X-Axis Adjustment
    # HSI 的 bar 比較少，我們每 2 格 (30分) 標示一次
    # GC/NQ 比較多，每 4 格 (1小時) 標示一次
    if len(intraday_vol) < 40:
        locator_interval = 2
    else:
        locator_interval = 4

    ax.xaxis.set_major_locator(ticker.MultipleLocator(locator_interval))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=9)

    ax.set_title(f'{nice_name} "Hunt vs Trap" Zones ({TARGET_TIMEZONE})', fontsize=16, weight='bold')
    ax.set_ylabel('Avg 15m Range (Points)', fontsize=12)
    ax.set_xlabel(f'Time of Day ({TARGET_TIMEZONE})', fontsize=12)
    ax.grid(True, axis='y', linestyle='--', alpha=0.3)

    # Threshold Line
    ax.axhline(y=threshold_grey, color='gray', linestyle=':', linewidth=1.5, alpha=0.7)
    ax.text(0, threshold_grey, '  Trap Zone Limit (Median)', color='gray', fontsize=9, va='bottom', ha='left')

    # Watermark
    ax.text(0.98, 0.95, 't.me/AlgoParisTrader', transform=ax.transAxes,
            fontsize=12, color='grey', alpha=0.5, ha='right', va='top', style='italic', weight='bold')

    plt.tight_layout()

    # 8. Export
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)

    best_time = intraday_vol.idxmax()

    note = ""
    if 'HSI' in ticker_symbol:
        note = "(註：使用現貨數據，僅涵蓋日間盤 09:30-16:00)\n"

    caption = (
        f"🔥 *{nice_name} Intraday Volatility Guide*\n"
        f"🕒 Timezone: {TARGET_TIMEZONE}\n"
        f"🎯 *Best Hunting Time:* {best_time}\n"
        f"{note}\n"
        f"🟥 *Red Bars (Hunt Zone - Top 20%):*\n"
        f"菁英時段。動能充足，適合 Breakout，TP 觸發率高。\n\n"
        f"⬜ *Grey Bars (Trap Zone - Bottom 50%):*\n"
        f"垃圾時間/陷阱區。\n"
        f"⚠️ *Why Avoid?*\n"
        f"1. Range 太窄，利潤不夠付點差。\n"
        f"2. 無方向震盪，易掃 SL。\n"
        f"3. 浪費時間。\n\n"
        f"👉 *建議：灰色時段嚴格空倉。*\n"
        f"👉 *愛你們的*\n"
        f"🔗 t.me/AlgoParisTrader"
    )

    if mode == 'mode2':
        send_to_telegram(buf, caption)
        time.sleep(1)
    elif mode == 'mode1':
        if html_sections is None:
            raise ValueError("html_sections collection is required for mode1.")
        buf.seek(0)
        encoded_image = base64.b64encode(buf.getvalue()).decode('utf-8')
        html_sections.append(
            {
                'name': nice_name,
                'desc': target.get('desc', ''),
                'caption': caption,
                'image_base64': encoded_image
            }
        )
        print(" -> Added to HTML report queue.")
    else:
        raise ValueError(f"Unknown mode '{mode}'. Valid options: {MODE_CHOICES}")


def parse_args():
    parser = argparse.ArgumentParser(description="Intraday Volatility visualizer")
    parser.add_argument(
        '--mode',
        default=DEFAULT_MODE,
        choices=MODE_CHOICES,
        help='mode1: generate HTML report, mode2: push to Telegram'
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_HTML_OUTPUT,
        help='HTML output path when mode1 is selected'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if MODE_OVERRIDE:
        if MODE_OVERRIDE not in MODE_CHOICES:
            raise ValueError(f"MODE_OVERRIDE must be one of {MODE_CHOICES}.")
        print(f"MODE_OVERRIDE detected -> Forcing mode '{MODE_OVERRIDE}'")
        args.mode = MODE_OVERRIDE
    html_sections = []

    print("Starting Multi-Asset Volatility Analysis...")
    for target in TARGETS:
        try:
            plot_intraday_zones(target, mode=args.mode, html_sections=html_sections)
        except Exception as e:
            print(f"Error processing {target['name']}: {e}")
    if args.mode == 'mode1':
        save_html_report(html_sections, args.output)
    print("\nProcessing completed.")