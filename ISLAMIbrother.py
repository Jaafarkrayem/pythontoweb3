# Imports

import logging
from urllib import response
from bs4 import BeautifulSoup
import requests

from telegram import __version__ as TG_VER

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This bot is not compatible with your current PTB version {TG_VER}"
    )

from web3 import Web3
from web3.middleware import geth_poa_middleware
import json
import time
import telegram
import asyncio
from collections import OrderedDict
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
import html
import plotly.graph_objects as go
from datetime import datetime
import hashlib
import hmac
# End of Imports

# //////////////////////////////////////////\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ #

# Web3 and bot token connection
bot = telegram.Bot(token="xxx")

chat_id = "-xx"

w3 = Web3(Web3.HTTPProvider("xxx"))

with open("ramadanABI.json") as f:
    ramadan_contract_abi = json.load(f)

ramadan_contract_address = "0x032919031C0439fbFD7C03fA6fBcA01B163035fb"
ramadan_contract = w3.eth.contract(address=ramadan_contract_address, abi=ramadan_contract_abi)

with open("p2pABI.json") as f:
    p2p_contract_abi = json.load(f)

p2p_contract_address = "0xE60708A80802619aEd5F9212407b93f83a9F0963"
p2p_contract = w3.eth.contract(address=p2p_contract_address, abi=p2p_contract_abi)    
# End of web3 and bot connection

# //////////////////////////////////////////\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ #

# Ramadan Competition
top_50_players = []

def save_events_data(events_data):
    with open("events_data.json", "w") as f:
        json.dump([OrderedDict(item) for item in events_data], f)

def load_events_data():
    try:
        with open('events_data.json', 'r') as f:
            data = json.load(f)
            if not data:
                return []
            return data
    except FileNotFoundError:
        return []

def fetch_player_data(address, old_contract):
    for player_data in events_data:
        if player_data['address'] == address:
            # Update the existing player's score and block number
            player = old_contract.functions.players(address).call()
            player_data['score'] = player[0]
            player_data['daysPlayed'] = player[3]
            player_data['blockNumber'] = w3.eth.block_number
            print(f"Fetched player data: {player_data}")
            break
    else:
        # Create a new dictionary for a new player and append it to events_data
        player = old_contract.functions.players(address).call()
        player_data = OrderedDict([("address", address), ("score", player[0]), ("daysPlayed", player[3]), ("blockNumber", w3.eth.block_number)])
        print(f"Fetched player data: {player_data}")
        events_data.append(player_data)

    # Save the updated events data to the file
    save_events_data(events_data)

    return player_data

def update_top_50_players(player_data):
    global top_50_players
    top_50_players.append(player_data)
    top_50_players = sorted(top_50_players, key=lambda x: x["score"], reverse=True)[:50]


event_abi = ramadan_contract.events.ScoreUpdated._get_event_abi()
event_signature = w3.keccak(text=f"{event_abi['name']}({','.join([input['type'] for input in event_abi['inputs']])})").hex()

from_block = load_events_data()[-1]['blockNumber'] + 1 if load_events_data() else 0
to_block = w3.eth.block_number
events = ramadan_contract.events.ScoreUpdated.get_logs(fromBlock=from_block, toBlock=to_block)

events_data = load_events_data()

player_addresses = {event["args"]["player"] for event in events}

for address in player_addresses:
    player_data = fetch_player_data(address, ramadan_contract)
    update_top_50_players(player_data)

def event_listener():
    global top_50_players
    global events_data
    latest_block = w3.eth.block_number

    print("Listening for new events...")

    while True:
        new_block = w3.eth.block_number

        if new_block > latest_block:
            events = ramadan_contract.events.ScoreUpdated.get_logs(fromBlock=latest_block + 1, toBlock=new_block)
            for event in events:
                print(f"Processing event: {event}")
                player_address = event["args"]["player"]
                player_data = fetch_player_data(player_address, ramadan_contract)
                update_top_50_players(player_data)
                events_data.append(event)

            latest_block = new_block

            # Save the updated events data to the file
            save_events_data(events_data)

            # Send the updated top 50 players to Telegram after processing the events
            asyncio.run(send_top_50_players_to_telegram(chat_id))

        time.sleep(300)

print(f"Total events fetched: {len(events)}")

def unicode_bold(text):
    return f"*{text}*"

def unicode_italic(text):
    return f"_{text}_"

async def send_top_50_players_to_telegram(chat_id):
      message = unicode_bold("🏆 Top 50 Players Ramadan Competition 🏆") + "\n\n"
      for i, player_data in enumerate(top_50_players):
          message += unicode_bold(f"{i + 1}. {player_data['address']}") + f" - {unicode_bold('Score')}: {unicode_italic(player_data['score'])} - {unicode_bold('Days Played')}: {unicode_italic(player_data['daysPlayed'])}\n"
      await bot.send_message(chat_id=chat_id, text=message, parse_mode="MARKDOWN")

async def update_top_players():
    global top_50_players
    global events_data

    prev_top_50_players = []

    while True:
        await asyncio.sleep(120)

        new_events_data = load_events_data()

        # check if there is new data
        if len(new_events_data) > len(events_data):

            # get the new events that haven't been processed
            new_events = new_events_data[len(events_data):]

            for event in new_events:
                player_address = event["address"]
                player_data = next((p for p in top_50_players if p["address"] == player_address), None)
                if player_data:
                    # update the player's score and daysPlayed
                    player_data["score"] = event["score"]
                    player_data["daysPlayed"] = event["daysPlayed"]
                else:
                    # add the player to the top 50 list
                    player_data = OrderedDict([("address", player_address), ("score", event["score"]), ("daysPlayed", event["daysPlayed"]), ("blockNumber", event["blockNumber"])])
                    top_50_players.append(player_data)

            # sort the top 50 players by score
            top_50_players = sorted(top_50_players, key=lambda x: x["score"], reverse=True)[:50]

            # check if top 50 players data has changed
            if top_50_players != prev_top_50_players:
                # send the updated top 50 players to Telegram
                await send_top_50_players_to_telegram(chat_id)

            prev_top_50_players = top_50_players

            # update the events_data
            events_data = new_events_data
# End of Ramadan Competition

# //////////////////////////////////////////\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ #

# Price and Chart

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Set your API key and secret for CoinStore
API_KEY = "e7c2bc2dd1f3c4a7a55a759ecb060882"
API_SECRET = "938a0c2def4158b5b49d5d01df0350f1"

async def islami(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    await update.message.reply_text('Asalam Alykum! I am your ISLAMI bot friend. Type /ihelp to see the available commands.')

async def ihelp(update: Update, context: CallbackContext):
    """Send a message when the command /ihelp is issued."""
    help_text = "The following commands are available:\n\n" \
                "/price - Get the current price of ISLAMICOIN\n" \
                "/chart <Time Frame> - Get a chart of the price history for ISLAMICOIN\n\n" \
                "Example usage: /price \n\n" \
                "'/chart 1h'"
    await update.message.reply_text(help_text)


EXCHANGES_URLS = {
    "CoinTiger": "https://www.cointiger.com/en-us/#/trade_pro?coin=islami_usdt",
    "Lbank": "https://www.lbank.com/en-US/trade/islami_usdt/",
    "DigiFinex": "https://www.digifinex.com/en-ww/trade/USDT/ISLAMI",
    "CoinStore": "https://www.coinstore.com/#/spot/ISLAMIUSDT"
}

EXCHANGE_LOGOS = {
    "CoinTiger": "https://www.cointiger.com/",
    "Lbank": "https://www.lbank.com/",
    "DigiFinex": "https://www.digifinex.com/",
    "CoinStore": "https://www.coinstore.com/"
}

# Dictionary of exchange URLs
EXCHANGES = {
    'CoinTiger': 'https://www.cointiger.com/exchange/api/public/market/detail',
    'Lbank': 'https://api.lbkex.com/v2/ticker.do?symbol=islami_usdt',
    'DigiFinex': 'https://openapi.digifinex.com/v3/ticker?symbol=islami_usdt',
    #'CoinStore': 'https://api.coinstore.com/api/v1/price?symbol=ISLAMI/USDT'
}

def get_coinstore_price():
    endpoint = "https://api.coinstore.com/api/v1/price"
    parameters = {"symbol": "ISLAMI/USDT"}
    timestamp = int(time.time() * 1000)
    message = str(timestamp) + "GET" + endpoint
    signature = hmac.new(API_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGNATURE": signature,
        "ACCESS-TIMESTAMP": str(timestamp),
        "Content-Type": "application/json"
    }
    response = requests.get(endpoint, headers=headers, params=parameters)
    if response.status_code == 200:
        data = response.json()
        return data['price']
    else:
        return 'API issue'

async def get_price():
    """Scrapes the price of the token from different exchanges and calculates percentage change"""
    prices = {}
    for exchange, url in EXCHANGES.items():
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            try:
                if exchange == "CoinTiger":
                    price = data['ISLAMIUSDT']['last']
                    pChange = float(data['ISLAMIUSDT']['percentChange'])
                elif exchange == "Lbank":
                    price = data['data'][0]['ticker']['latest']
                    pChange = data['data'][0]['ticker']['change']
                elif exchange == "DigiFinex":
                    price = data['ticker'][0]['last']
                    pChange = data['ticker'][0]['change']
                elif exchange == "CoinStore":
                    price = get_coinstore_price()
                    pChange = None
                prices[exchange] = (price, pChange)
            except KeyError:
                prices[exchange] = ('API issue', None)
    return prices


# Price handler
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message with a button that opens a the web app."""
    prices = await get_price()
    exchange_icons = {
        "CoinTiger": "🐯",
        "Lbank": "💱",
        "DigiFinex": "🔍",
        "CoinStore": "🔍"
    }
    message = 'Current ISLAMI/USDT prices:\n\n'
    for exchange, (price, pChange) in prices.items():
        url = EXCHANGES_URLS.get(exchange, '')
        exchange_icon = exchange_icons.get(exchange, '')
        exchange_link = f'<a href="{url}">{exchange_icon} {exchange}</a>'
        if pChange is not None:
            sign = "🟢" if pChange >= 0 else "🔴"
            message += f'{exchange_link}: {html.escape(str(price))} ({sign} {pChange:.2f}%)\n'
        else:
            message += f'{exchange_link}: {html.escape(str(price))}\n'
    message = message.replace(' :', ':')  # remove any spaces before the colon

    # Create inline keyboard buttons
    keyboard = [
        [
            InlineKeyboardButton("CMC", url="https://coinmarketcap.com/currencies/islamicoin"),
            InlineKeyboardButton("CG", url="https://www.coingecko.com/en/coins/islamicoin")
        ],
        [
            InlineKeyboardButton("P2P IOS", url="https://apps.apple.com/lb/app/islamiwallet/id1631212925"),
            InlineKeyboardButton("P2P Android", url="https://play.google.com/store/apps/details?id=com.islami.wallet&hl=en&gl=US")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(text=message, reply_markup=reply_markup, disable_web_page_preview=True)



# Chart Handler
async def chart(update, context):
    """Creates a chart of the price history for a token using data from CoinGecko."""
    # Get the token id
    token = 'islami'
    timeframe = context.args[0]
     # Construct the API URL based on the selected timeframe
    if timeframe == '1h':
        url = f'https://api.coingecko.com/api/v3/coins/islamicoin/market_chart?vs_currency=usd&days=1&interval=hourly'
    elif timeframe == '4h':
        url = f'https://api.coingecko.com/api/v3/coins/islamicoin/market_chart?vs_currency=usd&days=1&interval=4hour'
    elif timeframe == '1d':
        url = f'https://api.coingecko.com/api/v3/coins/islamicoin/market_chart?vs_currency=usd&days=1&interval=daily'
    elif timeframe == '1w':
        url = f'https://api.coingecko.com/api/v3/coins/islamicoin/market_chart?vs_currency=usd&days=7&interval=daily'
    elif timeframe == '1m':
        url = f'https://api.coingecko.com/api/v3/coins/islamicoin/market_chart?vs_currency=usd&days=30&interval=daily'
    elif timeframe == '-':
        url = f'https://api.coingecko.com/api/v3/coins/islamicoin/market_chart?vs_currency=usd&days=1&interval=15minutes'         
    else:
        await update.message.reply_text(text='Invalid timeframe selected.')
        return
    
    # Get the latest price from CoinGecko API
    latest_price_response = requests.get('https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=islamicoin&order=market_cap_desc&per_page=100&page=1&sparkline=false')
    if latest_price_response.status_code == 200:
        latest_price_data = latest_price_response.json()
        if latest_price_data:
            latest_price = latest_price_data[0]['current_price']
        else:
            latest_price = None
    else:
        latest_price = None

    # Get the price data
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if 'prices' in data:
            prices = data['prices']
            dates = [datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S') for timestamp, price in prices]
            open_prices = []
            close_prices = []
            high_prices = []
            low_prices = []
            for i in range(len(prices)):
                timestamp, price = prices[i]
                if i == 0:
                    open_price = price
                else:
                    open_price = prices[i - 1][1]
                if i == len(prices) - 1:
                    close_price = price
                else:
                    close_price = prices[i + 1][1]
                high_price = max(open_price, close_price, price)
                low_price = min(open_price, close_price, price)
                open_prices.append(open_price)
                close_prices.append(close_price)
                high_prices.append(high_price)
                low_prices.append(low_price)
            #latest_price = close_prices[-1]

            # Set colors for increasing and decreasing candles
            colors = []
            for i in range(len(prices) - 1):
                if close_prices[i + 1] > open_prices[i]:
                    colors.append('green')
                else:
                    colors.append('red')

            # Create the chart figure
            fig = go.Figure(data=[go.Candlestick(x=dates, open=open_prices, high=high_prices, low=low_prices, close=close_prices,
                                                 increasing_line_color='green', decreasing_line_color='red', showlegend=False)])
            fig.update_layout(title={'text': f"<b>ISLAMI Chart</b><br><span style='font-size:14px; font-weight: normal'>Latest Price: {latest_price:.5f} USD</span>",
                                     'y':0.9,
                                     'x':0.5,
                                     'xanchor': 'center',
                                     'yanchor': 'top'},
                              yaxis_title='Price (USD)')

            # Export the chart as an image and send it to the user
            chart_image = fig.to_image(format='png')
            await update.message.reply_photo(photo=chart_image)
        else:
            await update.message.reply_text(text='Price data not available.')
    else:
        await update.message.reply_text(text='Error retrieving price data.')

def priceChart() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token("xx").build()
    application.add_handler(CommandHandler("islami", islami))
    application.add_handler(CommandHandler("ihelp", ihelp))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("chart", chart))
    # application.add_handler(CallbackQueryHandler(button_callback))
    # Run the bot until the user presses Ctrl-C
    application.run_polling()        
# End of Price and Chart

# P2P smart contract notification
latest_block = w3.eth.block_number
p2p_event_filter = p2p_contract.events.orderCreated.get_logs(fromBlock= latest_block)

async def p2p_send_notifications():
#await get_chat_id()
    while True:
        # Get new event logs
        event_logs = p2p_event_filter.get_new_entries()

        # Send notifications to the Telegram group
        
        for log in event_logs:
            order = log['args']
            type_message = "🔥Sell🔥" if order['Type'] == 1 else "💰Buy💰"
            currency = "USDT" if order['Currency'] == "0xc2132D05D31c914a87C6611C10748AEb04B58e8F" else "USDC"
            message = f"💬 New P2P order created on ISLAMIwallet\n"
            message += f"Type: {type_message}\n"
            message += f"💰 Amount: {order['Amount']/ 10**7}  ISLAMI\n"
            message += f"💰 Price: {order['Price']/ 10**6:.6f} {currency} \n"
            await bot.send_message(chat_id=chat_id, text=message)


        # Sleep for some time
        time.sleep(30)

# End of P2P

if __name__ == "__main__":
   priceChart()
   asyncio.run(update_top_players())  
   asyncio.run(p2p_send_notifications())      
    
