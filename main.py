import requests
import json
import math
import pandas as pd
from datetime import datetime, timedelta
import os

# Input Parameters
symbol = "NIFTY"  # Options: "NIFTY" or "BANKNIFTY"
default_step = 50 if symbol == "NIFTY" else 100  # Strike step size

# Function to calculate trading days between two dates
def calculate_trading_days(start_date, end_date):
    trading_days = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:  # Count only weekdays
            trading_days += 1
        current_date += timedelta(days=1)
    return trading_days

# URLs for fetching data
url_oc = "https://www.nseindia.com/option-chain"
url_nf = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
url_indices = "https://www.nseindia.com/api/allIndices"

# Headers for requests
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

# Session setup
sess = requests.Session()

# Fetch data from URL
def get_data(url):
    response = sess.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        return response.text
    else:
        raise Exception(f"Failed to fetch data. Status code: {response.status_code}")

# Set session cookies
def set_cookie():
    response = sess.get(url_oc, headers=headers, timeout=10)
    sess.cookies.update(dict(response.cookies))

# Fetch underlying price and nearest strike price
def fetch_indices_data():
    response_text = get_data(url_indices)
    data = json.loads(response_text)
    ul_price = next(
        index["last"]
        for index in data["data"]
        if (symbol == "NIFTY" and index["index"] == "NIFTY 50")
        or (symbol == "BANKNIFTY" and index["index"] == "NIFTY BANK")
    )
    nearest_strike_price = int(round(ul_price / default_step) * default_step)
    return ul_price, nearest_strike_price

# Fetch expiry dates and option chain data
def fetch_option_chain():
    response_text = get_data(url_nf)
    data = json.loads(response_text)
    expiry_dates = data["records"]["expiryDates"]
    option_data = data["records"]["data"]
    return expiry_dates, option_data

# Prepare DataFrame for the selected expiry
def prepare_dataframe(option_data, expiry_date):
    option_list = [
        [
            item.get("CE", {}).get("impliedVolatility", 0),
            item.get("PE", {}).get("impliedVolatility", 0),
            item["strikePrice"],
        ]
        for item in option_data
        if item["expiryDate"] == expiry_date
    ]
    return pd.DataFrame(option_list, columns=["CE IV", "PE IV", "Strike"])

# Calculate the 1SD range
def calculate_sd_ranges(ltp, t_days, iv_values, sd_multiplier=1):
    civ = sum(iv_values) / len(iv_values)
    dv = civ / math.sqrt(252)
    mv = dv * math.sqrt(t_days)
    sd_range = ltp * (mv / 100) * sd_multiplier
    lower_sd = ltp - sd_range
    upper_sd = ltp + sd_range
    return lower_sd, upper_sd

# Send data to Discord
def send_discord_message(data):
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("Discord webhook URL not found. Please set the DISCORD_WEBHOOK_URL environment variable.")
        return
    headers = {"Content-Type": "application/json"}
    response = requests.post(webhook_url, json=data, headers=headers)
    if response.status_code == 204:
        print("Message sent successfully.")
    else:
        print(f"Failed to send message. Response: {response.text}")

# Process expiry data and send to Discord
def process_and_send(df, expiry_date, ltp, t_days, expiry_type):
    # Fetch ATM IV values
    atm_strike = int(round(ltp / default_step) * default_step)
    next_strike = atm_strike + default_step
    iv_values = [
        df[df["Strike"] == atm_strike]["CE IV"].values[0],
        df[df["Strike"] == next_strike]["CE IV"].values[0],
        df[df["Strike"] == atm_strike]["PE IV"].values[0],
        df[df["Strike"] == next_strike]["PE IV"].values[0],
    ]

    # Calculate 1SD and 2SD ranges
    lower_1sd, upper_1sd = calculate_sd_ranges(ltp, t_days, iv_values, sd_multiplier=1)
    lower_2sd, upper_2sd = calculate_sd_ranges(ltp, t_days, iv_values, sd_multiplier=1.3)

    # Calculate Iron Condor legs
    lower_leg = int(math.floor(lower_1sd / default_step) * default_step)
    upper_leg = int(math.ceil(upper_1sd / default_step) * default_step)
    outer_lower_leg = int(math.floor(lower_2sd / default_step) * default_step)
    outer_upper_leg = int(math.ceil(upper_2sd / default_step) * default_step)

    # Prepare embed for Discord
    embed = {
        "title": f"{symbol} Option Chain Analysis - {expiry_type}",
        "description": f"Data fetched for expiry on {expiry_date}",
        "color": 5814783,
        "fields": [
            {"name": "**LTP**", "value": f"{ltp}", "inline": True},
            {"name": "**1 SD Range**", "value": f"{lower_1sd:.2f} - {upper_1sd:.2f}", "inline": True},
            {"name": "**2 SD Range**", "value": f"{lower_2sd:.2f} - {upper_2sd:.2f}", "inline": True},
            {"name": "**Iron Condor Legs**", "value": "\u200b", "inline": False},
            {"name": "SELL", "value": f"{symbol} {expiry_date} PE {lower_leg}", "inline": False},
            {"name": "SELL", "value": f"{symbol} {expiry_date} CE {upper_leg}", "inline": False},
            {"name": "BUY", "value": f"{symbol} {expiry_date} PE {outer_lower_leg}", "inline": False},
            {"name": "BUY", "value": f"{symbol} {expiry_date} CE {outer_upper_leg}", "inline": False},
        ],
    }

    send_discord_message({"embeds": [embed]})

# Main Execution
set_cookie()
ul_price, nearest_strike_price = fetch_indices_data()
expiry_dates, option_data = fetch_option_chain()

# Process current and next expiry
for idx, expiry_date in enumerate(expiry_dates[:2]):  # Process only current and next expiry
    df = prepare_dataframe(option_data, expiry_date)
    t_days = calculate_trading_days(datetime.now(), datetime.strptime(expiry_date, "%d-%b-%Y"))
    process_and_send(df, expiry_date, ul_price, t_days, f"Expiry {idx + 1}")
