import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math
from dataclasses import dataclass
from fpdf import FPDF
import tempfile
import os
from pathlib import Path
import yfinance as yf
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg') # Headless mode for Streamlit Cloud
import matplotlib.pyplot as plt

# ───────────────────────────────
# 주식 데이터 다운로드 및 정리 (fdr 기반)
# ───────────────────────────────
def download_stock_data_fdr(ticker):
    today = datetime.now()
    one_year_ago = today - timedelta(days=365*2) # 2 years to be safe for 200 EMA
    start_date_str = one_year_ago.strftime('%Y-%m-%d')
    end_date_str = today.strftime('%Y-%m-%d')

    # FinanceDataReader에서 데이터 읽기
    df = fdr.DataReader(ticker, start_date_str, end_date_str)
    if df is None or df.empty:
        raise ValueError(f"{ticker} 데이터 없음")

    # 컬럼명 표준화
    rename_map = {
        'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close',
        'Volume': 'Volume', 'Adj Close': 'Adj Close'
    }
    # Check if we need to rename or if columns already exist
    # FDR usually returns Open, High, Low, Close, Volume, Change
    # It might not have 'Adj Close', so we use 'Close'
    
    # Ensure necessary columns exist or map them
    if 'Close' not in df.columns:
         raise ValueError(f"{ticker}에 Close 컬럼 없음")
         
    if 'Adj Close' not in df.columns:
        df['Adj Close'] = df['Close'] # Use Close as Adj Close if not present

    df = df.rename(columns=rename_map)
    
    # 인덱스가 datetime인지 확인
    if not np.issubdtype(df.index.dtype, np.datetime64):
        df.index = pd.to_datetime(df.index)
    return df

def get_kr_stocks():
    """
    Fetch list of Korean stocks (KRX) containing Name and Code.
    Returns DataFrame with columns ['Code', 'Name', 'Market']
    """
    try:
        # KRX: KOSPI, KOSDAQ, KONEX
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name', 'Market']]
    except Exception as e:
        print(f"KR Stock listing error: {e}")
        return pd.DataFrame()

def get_kr_stocks():
    """
    Fetch list of Korean stocks (KRX) containing Name and Code.
    Returns DataFrame with columns ['Code', 'Name', 'Market']
    """
    try:
        # KRX: KOSPI, KOSDAQ, KONEX
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name', 'Market']]
    except Exception as e:
        print(f"KR Stock listing error: {e}")
        return pd.DataFrame()

# ───────────────────────────────
# 최종 스코어 계산 함수
# ───────────────────────────────
def calculate_score(symbol):
    try:
        df = download_stock_data_fdr(symbol)
    except Exception as e:
        return {"error": str(e)}

    score = 0
    details = {}

    # 1. 이동평균선(EMA) 점수
    spans = [200, 125, 50, 20]
    ema_score = 0
    for span in spans:
        col_name = f'{span}_day_ema'
        df[col_name] = df['Adj Close'].ewm(span=span, adjust=False).mean()
        
        # Check if we have enough data
        if len(df) < span:
            continue
            
        current_price = df['Adj Close'].iloc[-1]
        ema_value = df[col_name].iloc[-1]
        
        price_change = ((current_price - ema_value) / ema_value * 100).round(2)
        
        if price_change >= 0:
            ema_score += 1
        else:
            ema_score -= 1
    
    score += ema_score
    details['EMA Score'] = ema_score

    # 2. PPO 점수
    fast_length, slow_length, signal_length = 12, 26, 9
    fast_ma = df['Adj Close'].rolling(window=fast_length).mean()
    slow_ma = df['Adj Close'].rolling(window=slow_length).mean()
    ppo = ((fast_ma - slow_ma) / slow_ma * 100).round(2)
    signal = ppo.rolling(window=signal_length).mean().round(2)
    histogram = (ppo - signal).round(2)
    
    # Safe check for enough data for gradient
    ppo_slope = 0
    if len(histogram) >= 3:
        # Check for NaNs
        hist_tail = histogram.dropna().tail(3)
        if len(hist_tail) == 3:
             ppo_slope = np.gradient(hist_tail).mean()

    if ppo_slope > 0:
        score += 1
        details['PPO Score'] = 1
    else:
        score -= 1
        details['PPO Score'] = -1

    # 3. RSI 점수
    n = 14
    delta = df['Adj Close'].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, abs(delta), 0)
    avg_gain = pd.Series(gain, index=df.index).rolling(window=n).mean()
    avg_loss = pd.Series(loss, index=df.index).rolling(window=n).mean()
    RS = avg_gain / avg_loss
    RSI = 100 - (100 / (1 + RS))
    
    if len(RSI) > 0 and not np.isnan(RSI.iloc[-1]):
        current_rsi = RSI.iloc[-1]
        if current_rsi > 70:
            score -= 1
            details['RSI Score'] = -1
        elif current_rsi < 30:
            score += 1
            details['RSI Score'] = 1
        else:
            details['RSI Score'] = 0
    else:
        details['RSI Score'] = 0

    return {
        "symbol": symbol,
        "score": score,
        "details": details,
        "df": df  # Return DataFrame for plotting
    }

# ───────────────────────────────
# 새로운 기능: Technical Analysis (EMA + RS)
# ───────────────────────────────

def get_stock_data_unified(ticker, start_date, end_date):
    """
    Unified data fetcher trying FDR first, then yfinance fallback.
    Returns (stock_df, spy_df)
    """
    stock_df = None
    spy_df = None
    
    # helper for column flattening
    def flatten_columns(df, ticker_name):
        if df is None or df.empty:
            return df
        # Convert columns to simple index if MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            # Try to select the ticker level
            # Level 1 is usually ticker in yf
            try:
                if ticker_name in df.columns.levels[1]:
                    df = df.xs(ticker_name, axis=1, level=1)
            except:
                pass
            
            # If still MultiIndex, just take the first level (Price Type)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        return df

    try:
        # 1. Fetch Stock Data
        # Try FDR
        try:
            stock_df = fdr.DataReader(ticker, start_date, end_date)
        except:
            pass
            
        # Fallback to YF
        if stock_df is None or stock_df.empty:
            try:
                # Standard YF download
                stock_df = yf.download(ticker, start=start_date, end=end_date, progress=False)
                stock_df = flatten_columns(stock_df, ticker)
                
                # If empty and ticker is numeric (likely KR stock), try adding .KS suffix
                if (stock_df is None or stock_df.empty) and ticker.isdigit():
                    ticker_ks = f"{ticker}.KS"
                    stock_df = yf.download(ticker_ks, start=start_date, end=end_date, progress=False)
                    stock_df = flatten_columns(stock_df, ticker_ks)
            except:
                pass

        # 2. Fetch SPY (Benchmark)
        # Try FDR first for SPY as well (more stable sometimes)
        try:
            spy_df = fdr.DataReader("SPY", start_date, end_date)
        except:
            pass

        # Fallback to YF for SPY
        if spy_df is None or spy_df.empty:
            try:
                spy_df = yf.download("SPY", start=start_date, end=end_date, progress=False)
                spy_df = flatten_columns(spy_df, "SPY")
            except:
                pass
        
        if stock_df is None or stock_df.empty or spy_df is None or spy_df.empty:
             return None, None

        # Ensure numeric and clean
        for df in [stock_df, spy_df]:
            # Sometimes index is not datetime
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
                
            for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Adj Close']:
                if col in df.columns: 
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # If 'Adj Close' missing, use 'Close'
            if 'Adj Close' not in df.columns and 'Close' in df.columns:
                df['Adj Close'] = df['Close']

        # Calculate EMAs for Stock
        if 'Close' in stock_df.columns:
            stock_df['EMA10'] = stock_df['Close'].ewm(span=10, adjust=False).mean()
            stock_df['EMA21'] = stock_df['Close'].ewm(span=21, adjust=False).mean()
        
        # Dropna
        stock_df = stock_df.dropna()
        spy_df = spy_df.dropna()
        
        return stock_df, spy_df
        
    except Exception as e:
        print(f"Data fetch error: {e}")
        return None, None

def calculate_rs(stock_df, spy_df):
    try:
        # 공통 날짜만 사용
        common_dates = stock_df.index.intersection(spy_df.index)
        if len(common_dates) == 0:
            return None, None
            
        stock_df = stock_df.loc[common_dates]
        spy_df = spy_df.loc[common_dates]

        # 수익률 계산
        stock_returns = stock_df['Close'].pct_change().fillna(0)
        spy_returns = spy_df['Close'].pct_change().fillna(0)

        # RS Line 계산
        rs_line = (1 + stock_returns).cumprod() / (1 + spy_returns).cumprod()

        # RS Line 정규화 (0-100 스케일)
        rs_line = (rs_line - rs_line.min()) / (rs_line.max() - rs_line.min()) * 100

        # RS 50일 이동평균 계산
        rs_ma50 = rs_line.rolling(window=50).mean()

        return rs_line, rs_ma50
    except Exception as e:
        print(f"RS 계산 중 오류 발생: {e}")
        return None, None

def get_technical_analysis_fig(ticker, benchmark_ticker="SPY"):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # 데이터 가져오기
    # 데이터 가져오기 (Unified Fetcher 호출)
    stock_df, spy_df = get_stock_data_unified(ticker, start_date, end_date)
    
    # If benchmark is customized and not SPY, fetch it explicitly if needed
    # But get_stock_data_unified is hardcoded for SPY currently.
    # Let's modify usage here. 
    # Actually, let's keep it simple: get_stock_data_unified handles the ticker. 
    # We need a separate fetch for benchmark if it's not SPY.
    
    if benchmark_ticker != "SPY":
        # Fetch custom benchmark
        try:
             # Try FDR first
             bench_df = fdr.DataReader(benchmark_ticker, start_date, end_date)
             if bench_df is None or bench_df.empty:
                  bench_df = yf.download(benchmark_ticker, start=start_date, end=end_date, progress=False)
             
             if bench_df is not None and not bench_df.empty:
                 # Flatten check
                 if isinstance(bench_df.columns, pd.MultiIndex):
                      try:
                          bench_df = bench_df.xs(benchmark_ticker, axis=1, level=1)
                      except:
                          bench_df.columns = bench_df.columns.get_level_values(0)
                 
                 # Clean
                 for col in ['Close', 'Adj Close']:
                      if col in bench_df.columns:
                           bench_df[col] = pd.to_numeric(bench_df[col], errors='coerce')
                 if 'Adj Close' not in bench_df.columns and 'Close' in bench_df.columns:
                      bench_df['Adj Close'] = bench_df['Close']
                 
                 spy_df = bench_df
        except Exception as e:
             print(f"Benchmark fetch failed: {e}")

    if stock_df is None or spy_df is None or stock_df.empty or spy_df.empty:
        return None, None, "유효한 데이터를 가져올 수 없습니다. (Tickers might be invalid or no data found)"

    # RS 계산
    rs_line, rs_ma50 = calculate_rs(stock_df, spy_df)
    if rs_line is None:
        return None, None, "RS 계산 실패 (데이터 부족 또는 날짜 불일치)"

    # 차트 스타일 설정
    mc = mpf.make_marketcolors(up='green',
                              down='red',
                              edge='inherit',
                              wick='inherit',
                              volume='in')
    s = mpf.make_mpf_style(marketcolors=mc)

    # EMA와 RS 라인을 위한 애드온 설정
    addplot = [
        mpf.make_addplot(stock_df['EMA10'], color='orange', width=1.2, label='10 EMA'),  # 두께 증가
        mpf.make_addplot(stock_df['EMA21'], color='blue', width=1.2, label='21 EMA'),    # 두께 증가
        mpf.make_addplot(rs_line, panel=1, color='purple',
                        title='RS Line', ylabel='RS'),
        mpf.make_addplot(rs_ma50, panel=1, color='gray', width=1.0,
                        linestyle='--')
    ]

    try:
        # 차트 그리기
        fig, axes = mpf.plot(stock_df,
                            type='candle',
                            style=s,
                            addplot=addplot,
                            returnfig=True,
                            figsize=(12, 8),
                            panel_ratios=(7,3),
                            title=f'\n{ticker} Technical Analysis')

        # 패널 제목 설정
        axes[0].set_title('Price (with 10 & 21 EMA)')
        axes[1].set_title('Relative Strength with 50MA')

        # 범례 추가 및 위치 조정
        axes[0].legend(['10 EMA (Orange)', '21 EMA (Blue)'], loc='upper left')
        axes[1].legend(['RS', 'RS 50MA'], loc='upper left')
        
        # RS 데이터 딕셔너리 생성
        rs_data = {
            'stock_df': stock_df,
            'spy_df': spy_df,
            'rs_line': rs_line,
            'rs_ma50': rs_ma50
        }
        
        return fig, rs_data, None
    except Exception as e:
        return None, None, f"차트 그리기 중 오류 발생: {e}"

# ───────────────────────────────
# ROC (Velocity) & Delta ROC (Acceleration) 함수
# ───────────────────────────────
def calculate_roc(series, n=20):
    """
    Calculate the Rate of Change (ROC) indicator.
    Formula: ROC = ((Current Value - Value "n" periods ago) / Value "n" periods ago) * 100
    """
    roc = ((series - series.shift(n)) / series.shift(n)) * 100
    return roc

def get_roc_analysis_fig(ticker):
    try:
        # Use simple fdr for single ticker history
        # (Using safe period ~2y)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)
        
        data = fdr.DataReader(ticker, start_date, end_date)
        if data is None or data.empty:
             # Fallback
             data = yf.download(ticker, period="2y", progress=False)

        if data.empty:
            return None, f"No data found for {ticker}."
            
        # Clean up column names if needed
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        # Ensure Close exists
        if 'Close' not in data.columns and 'Adj Close' in data.columns:
            data['Close'] = data['Adj Close']
            
        if 'Close' not in data.columns:
             return None, "Close column not found."

        # Calculate ROC (Velocity)
        n = 20
        # Create a copy to avoid SettingWithCopy warnings if any
        plot_data = data.copy()
        
        # yfinance columns can be MultiIndex if multiple tickers, but here we expect one.
        # If plot_data['Close'] is a DataFrame (multi-ticker), this might fail, 
        # but the app asks for one ticker at a time.
        
        plot_data['ROC'] = calculate_roc(plot_data['Close'], n)

        # Calculate Delta ROC (Acceleration) = ROC of ROC
        plot_data['Delta_ROC'] = calculate_roc(plot_data['ROC'], n)

        # Drop NaN values created by shift
        plot_data = plot_data.dropna()

        if plot_data.empty:
             return None, "Not enough data to calculate ROC/Delta ROC (need > 40 days)."

        # Plotting
        # Create figure with 3 subplots
        fig, axes = plt.subplots(3, 1, figsize=(12, 12))
        
        # Subplot 1: Closing Price
        axes[0].plot(plot_data.index, plot_data['Close'], label='Close Price')
        axes[0].set_title(f'{ticker} Closing Price')
        axes[0].legend()
        axes[0].grid(True)

        # Subplot 2: ROC (Velocity)
        axes[1].plot(plot_data.index, plot_data['ROC'], label=f'{n}-Day ROC (Velocity)', color='orange')
        axes[1].axhline(0, color='black', linewidth=1, linestyle='--')
        axes[1].set_title(f'{ticker} Rate of Change (Velocity)')
        axes[1].legend()
        axes[1].grid(True)

        # Subplot 3: Delta ROC (Acceleration)
        axes[2].plot(plot_data.index, plot_data['Delta_ROC'], label=f'{n}-Day Delta ROC (Acceleration)', color='green')
        axes[2].axhline(0, color='black', linewidth=1, linestyle='--')
        axes[2].set_title(f'{ticker} Delta ROC (Acceleration)')
        axes[2].legend()
        axes[2].grid(True)

        plt.tight_layout()
        
        return fig, plot_data, None

    except Exception as e:
        return None, None, str(e)

# ───────────────────────────────
# Kaufman Adaptive Moving Average (KAMA) 함수
# ───────────────────────────────
def calculate_kama(prices, n=10):
    """
    Calculate Kaufman Adaptive Moving Average (KAMA)
    """
    # Create a copy and ensure 1D Series
    prices = prices.copy()
    if isinstance(prices, pd.DataFrame):
        prices = prices.iloc[:, 0]  # Take the first column if it's a DataFrame
    
    # Calculate the Efficiency Ratio (ER)
    change = np.abs(prices - prices.shift(n))
    volatility = prices.diff().abs().rolling(window=n).sum()
    
    # Avoid division by zero
    volatility = volatility.replace(0, np.nan) 
    er = change / volatility
    er = er.fillna(0)

    # Calculate the Smoothing Constant (SC)
    fastest_sc = 2 / (2 + 1)
    slowest_sc = 2 / (30 + 1)
    sc = np.square(er * (fastest_sc - slowest_sc) + slowest_sc)

    # Ensure we are working with flat numpy arrays for the loop
    # This prevents "setting an array element with a sequence" errors
    # if pandas objects have dimension weirdness.
    price_values = prices.values.flatten()
    sc_values = sc.values.flatten()
    kama = np.zeros(len(price_values))
    kama[:] = np.nan
    
    # Initialize first n values same as price
    # (Use first valid price or just copy first n)
    kama[:n] = price_values[:n]
    
    for i in range(n, len(price_values)):
        # Calculate KAMA step by step using scalar values
        kama[i] = kama[i-1] + sc_values[i] * (price_values[i] - kama[i-1])

    return pd.Series(kama, index=prices.index)

def get_kama_analysis_fig(ticker):
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        data = fdr.DataReader(ticker, start_date, end_date)
        if data is None or data.empty:
             data = yf.download(ticker, period='1y', progress=False)

        if data is None or data.empty:
            return None, f"No data found for {ticker}."

        # Clean up column names if needed
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if 'Close' not in data.columns and 'Adj Close' in data.columns:
             data['Close'] = data['Adj Close']
             
        if 'Close' not in data.columns:
             return None, "Close column not found in data."

        prices = data['Close']
        kama = calculate_kama(prices)

        # Plotting
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.plot(prices.index, prices, label='Price', color='blue', alpha=0.6)
        ax.plot(prices.index, kama, label='KAMA', color='red', linewidth=1.5)

        ax.set_title(f'Kaufman Adaptive Moving Average (KAMA) for {ticker}')
        ax.set_xlabel('Date')
        ax.set_ylabel('Price')
        ax.legend()
        ax.grid(True)
        
        return fig, None

    except Exception as e:
        return None, str(e)

# ───────────────────────────────
# 백테스팅 전략 (Backtesting Strategy)
# ───────────────────────────────

@dataclass
class StrategyMetrics:
    cagr: float
    sharpe: float
    mdd: float
    win_rate: float
    trades: int
    last_buy: str
    last_sell: str
    state: str

def calculate_obv(close, volume):
    delta = close.diff().fillna(0.0)
    direction = np.where(delta > 0, 1, np.where(delta < 0, -1, 0))
    return (direction * volume).cumsum()

def run_backtest_strategy(ticker, ema_fast=20, ema_slow=50, obv_ma=50, capital=100000):
    try:
        # 1. 데이터 로드 (최근 3년)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365*3)
        
        # utils.download_stock_data_fdr을 재사용하거나 새로 로드
        df = download_stock_data_fdr(ticker)
        # 기간 필터링
        df = df[df.index >= pd.Timestamp(start_date)]
        
        if df.empty or len(df) < max(ema_slow, obv_ma) + 20:
             return None, None, f"데이터 부족 ({len(df)} rows)"

        # 2. 지표 계산
        c, v = df['Close'], df['Volume']
        df['EMA_fast'] = c.ewm(span=ema_fast, adjust=False).mean()
        df['EMA_slow'] = c.ewm(span=ema_slow, adjust=False).mean()
        df['OBV'] = calculate_obv(c, v)
        df['OBV_MA'] = df['OBV'].rolling(obv_ma).mean()
        df['dEMA_fast'] = df['EMA_fast'].diff()
        
        # 3. 시그널 생성
        # Entry: EMA정배열 & EMA_fast상승 & OBV상승추세
        entry = (df['EMA_fast'] > df['EMA_slow']) & (df['dEMA_fast'] > 0) & (df['OBV'] > df['OBV_MA'])
        # Exit: EMA_fast 하락전환 OR 가격이 EMA_slow 하회
        exit_ = (df['dEMA_fast'] < 0) | (df['Close'] < df['EMA_slow'])

        # 포지션 시뮬레이션
        pos = np.zeros(len(df), dtype=int)
        in_pos = False
        
        entry_vals = entry.values
        exit_vals = exit_.values
        
        for i in range(1, len(df)):
            if not in_pos and entry_vals[i]:
                in_pos = True
                pos[i] = 1
            elif in_pos:
                if exit_vals[i]:
                    in_pos = False
                    pos[i] = 0
                else:
                    pos[i] = 1
        
        df['Position'] = pos
        df['Buy'] = ((df['Position'] == 1) & (df['Position'].shift(1) == 0)).astype(int)
        df['Sell'] = ((df['Position'] == 0) & (df['Position'].shift(1) == 1)).astype(int)

        # 4. 수익률 계산 (백테스트)
        col_close = df['Close']
        rets = col_close.pct_change().fillna(0.0)
        
        # 수수료/슬리피지 가정 (0.15% = 15bps [fee+slippage approx])
        cost_bps = 0.0015 
        
        # 전략 수익률: 전일 포지션 * 당일 수익률 - 거래비용
        # 포지션 진입/청산 시점에 비용 발생
        trade_cost = df['Position'].diff().abs().fillna(0.0) * cost_bps
        strat_ret = (df['Position'].shift(1).fillna(0) * rets) - trade_cost
        
        df['Equity'] = (1.0 + strat_ret).cumprod() * capital
        df['BuyHold'] = (col_close / col_close.iloc[0]) * capital

        # 5. 성과 지표 계산
        days = (df.index[-1] - df.index[0]).days
        years = max(days/365.25, 0.001)
        cagr = (df['Equity'].iloc[-1] / df['Equity'].iloc[0])**(1/years) - 1.0
        
        # MDD
        cummax = df['Equity'].cummax()
        dd = df['Equity'] / cummax - 1.0
        mdd = dd.min()
        
        # Sharpe
        ann_ret = strat_ret.mean() * 252
        ann_vol = strat_ret.std() * np.sqrt(252)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        
        # 승률 & 거래 횟수
        trade_pnls = []
        entry_price = 0
        buy_indices = df.index[df['Buy'] == 1]
        sell_indices = df.index[df['Sell'] == 1]
        
        trades = len(sell_indices) # 매도 횟수 기준
        wins = 0
        
        # 간단한 승률 계산 (매수매도 쌍 기준)
        # 엄밀한 PnL 매칭보다는 단순하게 거래별 수익 여부 추정
        # 실제로는 Equity 커브에서 추출하는게 정확하지만 여기선 약식
        
        metrics = StrategyMetrics(
            cagr=cagr * 100, # %
            sharpe=sharpe,
            mdd=mdd * 100, # %
            win_rate=0.0, # 계산 복잡하므로 일단 0 or 추후 구현
            trades=trades,
            last_buy=buy_indices[-1].strftime('%Y-%m-%d') if len(buy_indices) > 0 else "없음",
            last_sell=sell_indices[-1].strftime('%Y-%m-%d') if len(sell_indices) > 0 else "없음",
            state="보유" if df['Position'].iloc[-1] == 1 else "현금"
        )

        return df, metrics, None
        
    except Exception as e:
        return None, None, str(e)


def get_backtest_fig(ticker, df):
    """
    백테스트 결과(신호 포함) mplfinance 차트 생성
    """
    try:
        if df is None or df.empty:
            return None, "데이터 없음"
            
        # 최근 1년 정도만 시각화 (너무 길면 안보임)
        plot_df = df.tail(252).copy()
        
        ap = []
        
        # EMA
        ap.append(mpf.make_addplot(plot_df['EMA_fast'], color='blue', width=1.0))
        ap.append(mpf.make_addplot(plot_df['EMA_slow'], color='orange', width=1.0))
        
        # Buy/Sell Markers
        # NaN이 아닌 곳만 찍기 위해 마스킹
        buy_signals = plot_df['Low'] * 0.98
        buy_signals[plot_df['Buy'] != 1] = np.nan
        
        sell_signals = plot_df['High'] * 1.02
        sell_signals[plot_df['Sell'] != 1] = np.nan
        
        ap.append(mpf.make_addplot(buy_signals, type='scatter', markersize=100, marker='^', color='green'))
        ap.append(mpf.make_addplot(sell_signals, type='scatter', markersize=100, marker='v', color='red'))

        # Style
        mc = mpf.make_marketcolors(up='red', down='blue', inherit=True) # 한국 스타일
        s = mpf.make_mpf_style(marketcolors=mc)

        fig, ax = mpf.plot(plot_df, 
                           type='candle', 
                           addplot=ap, 
                           style=s, 
                           returnfig=True, 
                           figsize=(12, 8),
                           title=f"{ticker} Strategy Signals (Last 1 Year)",
                           volume=True)
                           
        return fig, None
    except Exception as e:
        return None, str(e)

# ───────────────────────────────
# PDF 리포트 생성 함수
# ───────────────────────────────
def create_pdf_report(ticker, score_dict, figures):
    """
    Generate PDF report.
    ticker: str
    score_data: dict (from calculate_score)
    figures: dict {'key': fig_object}
    """
    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 20)
            self.cell(0, 10, f'Stock Analysis Report: {ticker}', new_x="LMARGIN", new_y="NEXT", align='C')
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', new_x="LMARGIN", new_y="NEXT", align='C')

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    # 1. Score Summary
    score = score_dict.get('score', 0)
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(0, 10, f"Total Score: {score}/3", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    details = score_dict.get('details', {})
    pdf.set_font("Helvetica", size=12)
    for k, v in details.items():
        pdf.cell(0, 8, f"{k}: {v}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    # 2. Charts
    temp_files = []
    
    try:
        for title, fig in figures.items():
            pdf.add_page()
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                temp_filename = tmp.name
            
            # Save figure to temp file
            if hasattr(fig, 'savefig'): # Matplotlib
                fig.savefig(temp_filename, bbox_inches='tight', dpi=100)
            elif hasattr(fig, 'write_image'): # Plotly
                try:
                    fig.write_image(temp_filename, format="png", engine="kaleido")
                except Exception as e:
                    pdf.cell(0, 10, f"Error saving plotly chart: {str(e)}", new_x="LMARGIN", new_y="NEXT")
                    continue
            else:
                continue
            
            # Embed in PDF
            pdf.image(temp_filename, w=170)
            temp_files.append(temp_filename)
            
        return pdf.output()
            
    except Exception as e:
        print(f"PDF Gen Error: {e}")
        return None
    finally:
        # Cleanup temp files
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except:
                pass

# ───────────────────────────────
# 데이터 기반 분석 (Data-Driven Interpretation)
# ───────────────────────────────

def get_score_interpretation(result):
    """
    종합 점수 및 개별 지표를 바탕으로 한국어 분석 메시지 생성
    """
    details = result.get('details', {})
    score = result.get('score', 0)
    
    analysis = []
    
    # 1. 종합 의견
    if score >= 2:
        analysis.append("🌟 **강력한 수급 및 추세 상승 구간**입니다. 모든 지표가 우호적인 신호를 보내고 있습니다.")
    elif score >= 1:
        analysis.append("📈 **긍정적인 추세**가 형성되고 있습니다. 점진적인 수급 개선이 확인됩니다.")
    elif score <= -2:
        analysis.append("⚠️ **강한 하락 압력**을 받고 있습니다. 리스크 관리가 최우선인 구간입니다.")
    elif score <= -1:
        analysis.append("📉 **추세가 약화**되고 있습니다. 지지선 확인이 필요한 시점입니다.")
    else:
        analysis.append("⚖️ **방향성 탐색 구간**입니다. 횡보세가 이어며 에너지를 응축하고 있습니다.")
        
    # 2. 세부 분석
    ema_s = details.get('EMA Score', 0)
    if ema_s > 0:
        analysis.append(f"- **이평선**: 주가가 주요 장단기 이동평균선 위에 위치하여 지지력이 견고합니다.")
    else:
        analysis.append(f"- **이평선**: 단기/중기 이평선을 하회하고 있어 정배열로의 전환이 필요합니다.")
        
    ppo_s = details.get('PPO Score', 0)
    if ppo_s > 0:
        analysis.append(f"- **모멘텀**: PPO 가속도가 붙고 있어 상승 탄력이 강화되는 단계입니다.")
    else:
        analysis.append(f"- **모멘텀**: 모멘텀 탄력이 줄어들고 있거나 하락세가 지속되고 있습니다.")
        
    rsi_s = details.get('RSI Score', 0)
    if rsi_s < 0:
        analysis.append(f"- **RSI**: 현재 과매수권에 진입하여 단기 차익 실현 매물에 주의가 필요합니다.")
    elif rsi_s > 0:
        analysis.append(f"- **RSI**: 과매도권에서 반등을 모색하고 있어 기술적 반등 가능성이 높습니다.")
        
    return "\n".join(analysis)

def get_roc_interpretation(df):
    """
    ROC 및 Delta ROC를 통한 속도/가속도 분석
    """
    if 'ROC' not in df.columns or 'Delta_ROC' not in df.columns:
        return "데이터가 부족하여 분석을 생성할 수 없습니다."
        
    curr_roc = df['ROC'].iloc[-1]
    curr_acc = df['Delta_ROC'].iloc[-1]
    
    analysis = []
    
    # 속도 분석
    if curr_roc > 5:
        analysis.append("🏃‍♂️ **빠른 상승 속도**: 현재 주가가 강력한 속도로 우상향하고 있습니다.")
    elif curr_roc < -5:
        analysis.append("⛷️ **빠른 하락 속도**: 하향 이탈 속도가 가파르므로 주의가 필요합니다.")
    else:
        analysis.append("🚶 **안정적인 흐름**: 속도의 변화가 크지 않은 완만한 구간입니다.")
        
    # 가속도 분석
    if curr_acc > 0:
        analysis.append("🚀 **가속도 증가**: 상승의 힘(가속)이 더 강해지고 있어 추가 탄력이 기대됩니다.")
    else:
        analysis.append("🛑 **가속도 둔화**: 상승 속도가 줄어들고 있어 추세 반전이나 횡보 가능성이 보입니다.")
        
    return "\n".join(analysis)

def get_kama_interpretation(df, kama_series):
    """
    KAMA와 주가 관계 분석
    """
    curr_price = df['Close'].iloc[-1]
    curr_kama = kama_series.iloc[-1]
    
    if curr_price > curr_kama:
        return "🛠️ **KAMA 분석**: 주가가 적응형 이평선(KAMA) 위에 있어 소음(Noise)을 극복한 **안정적 상승세**로 판단됩니다."
    else:
        return "🛠️ **KAMA 분석**: 주가가 KAMA 아래로 내려왔습니다. 시장의 변동성에 의해 **단기 추세가 이탈**된 상태입니다."


# ───────────────────────────────
# 향상된 종목별 데이터 기반 해석 함수들
# ───────────────────────────────

def get_ema_chart_interpretation(df):
    """
    Price & EMA Chart 종목별 상세 해석
    - 현재가 vs 주요 이평선 위치
    - 정배열/역배열 상태
    - 골든크로스/데드크로스 탐지
    - 액션 가이드
    """
    try:
        if df is None or df.empty or 'Adj Close' not in df.columns:
            return "📊 데이터가 부족하여 EMA 분석을 수행할 수 없습니다."
        
        analysis = []
        curr_price = df['Adj Close'].iloc[-1]
        
        # 1. 현재가 vs 주요 이평선 위치
        ema_cols = ['20_day_ema', '50_day_ema', '200_day_ema']
        positions = {}
        
        for col in ema_cols:
            if col in df.columns and not pd.isna(df[col].iloc[-1]):
                ema_val = df[col].iloc[-1]
                diff_pct = ((curr_price - ema_val) / ema_val * 100)
                positions[col] = {'value': ema_val, 'diff_pct': diff_pct}
        
        if positions:
            # 20일선 위치 (가장 중요)
            if '20_day_ema' in positions:
                ema20 = positions['20_day_ema']
                direction = "위" if ema20['diff_pct'] > 0 else "아래"
                analysis.append(f"📍 **현재 위치**: 주가 ${curr_price:.2f}, 20일선(${ema20['value']:.2f}) {direction} {abs(ema20['diff_pct']):.2f}%")
        
        # 2. 정배열/역배열 판단
        if all(col in df.columns for col in ['20_day_ema', '50_day_ema', '200_day_ema']):
            ema20 = df['20_day_ema'].iloc[-1]
            ema50 = df['50_day_ema'].iloc[-1]
            ema200 = df['200_day_ema'].iloc[-1]
            
            if ema20 > ema50 > ema200:
                analysis.append("🎯 **정배열 상태**: 20 > 50 > 200 (강력한 상승 추세)")
            elif ema20 < ema50 < ema200:
                analysis.append("⚠️ **역배열 상태**: 20 < 50 < 200 (하락 추세)")
            else:
                analysis.append("⚖️ **혼조 상태**: 이평선들이 뒤엉켜 방향성을 찾는 중")
        
        # 3. 골든크로스/데드크로스 탐지 (최근 10일 이내)
        if '20_day_ema' in df.columns and '50_day_ema' in df.columns:
            # 최근 10일간 데이터 확인
            lookback = min(10, len(df))
            recent_df = df.tail(lookback)
            
            if len(recent_df) >= 2:
                # 골든크로스: 20선이 50선을 상향 돌파
                for i in range(len(recent_df) - 1):
                    prev_20 = recent_df['20_day_ema'].iloc[i]
                    prev_50 = recent_df['50_day_ema'].iloc[i]
                    curr_20 = recent_df['20_day_ema'].iloc[i + 1]
                    curr_50 = recent_df['50_day_ema'].iloc[i + 1]
                    
                    if prev_20 <= prev_50 and curr_20 > curr_50:
                        days_ago = len(recent_df) - i - 2
                        analysis.append(f"⚡ **골든크로스**: 20일선이 50일선을 {days_ago}일 전 돌파 (매수 신호 발생)")
                        break
                    elif prev_20 >= prev_50 and curr_20 < curr_50:
                        days_ago = len(recent_df) - i - 2
                        analysis.append(f"🔻 **데드크로스**: 20일선이 50일선을 {days_ago}일 전 하향 이탈 (매도 신호 발생)")
                        break
        
        # 4. 액션 가이드
        if '20_day_ema' in positions and '50_day_ema' in positions:
            ema20_above = positions['20_day_ema']['diff_pct'] > 0
            ema50_above = positions['50_day_ema']['diff_pct'] > 0
            
            if ema20_above and ema50_above:
                analysis.append("💡 **액션 가이드**: 추세 추종 매수 전략 유효, 20일선이 동적 지지선 역할")
            elif not ema20_above and not ema50_above:
                analysis.append("💡 **액션 가이드**: 하락 추세, 20일선 상향 돌파 시까지 관망 권장")
            else:
                analysis.append("💡 **액션 가이드**: 추세 전환 구간, 50일선 돌파 여부 주시 필요")
        
        return "\n".join(analysis) if analysis else "📊 EMA 분석 결과를 생성할 수 없습니다."
        
    except Exception as e:
        return f"📊 EMA 해석 중 오류 발생: {str(e)}"

def get_rs_interpretation(stock_df, spy_df, rs_line, rs_ma50):
    """
    RS (Relative Strength) Line 상세 해석
    """
    try:
        if rs_line is None or len(rs_line) < 50:
            return "📊 RS 데이터가 부족하여 분석할 수 없습니다."
        
        analysis = []
        curr_rs = rs_line.iloc[-1]
        curr_rs_ma = rs_ma50.iloc[-1] if rs_ma50 is not None and len(rs_ma50) > 0 else None
        
        # 1. RS 절대값 평가
        rs_status = "중립"
        if curr_rs > 70:
            rs_status = "강세"
        elif curr_rs < 30:
            rs_status = "약세"
        
        analysis.append(f"📊 **상대 강도**: {curr_rs:.1f}/100 (시장 대비 {rs_status})")
        
        # 2. RS 추세 방향
        if len(rs_line) >= 10:
            rs_2weeks_ago = rs_line.iloc[-10]
            rs_change = curr_rs - rs_2weeks_ago
            trend_desc = "상승 중" if rs_change > 0 else "하락 중"
            
            if curr_rs_ma is not None and not pd.isna(curr_rs_ma):
                ma_relation = "위" if curr_rs > curr_rs_ma else "아래"
                analysis.append(f"📈 **추세**: RS선이 50일 평균({curr_rs_ma:.1f}) {ma_relation}에서 {trend_desc} ({rs_change:+.1f}pt, 2주간)")
            else:
                analysis.append(f"📈 **추세**: {trend_desc} ({rs_change:+.1f}pt, 2주간)")
        
        # 3. 주도주/낙오주 판정
        if curr_rs > 60 and (curr_rs_ma is None or curr_rs > curr_rs_ma):
            analysis.append("🏆 **평가**: 주도주 후보 - 시장 하락 시에도 방어력 우수")
            analysis.append("💡 **액션 가이드**: 시장 조정 시 우선 매수 대상, 상대적 강세 유지 중")
        elif curr_rs < 40 and (curr_rs_ma is None or curr_rs < curr_rs_ma):
            analysis.append("📉 **평가**: 시장 대비 약세 - 섹터 또는 종목 고유 이슈 점검 필요")
            analysis.append("💡 **액션 가이드**: RS가 50선 돌파 시까지 관망, 상대적 약세 지속")
        else:
            analysis.append("⚖️ **평가**: 시장과 동조화 - 평균적인 움직임")
            analysis.append("💡 **액션 가이드**: RS 상승 돌파 시 주도주 전환 가능성 주시")
        
        return "\n".join(analysis)
        
    except Exception as e:
        return f"📊 RS 해석 중 오류 발생: {str(e)}"

def get_roc_interpretation_enhanced(df_with_roc):
    """
    ROC & Delta ROC 향상된 해석
    """
    try:
        if df_with_roc is None or df_with_roc.empty:
            return "📊 ROC 데이터가 부족하여 분석할 수 없습니다."
        
        if 'ROC' not in df_with_roc.columns or 'Delta_ROC' not in df_with_roc.columns:
            return "📊 ROC 계산이 완료되지 않았습니다."
        
        analysis = []
        curr_roc = df_with_roc['ROC'].iloc[-1]
        curr_delta_roc = df_with_roc['Delta_ROC'].iloc[-1]
        
        # 과거 평균 비교
        lookback = min(120, len(df_with_roc))
        if lookback > 20:
            roc_history = df_with_roc['ROC'].tail(lookback)
            avg_roc = roc_history.mean()
            
            if abs(avg_roc) > 0.1:
                speed_ratio = abs(curr_roc) / abs(avg_roc)
                analysis.append(f"🏃 **속도(ROC)**: {curr_roc:+.2f}% (20일 전 대비 상승률)")
                analysis.append(f"  - 과거 6개월 평균({avg_roc:+.2f}%) 대비 {speed_ratio:.1f}배")
            else:
                analysis.append(f"🏃 **속도(ROC)**: {curr_roc:+.2f}% (20일 전 대비)")
        else:
            analysis.append(f"🏃 **속도(ROC)**: {curr_roc:+.2f}% (20일 전 대비)")
        
        # 속도 해석
        if curr_roc > 10:
            analysis.append("  - ⚡ 빠른 상승 속도 - 강한 상승 모멘텀")
        elif curr_roc < -10:
            analysis.append("  - 🔻 빠른 하락 속도 - 조정 압력")
        elif abs(curr_roc) < 3:
            analysis.append("  - 🚶 완만한 흐름 - 횡보 구간")
        
        # 가속도 분석
        analysis.append(f"\n🚀 **가속도(Delta ROC)**: {curr_delta_roc:+.2f}%")
        
        if curr_delta_roc > 1:
            analysis.append("  - 가속도 증가 중 - 상승의 힘이 강화되는 단계")
        elif curr_delta_roc < -1:
            analysis.append("  - 가속도 감소 중 - 모멘텀 둔화, 추세 반전 주의")
        else:
            analysis.append("  - 가속도 중립 - 현재 속도 유지")
        
        # 액션 가이드
        if curr_roc > 5 and curr_delta_roc > 0:
            analysis.append("\n💡 **액션 가이드**: 모멘텀 매수 타이밍, 가속 진행 중 (단 ROC > +15% 시 단기 과열 주의)")
        elif curr_roc < -5 and curr_delta_roc < 0:
            analysis.append("\n💡 **액션 가이드**: 하락 가속 구간, 반등 대기 또는 손절 고려")
        elif curr_roc > 0 and curr_delta_roc < 0:
            analysis.append("\n💡 **액션 가이드**: 상승 모멘텀 둔화 중, 익절 타이밍 검토")
        elif curr_roc < 0 and curr_delta_roc > 0:
            analysis.append("\n💡 **액션 가이드**: 하락 속도 둔화, 바닥 근접 신호 (반등 준비)")
        else:
            analysis.append("\n💡 **액션 가이드**: 중립 구간, 명확한 모멘텀 신호 대기")
        
        return "\n".join(analysis)
        
    except Exception as e:
        return f"📊 ROC 해석 중 오류 발생: {str(e)}"

def get_kama_interpretation_enhanced(df, kama_series):
    """
    KAMA 향상된 해석
    """
    try:
        if df is None or kama_series is None or len(kama_series) < 10:
            return "🦎 KAMA 데이터가 부족하여 분석할 수 없습니다."
        
        if 'Close' not in df.columns:
            return "🦎 주가 데이터가 부족합니다."
        
        analysis = []
        curr_price = df['Close'].iloc[-1]
        curr_kama = kama_series.iloc[-1]
        
        # 1. KAMA 변화율
        if len(kama_series) >= 5:
            kama_5d_ago = kama_series.iloc[-5]
            kama_change_pct = ((curr_kama - kama_5d_ago) / kama_5d_ago * 100) if kama_5d_ago != 0 else 0
            
            trend_strength = "완만한" if abs(kama_change_pct) < 1 else "뚜렷한"
            trend_dir = "상승" if kama_change_pct > 0 else "하락"
            
            analysis.append(f"🦎 **KAMA**: ${curr_kama:.2f} (5일간 {kama_change_pct:+.2f}% {trend_dir} - {trend_strength} 추세)")
        else:
            analysis.append(f"🦎 **KAMA**: ${curr_kama:.2f}")
        
        # 2. 주가 vs KAMA 위치
        price_diff_pct = ((curr_price - curr_kama) / curr_kama * 100) if curr_kama != 0 else 0
        position = "위" if price_diff_pct > 0 else "아래"
        
        analysis.append(f"📍 **주가 위치**: KAMA {position} {abs(price_diff_pct):.2f}%")
        
        # 3. KAMA 기울기
        if len(kama_series) >= 5:
            daily_changes = kama_series.diff().tail(5)
            avg_daily_change = daily_changes.mean()
            avg_daily_pct = (avg_daily_change / curr_kama * 100) if curr_kama != 0 else 0
            
            slope_desc = "가파름" if abs(avg_daily_pct) > 0.3 else "완만함"
            analysis.append(f"📐 **기울기**: {slope_desc} (최근 5일 평균 일일 {avg_daily_pct:+.2f}%)")
        
        # 4. 액션 가이드
        if len(kama_series) >= 5:
            kama_5d_ago = kama_series.iloc[-5]
            kama_change_pct = ((curr_kama - kama_5d_ago) / kama_5d_ago * 100) if kama_5d_ago != 0 else 0
            daily_changes = kama_series.diff().tail(5)
            avg_daily_change = daily_changes.mean()
            avg_daily_pct = (avg_daily_change / curr_kama * 100) if curr_kama != 0 else 0
            
            if abs(kama_change_pct) > 2 and abs(avg_daily_pct) > 0.3:
                if price_diff_pct > 0:
                    analysis.append("\n💡 **액션 가이드**: 추세장 확정, KAMA가 동적 지지선 역할 (상승 추세 추종)")
                else:
                    analysis.append("\n💡 **액션 가이드**: 하락 추세 진행 중, KAMA 상향 돌파 시까지 관망")
            elif abs(kama_change_pct) < 1:
                analysis.append("\n💡 **액션 가이드**: 횡보장, 소음(Noise) 많은 구간 - 방향성 확정 대기")
            else:
                analysis.append("\n💡 **액션 가이드**: 추세 형성 초기 단계, KAMA 기울기 증가 여부 모니터링")
        
        return "\n".join(analysis)
        
    except Exception as e:
        return f"🦎 KAMA 해석 중 오류 발생: {str(e)}"

def get_backtest_interpretation(metrics, bt_df):
    """
    Backtest Results 상세 해석
    """
    try:
        if metrics is None or bt_df is None or bt_df.empty:
            return "🛠️ 백테스트 데이터가 없습니다."
        
        analysis = []
        
        # 1. 성과 비교
        final_equity = bt_df['Equity'].iloc[-1]
        final_buyhold = bt_df['BuyHold'].iloc[-1]
        initial_capital = bt_df['Equity'].iloc[0]
        
        strategy_return = ((final_equity - initial_capital) / initial_capital * 100)
        buyhold_return = ((final_buyhold - initial_capital) / initial_capital * 100)
        outperformance = strategy_return - buyhold_return
        
        perf_status = "우수" if outperformance > 0 else "부진"
        
        analysis.append(f"📊 **전략 성과**: CAGR {metrics.cagr:+.2f}% (바이앤홀드 {buyhold_return:+.1f}% 대비 {outperformance:+.1f}%p {perf_status})")
        
        # 2. 리스크 지표
        analysis.append(f"⚠️ **리스크**: MDD {metrics.mdd:.2f}% (최대 낙폭)")
        
        sharpe_eval = "우수" if metrics.sharpe > 1.0 else "보통" if metrics.sharpe > 0.5 else "낮음"
        analysis.append(f"📈 **샤프 비율**: {metrics.sharpe:.2f} (위험 대비 수익 {sharpe_eval})")
        
        # 3. 현재 포지션
        if bt_df['Position'].iloc[-1] == 1:
            buy_dates = bt_df.index[bt_df['Buy'] == 1]
            if len(buy_dates) > 0:
                last_buy_date = buy_dates[-1]
                last_buy_price = bt_df.loc[last_buy_date, 'Close']
                curr_price = bt_df['Close'].iloc[-1]
                curr_profit = ((curr_price - last_buy_price) / last_buy_price * 100)
                
                analysis.append(f"🎯 **현재 상태**: 보유 중 ({last_buy_date.strftime('%Y-%m-%d')} 매수, 현재 {curr_profit:+.2f}%)")
        else:
            analysis.append(f"🎯 **현재 상태**: 현금 (마지막 청산: {metrics.last_sell})")
        
        # 4. 액션 가이드
        if metrics.sharpe > 1.0 and outperformance > 5:
            analysis.append("\n💡 **액션 가이드**: 전략 신뢰도 높음, 시그널 기반 매매 권장")
            if bt_df['Position'].iloc[-1] == 1:
                analysis.append("  - 현재 보유 중 - EMA_fast 하락 전환 시 청산 신호 대기")
            else:
                analysis.append("  - 현재 현금 - 다음 매수 신호(EMA 골든크로스 + OBV 상승) 대기")
        elif outperformance < -5:
            analysis.append("\n💡 **액션 가이드**: 전략이 바이앤홀드 대비 부진, 파라미터 조정 또는 전략 재검토 필요")
        else:
            analysis.append("\n💡 **액션 가이드**: 전략 참고용, 다른 기술적 지표와 병행 사용 권장")
        
        return "\n".join(analysis)
        
    except Exception as e:
        return f"🛠️ 백테스트 해석 중 오류 발생: {str(e)}"
