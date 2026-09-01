import requests
import time
from datetime import datetime, timedelta, timezone

# ---- Config ----
CURRENCY = "eur"
THRESHOLD_PCT = 5.0      # n% - change this to whatever threshold you want
CHECK_INTERVAL_SECONDS = 60


def get_current_price():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "bitcoin", "vs_currencies": CURRENCY}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()["bitcoin"][CURRENCY]


def get_yesterday_average_price():
    """
    Fetches hourly price data for the last 2 days and averages
    the points that fall within yesterday's date (UTC).
    """
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": CURRENCY, "days": 2}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    now = datetime.now(timezone.utc)
    yesterday_date = (now - timedelta(days=1)).date()

    yesterday_prices = [
        price
        for timestamp_ms, price in data["prices"]
        if datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date() == yesterday_date
    ]

    if not yesterday_prices:
        raise ValueError("No price data found for yesterday.")

    return sum(yesterday_prices) / len(yesterday_prices)


def check_price(current_price, yesterday_avg, threshold_pct):
    pct_change = (current_price - yesterday_avg) / yesterday_avg * 100

    if pct_change > threshold_pct:
        print(f"🔺 ALERT: BTC is UP {pct_change:+.2f}% vs yesterday's average "
              f"(now €{current_price:,.2f}, yesterday avg €{yesterday_avg:,.2f})")
    elif pct_change < -threshold_pct:
        print(f"🔻 ALERT: BTC is DOWN {pct_change:+.2f}% vs yesterday's average "
              f"(now €{current_price:,.2f}, yesterday avg €{yesterday_avg:,.2f})")
    else:
        print(f"BTC within normal range ({pct_change:+.2f}%) "
              f"(now €{current_price:,.2f}, yesterday avg €{yesterday_avg:,.2f})")


def main():
    print(f"Starting BTC monitor — threshold ±{THRESHOLD_PCT}%, checking every {CHECK_INTERVAL_SECONDS}s\n")

    # Yesterday's average doesn't change during the day, so fetch it once
    yesterday_avg = get_yesterday_average_price()
    print(f"Yesterday's average price: €{yesterday_avg:,.2f}\n")

    while True:
        try:
            current_price = get_current_price()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] ", end="")
            check_price(current_price, yesterday_avg, THRESHOLD_PCT)
        except requests.RequestException as e:
            print(f"Request failed: {e}")
        except ValueError as e:
            print(f"Data error: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()