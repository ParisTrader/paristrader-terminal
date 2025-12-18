from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from matplotlib.ticker import PercentFormatter

# === Current HSI 82 constituents (as of Nov 2025) ===
HSI_STOCKS = sorted(
    list(
        set(
            [
                "0005.HK",
                "0700.HK",
                "9988.HK",
                "1299.HK",
                "0939.HK",
                "2318.HK",
                "3690.HK",
                "1211.HK",
                "1810.HK",
                "9618.HK",
                "9961.HK",
                "9999.HK",
                "9888.HK",
                "1024.HK",
                "2269.HK",
                "3968.HK",
                "2020.HK",
                "0388.HK",
                "0001.HK",
                "0002.HK",
                "0003.HK",
                "0006.HK",
                "0011.HK",
                "0012.HK",
                "0016.HK",
                "0019.HK",
                "0066.HK",
                "0083.HK",
                "0267.HK",
                "0688.HK",
                "0823.HK",
                "0883.HK",
                "1088.HK",
                "1109.HK",
                "1378.HK",
                "1876.HK",
                "1928.HK",
                "1929.HK",
                "1997.HK",
                "2015.HK",
                "2382.HK",
                "2388.HK",
                "2628.HK",
                "2899.HK",
                "3328.HK",
                "3692.HK",
                "6098.HK",
                "6690.HK",
                "6862.HK",
                "9616.HK",
                "9688.HK",
                "9901.HK",
                "9966.HK",
                "9985.HK",
                "9992.HK",
                "1816.HK",
                "1918.HK",
                "2313.HK",
                "2319.HK",
                "3690.HK",
                "3968.HK",
                "6618.HK",
                "9999.HK",
                "1024.HK",
                "1810.HK",
                "9992.HK",
                "2269.HK",
                "9888.HK",
                "9988.HK",
                "0700.HK",
                "9618.HK",
            ]
        )
    )
)

BASE_DIR = Path(__file__).resolve().parent


def generate_market_breadth_hsi(output_png_path: str) -> str:
    """
    Generate the Hang Seng Index market breadth chart and save it as a PNG.
    """
    output_path = Path(output_png_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Downloading 2 years of data for {len(HSI_STOCKS)} HSI stocks + ^HSI...")
    data = yf.download(HSI_STOCKS + ["^HSI"], period="2y", progress=False, threads=True)
    if data.empty:
        raise RuntimeError("未能下载恒指成分股及指数数据。")

    try:
        close = data["Close"]
    except KeyError as exc:
        raise RuntimeError("下载的数据中缺少收盘价（Close）字段。") from exc

    if isinstance(close, pd.Series):
        raise RuntimeError("收盘价数据格式异常，无法获取多只股票的价格序列。")

    if "^HSI" not in close.columns:
        raise RuntimeError("收盘价数据中缺少 ^HSI 指数。")

    hsi = close["^HSI"]
    constituents = [ticker for ticker in HSI_STOCKS if ticker in close.columns]
    if not constituents:
        raise RuntimeError("未能匹配到任何恒指成分股的收盘价列。")

    sma20 = close[constituents].rolling(20).mean()
    above = close[constituents] > sma20
    valid = close[constituents].notna() & sma20.notna()
    breadth_pct = (above & valid).sum(axis=1) / valid.sum(axis=1) * 100

    breadth_pct = breadth_pct.dropna()
    hsi = hsi.reindex(breadth_pct.index).dropna()
    if breadth_pct.empty or hsi.empty:
        raise RuntimeError("无法计算恒指宽度指标，结果为空。")

    fig, ax1 = plt.subplots(figsize=(18, 10), facecolor="white")

    # HSI real level – thin black line
    ax1.plot(hsi.index, hsi, color="black", linewidth=1.3)
    ax1.set_ylabel("Index Level", color="black", fontsize=16, fontweight="bold")
    ax1.tick_params(axis="y", labelcolor="black")

    # Breadth % – thin red line
    ax2 = ax1.twinx()
    ax2.plot(breadth_pct.index, breadth_pct, color="#d32f2f", linewidth=1.6)
    ax2.set_ylabel("Breadth (%)", color="#d32f2f", fontsize=16, fontweight="bold")
    ax2.tick_params(axis="y", labelcolor="#d32f2f")
    ax2.set_ylim(0, 100)
    ax2.yaxis.set_major_formatter(PercentFormatter())

    # Title & signature
    plt.title("Hang Seng Index Market Breadth", fontsize=26, fontweight="bold", pad=40)
    fig.suptitle("ParisTrader", fontsize=12, color="#888888", x=0.98, y=0.93, ha="right")

    # X-axis
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=0, fontsize=12)

    # Style
    ax1.set_facecolor("#fafafa")
    ax1.grid(True, color="white", linewidth=1.2, alpha=0.8)

    for ax in [ax1, ax2]:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"[INFO] HSI market breadth chart saved to: {output_path}")
    return str(output_path)


def main() -> None:
    default_png = BASE_DIR / "market_breadth_hsi.png"
    generate_market_breadth_hsi(str(default_png))


if __name__ == "__main__":
    main()