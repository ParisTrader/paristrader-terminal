import yfinance as yf
import pandas as pd
import os

# --- 1. CONFIGURATION (設定指標參數與定義) ---
metrics_config = {
    'VIX': {
        'ticker': '^VIX',
        'min': 10, 'max': 35,
        'def': '<b>VIX (恐慌指數)</b><br>衡量未來30天市場預期的波動程度。<br>數值越高代表投資人預期會有大漲或大跌。'
    },
    'Skew': {
        'ticker': '^SKEW',
        'min': 0, 'max': 100,  # 使用百分比排行
        'def': '<b>Skew (黑天鵝指數)</b><br>衡量市場對「崩盤保險」(Put) 的需求。<br>數值越高，代表防範暴跌的避險成本越貴。'
    },
    'VVIX': {
        'ticker': '^VVIX',
        'min': 70, 'max': 120,
        'def': '<b>VVIX (波動率的波動)</b><br>衡量 VIX 指數本身的不穩定程度。<br>可以用來判斷 VIX 是否即將出現劇烈跳動。'
    },
    'VIX-VIX3M': {
        'ticker': None,
        'min': -5, 'max': 5,
        'def': '<b>期限結構 (Term Structure)</b><br>比較「短期恐慌」與「中期恐慌」。<br>正常情況下長期風險應高於短期，若倒掛代表現在有危機。'
    }
}

data = {}


# --- 2. HELPER FUNCTIONS (抓取數據與計算) ---

def get_latest_price(ticker):
    try:
        df = yf.Ticker(ticker).history(period='1d')
        if not df.empty:
            return df['Close'].iloc[-1].item()
    except:
        return 0.0
    return 0.0


def calculate_percentile(ticker):
    """計算百分位數 (PR值)：目前的數值贏過過去一年多少天"""
    try:
        hist = yf.Ticker(ticker).history(period='1y')
        if hist.empty: return 0.0
        current = hist['Close'].iloc[-1].item()
        hist = hist[hist['Close'] > 0]
        days_lower = hist[hist['Close'] < current].shape[0]
        return (days_lower / hist.shape[0]) * 100
    except:
        return 0.0


def get_market_insight(name, value):
    """
    Returns: (Status Title, Detailed Description, Color Hex)
    """
    # Colors
    c_red = "#ef5350"  # Danger
    c_orange = "#ffca28"  # Caution
    c_green = "#66bb6a"  # Safe
    c_blue = "#42a5f5"  # Complacent/Bullish
    c_text = "#b2b5be"  # Neutral

    if name == 'VIX':
        if value < 15.78:
            return ("過度安逸 (Complacency)",
                    "市場對風險毫無防備，投資人過於樂觀。這通常是暴風雨前的寧靜，需提防市場突然反轉。", c_blue)
        if value < 20:
            return ("正常波動 (Normal)",
                    "市場處於健康的波動範圍，投資人情緒穩定，沒有過度的恐慌或貪婪。", c_green)
        if value < 24:
            return ("情緒緊張 (Elevated Fear)",
                    "市場開始感到不安，避險需求增加。預期每日股市震盪幅度會擴大。", c_orange)
        return ("極度恐慌 (Panic Mode)",
                "市場正處於拋售潮，投資人不計代價購買保護。這通常發生在股市大跌期間。", c_red)

    if name == 'Skew':
        # Input is Percentile (0-100)
        if value < 20:
            return ("毫無避險意識 (Bullish)",
                    "幾乎沒有人在買崩盤保險(Put)，市場一面倒看多。注意「樂極生悲」的反轉風險。", c_blue)
        if value < 80:
            return ("正常避險 (Normal)",
                    "機構正常的買進避險保護，沒有出現異常的恐慌性避險。", c_text)
        return ("黑天鵝警戒 (High Tail Risk)",
                "機構正在瘋狂搶購崩盤保險(Put)。這暗示大戶極度擔心近期會發生突發性崩盤。", c_red)

    if name == 'VVIX':
        if value < 85:
            return ("結構穩定 (Stable)",
                    "恐慌指數(VIX)本身很穩定，市場風險是可以預測的。", c_green)
        if value < 110:
            return ("波動加劇 (Shifting)",
                    "VIX 開始變得不穩定，暗示市場趨勢可能即將改變。", c_orange)
        return ("極不穩定 (Volatile)",
                "VIX 指數隨時可能暴衝。這代表風險極難預測，建議減少槓桿。", c_red)

    if name == 'VIX-VIX3M':
        if value < -1:
            return ("結構健康 (Contango)",
                    "短期風險低於長期風險，這是牛市的正常狀態。", c_green)
        if value <= 0:
            return ("趨勢轉平 (Flattening)",
                    "短期恐慌開始上升，市場猶豫不決，需密切觀察是否轉為倒掛。", c_orange)
        return ("結構倒掛 (Inverted / Danger)",
                "警報！短期恐慌大於長期恐慌。這代表市場正在發生立即性的危機，通常伴隨股市重挫。", c_red)

    return ("", "", c_text)


# --- 3. MAIN LOGIC ---
print("Fetching Market Data...")

data['VIX'] = round(get_latest_price('^VIX'), 2)
data['VVIX'] = round(get_latest_price('^VVIX'), 2)
print("Calculating Skew Rank...")
data['Skew'] = round(calculate_percentile('^SKEW'), 2)

vix3m = get_latest_price('^VIX3M')
if data['VIX'] and vix3m:
    data['VIX-VIX3M'] = round(data['VIX'] - vix3m, 2)
else:
    data['VIX-VIX3M'] = 0.0


# --- 4. HTML GENERATION ---
def calculate_bar_pct(value, min_val, max_val):
    if value <= min_val: return 0
    if value >= max_val: return 100
    return ((value - min_val) / (max_val - min_val)) * 100


html_rows = ""
for name, config in metrics_config.items():
    val = data.get(name, 0)
    pct = calculate_bar_pct(val, config['min'], config['max'])

    # Get Text Insights
    title, desc, color = get_market_insight(name, val)
    definition = config['def']

    html_rows += f"""
    <div class="row">
        <div class="col-label">
            <span class="label-text">{name}</span>
            <div class="tooltip-container">
                <div class="info-icon">i</div>
                <div class="tooltip-text">{definition}</div>
            </div>
        </div>

        <div class="col-chart">
            <div class="value">{val}</div>
            <div class="bar-container">
                <div class="gradient-bar"></div>
                <div class="marker" style="left: {pct}%;">▼</div>
            </div>
        </div>

        <div class="col-text" style="border-left: 3px solid {color};">
            <div class="status-title" style="color: {color};">{title}</div>
            <div class="status-desc">{desc}</div>
        </div>
    </div>
    """

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            background-color: #0b0e14;
            color: #ffffff;
            font-family: "Microsoft JhengHei", "Heiti TC", sans-serif; /* Optimized for Chinese */
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }}
        .card {{
            background-color: #131722;
            border: 1px solid #2a2e39;
            border-radius: 8px;
            padding: 30px;
            width: 850px; /* Wide card */
            box-shadow: 0 4px 15px rgba(0,0,0,0.6);
        }}
        h2 {{
            text-align: center;
            font-size: 22px;
            margin-top: 0;
            margin-bottom: 30px;
            color: #e1e3e6;
            letter-spacing: 1px;
        }}
        .row {{
            display: flex;
            align-items: center;
            margin-bottom: 25px; /* Spacing between rows */
        }}

        /* --- Column 1: Label & Tooltip --- */
        .col-label {{
            width: 130px;
            display: flex;
            align-items: center;
        }}
        .label-text {{
            font-weight: 700;
            font-size: 16px;
            color: #b2b5be;
            margin-right: 8px;
        }}
        .tooltip-container {{
            position: relative;
            cursor: pointer;
        }}
        .info-icon {{
            width: 18px;
            height: 18px;
            background-color: #2a2e39;
            color: #787b86;
            border-radius: 50%;
            font-size: 12px;
            font-weight: bold;
            font-family: serif;
            display: flex;
            justify-content: center;
            align-items: center;
            transition: 0.2s;
        }}
        .info-icon:hover {{
            background-color: #2962ff;
            color: white;
        }}
        .tooltip-text {{
            visibility: hidden;
            width: 250px;
            background-color: #1e222d;
            color: #d1d4dc;
            text-align: left;
            border-radius: 6px;
            padding: 12px;
            position: absolute;
            z-index: 100;
            bottom: 140%;
            left: 50%;
            transform: translateX(-20%);
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 13px;
            line-height: 1.5;
            box-shadow: 0 4px 10px rgba(0,0,0,0.5);
            border: 1px solid #363a45;
            pointer-events: none;
        }}
        .tooltip-container:hover .tooltip-text {{
            visibility: visible;
            opacity: 1;
        }}

        /* --- Column 2: Chart --- */
        .col-chart {{
            width: 250px;
            margin-right: 40px;
        }}
        .value {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 8px;
            font-family: 'Consolas', monospace;
            text-align: right;
        }}
        .bar-container {{
            position: relative;
            width: 100%;
            height: 8px;
            background-color: #2a2e39;
            border-radius: 4px;
        }}
        .gradient-bar {{
            width: 100%;
            height: 100%;
            border-radius: 4px;
            background: linear-gradient(90deg, #26a69a 0%, #ffeb3b 50%, #ef5350 100%);
        }}
        .marker {{
            position: absolute;
            top: -16px;
            font-size: 14px;
            color: #ffffff;
            transform: translateX(-50%);
            text-shadow: 0 1px 2px black;
        }}

        /* --- Column 3: Insight Text --- */
        .col-text {{
            flex-grow: 1;
            padding-left: 20px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .status-title {{
            font-size: 15px;
            font-weight: 700;
            margin-bottom: 4px;
            text-transform: uppercase;
        }}
        .status-desc {{
            font-size: 14px;
            color: #9db2bd;
            line-height: 1.4;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h2>標普美盤風險儀表板 (S&P500 Market Risk Dashboard)</h2>
        {html_rows}
    </div>
</body>
</html>
"""

output_file = "implied_params.html"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"\n[成功] 已生成最終版 HTML: {os.path.abspath(output_file)}")