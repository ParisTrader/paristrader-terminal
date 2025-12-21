import yfinance as yf
import pandas as pd
from datetime import datetime
import os
csv_path = os.path.join("ThematicBasket", "thematic_basket.csv")
df = pd.read_csv(csv_path, encoding='ISO-8859-1')


def calculate_rsi(series, period=14):
    """標準 RSI 計算"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def get_live_metrics(ticker):
    try:
        stock = yf.Ticker(ticker)
        # 獲取市值數據
        info = stock.info
        hist = stock.history(period="60d")
        if hist.empty: return None

        # 格式化市值顯示
        mc_raw = info.get('marketCap', 0)
        if mc_raw >= 1e12:
            mc_formatted = f"${mc_raw / 1e12:.2f}T"
        elif mc_raw >= 1e9:
            mc_formatted = f"${mc_raw / 1e9:.2f}B"
        elif mc_raw >= 1e6:
            mc_formatted = f"${mc_raw / 1e6:.2f}M"
        else:
            mc_formatted = "N/A"

        avg_vol_30 = hist['Volume'].iloc[-31:-1].mean()
        curr_vol = hist['Volume'].iloc[-1]
        closes = hist['Close']

        today_pct = ((closes.iloc[-1] / closes.iloc[-2]) - 1) * 100
        five_day_pct = ((closes.iloc[-1] / closes.iloc[-6]) - 1) * 100
        rsi = calculate_rsi(closes).iloc[-1]
        rvol = curr_vol / avg_vol_30

        return {
            'Price': f"${closes.iloc[-1]:.2f}",
            'MarketCap': mc_formatted,
            'RVOL_val': rvol,
            'Today_val': today_pct,
            '5D_val': five_day_pct,
            'RSI_val': rsi
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None


# HTML 標頭：保留樣式並加入完整的兩段式教學板塊
html_header = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 40px; color: #1a1a1a; line-height: 1.6; }}

        /* 浮動視窗 (Tooltip) 樣式 */
        .ticker-cell {{ position: relative; cursor: help; color: #007bff; font-weight: bold; }}
        .tooltip-text {{
            visibility: hidden; width: 280px; background-color: #333; color: #fff;
            text-align: left; border-radius: 8px; padding: 12px; position: absolute;
            z-index: 999; bottom: 125%; left: 50%; margin-left: -140px; opacity: 0;
            transition: opacity 0.3s; box-shadow: 0 4px 15px rgba(0,0,0,0.3); font-size: 0.85em; font-weight: normal;
        }}
        .ticker-cell:hover .tooltip-text {{ visibility: visible; opacity: 1; }}

        /* 教育板塊樣式 */
        .edu-section {{ background: #fff; border: 2px solid #007bff; border-radius: 12px; padding: 25px; margin-bottom: 35px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
        .edu-title {{ font-size: 1.4em; font-weight: bold; color: #007bff; margin-bottom: 15px; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        .edu-part {{ margin-bottom: 20px; }}
        .edu-part h3 {{ color: #333; font-size: 1.1em; margin-bottom: 8px; }}
        .edu-part p {{ color: #555; font-size: 0.95em; margin: 5px 0; }}

        /* 數據卡片樣式 */
        .basket-card {{ background: white; border-radius: 12px; padding: 25px; margin-bottom: 35px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-top: 5px solid #007bff; }}
        .theme-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .theme-title {{ font-size: 1.3em; font-weight: bold; text-transform: uppercase; }}
        .consensus-badge {{ font-size: 0.85em; padding: 4px 10px; border-radius: 20px; font-weight: bold; }}
        .basket-perf {{ font-size: 1.1em; font-weight: bold; padding: 5px 12px; border-radius: 6px; }}

        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; padding: 12px; border-bottom: 2px solid #eee; color: #888; font-size: 0.75em; text-transform: uppercase; }}
        td {{ padding: 12px; border-bottom: 1px solid #f9f9f9; font-size: 0.9em; }}

        .pos {{ color: #28a745; font-weight: bold; }}
        .neg {{ color: #dc3545; font-weight: bold; }}
        .oversold {{ background: #d4edda; color: #155724; font-weight: bold; border-radius: 4px; padding: 2px 6px; }}
        .overbought {{ background: #f8d7da; color: #721c24; font-weight: bold; border-radius: 4px; padding: 2px 6px; }}
        .rel-strength {{ border-left: 5px solid #28a745; background-color: #f0fff4; }}
        .bullish {{ background: #d4edda; color: #155724; }}
        .bearish {{ background: #f8d7da; color: #721c24; }}
    </style>
</head>
<body>
    <h1>Elite Thematic Signal Dashboard</h1>
    <p style="color: #666;">數據更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <details class="edu-section" open>
        <summary style="font-size: 1.2em; font-weight: bold; cursor: pointer; color: #007bff;">🎓 新手必讀：如何解讀此分析頁面？ (點擊展開/收起)</summary>
        <div class="edu-content">

            <div class="edu-part">
                <div class="edu-title">第一階段：什麼是 Thematic Basket？為什麼要用？</div>
                <h3>什麼是主題籃子 (Basket)？</h3>
                <p>這是一種將相關股票分組的策略（例如：所有開發火箭技術的公司）。與其只押注一家公司，我們觀察整個「主題」。</p>
                <h3>為什麼要用 Basket？</h3>
                <p><strong>1. 分散風險：</strong> 避免單一公司因負面消息（例如 CEO 換人）導致大幅虧損。</p>
                <p><strong>2. 追蹤大資金：</strong> 機構投資者（如大銀行）通常是整組買入。跟隨籃子走勢，就是跟隨聰明錢 (Smart Money)。</p>
            </div>

            <div class="edu-part">
                <div class="edu-title">第二階段：實際操作指南 (Swing Trading)</div>
                <p><strong>1. 市值 (Market Cap)：</strong> 代表公司規模。大型股 ($10B+) 較穩定；中小型股潛力大但波動強。</p>
                <p><strong>2. 尋找「真領袖」 (Relative Strength)：</strong> 當籃子平均下跌 (RED)，但某股票上升 (GREEN)，該股票即為領袖，會標示為<strong>淺綠色背景</strong>。</p>
                <p><strong>3. RSI 抄底訊號：</strong> RSI < 35 (綠框) 為超賣反彈機會；RSI > 65 (紅框) 為過熱回調風險。</p>
                <p><strong>4. 浮動理由：</strong> 滑鼠移到 Ticker 上，即可查看該股票入選籃子的專業理由。</p>
            </div>

        </div>
    </details>
"""

content = ""
for theme, group in df.groupby('Theme'):
    stocks_data = []
    for _, row in group.iterrows():
        print(f"Loading {row['Ticker']}...")
        m = get_live_metrics(row['Ticker'])
        if m:
            stocks_data.append({**row.to_dict(), **m})

    if stocks_data:
        basket_avg = sum(s['Today_val'] for s in stocks_data) / len(stocks_data)
        pos_count = sum(1 for s in stocks_data if s['Today_val'] > 0)
        consensus_pct = (pos_count / len(stocks_data)) * 100

        if consensus_pct >= 70:
            badge = '<span class="consensus-badge bullish">🚀 強力看漲</span>'
        elif consensus_pct <= 30:
            badge = '<span class="consensus-badge bearish">⚠️ 注意風險</span>'
        else:
            badge = '<span class="consensus-badge" style="background:#eee;">⚖️ 走勢分歧</span>'

        perf_class = "pos" if basket_avg > 0 else "neg"
        content += f"""
        <div class="basket-card">
            <div class="theme-header">
                <div class="theme-title">{theme} {badge}</div>
                <div class="basket-perf {perf_class}">籃子今日平均: {basket_avg:+.2f}%</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>公司名稱</th>
                        <th>市值</th>
                        <th>現價</th>
                        <th>成交量比 (RVOL)</th>
                        <th>今日 %</th>
                        <th>5日累計 %</th>
                        <th>RSI (14)</th>
                    </tr>
                </thead>
                <tbody>"""

        for s in stocks_data:
            rs_class = "rel-strength" if s['Today_val'] > 0 and basket_avg < 0 else ""
            today_col = "pos" if s['Today_val'] > 0 else "neg"
            rsi_col = "oversold" if s['RSI_val'] <= 35 else ("overbought" if s['RSI_val'] >= 65 else "")

            content += f"""
            <tr class="{rs_class}">
                <td class="ticker-cell">
                    {s['Ticker']}
                    <span class="tooltip-text"><strong>選股理由：</strong><br>{s['Reason']}</span>
                </td>
                <td>{s['Company']}</td>
                <td style="color: #666;">{s['MarketCap']}</td>
                <td>{s['Price']}</td>
                <td>{s['RVOL_val']:.2f}x</td>
                <td class="{today_col}">{s['Today_val']:+.2f}%</td>
                <td class="{'pos' if s['5D_val'] > 0 else 'neg'}">{s['5D_val']:+.2f}%</td>
                <td><span class="{rsi_col}">{s['RSI_val']:.1f}</span></td>
            </tr>"""
        content += "</tbody></table></div>"

# Save to the specific folder
output_path = os.path.join("ThematicBasket", "elite_signal_dashboard.html")
with open(output_path, "w", encoding='utf-8') as f:
    f.write(html_header + content + "</body></html>")