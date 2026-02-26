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
import requests
import time
import random
import json
from enum import Enum
import finnhub

# ───────────────────────────────
# Robust Data Fetching Configuration
# ───────────────────────────────

# Universal headers to mimic a modern browser and bypass 429 throttling
UNIVERSAL_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'max-age=0',
}

# Global requests session for reuse
YF_SESSION = requests.Session()
YF_SESSION.headers.update(UNIVERSAL_HEADERS)

# Finnhub API client (free tier: 60 calls/min)
# Get your free API key at: https://finnhub.io/register
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY', 'd5qdonpr01qhn30f25tgd5qdonpr01qhn30f25u0')  # Using user's API key
try:
    FINNHUB_CLIENT = finnhub.Client(api_key=FINNHUB_API_KEY)
except:
    FINNHUB_CLIENT = None
    print("Finnhub client initialization failed. Will use fallback methods.")

def retry_request(max_retries=3, base_delay=1):
    """Decorator for retrying functions that fetch data"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if "429" in str(e):
                        delay = base_delay * (2 ** i) + random.uniform(0, 1)
                        print(f"Rate limited (429). Retrying in {delay:.2f}s... (Attempt {i+1}/{max_retries})")
                        time.sleep(delay)
                    else:
                        raise e
            return func(*args, **kwargs) # One last try or raise
        return wrapper
    return decorator

def fetch_stock_data_direct_yahoo(ticker, start_date, end_date):
    """Fallback fetcher using direct Yahoo Finance V8 endpoint"""
    try:
        # Convert dates to timestamps
        start_ts = int(time.mktime(time.strptime(start_date, '%Y-%m-%d')))
        end_ts = int(time.mktime(time.strptime(end_date, '%Y-%m-%d')))
        
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_ts}&period2={end_ts}&interval=1d&includeAdjustedClose=true"
        response = YF_SESSION.get(url, timeout=10)
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        result = data.get('chart', {}).get('result', [])
        if not result:
            return None
            
        res = result[0]
        timestamps = res.get('timestamp', [])
        indicators = res.get('indicators', {}).get('quote', [{}])[0]
        adj_close = res.get('indicators', {}).get('adjclose', [{}])[0].get('adjclose', [])
        
        df = pd.DataFrame({
            'Open': indicators.get('open', []),
            'High': indicators.get('high', []),
            'Low': indicators.get('low', []),
            'Close': indicators.get('close', []),
            'Volume': indicators.get('volume', []),
            'Adj Close': adj_close
        }, index=pd.to_datetime(timestamps, unit='s'))
        
        return df.dropna()
    except Exception as e:
        print(f"Direct fetch failed for {ticker}: {e}")
        return None

# ───────────────────────────────
# Time Period Configuration
# ───────────────────────────────
class TimePeriod(Enum):
    """Time periods for data analysis"""
    MONTHS_6 = ("6M", 180, "6개월")
    YEAR_1 = ("1Y", 365, "1년")
    YEARS_2 = ("2Y", 730, "2년")
    YEARS_5 = ("5Y", 1825, "5년")
    
    def __init__(self, code, days, korean_name):
        self.code = code
        self.days = days
        self.korean_name = korean_name
    
    @classmethod
    def from_code(cls, code):
        for period in cls:
            if period.code == code:
                return period
        return cls.YEAR_1  # default

# Enhanced matplotlib styling for Apple-style charts
def setup_modern_chart_style():
    """Configure matplotlib with clean, white Apple-style styling"""
    plt.style.use('fast') # Use a clean base
    plt.rcParams['figure.facecolor'] = 'white'
    plt.rcParams['axes.facecolor'] = 'white'
    plt.rcParams['axes.edgecolor'] = '#1D1D1F' # Darker edge
    plt.rcParams['axes.linewidth'] = 1.0
    plt.rcParams['axes.grid'] = True
    plt.rcParams['grid.color'] = '#EBEBEB' # Slightly darker grid
    plt.rcParams['grid.linestyle'] = '-'
    plt.rcParams['grid.linewidth'] = 0.5
    plt.rcParams['grid.alpha'] = 1.0
    plt.rcParams['text.color'] = '#000000'
    plt.rcParams['axes.labelcolor'] = '#000000'
    plt.rcParams['axes.titlecolor'] = '#000000'
    plt.rcParams['xtick.color'] = '#000000'
    plt.rcParams['ytick.color'] = '#000000'
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.titlesize'] = 14
    plt.rcParams['axes.titleweight'] = 'normal'
    plt.rcParams['axes.labelsize'] = 11
    plt.rcParams['figure.dpi'] = 100
    plt.rcParams['savefig.dpi'] = 100
    plt.rcParams['savefig.facecolor'] = 'white'
    
# Modern color palette for better aesthetics
# Apple-inspired color palette
APPLE_COLORS = {
    'blue': '#0071E3',
    'sky': '#5FC9F8',
    'green': '#28CD41',
    'orange': '#FF9500',
    'red': '#FF3B30',
    'purple': '#AF52DE',
    'pink': '#FF2D55',
    'gray': '#86868B',
    'light_gray': '#F5F5F7'
}

# ───────────────────────────────
# 주식 데이터 다운로드 및 정리 (fdr 기반)
# ───────────────────────────────
def download_stock_data_fdr(ticker, period=TimePeriod.YEAR_1):
    """
    Download stock data with configurable time period
    
    Parameters:
    -----------
    ticker : str
        Stock ticker symbol
    period : TimePeriod
        Time period for data (default: 1 year)
    """
    today = datetime.now()
    # Always fetch extra data for 200-day EMA calculation
    extra_days = 250  # ~1 year buffer for technical indicators
    lookback_days = period.days + extra_days
    start_date = today - timedelta(days=lookback_days)
    start_date_str = start_date.strftime('%Y-%m-%d')
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

# ───────────────────────────────
# 최종 스코어 계산 함수
# ───────────────────────────────
def calculate_score(symbol, period=TimePeriod.YEAR_1):
    """
    Calculate trend score with configurable time period
    
    Parameters:
    -----------
    symbol : str
        Stock ticker symbol
    period : TimePeriod
        Time period for analysis (default: 1 year)
    """
    try:
        df = download_stock_data_fdr(symbol, period=period)
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
                # Standard YF download with custom session
                stock_df = yf.download(ticker, start=start_date, end=end_date, progress=False, session=YF_SESSION)
                stock_df = flatten_columns(stock_df, ticker)
                
                # If still empty, try direct fetch fallback
                if (stock_df is None or stock_df.empty):
                    stock_df = fetch_stock_data_direct_yahoo(ticker, start_date, end_date)
                
                # If empty and ticker is numeric (likely KR stock), try adding .KS suffix
                if (stock_df is None or stock_df.empty) and ticker.isdigit():
                    ticker_ks = f"{ticker}.KS"
                    stock_df = yf.download(ticker_ks, start=start_date, end=end_date, progress=False, session=YF_SESSION)
                    stock_df = flatten_columns(stock_df, ticker_ks)
                    if (stock_df is None or stock_df.empty):
                        stock_df = fetch_stock_data_direct_yahoo(ticker_ks, start_date, end_date)
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
                spy_df = yf.download("SPY", start=start_date, end=end_date, progress=False, session=YF_SESSION)
                spy_df = flatten_columns(spy_df, "SPY")
                
                if (spy_df is None or spy_df.empty):
                    spy_df = fetch_stock_data_direct_yahoo("SPY", start_date, end_date)
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

def get_technical_analysis_fig(ticker, benchmark_ticker="SPY", period=TimePeriod.YEAR_1):
    """
    Generate technical analysis chart with EMA and RS - Restored 0109 version with Period support
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period.days + 100) # Buffer for MA calculation
        
        # 데이터 가져오기 (Unified Fetcher 호출)
        stock_df, spy_df = get_stock_data_unified(ticker, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        
        if benchmark_ticker != "SPY":
            # Fetch custom benchmark if needed
            try:
                bench_df = fdr.DataReader(benchmark_ticker, start_date, end_date)
                if bench_df is None or bench_df.empty:
                    bench_df = yf.download(benchmark_ticker, start=start_date, end=end_date, progress=False, session=YF_SESSION)
                    if bench_df is None or bench_df.empty:
                         bench_df = fetch_stock_data_direct_yahoo(benchmark_ticker, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                
                if bench_df is not None and not bench_df.empty:
                    if isinstance(bench_df.columns, pd.MultiIndex):
                        try:
                            bench_df = bench_df.xs(benchmark_ticker, axis=1, level=1)
                        except:
                            bench_df.columns = bench_df.columns.get_level_values(0)
                    
                    for col in ['Close', 'Adj Close']:
                        if col in bench_df.columns:
                            bench_df[col] = pd.to_numeric(bench_df[col], errors='coerce')
                    if 'Adj Close' not in bench_df.columns and 'Close' in bench_df.columns:
                        bench_df['Adj Close'] = bench_df['Close']
                    spy_df = bench_df
            except:
                pass

        if stock_df is None or spy_df is None or stock_df.empty or spy_df.empty:
            return None, None, "유효한 데이터를 가져올 수 없습니다."

        # RS 계산
        rs_line, rs_ma50 = calculate_rs(stock_df, spy_df)
        if rs_line is None:
            return None, None, "RS 계산 실패"

        # 차트 스타일 설정 - WHITE THEME
        mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', facecolor='white', edgecolor='black')

        # EMA와 RS 라인을 위한 애드온 설정
        # Redraw only the period requested
        mask_start = end_date - timedelta(days=period.days)
        stock_plot = stock_df[stock_df.index >= mask_start]
        rs_plot = rs_line[rs_line.index >= mask_start]
        rs_ma_plot = rs_ma50[rs_ma50.index >= mask_start]

        addplot = [
            mpf.make_addplot(stock_plot['EMA10'], color='#FF9500', width=1.5, label='10 EMA'), # Apple Orange
            mpf.make_addplot(stock_plot['EMA21'], color='#0071E3', width=1.5, label='21 EMA'), # Apple Blue
            mpf.make_addplot(rs_plot, panel=1, color='#AF52DE', title='RS Line', ylabel='RS'), # Apple Purple
            mpf.make_addplot(rs_ma_plot, panel=1, color='#86868B', width=1.0, linestyle='--')  # Apple Gray
        ]

        # 차트 그리기
        fig, axes = mpf.plot(stock_plot, type='candle', style=s, addplot=addplot, returnfig=True,
                            figsize=(12, 8), panel_ratios=(7,3), title=f'\n{ticker} Technical Analysis ({period.korean_name})',
                            tight_layout=True)

        axes[0].set_title('Price (with 10 & 21 EMA)')
        axes[1].set_title('Relative Strength with 50MA')
        axes[0].legend(['10 EMA', '21 EMA'], loc='upper left')
        axes[1].legend(['RS', 'RS 50MA'], loc='upper left')
        
        rs_data = {'stock_df': stock_df, 'spy_df': spy_df, 'rs_line': rs_line, 'rs_ma50': rs_ma50}
        return fig, rs_data, None
    except Exception as e:
        return None, None, str(e)

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

def get_roc_analysis_fig(ticker, period=TimePeriod.YEAR_1):
    """
    Generate ROC analysis chart - Restored 0109 version with Period support
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period.days + 50)
        
        data = fdr.DataReader(ticker, start_date, end_date)
        if data is None or data.empty:
             data = yf.download(ticker, start=start_date, end=end_date, progress=False, session=YF_SESSION)
             if data is None or data.empty:
                  data = fetch_stock_data_direct_yahoo(ticker, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

        if data is None or data.empty:
            return None, None, f"No data found for {ticker}."
            
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        if 'Close' not in data.columns and 'Adj Close' in data.columns:
            data['Close'] = data['Adj Close']
            
        # Calculate ROC (Velocity)
        n = 20
        plot_data = data.copy()
        plot_data['ROC'] = calculate_roc(plot_data['Close'], n)
        plot_data['Delta_ROC'] = calculate_roc(plot_data['ROC'], n)
        plot_data = plot_data.dropna()

        # Restrict to period
        mask_start = end_date - timedelta(days=period.days)
        plot_data = plot_data[plot_data.index >= mask_start]

        if plot_data.empty:
             return None, None, "데이터 부족"

        # Plotting - White theme
        fig, axes = plt.subplots(3, 1, figsize=(12, 12), facecolor='white')
        
        axes[0].plot(plot_data.index, plot_data['Close'], label='Close Price', color='#0071E3', lw=2)
        axes[0].set_title(f'{ticker} Closing Price', pad=15)
        axes[0].grid(True, axis='y', alpha=0.3)
        axes[0].legend(frameon=False)

        axes[1].plot(plot_data.index, plot_data['ROC'], label='20-Day ROC (Velocity)', color='#FF9500')
        axes[1].axhline(0, color='#1D1D1F', linewidth=0.8, linestyle='--')
        axes[1].set_title(f'{ticker} Rate of Change (Velocity)', pad=15)
        axes[1].grid(True, axis='y', alpha=0.3)
        axes[1].legend(frameon=False)

        axes[2].plot(plot_data.index, plot_data['Delta_ROC'], label='20-Day Delta ROC (Acceleration)', color='#28CD41')
        axes[2].axhline(0, color='#1D1D1F', linewidth=0.8, linestyle='--')
        axes[2].set_title(f'{ticker} Delta ROC (Acceleration)', pad=15)
        axes[2].grid(True, axis='y', alpha=0.3)
        axes[2].legend(frameon=False)

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

def get_kama_analysis_fig(ticker, period=TimePeriod.YEAR_1):
    """
    Generate KAMA analysis chart - Restored 0109 version with Period support
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period.days + 50)
        
        data = fdr.DataReader(ticker, start_date, end_date)
        if data is None or data.empty:
             data = yf.download(ticker, start=start_date, end=end_date, progress=False, session=YF_SESSION)
             if data is None or data.empty:
                 data = fetch_stock_data_direct_yahoo(ticker, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

        if data is None or data.empty:
            return None, f"No data found for {ticker}."

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if 'Close' not in data.columns and 'Adj Close' in data.columns:
             data['Close'] = data['Adj Close']
             
        prices = data['Close']
        kama = calculate_kama(prices)

        # Restrict to period
        mask_start = end_date - timedelta(days=period.days)
        prices_plot = prices[prices.index >= mask_start]
        kama_plot = kama[kama.index >= mask_start]

        # Plotting - White theme
        fig, ax = plt.subplots(figsize=(14, 7), facecolor='white')
        ax.plot(prices_plot.index, prices_plot, label='Price', color='#0071E3', alpha=0.4, lw=1)
        ax.plot(prices_plot.index, kama_plot, label='KAMA', color='#FF3B30', linewidth=2)

        ax.set_title(f'Kaufman Adaptive Moving Average (KAMA) for {ticker} ({period.korean_name})', pad=20)
        ax.set_xlabel('Date')
        ax.set_ylabel('Price')
        ax.legend(frameon=False)
        ax.grid(True, axis='y', alpha=0.3)
        
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
            
        return bytes(pdf.output())
            
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

def get_analyst_targets(ticker):
    """
    Fetches analyst price targets using direct HTML scraping.
    Uses BeautifulSoup for robust parsing of:
    - Yahoo Finance Summary page (US stocks)
    - Naver Finance (Korean stocks)
    """
    from bs4 import BeautifulSoup
    
    # Initialize result structure
    targets = {
        'current': None,
        'mean': None,
        'high': None,
        'low': None,
        'median': None,
        'currency': 'USD',
        'consensus': 'N/A',
        'num_analysts': 0
    }
    recs_list = []
    has_data = False
    
    is_korean = ticker.isdigit()
    
    # ═══════════════════════════════════════════════════════
    # KOREAN STOCKS - Naver Finance
    # ═══════════════════════════════════════════════════════
    if is_korean:
        try:
            print(f"[Naver Finance] Scraping {ticker}...")
            url = f"https://finance.naver.com/item/main.naver?code={ticker}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Naver uses euc-kr encoding - decode properly
            soup = BeautifulSoup(response.content, 'html.parser', from_encoding='euc-kr')
            
            # Find table with class 'rwidth' and look for '목표주가' row
            rwidth_tables = soup.find_all('table', class_='rwidth')
            for table in rwidth_tables:
                rows = table.find_all('tr')
                for row in rows:
                    th = row.find('th')
                    if th and '목표주가' in th.get_text():
                        td = row.find('td')
                        if td:
                            # Get the last <em> tag which contains the target price
                            em_tags = td.find_all('em')
                            if em_tags:
                                try:
                                    price_text = em_tags[-1].get_text(strip=True).replace(',', '')
                                    targets['mean'] = float(price_text)
                                    targets['currency'] = 'KRW'
                                    has_data = True
                                    print(f"[Naver Finance] ✓ Target price: {targets['mean']:,.0f} KRW")
                                    break
                                except (ValueError, IndexError) as e:
                                    print(f"[Naver Finance] Parse error: {e}")
                if has_data:
                    break
                        
        except Exception as e:
            print(f"[Naver Finance] ✗ Failed: {e}")
    
    # ═══════════════════════════════════════════════════════  
    # US STOCKS - Yahoo Finance Summary Page
    # ═══════════════════════════════════════════════════════
    else:
        try:
            print(f"[Yahoo Finance] Scraping {ticker}...")
            # Use the summary page which has the analyst price target card
            url = f"https://finance.yahoo.com/quote/{ticker}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Method 1: Look for the specific analyst price target card
            target_card = soup.find('section', {'data-testid': 'analyst-price-target-card'})
            if target_card:
                # Find all elements with class 'price'
                price_elements = target_card.find_all(class_='price')
                
                # Usually: [current, low, average, high]
                if len(price_elements) >= 3:
                    try:
                        # Extract average (usually the 3rd or labeled as "average")
                        for elem in target_card.find_all(['div', 'span']):
                            if 'average' in elem.get('class', []):
                                price_span = elem.find(class_='price')
                                if price_span:
                                    price_text = price_span.get_text(strip=True).replace(',', '').replace('$', '')
                                    targets['mean'] = float(price_text)
                                    targets['currency'] = 'USD'
                                    has_data = True
                                    print(f"[Yahoo Finance] ✓ Target price: ${targets['mean']:.2f}")
                                    break
                        
                        # If average not found, try to get all prices
                        if not has_data and len(price_elements) >= 4:
                            # Order might be: current, low, average, high
                            try:
                                avg_price = price_elements[2].get_text(strip=True).replace(',', '').replace('$', '')
                                targets['mean'] = float(avg_price)
                                targets['currency'] = 'USD'
                                has_data = True
                                print(f"[Yahoo Finance] ✓ Target price: ${targets['mean']:.2f}")
                            except:
                                pass
                                
                    except Exception as parse_err:
                        print(f"[Yahoo Finance] Parse error: {parse_err}")
            
            # Method 2: Fallback - search for text pattern
            if not has_data:
                import re
                # Pattern: numbers that look like stock prices
                text_content = soup.get_text()
                if 'Price Target' in text_content or 'price target' in text_content:
                    # Try to find patterns like "Average: $287.22"
                    match = re.search(r'(?:Average|Mean).*?\$\s*([\d,.]+)', text_content, re.IGNORECASE)
                    if match:
                        try:
                            price_str = match.group(1).replace(',', '')
                            targets['mean'] = float(price_str)
                            targets['currency'] = 'USD'
                            has_data = True
                            print(f"[Yahoo Finance] ✓ Target found (regex): ${targets['mean']:.2f}")
                        except:
                            pass
                        
        except Exception as e:
            print(f"[Yahoo Finance] ✗ Failed: {e}")
    
    # Final result
    if not has_data:
        print(f"[Scraping] ✗ No analyst target found for {ticker}")
    
    return {
        'targets': targets,
        'recommendations': recs_list,
        'has_data': has_data
    }

def get_analyst_targets_scraping_fallback(ticker):
    """
    Emergency scraper fallback for Finviz (US) or Naver (KR).
    Used when yfinance is throttled or missing data.
    """
    import re
    # Initialize with full structure to avoid KeyError in UI
    results = {
        'targets': {
            'current': None,
            'mean': None,
            'high': None,
            'low': None,
            'median': None,
            'currency': 'USD',
            'consensus': 'N/A',
            'num_analysts': 0
        }, 
        'recommendations': [], 
        'has_data': False
    }
    try:
        if ticker.isdigit(): # Korea
            url = f"https://finance.naver.com/item/main.naver?code={ticker}"
            resp = YF_SESSION.get(url, timeout=5)
            # Find "목표주가" (Target Price)
            # <em>160,000</em> 
            match = re.search(r'목표주가.*?<em>(.*?)</em>', resp.text, re.DOTALL)
            if match:
                price_str = match.group(1).replace(',', '')
                results['targets'] = {
                    'mean': float(price_str),
                    'currency': 'KRW',
                    'consensus': 'N/A',
                    'num_analysts': 0
                }
                results['has_data'] = True
        else: # US (Try Finviz AND MarketBeat)
            # Try Finviz First
            try:
                url_fv = f"https://finviz.com/quote.ashx?t={ticker}"
                resp_fv = YF_SESSION.get(url_fv, timeout=5)
                html_fv = resp_fv.text
                
                # Check for "Target Price" in Finviz
                target_match = re.search(r'>Target Price</td>.*?<b>(.*?)</b>', html_fv, re.DOTALL)
                if target_match:
                    price_text = re.sub(r'<.*?>', '', target_match.group(1)).strip()
                    results['targets']['mean'] = float(price_text)
                    results['targets']['consensus'] = 'BUY (Consensus)'
                    results['has_data'] = True
                
                # Try to get ratings table from Finviz
                ratings_section = re.search(r'class="fullview-ratings-outer".*?>(.*?)</table>', html_fv, re.DOTALL)
                if ratings_section:
                    rows = re.findall(r'<tr.*?>(.*?)</tr>', ratings_section.group(1), re.DOTALL)
                    for row in rows:
                        cols = re.findall(r'<td.*?>(.*?)</td>', row, re.DOTALL)
                        if len(cols) >= 5:
                            def clean_html(text):
                                return re.sub(r'<.*?>', '', text).strip()
                            d_str = clean_html(cols[0])
                            if len(d_str) < 5: continue
                            results['recommendations'].append({
                                'Date': d_str,
                                'Firm': clean_html(cols[2]),
                                'Grade': clean_html(cols[3]),
                                'Action': clean_html(cols[1]),
                                'Target': clean_html(cols[4])
                            })
                            results['has_data'] = True
            except:
                pass

            # IF FINVIZ FAILED TO GET TARGET PRICE, TRY MARKETBEAT (Very Robust)
            if not results['targets'].get('mean'):
                try:
                    # MarketBeat needs the exchange prefix sometimes, but usually ticker works
                    # For simplicity, we try common NASDAQ/NYSE pattern
                    url_mb = f"https://www.marketbeat.com/stocks/NASDAQ/{ticker}/forecast/"
                    resp_mb = YF_SESSION.get(url_mb, timeout=5)
                    # If 404, try NYSE
                    if resp_mb.status_code == 404:
                        url_mb = f"https://www.marketbeat.com/stocks/NYSE/{ticker}/forecast/"
                        resp_mb = YF_SESSION.get(url_mb, timeout=5)
                    
                    html_mb = resp_mb.text
                    # Search for the sentence: "the average price target is $263.41"
                    avg_match = re.search(r'average price target is \$([\d,.]+)', html_mb)
                    high_match = re.search(r'highest price target.*?is \$([\d,.]+)', html_mb)
                    low_match = re.search(r'lowest price target.*?is \$([\d,.]+)', html_mb)
                    
                    if avg_match:
                        results['targets']['mean'] = float(avg_match.group(1).replace(',', ''))
                        if high_match: results['targets']['high'] = float(high_match.group(1).replace(',', ''))
                        if low_match: results['targets']['low'] = float(low_match.group(1).replace(',', ''))
                        results['targets']['consensus'] = 'MarketBeat Consensus'
                        results['has_data'] = True
                except:
                    pass

    except Exception as e:
        print(f"Scraping fallback failed: {e}")
    
    return results

def get_stock_news(ticker, display_name, source_type='US'):
    """
    Fetch news from specific source.
    source_type: 'US' (Yahoo Finance) or 'KR' (Google News)
    """
    import xml.etree.ElementTree as ET
    from urllib.parse import quote
    import requests
    import urllib3
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    headers = {'User-Agent': 'Mozilla/5.0'}
    news_items = []
    
    try:
        if source_type == 'KR':
            # Search by Name + Code on Google News KR
            query = quote(f"{display_name}")
            url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
            resp = requests.get(url, headers=headers, verify=False, timeout=5)
            root = ET.fromstring(resp.content)
            for item in root.findall('.//item')[:4]:
                news_items.append({
                    'title': item.find('title').text,
                    'link': item.find('link').text,
                    'source': item.find('source').text if item.find('source') is not None else "Google News",
                    'date': item.find('pubDate').text
                })
        else:
            # US: Use Yahoo Finance RSS
            # For KR stocks on Yahoo, we often need .KS or .KQ
            clean_ticker = ticker
            if ticker.isdigit(): # Korea
                 clean_ticker = f"{ticker}.KS" # Assume KOSPI default for RSS if unknown
            
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={clean_ticker}&region=US&lang=en-US"
            resp = requests.get(url, headers=headers, verify=False, timeout=5)
            root = ET.fromstring(resp.content)
            for item in root.findall('.//item')[:4]:
                news_items.append({
                    'title': item.find('title').text,
                    'link': item.find('link').text,
                    'source': "Yahoo Finance",
                    'date': item.find('pubDate').text
                })
    except Exception as e:
        print(f"News fetch error ({source_type}): {e}")
        
    return news_items

def generate_stock_summary_for_ai(display_name, result, recommendation_text="", confluence_data=None):
    """
    Generates a comprehensive analysis prompt for AI, focusing on technical recommendations.
    Includes confluence data for deeper technical context.
    """
    score = result.get('score', 0)
    details = result.get('details', {})
    
    prompt = f"### [Stock Technical Analysis: {display_name}]\n\n"
    prompt += "1. Score Summary (Range: -6 to +6):\n"
    prompt += f"- Total Score: {score}/+6\n"
    prompt += f"- EMA Score (Trend): {details.get('EMA Score', 0)}/4\n"
    prompt += f"- PPO Score (Momentum): {details.get('PPO Score', 0)}/1\n"
    prompt += f"- RSI Score (Overbought/Sold): {details.get('RSI Score', 0)}/1\n\n"
    
    if confluence_data:
        prompt += "2. Technical Confluence & Patterns Detected:\n"
        for conf in confluence_data:
            prompt += f"- [{conf['type']}] {conf['title']}: {conf['desc']}\n"
        prompt += "\n"

    if recommendation_text:
        prompt += "3. System Interpretation & Recommendations:\n"
        prompt += f"{recommendation_text}\n\n"
        
    prompt += "4. Request for Deep Dive Analysis:\n"
    prompt += "Based on the internal technical confluence and indicators above, please provide your professional trader's perspective. In particular:\n"
    prompt += "- Analyze potential risks that these technical patterns might miss (e.g., KOSPI index correlation, foreign investment supply/demand).\n"
    prompt += "- Evaluate the strength of the detected confluence patterns (e.g., is Mean Reversion likely to yield a strong bounce or just a minor consolidation?).\n"
    prompt += "- Suggest a concrete entry/exit strategy with specific stop-loss and target price zones based on these technical levels."
    
    return prompt

# ───────────────────────────────
# Multi-Level Interpretation System
# ───────────────────────────────

def format_interpretation_multi_level(expert_text, beginner_text):
    """
    Format interpretation text for both expert and beginner levels
    
    Parameters:
    -----------
    expert_text : str
        Detailed technical analysis for experts
    beginner_text : str
        Simple, actionable guidance for beginners
    
    Returns:
    --------
    dict : {'expert': str, 'beginner': str}
    """
    return {
        'expert': expert_text,
        'beginner': beginner_text
}

def get_trading_recommendation(score_data, interpretations_dict, backtest_metrics=None, confluence_data=None):
    """
    Generate comprehensive trading recommendation with confidence score
    
    Weights:
    --------
    - EMA Score: 20%
    - RS Analysis: 20%
    - ROC/Momentum: 15%
    - KAMA: 10%
    - Confluence: 15% (NEW)
    - Backtest: 20%
    """
    try:
        # Extract signals from each indicator
        signals = []
        weights = []
        
        # 1. EMA Score (25% weight)
        ema_score = score_data.get('details', {}).get('EMA Score', 0)
        if ema_score > 0:
            signals.append(1)  # Bullish
        elif ema_score < 0:
            signals.append(-1)  # Bearish
        else:
            signals.append(0)  # Neutral
        weights.append(0.25)
        
        # 2. Analyze sentiment from RS interpretation (20% weight)
        rs_text = interpretations_dict.get('rs', '').lower()
        rs_signal = 0
        if any(word in rs_text for word in ['주도주', '강세', '우수', '매수']):
            rs_signal = 1
        elif any(word in rs_text for word in ['약세', '낙오', '매도', '관망']):
            rs_signal = -1
        signals.append(rs_signal)
        weights.append(0.20)
        
        # 3. ROC/Momentum (15% weight)
        roc_text = interpretations_dict.get('roc', '').lower()
        roc_signal = 0
        if any(word in roc_text for word in ['가속', '상승', '모멘텀 매수']):
            roc_signal = 1
        elif any(word in roc_text for word in ['둔화', '하락', '손절']):
            roc_signal = -1
        signals.append(roc_signal)
        weights.append(0.15)
        
        # 4. KAMA (15% weight)
        kama_text = interpretations_dict.get('kama', '').lower()
        kama_signal = 0
        if any(word in kama_text for word in ['추세장', '지지', '상승 추세']):
            kama_signal = 1
        elif any(word in kama_text for word in ['하락 추세', '관망']):
            kama_signal = -1
        signals.append(kama_signal)
        weights.append(0.15)
        
        # 5. Confluence (15% weight) - NEW
        conf_signal = 0
        conf_bonus_desc = ""
        if confluence_data:
            pos_conf = sum(1 for c in confluence_data if c['sentiment'] == 'positive')
            neg_conf = sum(1 for c in confluence_data if c['sentiment'] == 'negative')
            if pos_conf > neg_conf:
                conf_signal = 1
                conf_bonus_desc = " (복합 신호 긍정)"
            elif neg_conf > pos_conf:
                conf_signal = -1
                conf_bonus_desc = " (복합 신호 부정)"
        signals.append(conf_signal)
        weights.append(0.15)

        # 6. Backtest (20% weight) - ADJUSTED WEIGHT
        bt_signal = 0
        if backtest_metrics:
            # If strategy is profitable and in position, bullish
            if backtest_metrics.cagr > 5 and backtest_metrics.state == "보유":
                bt_signal = 1
            elif backtest_metrics.cagr < -5 or (backtest_metrics.mdd < -30):
                bt_signal = -1
        signals.append(bt_signal)
        weights.append(0.20)
        
        # Calculate weighted score (-1 to +1)
        weighted_score = sum(s * w for s, w in zip(signals, weights))
        
        # Count agreement level for confidence
        positive_count = sum(1 for s in signals if s > 0)
        negative_count = sum(1 for s in signals if s < 0)
        neutral_count = sum(1 for s in signals if s == 0)
        total_signals = len(signals)
        
        # Determine action
        if weighted_score > 0.3:
            action = "BUY"
            action_kr = "매수"
            emoji = "🟢"
        elif weighted_score < -0.3:
            action = "SELL"
            action_kr = "매도"
            emoji = "🔴"
        else:
            action = "HOLD"
            action_kr = "홀딩"
            emoji = "🟡"
        
        # Calculate confidence (0-100%)
        # Higher agreement = higher confidence
        max_agreement = max(positive_count, negative_count, neutral_count)
        confidence = (max_agreement / total_signals) * 100
        
        # Adjust confidence based on strength of weighted score
        confidence *= (abs(weighted_score) + 0.5)  # Boost for strong signals
        confidence = min(confidence, 100)  # Cap at 100%
        
        # Generate reasoning
        expert_parts = [
            f"**신호 분석 ({positive_count}개 긍정 / {negative_count}개 부정 / {neutral_count}개 중립)**",
            "",
            f"가중 점수: {weighted_score:.2f} (범위: -1 ~ +1)",
            f"- EMA 점수: {ema_score} (가중치 20%)",
            f"- RS 시그널: {'긍정' if rs_signal > 0 else '부정' if rs_signal < 0 else '중립'} (가중치 20%)",
            f"- ROC 시그널: {'긍정' if roc_signal > 0 else '부정' if roc_signal < 0 else '중립'} (가중치 15%)",
            f"- KAMA 시그널: {'긍정' if kama_signal > 0 else '부정' if kama_signal < 0 else '중립'} (가중치 10%)",
            f"- 복합 지표(Confluence): {'긍정' if conf_signal > 0 else '부정' if conf_signal < 0 else '중립'} (가중치 15%)",
            f"- 백테스트: {'긍정' if bt_signal > 0 else '부정' if bt_signal < 0 else 'N/A'} (가중치 20%)",
            "",
            f"**결론**: 종합 지표의 {max_agreement}/{total_signals}개가 동일 방향을 가리키며, 가중 분석 결과 **{action_kr}** 의견입니다."
        ]
        expert_reasoning = "\n".join(expert_parts)
        
        beginner_parts = [
            f"{emoji} **{action_kr} 추천** (신뢰도: {confidence:.0f}%)",
            "",
            "📊 **쉽게 설명하면:**"
        ]
        beginner_reasoning = "\n".join(beginner_parts)
        
        if action == "BUY":
            beginner_reasoning += f"""
- {positive_count}개 지표가 "지금 오를 것 같다"고 말하고 있어요
- 추세, 모멘텀, 시장 대비 강도 등이 긍정적입니다
- 하지만 {neutral_count + negative_count}개는 아직 확신하지 못하거나 반대 의견이에요

[TIP] **초보자 가이드**: 분할 매수를 고려해보세요. 한 번에 전액 투자하기보다, 2-3번에 나눠서 매수하면 리스크를 줄일 수 있습니다.
"""
        elif action == "SELL":
            beginner_reasoning += f"""
- {negative_count}개 지표가 "위험할 수 있다"고 경고하고 있어요
- 하락 신호나 모멘텀 약화가 감지됩니다
- {positive_count}개 지표는 아직 괜찮다고 하지만 주의가 필요해요

[TIP] **초보자 가이드**: 보유 중이라면 일부 또는 전체 매도를 고려하세요. 신규 진입은 피하는 것이 좋습니다.
"""
        else:  # HOLD
            beginner_reasoning += f"""
- 지표들이 서로 다른 의견을 내고 있어요
- 명확한 방향성이 아직 나오지 않았습니다
- {positive_count}개는 매수, {negative_count}개는 매도, {neutral_count}개는 중립 의견

[TIP] **초보자 가이드**: 지금은 관망하면서 다음 신호를 기다리세요. 보유 중이라면 계속 들고 있고, 현금이라면 서두르지 마세요.
"""
        
        # Risk warnings
        risk_warnings = []
        if confidence < 60:
            risk_warnings.append("⚠️ 신뢰도가 낮습니다. 지표 간 의견 불일치가 있으므로 신중하게 접근하세요.")
        
        if backtest_metrics and abs(backtest_metrics.mdd) > 25:
            risk_warnings.append(f"⚠️ 백테스트 최대 낙폭이 {backtest_metrics.mdd:.1f}%로 높습니다. 큰 변동성에 대비하세요.")
        
        if ema_score < 0 and action == "BUY":
            risk_warnings.append("⚠️ 이동평균선은 부정적이지만 다른 지표가 긍정적입니다. 역추세 매수 리스크 존재.")
        
        risk_warning_text = "\n".join(risk_warnings) if risk_warnings else "✅ 특별한 위험 신호는 감지되지 않았습니다."
        
        return {
            'action': action,
            'action_kr': action_kr,
            'confidence': confidence,
            'reasoning_expert': expert_reasoning.strip(),
            'reasoning_beginner': beginner_reasoning.strip(),
            'risk_warning': risk_warning_text,
            'emoji': emoji
        }
        
    except Exception as e:
        return {
            'action': 'HOLD',
            'action_kr': '홀딩',
            'confidence': 0,
            'reasoning_expert': f"분석 중 오류 발생: {str(e)}",
            'reasoning_beginner': "지표 분석을 완료할 수 없습니다. 관망을 권장합니다.",
            'risk_warning': "⚠️ 분석 오류로 인해 추천을 신뢰할 수 없습니다.",
            'emoji': '⚪'
        }

# ───────────────────────────────
# 데이터 기반 분석 (Data-Driven Interpretation)
# ───────────────────────────────

def analyze_indicator_confluence(df, result, rs_data=None, roc_df=None, kama_series=None):
    """
    Detects complex patterns where multiple indicators converge (Confluence).
    """
    confluences = []
    curr_price = df['Adj Close'].iloc[-1]
    
    # 1. Mean Reversion Setup (Oversold Bounce)
    # Price far below long-term EMA but short-term momentum turning up
    if '200_day_ema' in df.columns and '20_day_ema' in df.columns:
        ema200 = df['200_day_ema'].iloc[-1]
        ema20 = df['20_day_ema'].iloc[-1]
        if curr_price < ema200 * 0.9 and roc_df is not None:
             if roc_df['Delta_ROC'].iloc[-1] > 0 and roc_df['ROC'].iloc[-1] > roc_df['ROC'].iloc[-2]:
                 confluences.append({
                     'type': 'Mean Reversion',
                     'sentiment': 'positive',
                     'title': '⚡ 과매도 반등 시그널 (Mean Reversion)',
                     'desc': '주가가 장기 평균선에서 크게 벗어났으나, 하락 속도가 줄어들며 기술적 반등 가능성이 높아진 구간입니다.'
                 })

    # 2. Strong Momentum Breakout (Bullish Confluence)
    # RS rising, Price > EMA20, ROC accel rising
    if rs_data and roc_df is not None:
        rs_line = rs_data.get('rs_line')
        if rs_line is not None and len(rs_line) > 5:
            rs_rising = rs_line.iloc[-1] > rs_line.iloc[-5]
            roc_accel = roc_df['Delta_ROC'].iloc[-1] > 0
            price_above_ema20 = curr_price > (df['20_day_ema'].iloc[-1] if '20_day_ema' in df.columns else 0)
            
            if rs_rising and roc_accel and price_above_ema20:
                confluences.append({
                    'type': 'Momentum Breakout',
                    'sentiment': 'positive',
                    'title': '🚀 강력한 모멘텀 돌파 (Momentum Breakout)',
                    'desc': '시장보다 강한 힘(RS)과 상승 가속도(ROC)가 결합된 전형적인 주도주 돌파 패턴입니다.'
                 })

    # 3. Hidden Bearish Divergence (Warning)
    # Price near high but ROC or RSI trending down
    if roc_df is not None and len(df) > 20:
        recent_max_price = df['Adj Close'].tail(10).max()
        if curr_price >= recent_max_price * 0.98: # Near high
            if roc_df['ROC'].iloc[-1] < roc_df['ROC'].tail(10).max() * 0.7:
                confluences.append({
                    'type': 'Bearish Divergence',
                    'sentiment': 'negative',
                    'title': '⚠️ 하락 다이버전스 감지 (Bearish Divergence)',
                    'desc': '주가는 고점 부근이나 상승 에너지(ROC)가 급격히 식고 있어, 추세 전환 혹은 조정 가능성에 유의해야 합니다.'
                })

    return confluences

def get_score_interpretation(result):
    """
    종합 점수 및 개별 지표를 바탕으로 한국어 분석 메시지 생성 (초보자용 비유 추가)
    """
    details = result.get('details', {})
    score = result.get('score', 0)
    
    analysis = []
    
    # 지표별 점수 추출
    ema_s = details.get('EMA Score', 0)
    ppo_s = details.get('PPO Score', 0)
    rsi_s = details.get('RSI Score', 0)

    # 1. 종합 의견
    if score >= 5:
        analysis.append("🌟 **[강세] 엔진에 풀가동 중입니다!** 모든 지표가 상승을 가리키는 시원한 정배열 구간입니다.")
    elif score >= 2:
        analysis.append("📈 **[우상향] 순항 중입니다.** 중장기 체력이 좋아지고 있어 긍정적입니다.")
    elif score <= -4:
        analysis.append("⚠️ **[경고] 폭풍우 구간입니다.** 하락 압력이 매우 강하니 소나기는 피하는 것이 상책입니다.")
    elif score <= -1:
        analysis.append("📉 **[약세] 기력이 떨어지고 있습니다.** 추세가 꺾이고 있으니 바닥을 확인하며 조심해야 합니다.")
    else:
        analysis.append("⚪ **[안기] 숨 고르기 중입니다.** 방향을 정하기 전 에너지를 모으는 횡보 구간입니다.")
        
    # 2. 초보자를 위한 비유 (Summary)
    analysis.append("\n💡 **쉽게 이해하기**:")
    if ema_s >= 3:
        analysis.append("- **추세(EMA)**: '용수철'이 단단하게 버티고 있어 주가가 쉽게 떨어지지 않는 튼튼한 상태입니다.")
    elif ema_s < 0:
        analysis.append("- **추세(EMA)**: '용수철'이 아래로 눌려 있어 위로 올라가기가 벅찬 상태입니다.")
    
    if rsi_s < 0:
        analysis.append("- **심리(RSI)**: '고무줄'이 너무 팽팽하게 늘어났습니다. 언제든 제자리로 튕겨 돌아올(조정) 수 있으니 욕심을 줄여야 합니다.")
    elif rsi_s > 0:
        analysis.append("- **심리(RSI)**: '고무줄'이 바닥까지 느슨해졌습니다. 조만간 위로 튕겨 오를(반등) 준비를 하고 있습니다.")

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
    Price & EMA Chart 종목별 상세 해석 (초보자용/전문가용 통합)
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
        
        # 2. 분석 내용 구성
        if '20_day_ema' in positions:
            ema20 = positions['20_day_ema']
            status = "위" if ema20['diff_pct'] > 0 else "아래"
            if status == "위":
                 analysis.append(f"📍 **[초보]** 주가가 20일 생명선(${ema20['value']:.2f}) '위'에서 춤을 추고 있습니다. 지지력이 좋네요!")
            else:
                 analysis.append(f"📍 **[초보]** 주가가 20일 생명선 아래로 내려왔습니다. 기운이 좀 빠진 상태입니다.")
        
        # Expert level
        if all(col in df.columns for col in ['20_day_ema', '50_day_ema', '200_day_ema']):
            e20, e50, e200 = df['20_day_ema'].iloc[-1], df['50_day_ema'].iloc[-1], df['200_day_ema'].iloc[-1]
            if e20 > e50 > e200:
                analysis.append("🎯 **[전문] 정배열(Full Alignment)**: 전형적인 Bull-market 셋업으로 장기적인 상승 탄력이 확보되었습니다.")
            elif e20 < e50 < e200:
                analysis.append("⚠️ **[전문] 역배열(Inverse Alignment)**: 모든 이평선이 저항대로 작용하는 Bear-market 구간입니다.")
        
        return "\n".join(analysis)
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
        
        # 초보자용 비유: 마라톤
        if curr_rs > 70:
            analysis.append("🏆 **[초보] 마라톤 1등 주자!** 이 종목은 시장이라는 마라톤 대회에서 선두 그룹을 이끄는 '주도주'입니다. 남들보다 훨씬 잘 달리고 있네요.")
        elif curr_rs < 30:
            analysis.append("🐢 **[초보] 힘겨운 달리기.** 지금은 시장 흐름을 따라가지 못하고 뒤처져 있습니다. 나중에 기운을 차릴 때까지는 좀 더 기다려야 할 것 같아요.")
        else:
            analysis.append("🚶 **[초보] 페이스 유지.** 시장이 달리는 만큼 비슷하게 보폭을 맞추어 걷고 있는 안정적인 상태입니다.")

        # 전문가용
        if rs_ma50 is not None:
            curr_ma = rs_ma50.iloc[-1]
            relation = "Outperforming" if curr_rs > curr_ma else "Underperforming"
            analysis.append(f"📈 **[전문] Relative Strength**: 50일 RS-MA 대비 {relation} 구간입니다. 시장과의 상관관계를 볼 때 Alpha 창출이 가능한 {('주도적' if curr_rs > curr_ma else '소극적')} 섹터입니다.")

        return "\n".join(analysis)
    except Exception as e:
        return f"📊 RS 해석 중 오류 발생: {str(e)}"

def get_roc_interpretation_enhanced(df_with_roc):
    """
    ROC & Delta ROC 향상된 해석 (속도계/가속도계 비유)
    """
    try:
        if df_with_roc is None or df_with_roc.empty:
            return "📊 ROC 데이터가 부족하여 분석할 수 없습니다."
        
        curr_roc = df_with_roc['ROC'].iloc[-1]
        curr_accel = df_with_roc['Delta_ROC'].iloc[-1]
        
        analysis = []
        # 1. 속도계 (ROC)
        if curr_roc > 10:
             analysis.append(f"🏎️ **[초보] 속도(ROC): {curr_roc:+.1f}%** - 스포츠카처럼 아주 빠르게 달리고 있습니다! 너무 빠르면 과속 딱지(조정)를 뗄 수 있으니 조심하세요.")
        elif curr_roc < -10:
             analysis.append(f"⛷️ **[초보] 속도(ROC): {curr_roc:+.1f}%** - 내리막길을 아주 빠르게 내려가고 있습니다. 밑에서 멈추는 신호(반등)가 보일 때까지 대기하세요.")
        else:
             analysis.append(f"🚶 **[초보] 속도(ROC): {curr_roc:+.1f}%** - 평범하게 걷고 있는 속도입니다.")

        # 2. 가속도 (Delta ROC)
        if curr_accel > 5:
             analysis.append("🚀 **[초보] 가속도(Accel): UP!** 엑셀을 힘껏 밟기 시작했습니다. 속도가 더 빨라질 것 같아요.")
        elif curr_accel < -5:
             analysis.append("🛑 **[초보] 가속도(Accel): DOWN!** 브레이크를 밟기 시작했습니다. 조만간 속도가 줄어들 것 같으니 대비하세요.")
        
        # Action Guide (Expert Integration)
        analysis.append("\n💡 **[전문가 견해]**")
        if curr_roc > 0 and curr_accel > 0:
            analysis.append("- Momentum Accumulation: 속도와 가속도가 모두 정방향인 전형적인 시세 분출 초입 구간입니다.")
        elif curr_roc > 0 and curr_accel < 0:
            analysis.append("- Momentum Exhaustion: 속도는 여전히 '+'이나 가속도가 꺾이며 상승 에너지가 소진되는 Divergence 징후가 포착됩니다.")
            
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
        
        # 2. 리스크 지표 - MDD with enhanced explanation
        mdd_value = abs(metrics.mdd)
        
        # MDD 안정성 평가
        if mdd_value < 15:
            mdd_rating = "매우 안정적"
            mdd_emoji = "🟢"
            mdd_desc = "손실 폭이 매우 작아 심리적 부담이 적습니다"
        elif mdd_value < 25:
            mdd_rating = "안정적"
            mdd_emoji = "🟡"
            mdd_desc = "일반적으로 허용 가능한 수준의 변동성입니다"
        elif mdd_value < 35:
            mdd_rating = "보통"
            mdd_emoji = "🟠"
            mdd_desc = "중간 수준의 변동성으로 멘탈 관리가 필요합니다"
        else:
            mdd_rating = "변동성 높음"
            mdd_emoji = "🔴"
            mdd_desc = "큰 손실을 감내할 수 있는 투자자에게 적합합니다"
        
        analysis.append(f"⚠️ **최대 낙폭(MDD)**: {metrics.mdd:.2f}%")
        analysis.append(f"  {mdd_emoji} 안정성: {mdd_rating} - {mdd_desc}")
        
        sharpe_eval = "우수" if metrics.sharpe > 1.0 else "보통" if metrics.sharpe > 0.5 else "낮음"
        analysis.append(f"\n📈 **샤프 비율**: {metrics.sharpe:.2f} (위험 대비 수익 {sharpe_eval})")
        
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


def get_overall_sentiment_summary(interpretations_dict):
    """
    모든 차트 해석을 종합하여 전반적 의견과 불일치 감지
    
    Parameters:
    -----------
    interpretations_dict : dict
        형식: {'ema': str, 'rs': str, 'roc': str, 'kama': str, 'backtest': str}
    
    Returns:
    --------
    str : 종합 분석 메시지
    """
    try:
        if not interpretations_dict:
            return "📊 종합 분석을 생성할 수 없습니다."
        
        analysis = []
        
        # 각 차트의 sentiment 분석 (긍정/중립/부정)
        sentiments = {}
        conflicts = []
        
        for chart_name, interpretation in interpretations_dict.items():
            if not interpretation:
                continue
                
            text_lower = interpretation.lower()
            
            # 긍정적 키워드
            positive_keywords = [
                '매수', '상승', '강세', '주도주', '우수', '추세장', '정배열',
                '골든크로스', '가속', '긍정', '강화', '지지', '매수 신호',
                'buy', 'bullish', 'strong', 'uptrend'
            ]
            
            # 부정적 키워드  
            negative_keywords = [
                '매도', '하락', '약세', '낙오주', '부진', '역배열',
                '데드크로스', '둔화', '조정', '하락 압력', '관망', '매도 신호',
                '과열', 'sell', 'bearish', 'weak', 'downtrend'
            ]
            
            # 점수 계산
            pos_count = sum(1 for kw in positive_keywords if kw in text_lower)
            neg_count = sum(1 for kw in negative_keywords if kw in text_lower)
            
            if pos_count > neg_count * 1.5:
                sentiments[chart_name] = 'positive'
            elif neg_count > pos_count * 1.5:
                sentiments[chart_name] = 'negative'
            else:
                sentiments[chart_name] = 'neutral'
        
        if not sentiments:
            return "📊 분석할 데이터가 부족합니다."
        
        # 전체 sentiment 집계
        positive_count = sum(1 for s in sentiments.values() if s == 'positive')
        negative_count = sum(1 for s in sentiments.values() if s == 'negative')
        neutral_count = sum(1 for s in sentiments.values() if s == 'neutral')
        total_count = len(sentiments)
        
        # 종합 의견
        if positive_count >= total_count * 0.6:
            overall = "긍정적 (매수 신호)"
            emoji = "📈"
        elif negative_count >= total_count * 0.6:
            overall = "부정적 (매도/관망 신호)"
            emoji = "📉"
        else:
            overall = "혼조 (신중한 접근)"
            emoji = "⚖️"
        
        analysis.append(f"{emoji} **종합 의견**: {positive_count}/{total_count} 차트가 긍정적 - {overall}")
        
        # 의견 불일치 감지
        if positive_count > 0 and negative_count > 0:
            analysis.append("\n⚠️ **의견 불일치 감지됨**")
            
            # 어떤 차트가 다른 의견인지 표시
            conflicting_charts = []
            
            if positive_count > negative_count:
                # 대부분 긍정적인데 부정적인 차트 찾기
                for chart, sentiment in sentiments.items():
                    if sentiment == 'negative':
                        chart_names = {
                            'ema': 'EMA 차트',
                            'rs': 'RS 차트',
                            'roc': 'ROC 차트',
                            'kama': 'KAMA 차트',
                            'backtest': '백테스트'
                        }
                        conflicting_charts.append(chart_names.get(chart, chart))
                
                if conflicting_charts:
                    analysis.append(f"  - {', '.join(conflicting_charts)}는 부정적 신호")
            else:
                # 대부분 부정적인데 긍정적인 차트 찾기  
                for chart, sentiment in sentiments.items():
                    if sentiment == 'positive':
                        chart_names = {
                            'ema': 'EMA 차트',
                            'rs': 'RS 차트',
                            'roc': 'ROC 차트',
                            'kama': 'KAMA 차트',
                            'backtest': '백테스트'
                        }
                        conflicting_charts.append(chart_names.get(chart, chart))
                
                if conflicting_charts:
                    analysis.append(f"  - {', '.join(conflicting_charts)}는 긍정적 신호")
        
        # 권장사항
        analysis.append("\n💡 **권장사항**:")
        if positive_count >= total_count * 0.7:
            analysis.append("  - 대부분의 지표가 긍정적입니다. 매수 타이밍 고려")
        elif negative_count >= total_count * 0.7:
            analysis.append("  - 대부분의 지표가 부정적입니다. 관망 또는 청산 고려")
        elif positive_count > negative_count:
            if negative_count > 0:
                analysis.append("  - 긍정적이나 일부 주의 신호 있음. 분할 매수 또는 진입 타이밍 조정")
            else:
                analysis.append("  - 긍정적 신호 우세. 진입 고려")
        elif negative_count > positive_count:
            if positive_count > 0:
                analysis.append("  - 부정적이나 일부 긍정 신호 있음. 신중한 접근 필요")
            else:
                analysis.append("  - 부정적 신호 우세. 관망 권장")
        else:
            analysis.append("  - 명확한 방향성 없음. 추가 신호 대기")
        
        return "\n".join(analysis)
        
    except Exception as e:
        return f"📊 종합 분석 생성 중 오류: {str(e)}"
