import datetime
import requests
import pandas as pd
import yfinance as yf
import time

# ============== Next Monday to Friday ==============
today = datetime.date.today()
days_to_monday = (7 - today.weekday()) % 7 or 7
next_monday = today + datetime.timedelta(days=days_to_monday)
next_friday = next_monday + datetime.timedelta(days=4)

dates = [(next_monday + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
print(f"Fetching earnings {next_monday} to {next_friday} from Nasdaq...")

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
all_earnings = []

for date in dates:
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date}"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json().get("data", {}).get("rows", [])
        for row in data:
            all_earnings.append({
                "Date": date,
                "Ticker": row["symbol"].strip(),
                "Company": row.get("name", "N/A").strip(),
            })
        print(f"   {date}: {len(data)} companies")
    except Exception as e:
        print(f"   Failed to fetch {date}: {e}")

if not all_earnings:
    print("No data received.")
    exit()

df = pd.DataFrame(all_earnings)
print(f"\nTotal announcements: {len(df)} → Now enriching with market cap & sector...")

# ============== Reliable yfinance fetch (sector/industry works!) ==============
def get_company_info(ticker):
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        return pd.Series({
            "MarketCap": info.get("marketCap"),
            "Sector": info.get("sector", "N/A"),
            "Industry": info.get("industry", "N/A"),
        })
    except Exception:
        return pd.Series({"MarketCap": None, "Sector": "N/A", "Industry": "N/A"})

# Apply with small delay to be nice to Yahoo
results = []
for ticker in df["Ticker"]:
    results.append(get_company_info(ticker))
    time.sleep(0.05)  # 20 requests/sec → safe & fast

extra = pd.DataFrame(results)
df = pd.concat([df, extra], axis=1)

# ============== Filter & Sort ==============
df = df.dropna(subset=["MarketCap"])
df = df[df["MarketCap"] >= 100_000_000]        # ≥ $100 Million
df["Date"] = pd.to_datetime(df["Date"]).dt.date
df = df.sort_values(by=["Date", "MarketCap"], ascending=[True, False])

# Format MarketCap for display
df["MarketCap"] = df["MarketCap"].apply(lambda x: f"${x:,.0f}")

# Select columns for output
df_out = df[["Date", "Ticker", "Company", "Sector", "Industry", "MarketCap"]]

# Use pandas styling to highlight rows with MarketCap > 10B
def highlight_large_marketcap(row):
    mc = float(row["MarketCap"].replace("$", "").replace(",", ""))
    if mc > 10_000_000_000:
        return ['background-color: #ffefc1'] * len(row)  # light yellow
    else:
        return [''] * len(row)

styled_df = df_out.style.apply(highlight_large_marketcap, axis=1)

# ============== Generate Interactive HTML ==============
html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Earnings Week of {next_monday}</title>
<!-- Bootstrap CSS for styling -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body {{
    margin: 20px;
    background-color: #f8f9fa;
  }}
  h2 {{
    text-align: center;
    margin-bottom: 20px;
  }}
  .toggle-btn {{
    margin-bottom: 15px;
  }}
</style>
</head>
<body>

<h2>NEXT WEEK EARNINGS | {next_monday} to {next_friday}</h2>

<footer style="margin-top: 30px; text-align: center; font-size: 0.9em; color: #666;">
  &copy; 2025 ParisTrader. All rights reserved. 
  <br />
  <a href="https://t.me/algoparistrader" target="_blank" rel="noopener noreferrer">Telegram: @algoparistrader</a>
</footer>


<div class="container">
  {styled_df.set_table_attributes('class="table table-striped table-hover table-bordered"').hide(axis=0).to_html()}
</div>


</body>
</html>
"""

filename = f"ParisTrader_NQ_EarningsWeek_of_{next_monday.strftime('%Y%m%d')}.html"
with open(filename, "w", encoding="utf-8") as f:
    f.write(html_template)

print(f"\nInteractive HTML saved → {filename} ({len(df_out)} companies)")
