from pathlib import Path
from datetime import datetime, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent


def generate_spx_vix_chart(output_png_path: str) -> str:
    """
    Generate the SPX vs VIX scatter plot and save it as a PNG.
    """
    output_path = Path(output_png_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=100)  # little buffer

    print("[INFO] Downloading SPX and VIX data (~100 calendar days)...")
    spx = yf.download("^GSPC", start=start_date, end=end_date, progress=False, auto_adjust=False, threads=False)
    vix = yf.download("^VIX", start=start_date, end=end_date, progress=False, auto_adjust=False, threads=False)

    missing_assets = []
    if spx.empty:
        missing_assets.append("S&P 500 (^GSPC)")
    if vix.empty:
        missing_assets.append("VIX (^VIX)")

    if missing_assets:
        raise RuntimeError(f"未能获取以下资产数据：{', '.join(missing_assets)}。")

    # ==================== Daily % changes ====================
    spx["pct"] = spx["Close"].pct_change() * 100
    vix["pct"] = vix["Close"].pct_change() * 100

    spx_pct = spx["pct"].rename("SPX_%")
    vix_pct = vix["pct"].rename("VIX_%")

    df = (
        pd.concat([spx_pct, vix_pct], axis=1, join="inner")
        .dropna()
        .reset_index()
        .rename(columns={"index": "Date"})
    )

    if df.empty:
        raise RuntimeError("清洗后的 SPX/VIX 数据为空，无法绘图。")

    if len(df) < 5:
        raise RuntimeError(f"绘图至少需要 5 个交易日，但当前只有 {len(df)} 个。")

    # ==================== Plot ====================
    fig = plt.figure(figsize=(12, 8))

    # All older points (light gray)
    plt.scatter(
        df["SPX_%"][:-5],
        df["VIX_%"][:-5],
        color="lightgray",
        alpha=0.8,
        s=60,
        label="Earlier days",
    )

    # Last 5 trading days (red → yellow gradient)
    colors = [
        "#ffff66",  # 淺黃
        "#ffaa33",  # 中橘
        "#ff6600",  # 橘
        "#ff3300",  # 橘紅
        "#cc0000",  # 深紅
    ]
    labels = ["-4 days", "-3 days", "-2 days", "-1 day", "Latest"]

    for i in range(5):
        idx = -5 + i
        plt.scatter(
            df["SPX_%"].iloc[idx],
            df["VIX_%"].iloc[idx],
            color=colors[i],
            s=140,
            edgecolors="black",
            linewidth=1.2,
            zorder=10,
        )

        # Date label
        date_str = df["Date"].iloc[idx].strftime("%Y-%m-%d")
        plt.text(
            df["SPX_%"].iloc[idx] + 0.08,
            df["VIX_%"].iloc[idx] + 0.3,
            f"{date_str}\n{labels[i]}",
            fontsize=9,
            ha="left",
            va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.9),
        )

    # ==================== Axis settings ====================
    plt.axhline(0, color="black", lw=0.8, alpha=0.5)
    plt.axvline(0, color="black", lw=0.8, alpha=0.5)

    # X-axis: every 0.5%
    xmin, xmax = df["SPX_%"].min() - 0.5, df["SPX_%"].max() + 0.5
    plt.xticks(np.arange(np.floor(2 * xmin) / 2, np.ceil(2 * xmax) / 2 + 0.5, 0.5))

    # Y-axis: every 2%
    ymin, ymax = df["VIX_%"].min() - 2, df["VIX_%"].max() + 2
    plt.yticks(np.arange(np.floor(ymin / 2) * 2, np.ceil(ymax / 2) * 2 + 2, 2))

    plt.xlabel("S&P 500 Daily % Change", fontsize=12)
    plt.ylabel("VIX Daily % Change", fontsize=12)
    plt.title(
        "SPX vs VIX Daily % Changes (Past ~3 Months)\nLast 5 Trading Days Highlighted",
        fontsize=14,
        pad=20,
    )

    plt.grid(True, alpha=0.3)
    plt.legend(loc="upper right")

    # Light quadrant coloring
    plt.axhspan(0, ymax, facecolor="green", alpha=0.03)
    plt.axhspan(ymin, 0, facecolor="red", alpha=0.03)
    plt.axvspan(0, xmax, facecolor="green", alpha=0.03)
    plt.axvspan(xmin, 0, facecolor="red", alpha=0.03)

    plt.tight_layout()

    plt.text(
        0.98,
        0.02,
        "@ParisTrader",
        transform=plt.gca().transAxes,
        fontsize=14,
        color="gray",
        alpha=0.6,
        ha="right",
        va="bottom",
        style="italic",
        weight="bold",
    )

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ==================== Print last 5 days ====================
    print("\nLast 5 trading days:")
    print(df.tail(5)[["Date", "SPX_%", "VIX_%"]].round(3))
    print(f"[INFO] SPX vs VIX chart saved to: {output_path}")

    return str(output_path)


def main() -> None:
    default_png = BASE_DIR / "spx_vix.png"
    generate_spx_vix_chart(str(default_png))


if __name__ == "__main__":
    main()