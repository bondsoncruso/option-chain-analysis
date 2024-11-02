# Libraries
import requests
import json
import math
import pandas as pd
from datetime import datetime, timedelta
import os

# Input Parameters - You can change these
symbol = "NIFTY"         # Options: "NIFTY" or "BANKNIFTY"
num_rows = 50            # Rows above and below the nearest strike
default_step = 50        # Step size for strike rounding (50 for NIFTY, 100 for BANKNIFTY)

# Styling Functions for Console Output

def strRed(skk):         return "\033[91m {}\033[00m".format(skk)
def strGreen(skk):       return "\033[92m {}\033[00m".format(skk)
def strYellow(skk):      return "\033[93m {}\033[00m".format(skk)
def strLightPurple(skk): return "\033[94m {}\033[00m".format(skk)
def strPurple(skk):      return "\033[95m {}\033[00m".format(skk)
def strCyan(skk):        return "\033[96m {}\033[00m".format(skk)
def strLightGray(skk):   return "\033[97m {}\033[00m".format(skk)
def strBlack(skk):       return "\033[98m {}\033[00m".format(skk)
def strBold(skk):        return "\033[1m {}\033[00m".format(skk)

# Function to Get Nearest Strike Prices
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
    return trading_days + 1
 
# URLs for fetching data
url_oc = "https://www.nseindia.com/option-chain"
url_nf = f'https://www.nseindia.com/api/option-chain-indices?symbol={symbol}'
url_indices = "https://www.nseindia.com/api/allIndices"

# Headers for requests
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36',
    'accept-language': 'en,gu;q=0.9,hi;q=0.8',
    'accept-encoding': 'gzip, deflate, br'
}

# Session setup
sess = requests.Session()
cookies = dict()

# Set cookies for session
def set_cookie():
    global cookies
    request = sess.get(url_oc, headers=headers, timeout=5)
    cookies = dict(request.cookies)

# Fetch data from URL
def get_data(url):
    set_cookie()
    response = sess.get(url, headers=headers, timeout=5, cookies=cookies)
    if response.status_code == 401:
        set_cookie()
        response = sess.get(url, headers=headers, timeout=5, cookies=cookies)
    if response.status_code == 200:
        return response.text
    return ""

# Set header and global variables for indices data
def set_header():
    global nearest_strike_price, ul_price, expiry_date
    response_text = get_data(url_indices)
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
    data = json.loads(response_text)
    expiry_date = data["records"]["expiryDates"][0]

# Fetch and organize option chain data for DataFrame
def fetch_option_chain(num, step, nearest, url, expiry_date):
    response_text = get_data(url)
    data = json.loads(response_text)

    # Prepare data list for DataFrame
    option_data = []
    for item in data['records']['data']:
        if item["expiryDate"] == expiry_date and nearest - num * step <= item["strikePrice"] <= nearest + num * step:
            strike_price = item["strikePrice"]

            # Get CE and PE data, handle cases where data might be missing
            ce_data = item.get("CE", {})
            pe_data = item.get("PE", {})

            # Append row with the specified column order
            option_data.append([
                ce_data.get("openInterest", 0), ce_data.get("changeinOpenInterest", 0), ce_data.get("totalTradedVolume", 0),
                ce_data.get("impliedVolatility", 0), ce_data.get("lastPrice", 0), ce_data.get("change", 0),
                ce_data.get("bidQty", 0), ce_data.get("bidprice", 0), ce_data.get("askPrice", 0), ce_data.get("askQty", 0),
                strike_price,
                pe_data.get("bidQty", 0), pe_data.get("bidprice", 0), pe_data.get("askPrice", 0), pe_data.get("askQty", 0),
                pe_data.get("change", 0), pe_data.get("lastPrice", 0), pe_data.get("impliedVolatility", 0),
                pe_data.get("totalTradedVolume", 0), pe_data.get("changeinOpenInterest", 0), pe_data.get("openInterest", 0)
            ])

    # Create DataFrame with specified column names
    columns = [
        "CE OI", "CE Chng in OI", "CE Volume", "CE IV", "CE LTP", "CE Chng",
        "CE Bid Qty", "CE Bid", "CE Ask", "CE Ask Qty", "Strike",
        "PE Bid Qty", "PE Bid", "PE Ask", "PE Ask Qty", "PE Chng",
        "PE LTP", "PE IV", "PE Volume", "PE Chng in OI", "PE OI"
    ]
    df = pd.DataFrame(option_data, columns=columns)
    
    # Save to CSV file
    df.to_csv(f"data\{symbol}_option_chain_{expiry_date}.csv", index=False)
    return df

import math

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
set_header()

df = fetch_option_chain(num_rows, default_step, nearest_strike_price, url_nf, expiry_date)

expiry_date_obj = datetime.strptime(expiry_date, "%d-%b-%Y")
current_date = datetime.now()

# Automatically determined inputs based on fetched data
ltp = ul_price            # Latest Traded Price (LTP), dynamically set from the index data
t_days = (expiry_date_obj - current_date).days  # Time to Expiry (TTE), calculated dynamically based on expiry date
atm_call_iv = df[df['Strike'] == nearest_strike_price]['CE IV'].values[0]  # ATM Call IV, fetched from the option chain DataFrame
atm_call_iv2 = atm_call_iv2 = df[df['Strike'] == nearest_strike_price + default_step]['CE IV'].values[0]
atm_put_iv = df[df['Strike'] == nearest_strike_price]['PE IV'].values[0]  # ATM Put IV, fetched from the option chain DataFrame
atm_put_iv2 = df[df['Strike'] == nearest_strike_price + default_step]['PE IV'].values[0]

# print(atm_call_iv, atm_call_iv2, atm_put_iv, atm_put_iv2)

# Call the function
result = calculate_1sd_range(ltp, t_days, atm_call_iv, atm_call_iv2, atm_put_iv, atm_put_iv2)

# Calculate Iron Condor legs based on 1SD range and display results
lower_leg = int(math.floor(result['Lower 1SD'] / default_step) * default_step)
upper_leg = int(math.ceil(result['Upper 1SD'] / default_step) * default_step)
outer_lower_leg = lower_leg - (4 * default_step)
outer_upper_leg = upper_leg + (4 * default_step)

time_to_expiry = calculate_trading_days(current_date, expiry_date_obj)
formatted_current_date = current_date.strftime("%d-%b-%Y")



# Display Option Chain Data in Bloomberg-inspired style
print(
    strLightPurple(strBold("\nFETCHING OPTION CHAIN DATA")) + "\n" +  # Heading in light purple
    "══════════════════════════════════════════════════" + "\n" +
    f"{'INSTRUMENT:':>16} {strBold(strCyan(symbol))}  |  " +
    f"{'EXPIRY DATE:':>16} {strBold(strCyan(expiry_date))}" + "\n" +
    f"{'CURRENT DATE:':>16} {strBold(strCyan(formatted_current_date))}  |  " +
    f"{'TIME TO EXPIRY:':>16} {strBold(strYellow(time_to_expiry))} trading days" + "\n" +
    f"{'NEAREST STRIKE:':>16} {strBold(strYellow(nearest_strike_price))}  |  " +
    f"{'LAST TRADED PRICE:':>16} {strBold(strYellow(ul_price))}" + "\n" +
    "══════════════════════════════════════════════════"
)

# Display 1SD Calculation Results
print(
    strLightPurple(strBold("\n1 STANDARD DEVIATION (1SD) CALCULATION RESULTS")) + "\n" +
    "══════════════════════════════════════════════════" + "\n" +
    f"{'CUMULATIVE IMPLIED VOLATILITY (CIV):':>40} " + strBold(strYellow(f"{result['CIV']:.2f}%")) + "\n" +
    f"{'DAILY VOLATILITY (DV):':>40} " + strBold(strYellow(f"{result['DV']:.2f}%")) + "\n" +
    f"{'MONTHLY VOLATILITY (MV):':>40} " + strBold(strYellow(f"{result['MV']:.2f}% for {t_days} days")) + "\n" +
    "──────────────────────────────────────────────────" + "\n" +
    f"{'LOWER 1SD:':>40} " + strBold(strGreen(f"{result['Lower 1SD']:.2f}")) + "\n" +
    f"{'UPPER 1SD:':>40} " + strBold(strRed(f"{result['Upper 1SD']:.2f}")) + "\n" +
    "══════════════════════════════════════════════════"
)
# Display Iron Condor Strategy Legs in the specified format with word-by-word color coding
print(
    strLightPurple(strBold("\nIRON CONDOR STRATEGY LEGS")) + "\n" +  # Heading in light purple
    "══════════════════════════════════════════════════" + "\n" +
    f"{strRed('SELL')} {strCyan(symbol)} {strYellow(expiry_date[:6].upper())} PE {strYellow(lower_leg)}" + "\n" +
    f"{strRed('SELL')} {strCyan(symbol)} {strYellow(expiry_date[:6].upper())} CE {strYellow(upper_leg)}" + "\n" +
    f"{strGreen('BUY')} {strCyan(symbol)} {strYellow(expiry_date[:6].upper())} PE {strYellow(outer_lower_leg)}" + "\n" +
    f"{strGreen('BUY')} {strCyan(symbol)} {strYellow(expiry_date[:6].upper())} CE {strYellow(outer_upper_leg)}" + "\n" +
    "══════════════════════════════════════════════════"
)

import requests

def send_discord_message():
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
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
                "value": f"{time_to_expiry} trading days",
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
