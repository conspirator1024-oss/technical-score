import streamlit as st
import plotly.graph_objects as go
from utils import calculate_score, get_technical_analysis_fig, get_roc_analysis_fig, get_kama_analysis_fig

st.set_page_config(page_title="Stock Trend Scorer", layout="wide")

st.title("📈 Stock Trend Scorer & Analyzer")
st.markdown("""
This app calculates a trend score for a given stock based on **Moving Averages**, **PPO**, and **RSI**.
- **Score > 0**: Positive Trend
- **Score < 0**: Negative Trend
""")

# Input Section
with st.sidebar:
    st.header("Search Settings")
    ticker = st.text_input("Enter Stock Ticker", value="AAPL", help="Enter symbol like AAPL, TSLA, or 005930 (for KRX)").strip().upper()
    submitted = st.button("Analyze Stock", type="primary")

if submitted or ticker:
    if not ticker:
        st.warning("Please enter a ticker.")
    else:
        with st.spinner(f"Analyzing {ticker}..."):
            result = calculate_score(ticker)
        
        if "error" in result:
            st.error(f"Error: {result['error']}")
        else:
            # Display Score
            score = result['score']
            df = result['df']
            details = result['details']

            # Metrics Row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(label="Total Score", value=score)
            with col2:
                st.metric(label="EMA Score", value=details.get('EMA Score', 0))
            with col3:
                st.metric(label="PPO Score", value=details.get('PPO Score', 0))
            with col4:
                st.metric(label="RSI Score", value=details.get('RSI Score', 0))

            # Charting
            st.subheader(f"Price & EMA Chart: {ticker}")
            
            # Create Plotly Figure
            fig = go.Figure()
            
            # Candlestick (Optional, or just Line for Close)
            # Let's use Line for Close to keep it clean with EMAs
            fig.add_trace(go.Scatter(x=df.index, y=df['Adj Close'], mode='lines', name='Close Price', line=dict(color='white', width=2)))
            
            # EMAs
            colors = {'20_day_ema': '#FFD700', '50_day_ema': '#FFA500', '125_day_ema': '#FF4500', '200_day_ema': '#FF0000'}
            for col, color in colors.items():
                if col in df.columns:
                    fig.add_trace(go.Scatter(x=df.index, y=df[col], mode='lines', name=col.replace('_', ' ').upper(), line=dict(color=color, width=1)))

            fig.update_layout(
                xaxis_title="Date",
                yaxis_title="Price",
                template="plotly_dark",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig, use_container_width=True)

            # Data Table (Optional)
            with st.expander("See raw data"):
                st.dataframe(df.tail(200))
                
            # ───────────────────────────────
            # New Feature: Technical Analysis Chart
            # ───────────────────────────────
            st.divider()
            st.subheader(f"📊 Advanced Technical Analysis: {ticker}")
            st.markdown("This chart shows **Price with EMAs (10, 21)** and **Relative Strength (RS) vs SPY**.")
            
            with st.spinner("Generating Technical Chart..."):
                tech_fig, error_msg = get_technical_analysis_fig(ticker)
                
            if error_msg:
                st.error(f"Could not generate technical chart (using yfinance): {error_msg}")
                st.info("Note: 'yfinance' mainly supports US stocks. For Korean stocks, try adding '.KS' (e.g. 005930.KS).")
            else:
                st.pyplot(tech_fig)

            # ───────────────────────────────
            # New Feature: ROC & Delta ROC Analysis
            # ───────────────────────────────
            st.divider()
            st.subheader(f"🚀 ROC (Velocity) & Delta ROC (Acceleration): {ticker}")
            st.markdown("""
            This section analyzes the **Velocity** (Speed of price change) and **Acceleration** (Change in velocity).
            - **ROC (Velocity)**: Measures how fast the price is changing over 20 days.
            - **Delta ROC (Acceleration)**: Measures how fast the ROC itself is changing. Increasing acceleration often precedes strong moves.
            """)

            with st.spinner("Calculating Momentum Indicators..."):
                roc_fig, roc_error = get_roc_analysis_fig(ticker)
            
            if roc_error:
                st.error(f"Could not generate ROC analysis: {roc_error}")
            else:
                st.pyplot(roc_fig)

            # ───────────────────────────────
            # New Feature: KAMA Analysis
            # ───────────────────────────────
            st.divider()
            st.subheader(f"🦎 Kaufman Adaptive Moving Average (KAMA): {ticker}")
            st.markdown("""
            **Kaufman Adaptive Moving Average (KAMA)** accounts for market noise or volatility. 
            - It closely follows prices when noise is low.
            - It smooths out the noise when prices fluctuate significantly.
            """)

            with st.spinner("Calculating KAMA..."):
                kama_fig, kama_error = get_kama_analysis_fig(ticker)
            
            if kama_error:
                st.error(f"Could not generate KAMA analysis: {kama_error}")
            else:
                st.pyplot(kama_fig)
