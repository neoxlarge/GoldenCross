import os
import talib
import requests
import pandas as pd
import numpy as np
import datetime as dt
import time
import ccxt
import plotly.graph_objects as px
from plotly.subplots import make_subplots
import yfinance as yf
import requests_cache

# User settings
ema_s = 12
ema_m1 = 55
ema_m2 = 76
ema_h1 = 144
ema_h2 = 169
sma_s = 20
strategy = "KD_over"
kd_over_bought = 90
kd_over_sold = 10
scan_crypto = False
t_frame = "1h"
scan_twstock = False
scan_usstock = True
scan_timelimit = False
plotly_theme = "plotly_dark"
sub_plot_1 = "KD"
sub_plot_2 = ""

bot_token = os.environ.get('BOT_TOKEN')
chat_id = os.environ.get('CHAT_ID')
line_notify_token = os.environ.get('LINE_NOTIFY_TOKEN')

scan_market = []
if scan_crypto:
    scan_market.append("scan_crypto")
if scan_twstock:
    scan_market.append("scan_twstock")
if scan_usstock:
    scan_market.append("scan_usstock")

# Setup cache
session = requests_cache.CachedSession('yfinance.cache', expire_after=dt.timedelta(hours=4))
session.headers['User-agent'] = 'my-program/1.0'

# Time limit logic
if scan_timelimit:
    tzone = dt.timezone(dt.timedelta(hours=8))
    now = dt.datetime.now(tz=tzone)
    # TW stock time limit
    limit_hour_tw = (18,)
    limit_weekday_tw = (1, 2, 3, 4, 5)
    if now.hour not in limit_hour_tw or now.isoweekday() not in limit_weekday_tw:
        if "scan_twstock" in scan_market:
            scan_market.remove("scan_twstock")
    # US stock time limit
    limit_hour_us = (7,)
    limit_weekday_us = (2, 3, 4, 5, 6)
    if now.hour not in limit_hour_us or now.isoweekday() not in limit_weekday_us:
        if "scan_usstock" in scan_market:
            scan_market.remove("scan_usstock")

# Symbol lists
crypto_symbol_list = []
if 'scan_crypto' in scan_market:
    exchange = ccxt.ftx()
    exchange.load_markets()
    ex_symbol_list = set()
    ex_string = ("USD:USD", "BULL", "BEAR", "HALF", "HEDGE", "JPY", "EUR", "TRYB", "AUD", "/BTC", "/DOGE", "/USDT", "GBP", "HKD", "ZAR", "CAD", "BRZ", "MXN", "ARS", "DAI")
    for i in exchange.symbols:
        for j in ex_string:
            if i.find(j) != -1:
                ex_symbol_list.add(i)
    crypto_symbol_list = list(set(exchange.symbols) - ex_symbol_list)

twstock_symbol_list = []
if "scan_twstock" in scan_market:
    twse_mode = (2, 4, 5)
    for i in twse_mode:
        res = requests.get(f"http://isin.twse.com.tw/isin/C_public.jsp?strMode={i}")
        df = pd.read_html(res.text)[0]
        df.columns = ['symbol', 'ISINCode', 'start', 'market', 'type', 'CFICode', 'remakr']
        df = df.iloc[2:]
        df = df.reset_index()
        for j in range(df.shape[0]):
            if df.at[j, 'CFICode'] == 'ESVUFR':
                symbol_part = df.at[j, 'symbol'].split('\\u3000')[0]
                if i in (2,):
                    twstock_symbol_list.append(f"{symbol_part}.tw/{df.at[j, 'symbol'].split('\\u3000')[1]}")
                elif i in (4, 5):
                    twstock_symbol_list.append(f"{symbol_part}.two/{df.at[j, 'symbol'].split('\\u3000')[1]}")
    print(f"台股數量(上市,上櫃,興櫃):{len(twstock_symbol_list)}")

usstock_symbol_list = []
if "scan_usstock" in scan_market:
    res = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    df = pd.read_html(res.text)[0]
    usstock_symbol_list = [f"{df.at[i, 'Symbol']}/{df.at[i, 'Security']}" for i in range(df.shape[0])]

# Functions
def add_technical_indicators(ohlc_df):
    ohlc_df['ema_sline'] = talib.EMA(ohlc_df["close"], timeperiod=ema_s)
    ohlc_df['ema_m1line'] = talib.EMA(ohlc_df["close"], timeperiod=ema_m1)
    ohlc_df['ema_m2line'] = talib.EMA(ohlc_df["close"], timeperiod=ema_m2)
    ohlc_df['ema_h1line'] = talib.EMA(ohlc_df["close"], timeperiod=ema_h1)
    ohlc_df['ema_h2line'] = talib.EMA(ohlc_df["close"], timeperiod=ema_h2)
    ohlc_df['sma_sline'] = talib.SMA(ohlc_df["close"], timeperiod=sma_s)
    ohlc_df['slowk'], ohlc_df['slowd'] = talib.STOCH(high=ohlc_df["high"], low=ohlc_df["low"], close=ohlc_df["close"], fastk_period=9, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
    ohlc_df['macd'], ohlc_df['macdsignal'], ohlc_df['macdhist'] = talib.MACD(ohlc_df["close"], fastperiod=12, slowperiod=26, signalperiod=9)
    return ohlc_df

def get_crypto_ohlc_data(symbol, timeframe="1h"):
    try:
        ohlc_data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=400)
        for i in ohlc_data:
            i[0] = dt.datetime.fromtimestamp(i[0] / 1000)
        ohlc_df = pd.DataFrame(ohlc_data, columns=["date", "open", "high", "low", "close", "volume"])
        ohlc_df.date = pd.to_datetime(ohlc_df.date)
        ohlc_df = add_technical_indicators(ohlc_df)
        data = {'symbol': symbol, 'ohlc_df': ohlc_df.tail(150), 'timeframe': timeframe, 'market': "crypto"}
        time.sleep(100 / 1000)
        return data
    except Exception as e:
        print(f"Error getting crypto data for {symbol}: {e}")
        return None

def get_yfstock_ohlc_data(symbol):
    try:
        symbol_code = symbol.split("/")[0]
        ticker = yf.Ticker(symbol_code)
        ohlc_df = ticker.history(period='1y', interval='1d')
        ohlc_df = ohlc_df.reset_index()
        ohlc_df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividends', 'stocksplits']
        ohlc_df = add_technical_indicators(ohlc_df)
        data = {'symbol': symbol, 'ohlc_df': ohlc_df.tail(150), 'timeframe': "1d", 'market': "stock"}
        time.sleep(100 / 1000)
        return data
    except Exception as e:
        print(f"Error getting yfinance data for {symbol}: {e}")
        return None

def check_bullorbear_ema(data):
    df = data["ohlc_df"]
    if df["ema_m1line"].iat[-1] > df["ema_m2line"].iat[-1]:
        if df["ema_sline"].iat[-1] > df["ema_m1line"].iat[-1] and df["ema_sline"].iat[-2] < df["ema_m1line"].iat[-2]:
            return "bull"
        elif df["ema_sline"].iat[-1] < df["ema_m2line"].iat[-1] and df["ema_sline"].iat[-2] > df["ema_m2line"].iat[-2]:
            return "bear"
    else:
        if df["ema_sline"].iat[-1] > df["ema_m2line"].iat[-1] and df["ema_sline"].iat[-2] < df["ema_m2line"].iat[-2]:
            return "bull"
        elif df["ema_sline"].iat[-1] < df["ema_m1line"].iat[-1] and df["ema_sline"].iat[-2] > df["ema_m1line"].iat[-2]:
            return "bear"
    return ""

def check_bullorbear_sma(data):
    df = data["ohlc_df"]
    if df["sma_sline"].iat[-1] > df["ema_sline"].iat[-1] and df["sma_sline"].iat[-2] < df["ema_sline"].iat[-2]:
        return "bull"
    elif df["sma_sline"].iat[-1] < df["ema_sline"].iat[-1] and df["sma_sline"].iat[-2] > df["ema_sline"].iat[-2]:
        return "bear"
    return ""

def check_bullorbear_kd(data):
    df = data["ohlc_df"]
    if df["slowk"].iat[-1] > kd_over_bought and df["slowd"].iat[-1] > kd_over_bought:
        return "bear"
    elif df["slowk"].iat[-1] < kd_over_sold and df["slowd"].iat[-1] < kd_over_sold:
        return "bull"
    return ""

def plotly_kline(data):
    df = data["ohlc_df"]
    candlestick = px.Candlestick(x=df["date"], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Kline")
    ema_sline = px.Scatter(x=df["date"], y=df['ema_sline'], line=dict(color='orange', width=1), mode='lines', name=f"EMA{ema_s}")
    ema_m1line = px.Scatter(x=df["date"], y=df['ema_m1line'], line=dict(color='green', width=1), mode='lines', name=f"EMA{ema_m1}")
    ema_m2line = px.Scatter(x=df["date"], y=df['ema_m2line'], line=dict(color='blue', width=1), mode='lines', name=f"EMA{ema_m2}")
    ema_h1line = px.Scatter(x=df["date"], y=df['ema_h1line'], line=dict(color='pink', width=1), mode='lines', name=f"EMA{ema_h1}")
    ema_h2line = px.Scatter(x=df["date"], y=df['ema_h2line'], line=dict(color='red', width=1), mode='lines', name=f"EMA{ema_h2}")
    sma_sline = px.Scatter(x=df["date"], y=df['sma_sline'], line=dict(color='yellow', width=1), mode='lines', name=f"SMA{sma_s}")

    fig = make_subplots(rows=1, cols=1, shared_xaxes=True, row_heights=[1])
    fig.add_traces([sma_sline, ema_sline, ema_m1line, ema_m2line, ema_h1line, ema_h2line, candlestick], rows=1, cols=1)

    title_text = f"{data['market']} {data.get('result', '')} 時框:{data['timeframe']} Last update: {df['date'].iat[-1]}"
    fig.update_layout(xaxis_rangeslider_visible=False, title=title_text, title_font_family="sans-serif", autosize=False, width=1000, height=450, template=plotly_theme)

    # try:
    #     import kaleido
    #     fig.write_image(f"{data['symbol'].split('/')[0]}.png")
    # except ImportError:
    #     print("Kaleido not installed. Skipping image generation.")
    # fig.show()

def send_to_bot_photo(tid_, msg, bot_token_, photo_path):
    if not bot_token_: return
    url = f'https://api.telegram.org/bot{bot_token_}/sendPhoto'
    with open(photo_path, "rb") as photo_opened:
        r = requests.post(url, data={"chat_id": tid_, "caption": msg, "parse_mode": "HTML"}, files={'photo': photo_opened})
        if r.status_code != 200:
            print(f"Telegram API error: {r.text}")

def send_to_line_notify_bot(msg, token, photo_path):
    if not token: return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {token}"}
    with open(photo_path, "rb") as image_file:
        r = requests.post(url=url, data={"message": msg}, headers=headers, files={'imageFile': image_file})
        if r.status_code != 200:
            print(f"Line Notify API error: {r.text}")

# Main loop
for market_type in scan_market:
    symbol_list = []
    if market_type == 'scan_crypto':
        symbol_list = crypto_symbol_list
    elif market_type == 'scan_twstock':
        symbol_list = twstock_symbol_list
    elif market_type == 'scan_usstock':
        symbol_list = usstock_symbol_list

    total_symbols = len(symbol_list)
    for count, symbol in enumerate(symbol_list):
        print(f"Processing [{count + 1}/{total_symbols}]: {symbol}...")
        try:
            ta_data = None
            if market_type == 'scan_crypto':
                ta_data = get_crypto_ohlc_data(symbol)
                if ta_data:
                    ta_data['emoji'] = "₿"
            elif market_type == 'scan_twstock':
                ta_data = get_yfstock_ohlc_data(symbol)
                if ta_data:
                    ta_data['market'] = "TW stock"
                    ta_data['emoji'] = "🇹🇼"
            elif market_type == "scan_usstock":
                ta_data = get_yfstock_ohlc_data(symbol)
                if ta_data:
                    ta_data['market'] = "US stock"
                    ta_data['emoji'] = "🇺🇸"

            if not ta_data:
                continue

            result = ""
            if strategy == 'ema_cross':
                result = check_bullorbear_ema(ta_data)
            elif strategy == 'sma_cross':
                result = check_bullorbear_sma(ta_data)
            elif strategy == 'KD_over':
                result = check_bullorbear_kd(ta_data)

            if result:
                ta_data["result"] = f"#{symbol.replace('/', ' /')} {strategy} is {result}!!"
                ta_data["emoji"] += "💰💰" if result == "bull" else "☠️☠️"

                print(f"{ta_data['emoji']} {ta_data['symbol']} {ta_data['result']}")

                # photo_path = f"{symbol.split('/')[0]}.png"
                # plotly_kline(ta_data)

                # send_to_bot_photo(chat_id, f"{ta_data['emoji']} {ta_data['result']}", bot_token, photo_path)
                # send_to_line_notify_bot(f"{ta_data['emoji']} {ta_data['result']}", line_notify_token, photo_path)

        except Exception as e:
            import traceback
            print(f"Error processing {symbol}: {e}")
            traceback.print_exc()

print("Script finished.")
