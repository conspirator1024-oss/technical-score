import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

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
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt

def get_stock_data_yf(ticker, start_date, end_date):
    try:
        # Ticker 객체 생성
        stock_ticker = yf.Ticker(ticker)
        spy_ticker = yf.Ticker("SPY")

        # 히스토리 데이터 가져오기
        stock = stock_ticker.history(start=start_date, end=end_date)
        spy = spy_ticker.history(start=start_date, end=end_date)

        if stock.empty or spy.empty:
             return None, None

        # EMA 계산
        stock['EMA10'] = stock['Close'].ewm(span=10, adjust=False).mean()
        stock['EMA21'] = stock['Close'].ewm(span=21, adjust=False).mean()

        # 데이터 타입 변환
        for df in [stock, spy]:
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

        # 결측치 제거
        stock = stock.dropna()
        spy = spy.dropna()

        return stock, spy
    except Exception as e:
        print(f"데이터 다운로드 중 오류 발생: {e}")
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

def get_technical_analysis_fig(ticker):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # 데이터 가져오기
    stock_df, spy_df = get_stock_data_yf(ticker, start_date, end_date)
    if stock_df is None or spy_df is None or stock_df.empty or spy_df.empty:
        return None, "유효한 데이터를 가져올 수 없습니다. (Tickers might be invalid or no data found)"

    # RS 계산
    rs_line, rs_ma50 = calculate_rs(stock_df, spy_df)
    if rs_line is None:
        return None, "RS 계산 실패 (데이터 부족 또는 날짜 불일치)"

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
        
        return fig, None
    except Exception as e:
        return None, f"차트 그리기 중 오류 발생: {e}"

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
    """
    Generate a matplotlib figure for Price, ROC (Velocity), and Delta ROC (Acceleration).
    Returns (fig, error_message)
    """
    try:
        # Download data for the last 2 years
        # yf.download might print progress to stdout, which we can't easily capture in streamlit
        # but it returns a dataframe. 
        # Using auto_adjust=True to get meaningful Close prices if needed, 
        # but standard download is fine as per user snippet.
        data = yf.download(ticker, period="2y", progress=False)

        if data.empty:
            return None, f"No data found for {ticker}."

        # Ensure we have a Close column (yfinance usually returns 'Close' or 'Adj Close')
        # User script uses 'Close'. valid for yfinance.
        if 'Close' not in data.columns:
             return None, "Close column not found in data."

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
        
        return fig, None

    except Exception as e:
        return None, str(e)

# ───────────────────────────────
# Kaufman Adaptive Moving Average (KAMA) 함수
# ───────────────────────────────
def calculate_kama(prices, n=10):
    """
    Calculate Kaufman Adaptive Moving Average (KAMA)
    """
    # Create a copy to ensure we don't modify original data
    prices = prices.copy()
    
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

    # Calculate the KAMA
    kama = np.zeros(len(prices))
    kama[:] = np.nan # Initialize with NaNs
    
    # Initialize the first valid KAMA value (typically the n-th price or similar)
    # The user's code: kama[:n] = prices.values[:n].flatten() 
    # But usually KAMA starts calculation after n periods.
    # Let's stick to user's initialization logic but make it robust.
    
    price_values = prices.values.flatten() if hasattr(prices.values, 'flatten') else prices.values
    
    # Initialize first n values same as price (simple commonly used method for startup)
    kama[:n] = price_values[:n]
    
    for i in range(n, len(prices)):
        kama[i] = kama[i-1] + sc.values[i] * (price_values[i] - kama[i-1])

    return pd.Series(kama, index=prices.index)

def get_kama_analysis_fig(ticker):
    """
    Generate a matplotlib figure for Price and KAMA.
    Returns (fig, error_message)
    """
    try:
        data = yf.download(ticker, period='1y', interval='1d', progress=False)

        if data.empty:
            return None, f"No data found for {ticker}."
            
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
