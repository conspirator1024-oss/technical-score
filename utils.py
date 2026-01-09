import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math
from dataclasses import dataclass

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
import matplotlib
matplotlib.use('Agg') # Headless mode for Streamlit Cloud
import matplotlib.pyplot as plt

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
                stock_df = yf.download(ticker, start=start_date, end=end_date, progress=False)
                stock_df = flatten_columns(stock_df, ticker)
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

def get_technical_analysis_fig(ticker):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # 데이터 가져오기
    # 데이터 가져오기 (Unified Fetcher 호출)
    stock_df, spy_df = get_stock_data_unified(ticker, start_date, end_date)
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
