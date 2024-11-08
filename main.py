import requests
import json
import math
import pandas as pd
from datetime import datetime, timedelta

# Input Parameters
symbol = "NIFTY"
default_step = 50 if symbol == "NIFTY" else 100

url_oc = "https://www.nseindia.com/option-chain"
url_nf = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
url_indices = "https://www.nseindia.com/api/allIndices"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/option-chain",
    "Connection": "keep-alive",
}

sess = requests.Session()

def set_cookie():
    try:
        response = sess.get(url_oc, headers=headers, timeout=10)
        sess.cookies.update(dict(response.cookies))
        print("Cookies set:", sess.cookies.get_dict())
    except Exception as e:
        print(f"Error setting cookies: {e}")
        raise

def get_data(url):
    try:
        response = sess.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and response.text.strip():
            return response.text
        else:
            print(f"Failed to fetch data from {url}. Status: {response.status_code}")
            print(f"Response content: {response.text}")
            raise Exception("Empty or invalid response.")
    except Exception as e:
        print(f"Error fetching data: {e}")
        raise

def fetch_indices_data():
    response_text = get_data(url_indices)
    if not response_text.strip():
        raise Exception("Empty response for indices data.")
    data = json.loads(response_text)
    ul_price = next(
        index["last"]
        for index in data["data"]
        if (symbol == "NIFTY" and index["index"] == "NIFTY 50") or
           (symbol == "BANKNIFTY" and index["index"] == "NIFTY BANK")
    )
    nearest_strike_price = int(round(ul_price / default_step) * default_step)
    return ul_price, nearest_strike_price

def fetch_option_chain():
    response_text = get_data(url_nf)
    if not response_text.strip():
        raise Exception("Empty response for option chain.")
    data = json.loads(response_text)
    expiry_dates = data["records"]["expiryDates"]
    option_data = data["records"]["data"]
    return expiry_dates, option_data

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

def send_discord_message(data):
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("Discord webhook URL not found. Please set it in the environment.")
        return
    headers = {"Content-Type": "application/json"}
    response = requests.post(webhook_url, json=data, headers=headers)
    if response.status_code == 204:
        print("Message sent successfully.")
    else:
        print(f"Failed to send message: {response.text}")

set_cookie()
ul_price, nearest_strike_price = fetch_indices_data()
expiry_dates, option_data = fetch_option_chain()
