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
    
    def __init__(self, symbol, bar_length, rsi_length, rsi_overbought,rsi_oversold, ema_s, ema_l, signal_mw, units, position = 0):
        
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
        #**********RSI************************
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.rsi_length = rsi_length
        #*********MACD***********************
        self.EMA_S = ema_s
        self.EMA_L = ema_l
        self.signal_mw = signal_mw
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

        data["EMA_S"] = data.Close.ewm(span = self.EMA_S, min_periods = self.EMA_S).mean() 
        data["EMA_L"] = data.Close.ewm(span = self.EMA_L, min_periods = self.EMA_L).mean()
        data["MACD"] = data.EMA_S - data.EMA_L
        data["MACD_Signal"] = data.MACD.ewm(span = self.signal_mw, min_periods = self.signal_mw).mean() 

        
        data.dropna(inplace = True)
        
        cond1 = (data.RSI < rsi_oversold) #===> Señal de compra
        cond2 = (data.RSI > rsi_overbought)#===> Señal de Venta

        cond3 = (data.MACD > data.MACD_Signal) 
        cond4 = (data.MACD < data.MACD_Signal)
        
                   
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

    api_key = "api key"
    secret_key = "secret key"

    client = Client(api_key = api_key, api_secret = secret_key, tld = "com", testnet=True)

    symbol = "BTCUSDT"
    bar_length = "1m"
    rsi_length = 14        #14
    rsi_overbought = 70    #70
    rsi_oversold = 30      #30
    ema_s = 12             #12
    ema_l = 26             #26
    signal_mw = 9          #9
    units = 0.00028
    position = 0 

    trader = LongShortTrader(symbol = symbol, bar_length = bar_length, rsi_length = rsi_length,
                       rsi_overbought = rsi_overbought, rsi_oversold = rsi_oversold, ema_s = ema_s,
                       ema_l = ema_l, signal_mw = signal_mw,  units = units, position = position)

    trader.start_trading(historical_days = 1/24)

    timeout = 0.1 # seconds
    while True and trader.twm.is_alive():
        trader.twm.join(timeout=timeout) # Give twm a call to process the streaming
    # Do other stuff here

    # Stopping websocket
    trader.twm.stop()