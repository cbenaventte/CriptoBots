import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from itertools import product
import warnings
from datetime import datetime, timedelta
import time
from binance.client import Client
from binance import ThreadedWebsocketManager
import logging
warnings.filterwarnings("ignore")
plt.style.use("seaborn")
import pandas_ta as ta


class FuturesTrader():
    
    def __init__(self, symbol, bar_length, rsi_14, sma_200, sma, dev, units, position = 0, leverage = 5):
        
        self.symbol = symbol
        self.bar_length = bar_length
        self.available_intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
        self.units = units
        self.position = position
        self.leverage = leverage # NEW
        self.cum_profits = 0
        #self.trades = 0 
        #self.trade_values = []
        
        #*****************add strategy-specific attributes here******************
        
        self.RSI_14 = rsi_14
        self.SMA_200 = sma_200
        self.SMA = sma
        self.dev = dev
        
        #************************************************************************

    def start_trading(self, historical_days):

        client.futures_change_leverage(symbol = self.symbol, leverage = self.leverage) # NEW

        self.twm = ThreadedWebsocketManager(testnet = True) # testnet
        self.twm.start()
        
        if self.bar_length in self.available_intervals:
            self.get_most_recent(symbol = self.symbol, interval = self.bar_length,
                                 days = historical_days)
            self.twm.start_kline_futures_socket(callback = self.stream_candles,
                                        symbol = self.symbol, interval = self.bar_length) # Adj: start_kline_futures_socket
        # "else" to be added later in the course 

    def get_most_recent(self, symbol, interval, days):
    
        now = datetime.utcnow()
        past = str(now - timedelta(days = days))
    
        bars = client.futures_historical_klines(symbol = symbol, interval = interval,
                                            start_str = past, end_str = None, limit = 1000) # Adj: futures_historical_klines
        df = pd.DataFrame(bars)
        df["Date"] = pd.to_datetime(df.iloc[:,0], unit = "ms")
        df.columns = ["Open Time", "Open", "High", "Low", "Close", "Volume",
                      "Clos Time", "Quote Asset Volume", "Number of Trades",
                      "Taker Buy Base Asset Volume", "Taker Buy Quote Asset Volume", "Ignore", "Date"]
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        df.set_index("Date", inplace = True)
        for column in df.columns:
            df[column] = pd.to_numeric(df[column], errors = "coerce")
        df["Complete"] = [True for row in range(len(df)-1)] + [False]
        
        self.data = df

    def stream_candles(self, msg):
        
        # extract the required items from msg
        event_time = pd.to_datetime(msg["E"], unit = "ms")
        start_time = pd.to_datetime(msg["k"]["t"], unit = "ms")
        first   = float(msg["k"]["o"])
        high    = float(msg["k"]["h"])
        low     = float(msg["k"]["l"])
        close   = float(msg["k"]["c"])
        volume  = float(msg["k"]["v"])
        complete=       msg["k"]["x"]

        # stop trading session
        #if self.trades >= 5: # stop stream after 5 trades
            #self.twm.stop()
            #if self.position == 1:
                #order = client.futures_create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = self.units)
                #self.report_trade(order, "GOING NEUTRAL AND STOP")
                #self.position = 0
            #elif self.position == -1:
                #order = client.futures_create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = self.units)
                #self.report_trade(order, "GOING NEUTRAL AND STOP")
                #self.position = 0
            #else: 
                #print("STOP")
    
        # print out
        print(".", end = "", flush = True) # just print something to get a feedback (everything OK) 

         # feed df (add new bar / update latest bar)
        self.data.loc[start_time] = [first, high, low, close, volume, complete]
        
        # prepare features and define strategy/trading positions whenever the latest bar is complete
        if complete == True:
            self.define_strategy()
            self.execute_trades()

    def define_strategy(self):
        
        data = self.data.copy()
        
    #******************** define your strategy here ************************
        data = data[["Close", "Open", "High", "Low"]].copy()
        data["RSI_14"] = ta.rsi(close=data.Close, length = self.RSI_14, append=True)
        data["SMA_200"] = data.Close.rolling(window = self.SMA_200).mean()
        data['SMA'] = data.Close.rolling(window = self.SMA).mean() 
        data["Lower"] = data["SMA"] - data.Close.rolling(window = self.SMA).std() * self.dev
        data["Upper"] = data["SMA"] + data.Close.rolling(window = self.SMA).std() * self.dev
        
        data.dropna(inplace = True)
        
        cond1 = (data.SMA_200 < data.Close) & (data.Lower > data.Close)
        cond2 = (data.RSI_14 >  50) 
                                   
        data["position"] = 0
        data.loc[cond1, "position"] = 1   #Señal de compra
        data.loc[cond2, "position"] = -1  #Señal de venta
    #***********************************************************************

        self.prepared_data = data.copy()

    def execute_trades(self): # Adj! 
        if self.prepared_data["position"].iloc[-1] == 1: # if position is long -> go/stay long
            if self.position == 0:
                order = client.futures_create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING LONG")  
            elif self.position == -1:
                order = client.futures_create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = 2 * self.units)
                self.report_trade(order, "GOING LONG")
            self.position = 1

        elif self.prepared_data["position"].iloc[-1] == 0: # if position is neutral -> go/stay neutral
            if self.position == 1:
                order = client.futures_create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING NEUTRAL") 
            elif self.position == -1:
                order = client.futures_create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING NEUTRAL")
            self.position = 0

        if self.prepared_data["position"].iloc[-1] == -1: # if position is short -> go/stay short
            if self.position == 0:
                order = client.futures_create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING SHORT") 
            elif self.position == 1:
                order = client.futures_create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = 2 * self.units)
                self.report_trade(order, "GOING SHORT")
            self.position = -1

    def report_trade(self, order, going): # Adj!

        time.sleep(0.1)
        order_time = order["updateTime"]
        trades = client.futures_account_trades(symbol = self.symbol, startTime = order_time)
        order_time = pd.to_datetime(order_time, unit = "ms")
        
       # extract data from trades object
        df = pd.DataFrame(trades)
        columns = ["qty", "quoteQty", "commission","realizedPnl"]
        for column in columns:
            df[column] = pd.to_numeric(df[column], errors = "coerce")
        base_units = round(df.qty.sum(), 5)
        quote_units = round(df.quoteQty.sum(), 5)
        commission = -round(df.commission.sum(), 5)
        real_profit = round(df.realizedPnl.sum(), 5)
        price = round(quote_units / base_units, 5)
        
       # calculate cumulative trading profits
        self.cum_profits += round((commission + real_profit), 5)
        
        # print trade report
        print(2 * "\n" + 100* "-")
        print("{} | {}".format(order_time, going)) 
        print("{} | Base_Units = {} | Quote_Units = {} | Price = {} ".format(order_time, base_units, quote_units, price))
        print("{} | Profit = {} | CumProfits = {} ".format(order_time, real_profit, self.cum_profits))
        print("{} | Commission = {} ".format(order_time, commission))
        print(100 * "-" + "\n")

if __name__ == "__main__": # only if we run trader.py as a script, please do the following:

    api_key = "API KEY"
    secret_key = "SECRET KEY"

    client = Client(api_key = api_key, api_secret = secret_key, tld = "com", testnet = True)

    symbol = "ETHUSDT"
    bar_length = "1m"
    rsi_14 = 14
    sma_200= 200
    sma = 20
    dev = 2
    units = 0.032
    position = 0
    leverage = 10 

    trader = FuturesTrader(symbol = symbol, bar_length = bar_length,rsi_14 = rsi_14, 
                           sma_200 = sma_200, sma = sma, dev = dev,  units = units, position = position)

    trader.start_trading(historical_days = 1)

    timeout = 0.1 # seconds
    while True and trader.twm.is_alive():
        trader.twm.join(timeout=timeout) # Give twm a call to process the streaming
    # Do other stuff here

    # Stopping websocket
    trader.twm.stop()