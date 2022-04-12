


# The below code should only be used in combination with the Binance Spot Testnet and NOT with a Live Trading Account.


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

class  LongShortTrader():
    
    def __init__(self, symbol, bar_length, rsi_length, rsi_overbought,rsi_oversold, sma, dev, units, position = 0):
        
        self.symbol = symbol
        self.bar_length = bar_length
        self.available_intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
        self.units = units
        self.position = position
        #self.leverage = leverage # NEW
        self.cum_profits = 0
        self.trades = 0 
        self.trade_values = []
        
        #*****************add strategy-specific attributes here******************
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.rsi_length = rsi_length
        self.SMA = sma
        self.dev = dev
        #************************************************************************
    
    def start_trading(self, historical_days):
        self.twm = ThreadedWebsocketManager(testnet = True) # testnet
        self.twm.start()
        
        if self.bar_length in self.available_intervals:
            self.get_most_recent(symbol = self.symbol, interval = self.bar_length,
                                 days = historical_days)
            self.twm.start_kline_socket(callback = self.stream_candles,
                                        symbol = self.symbol, interval = self.bar_length) # Adj: start_kline_futures_socket
        # "else" to be added later in the course 
    
    def get_most_recent(self, symbol, interval, days):
    
        now = datetime.utcnow()
        past = str(now - timedelta(days = days))
    
        bars = client.get_historical_klines(symbol = symbol, interval = interval,
                                            start_str = past, end_str = None, limit = 1000)
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
        if self.trades >= 5: # stop stream after 5 trades
            self.twm.stop()
            if self.position == 1:
                order = client.create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING NEUTRAL AND STOP")
                self.position = 0
            elif self.position == -1:
                order = client.create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING NEUTRAL AND STOP")
                self.position = 0
            else: 
                print("STOP")
        
    
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
        data = data[["Close"]].copy()
        data["RSI"] = ta.rsi(close=data.Close, length = self.rsi_length, append=True)

        data['SMA'] = data.Close.rolling(window = self.SMA).mean() 
        data["Lower"] = data["SMA"] - data.Close.rolling(window = self.SMA).std() * self.dev
        data["Upper"] = data["SMA"] + data.Close.rolling(window = self.SMA).std() * self.dev

        #data['bollinger_first'] = data.Close.rolling(window = self.SMA).mean() + (self.mult_BB)*(data.Close.rolling(self.SMA).std())
        #data['bollinger_second'] = data.Close.rolling(window = self.SMA).mean() - (self.mult_BB)*(data.Close.rolling(self.SMA).std())
        data.dropna(inplace = True)
        
        cond1 = (data.RSI < rsi_oversold) #===> Señal de compra
        cond2 = (data.RSI > rsi_overbought)#===> Señal de Venta

        cond3 = (data.Upper < data.Close) #===> Señal de venta
        cond4 = (data.Lower > data.Close)#===> Señal de compra 
        #cond3 = (data.bollinger_first < data.Close) #===> Señal de venta
        #cond4 = (data.bollinger_second > data.Close)#===> Señal de compra 
                   
        data["position"] = 0
        data.loc[cond1 & cond4,"position"] = 1
        data.loc[cond2 & cond3, "position"] = -1

    #***********************************************************************

        self.prepared_data = data.copy()
    
    def execute_trades(self): 

        if self.prepared_data["position"].iloc[-1] == 1: # if position is long -> go/stay long
            if self.position == 0:
                order = client.create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING LONG")  
            elif self.position == -1:
                order = client.create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING NEUTRAL")
                time.sleep(0.1)
                order = client.create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING LONG")
            self.position = 1

        elif self.prepared_data["position"].iloc[-1] == 0: # if position is neutral -> go/stay neutral
            if self.position == 1:
                order = client.create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING NEUTRAL") 
            elif self.position == -1:
                order = client.create_order(symbol = self.symbol, side = "BUY", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING NEUTRAL") 
            self.position = 0

        if self.prepared_data["position"].iloc[-1] == -1: # if position is short -> go/stay short
            if self.position == 0:
                order = client.create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING SHORT") 
            elif self.position == 1:
                order = client.create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING NEUTRAL")
                time.sleep(0.1)
                order = client.create_order(symbol = self.symbol, side = "SELL", type = "MARKET", quantity = self.units)
                self.report_trade(order, "GOING SHORT")
            self.position = -1

    
    def report_trade(self, order, going): # Adj!
        # extract data from order object
        side = order["side"]
        time = pd.to_datetime(order["transactTime"], unit = "ms")
        base_units = float(order["executedQty"])
        quote_units = float(order["cummulativeQuoteQty"])
        price = round(quote_units / base_units, 5)
        
        # calculate trading profits
        self.trades += 1
        if side == "BUY":
            self.trade_values.append(-quote_units)
        elif side == "SELL":
            self.trade_values.append(quote_units) 
        
        if self.trades % 2 == 0:
            real_profit = round(np.sum(self.trade_values[-2:]), 3) 
            self.cum_profits = round(np.sum(self.trade_values), 3)
        else: 
            real_profit = 0
            self.cum_profits = round(np.sum(self.trade_values[:-1]), 3)
        
        # print trade report
        print(2 * "\n" + 100* "-")
        print("{} | {}".format(time, going)) 
        print("{} | Base_Units = {} | Quote_Units = {} | Price = {} ".format(time, base_units, quote_units, price))
        print("{} | Profit = {} | CumProfits = {} ".format(time, real_profit, self.cum_profits))
        print(100 * "-" + "\n")


        
if __name__ == "__main__": # only if we run trader.py as a script, please do the following:

    api_key = "iYVe0tfCC43lA64fLh2UnrEeEm0QlrMv3m2qCi7L4S9a7Q0LKuQAO6Ms9uLMPcKR"
    secret_key = "qmhBrATuJIfLMty6VnyVZOGmV5Ek1NBoXKXemAhTxn9Mv1MkSzuH4N2QyJGh81gX"

    client = Client(api_key = api_key, api_secret = secret_key, tld = "com")
    
    symbol = "BTCUSDT"
    bar_length = "1m"
    rsi_length = 10         #14
    rsi_overbought = 65    #70
    rsi_oversold = 31      #30
    sma= 20                #20
    dev = 2                #2
    units = 0.0001
    position = 0 

    trader = LongShortTrader(symbol = symbol, bar_length = bar_length, rsi_length = rsi_length, dev = dev,
                       rsi_overbought = rsi_overbought, rsi_oversold = rsi_oversold, 
                       sma = sma, units = units, position = position)

    trader.start_trading(historical_days = 1/24)

    timeout = 0.1 # seconds
    while True and trader.twm.is_alive():
        trader.twm.join(timeout=timeout) # Give twm a call to process the streaming
    # Do other stuff here

    # Stopping websocket
    trader.twm.stop()
