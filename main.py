# Libraries
import requests
import json
import math
import pandas as pd
from datetime import datetime, timedelta
import os

# Input Parameters - You can change these
symbol = "NIFTY"         # Options: "NIFTY" or "BANKNIFTY"
default_step = 50        # Step size for strike rounding (50 for NIFTY, 100 for BANKNIFTY)

# Function to Get Nearest Strike Price
def round_nearest(x, num=50): return int(math.ceil(float(x) / num) * num)
def nearest_strike(x): return round_nearest(x, default_step if symbol == "NIFTY" else 100)

# Function to calculate trading days between two dates
def calculate_trading_days(start_date, end_date):
    trading_days = 0
    current_date = start_date
    while current_date <= end_date:
        # Count only weekdays (Monday=0, ..., Friday=4)
        if current_date.weekday() < 5:
            trading_days += 1
        current_date += timedelta(days=1)
    return trading_days

# URLs for fetching data
url_oc = "https://www.nseindia.com/option-chain"
url_nf = f'https://www.nseindia.com/api/option-chain-indices?symbol={symbol}'
url_indices = "https://www.nseindia.com/api/allIndices"

# Headers for requests
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Sec-Fetch-Dest': 'document'
}

# Session setup
sess = requests.Session()
cookies = dict()

# Set cookies for session
def set_cookie():
    global cookies
    response = sess.get(url_oc, headers=headers, timeout=10)
    cookies = dict(response.cookies)
    sess.cookies.update(cookies)

# Fetch data from URL
def get_data(url):
    response = sess.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        return response.text
    else:
        print(f"Failed to get data from {url}. Status code: {response.status_code}")
        return ""

# Set header and global variables for indices data
def set_header():
    global nearest_strike_price, ul_price, expiry_date
    response_text = get_data(url_indices)
    if not response_text:
        print("Failed to retrieve data from NSE indices API.")
        exit()
    data = json.loads(response_text)
    ul_price = 0

    # Get last price for symbol
    for index in data["data"]:
        if (symbol == "NIFTY" and index["index"] == "NIFTY 50") or (symbol == "BANKNIFTY" and index["index"] == "NIFTY BANK"):
            ul_price = index["last"]
            break
    nearest_strike_price = nearest_strike(ul_price)

    # Get nearest expiry date
    response_text = get_data(url_nf)
    if not response_text:
        print("Failed to retrieve option chain data.")
        exit()
    data = json.loads(response_text)
    expiry_date = data["records"]["expiryDates"][0]

# Fetch and organize option chain data into a DataFrame
def fetch_option_chain(url, expiry_date):
    response_text = get_data(url)
    if not response_text:
        print("Failed to retrieve option chain data.")
        exit()
    data = json.loads(response_text)

    # Prepare data list for DataFrame
    option_data = []
    for item in data['records']['data']:
        if item["expiryDate"] == expiry_date:
            strike_price = item["strikePrice"]

            # Get CE and PE data, handle cases where data might be missing
            ce_data = item.get("CE", {})
            pe_data = item.get("PE", {})

            # Append row with the specified column order
            option_data.append([
                ce_data.get("impliedVolatility", 0),
                pe_data.get("impliedVolatility", 0),
                strike_price,
            ])

    # Create DataFrame with specified column names
    columns = ["CE IV", "PE IV", "Strike"]
    df = pd.DataFrame(option_data, columns=columns)
    return df

def calculate_1sd_range(ltp, t_days, atm_call_iv, atm_call_iv2, atm_put_iv, atm_put_iv2):
    """
    Calculate the 1 Standard Deviation (1SD) range based on LTP, time to expiry, 
    and implied volatilities of ATM call and put options.
        
    Parameters:
    - ltp (float): Latest Traded Price
    - t_days (int): Time to Expiry (TTE) in market trading days
    - atm_call_iv (float): ATM Call Implied Volatility
    - atm_call_iv2 (float): Alternate ATM Call Implied Volatility
    - atm_put_iv (float): ATM Put Implied Volatility
    - atm_put_iv2 (float): Alternate ATM Put Implied Volatility
        
    Returns:
    - dict: Dictionary containing CIV, DV, MV, lower 1SD, and upper 1SD
    """
    # Step 1: Calculate Cumulative Implied Volatility (CIV)
    civ = (atm_call_iv + atm_call_iv2 + atm_put_iv + atm_put_iv2) / 4

    # Step 2: Calculate Daily Volatility (DV)
    dv = civ / math.sqrt(252)

    # Step 3: Calculate Monthly Volatility (MV) for the remaining days until expiry
    mv = dv * math.sqrt(t_days)

    # Step 4: Calculate the 1 Standard Deviation (1SD) range
    lower_sd = ltp - (ltp * (mv / 100))
    upper_sd = ltp + (ltp * (mv / 100))

    # Return the results as a dictionary
    return {
        "CIV": civ,
        "DV": dv,
        "MV": mv,
        "Lower 1SD": lower_sd,
        "Upper 1SD": upper_sd
    }

# Main Execution
set_cookie()
set_header()

df = fetch_option_chain(url_nf, expiry_date)

expiry_date_obj = datetime.strptime(expiry_date, "%d-%b-%Y")
current_date = datetime.now()

# Automatically determined inputs based on fetched data
ltp = ul_price  # Latest Traded Price (LTP), dynamically set from the index data
t_days = calculate_trading_days(current_date, expiry_date_obj)  # Time to Expiry (TTE), calculated dynamically

# Fetch ATM IVs
atm_strike = nearest_strike_price
next_strike = atm_strike + default_step

atm_call_iv = df[df['Strike'] == atm_strike]['CE IV'].values[0]
atm_call_iv2 = df[df['Strike'] == next_strike]['CE IV'].values[0]
atm_put_iv = df[df['Strike'] == atm_strike]['PE IV'].values[0]
atm_put_iv2 = df[df['Strike'] == next_strike]['PE IV'].values[0]

# Call the function
result = calculate_1sd_range(ltp, t_days, atm_call_iv, atm_call_iv2, atm_put_iv, atm_put_iv2)

# Calculate Iron Condor legs based on 1SD range
lower_leg = int(math.floor(result['Lower 1SD'] / default_step) * default_step)
upper_leg = int(math.ceil(result['Upper 1SD'] / default_step) * default_step)
outer_lower_leg = lower_leg - (4 * default_step)
outer_upper_leg = upper_leg + (4 * default_step)

formatted_current_date = current_date.strftime("%d-%b-%Y")

import requests

def send_discord_message():
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("Discord webhook URL not found in environment variables.")
        exit()
    # Construct the embed
    embed = {
        "title": f"{symbol} Option Chain Analysis",
        "description": f"Data fetched on {formatted_current_date}",
        "color": 5814783,  # Optional: Change the color code as desired
        "fields": [
            {
                "name": "**INSTRUMENT**",
                "value": symbol,
                "inline": True
            },
            {
                "name": "**EXPIRY DATE**",
                "value": expiry_date,
                "inline": True
            },
            {
                "name": "**CURRENT DATE**",
                "value": formatted_current_date,
                "inline": True
            },
            {
                "name": "**TIME TO EXPIRY**",
                "value": f"{t_days} trading days",
                "inline": True
            },
            {
                "name": "**NEAREST STRIKE**",
                "value": str(nearest_strike_price),
                "inline": True
            },
            {
                "name": "**LAST TRADED PRICE**",
                "value": str(ul_price),
                "inline": True
            },
            {
                "name": "**1 STANDARD DEVIATION (1SD) CALCULATION RESULTS**",
                "value": "\u200b",  # Empty value to create a separator
                "inline": False
            },
            {
                "name": "CIV",
                "value": f"{result['CIV']:.2f}%",
                "inline": True
            },
            {
                "name": "DV",
                "value": f"{result['DV']:.2f}%",
                "inline": True
            },
            {
                "name": "MV",
                "value": f"{result['MV']:.2f}% for {t_days} days",
                "inline": True
            },
            {
                "name": "LOWER 1SD",
                "value": f"{result['Lower 1SD']:.2f}",
                "inline": True
            },
            {
                "name": "UPPER 1SD",
                "value": f"{result['Upper 1SD']:.2f}",
                "inline": True
            },
            {
                "name": "**IRON CONDOR STRATEGY LEGS**",
                "value": "\u200b",  # Empty value to create a separator
                "inline": False
            },
            {
                "name": "SELL",
                "value": f"{symbol} {expiry_date[:6].upper()} PE {lower_leg}",
                "inline": False
            },
            {
                "name": "SELL",
                "value": f"{symbol} {expiry_date[:6].upper()} CE {upper_leg}",
                "inline": False
            },
            {
                "name": "BUY",
                "value": f"{symbol} {expiry_date[:6].upper()} PE {outer_lower_leg}",
                "inline": False
            },
            {
                "name": "BUY",
                "value": f"{symbol} {expiry_date[:6].upper()} CE {outer_upper_leg}",
                "inline": False
            }
        ],
        "footer": {
            "text": "Generated by your Python script"
        }
    }

    data = {
        "embeds": [embed]
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(
        webhook_url, json=data, headers=headers
    )

    if response.status_code == 204:
        print("Message sent successfully to Discord.")
    else:
        print(f"Failed to send message to Discord: {response.text}")

# Send the message via Discord
send_discord_message()
