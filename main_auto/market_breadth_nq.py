from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from matplotlib.ticker import PercentFormatter

# === YOUR 100-STOCK LIST (or keep it – works perfectly) ===
NQ_STOCKS = [
    "NVDA",
    "AAPL",
    "MSFT",
    "AVGO",
    "AMZN",
    "GOOG",
    "TSLA",
    "META",
    "NFLX",
    "COST",
    "AMD",
    "PLTR",
    "CSCO",
    "MU",
    "TMUS",
    "PEP",
    "LIN",
    "ISRG",
    "QCOM",
    "LRCX",
    "INTU",
    "AMGN",
    "AMAT",
    "SHOP",
    "APP",
    "BKNG",
    "INTC",
    "GILD",
    "KLAC",
    "TXN",
    "ADBE",
    "PANW",
    "CRWD",
    "HON",
    "ADI",
    "VRTX",
    "CEG",
    "MELI",
    "ADP",
    "CMCSA",
    "SBUX",
    "PDD",
    "CDNS",
    "ASML",
    "ORLY",
    "DASH",
    "MAR",
    "CTAS",
    "MRVL",
    "MDLZ",
    "REGN",
    "SNPS",
    "MNST",
    "CSX",
    "AEP",
    "ADSK",
    "TRI",
    "FTNT",
    "PYPL",
    "DDOG",
    "WBD",
    "IDXX",
    "MSTR",
    "ROST",
    "ABNB",
    "AZN",
    "EA",
    "PCAR",
    "WDAY",
    "NXPI",
    "ROP",
    "BKR",
    "XEL",
    "ZS",
    "FAST",
    "EXC",
    "AXON",
    "TTWO",
    "FANG",
    "CCEP",
    "PAYX",
    "CPRT",
    "KDP",
    "CTSH",
    "GEHC",
    "VRSK",
    "KHC",
    "MCHP",
    "CSGP",
    "ODFL",
    "CHTR",
    "TEAM",
    "BIIB",
    "DXCM",
    "LULU",
    "ON",
    "ARM",
    "CDW",
    "TTD",
    "GFS",
]

BASE_DIR = Path(__file__).resolve().parent


def generate_market_breadth_nq(output_png_path: str) -> str:
    """
    Generate the Nasdaq 100 market breadth chart and save it as a PNG.
    """
    output_path = Path(output_png_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("[INFO] Downloading 2 years of NDX constituent data (30-40 seconds)...")
    data = yf.download(NQ_STOCKS + ["^NDX"], period="2y", progress=False, auto_adjust=False, threads=True)
    if data.empty:
        raise RuntimeError("未能下载纳指成分股及指数数据。")

    try:
        close = data["Close"]
    except KeyError as exc:
        raise RuntimeError("下载的数据中缺少收盘价（Close）字段。") from exc

    if isinstance(close, pd.Series):
        raise RuntimeError("收盘价数据格式异常，无法获取多只股票的价格序列。")

    if "^NDX" not in close.columns:
        raise RuntimeError("收盘价数据中缺少 ^NDX 指数。")

    ndx = close["^NDX"]
    constituents = [ticker for ticker in NQ_STOCKS if ticker in close.columns]
    if not constituents:
        raise RuntimeError("未能匹配到任何纳指成分股的收盘价列。")

    sma20 = close[constituents].rolling(20).mean()
    above = close[constituents] > sma20
    valid = close[constituents].notna() & sma20.notna()
    breadth_pct = (above & valid).sum(axis=1) / valid.sum(axis=1) * 100

    breadth_pct = breadth_pct.dropna()
    ndx = ndx.reindex(breadth_pct.index).dropna()
    if breadth_pct.empty or ndx.empty:
        raise RuntimeError("无法计算纳指宽度指标，结果为空。")

    fig, ax1 = plt.subplots(figsize=(18, 10), facecolor="white")

    # NDX – thin black line (exactly like original)
    ax1.plot(ndx.index, ndx, color="black", linewidth=1.3)

    ax1.set_ylabel("Index Level", color="black", fontsize=16, fontweight="bold")
    ax1.tick_params(axis="y", labelcolor="black")

    ax2 = ax1.twinx()
    ax2.plot(breadth_pct.index, breadth_pct, color="#d32f2f", linewidth=1.6)

    ax2.set_ylabel("Breadth (%)", color="#d32f2f", fontsize=16, fontweight="bold")
    ax2.tick_params(axis="y", labelcolor="#d32f2f")
    ax2.set_ylim(0, 100)
    ax2.yaxis.set_major_formatter(PercentFormatter())

    plt.title("Nasdaq100 Market Breadth", fontsize=26, fontweight="bold", pad=40)
    fig.suptitle("ParisTrader", fontsize=12, color="#888888", x=0.98, y=0.93, ha="right")

    # X-axis
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=0, fontsize=12)

    # Background & grid
    ax1.set_facecolor("#fafafa")
    ax1.grid(True, color="white", linewidth=1.2, alpha=0.8)

    # Remove top/right borders
    for ax in [ax1, ax2]:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"[INFO] Nasdaq breadth chart saved to: {output_path}")
    return str(output_path)


def main() -> None:
    default_png = BASE_DIR / "market_breadth_nq.png"
    generate_market_breadth_nq(str(default_png))


if __name__ == "__main__":
    main()