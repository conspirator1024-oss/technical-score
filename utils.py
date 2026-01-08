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
