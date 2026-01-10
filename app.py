import streamlit as st
import plotly.graph_objects as go
from utils import (
    calculate_score, get_technical_analysis_fig, get_roc_analysis_fig, 
    get_kama_analysis_fig, run_backtest_strategy, get_backtest_fig, 
    get_kr_stocks, create_pdf_report,
    get_score_interpretation, get_roc_interpretation, get_kama_interpretation,
    # New enhanced interpretation functions
    get_ema_chart_interpretation, get_rs_interpretation, get_roc_interpretation_enhanced,
    get_kama_interpretation_enhanced, get_backtest_interpretation, calculate_kama
)

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
    
    # Market Selection
    market = st.radio("Select Market / 시장 선택", ["US Stocks (미국)", "Korea Stocks (한국)"])
    
    ticker = None
    benchmark_ticker = "SPY" # Default US Benchmark
    
    if "Korea" in market:
        benchmark_ticker = "069500" # KODEX 200 for Korea Benchmark
        
        @st.cache_data
        def load_kr_stocks():
            return get_kr_stocks()
            
        with st.spinner("Loading KRX Stock List..."):
            kr_df = load_kr_stocks()
            
        if not kr_df.empty:
            # Create options: "Samsung Electronics (005930)"
            kr_df['Display'] = kr_df['Name'] + " (" + kr_df['Code'] + ")"
            # Default index: try to find 'Samsung Electronics' or 005930
            default_ix = 0
            if '005930' in kr_df['Code'].values:
                default_ix = int(kr_df[kr_df['Code'] == '005930'].index[0])
                
            selection = st.selectbox("Search Stock / 종목 검색", options=kr_df['Display'], index=default_ix)
            if selection:
                # Extract code: "Name (Code)" -> "Code"
                ticker = selection.split('(')[-1].strip(')')
        else:
            st.error("Failed to load KR stock list.")
            ticker = st.text_input("Enter Stock Code (e.g. 005930)", value="005930")
    else:
        # US Market
        ticker = st.text_input("Enter Stock Ticker (e.g. AAPL)", value="AAPL", help="Enter symbol like AAPL, TSLA, NVDA").strip().upper()

    submitted = st.button("Analyze Stock", type="primary")

    st.divider()
    st.header("Strategy Backtest Settings")
    run_bt = st.button("Run Backtest Strategy")
    with st.expander("Strategy Parameters"):
        ema_fast_param = st.number_input("Fast EMA", value=20)
        ema_slow_param = st.number_input("Slow EMA", value=50)
        obv_ma_param = st.number_input("OBV MA", value=50)
        capital_param = st.number_input("Initial Capital ($)", value=100000)

if submitted or ticker:
    if not ticker:
        st.warning("Please enter a ticker.")
    else:
        # Prevent auto-run if just typing, usually 'submitted' or existing 'ticker' from selectbox triggers
        # For selectbox, it updates 'ticker' immediately.
        
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

            with st.expander("📊 점수 산출 방식 설명 (Trend Score Methodology)"):
                st.markdown("""
                **종합 점수(Total Score)**는 다음 3가지 핵심 기술 지표를 조합하여 산출됩니다:
                
                1. **EMA Score (이동평균선 점수)**: 
                   - 주가가 20, 50, 125, 200일 지수이동평균선(EMA) 위에 있는지 확인합니다.
                   - 주가가 평균선보다 높으면 추세가 강하다고 판단하여 점수를 부여합니다.
                
                2. **PPO Score (가격 비율 오실레이터 점수)**:
                   - 단기 EMA와 장기 EMA의 차이를 활용해 모멘텀의 '방향성'과 '가속도'를 측정합니다.
                   - 모멘텀이 강화되는 시점(상승 가속)에서 가점을 부여합니다.
                
                3. **RSI Score (상대강도지수 점수)**:
                   - 현재 주가가 과하게 올랐는지(과매수 > 70) 아니면 과하게 내렸는지(과매도 < 30)를 판단합니다.
                   - **역발상 관점**: 지나치게 높은 RSI는 단기 조정 가능성(-)으로, 낮은 RSI는 반등 가능성(+)으로 점수에 반영됩니다.
                """)
            
            # --- New: Interpretation Text ---
            st.success(get_score_interpretation(result))

            # Charting
            st.subheader(f"Price & EMA Chart: {ticker}")
            
            # Create Plotly Figure
            fig = go.Figure()
            
            # Candlestick (Optional, or just Line for Close)
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
            
            # Mobile Optimization: disable scroll zoom
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': False})
            
            # --- Enhanced: EMA Chart Interpretation ---
            st.success(get_ema_chart_interpretation(df))
            
            st.info("""
            **EMA (지수이동평균)**: 최근 가격에 더 높은 가중치를 두어 추세를 파악하는 지표입니다. 
            - **골든크로스**: 단기 선이 장기 선을 뚫고 올라올 때 상승 신호가 강화됩니다.
            """)

            # Data Table (Optional)
            with st.expander("See raw data"):
                st.dataframe(df.tail(200))
                
            # ───────────────────────────────
            # New Feature: Technical Analysis Chart
            # ───────────────────────────────
            st.divider()
            st.subheader(f"📊 Advanced Technical Analysis: {ticker}")
            st.markdown(f"This chart shows **Price with EMAs (10, 21)** and **Relative Strength (RS) vs {'KOSPI 200' if 'Korea' in market else 'SPY'}**.")
            
            figs_for_pdf = {}
            figs_for_pdf['Price Chart'] = fig
            
            with st.spinner("Generating Technical Chart..."):
                # Pass benchmark ticker - NOW returns 3 values
                tech_fig, rs_data, error_msg = get_technical_analysis_fig(ticker, benchmark_ticker=benchmark_ticker)
                
            if error_msg:
                st.error(f"Could not generate technical chart (using yfinance): {error_msg}")
            else:
                st.pyplot(tech_fig)
                figs_for_pdf['Technical Analysis'] = tech_fig
                
                with st.expander("💡 RS(상대 강도) 라인 설명"):
                    st.markdown(f"""
                    **RS (Relative Strength) Line**: 대상 종목의 수익률을 벤치마크({'KOSPI 200' if 'Korea' in market else 'SPY'}) 수익률로 나눈 값입니다.
                    - **상승 하는 RS 라인**: 시장(벤치마크)보다 더 강하게 오르거나 더 적게 떨어지는 '주도주'임을 의미합니다.
                    - **보라색 라인**: 현재 RS 추세 / **점선**: RS의 50일 평균선입니다.
                    """)
                
                # --- Enhanced: RS Interpretation ---
                if rs_data:
                    st.success(get_rs_interpretation(**rs_data))

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
                # NOW returns 3 values
                roc_fig, roc_df, roc_error = get_roc_analysis_fig(ticker)
            
            if roc_error:
                st.error(f"Could not generate ROC analysis: {roc_error}")
            else:
                st.pyplot(roc_fig)
                figs_for_pdf['ROC Analysis'] = roc_fig
                
                with st.expander("💡 속도(Velocity)와 가속도(Acceleration) 분석"):
                    st.markdown("""
                    이 차트는 주가의 움직임을 물리적인 '운동'으로 해석합니다.
                    
                    - **ROC (Price Velocity)**: 현재 주가가 20일 전보다 얼마나 빨리 움직이는지 보여주는 **속도**입니다. 0 위로 돌파 시 상승 속도가 붙기 시작함을 뜻합니다.
                    - **Delta ROC (Price Acceleration)**: 속도의 변화량인 **가속도**입니다. 주가가 본격적으로 오르기 전 '가속도'가 먼저 치솟는 경향이 있어, 선행 지표로 활용됩니다.
                    """)
                
                # --- Enhanced: ROC Interpretation (NOW WITH DATA!) ---
                if roc_df is not None and not roc_df.empty:
                    st.success(get_roc_interpretation_enhanced(roc_df))
                else:
                    st.warning("ROC 데이터를 사용할 수 없습니다.")

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
                figs_for_pdf['KAMA Analysis'] = kama_fig
                
                with st.expander("💡 KAMA(적응형 이평선)의 역할"):
                    st.markdown("""
                    **KAMA (Kaufman Adaptive Moving Average)**는 시장의 '소음(Noise)'을 인지하여 스스로를 조절합니다.
                    - **횡보장**: 잦은 위아래 흔들림(소음)이 많을 때는 반응을 늦춰 가짜 신호를 방지합니다.
                    - **추세장**: 명확한 방향이 설정되면 반응 속도를 높여 추세를 빠르게 따라갑니다.
                    """)
                
                # --- Enhanced: KAMA Interpretation ---
                if 'Close' in df.columns:
                    kama_s = calculate_kama(df['Close'])
                    st.success(get_kama_interpretation_enhanced(df, kama_s))
                
            # ───────────────────────────────
            # PDF Report Generation Button
            # ───────────────────────────────
            st.divider()
            col_pdf, _ = st.columns([1, 4])
            with col_pdf:
                # Generate PDF
                # We generate it on the fly and offer download
                if st.button("📄 Generate PDF Report"):
                     with st.spinner("Creating PDF..."):
                         pdf_data = create_pdf_report(ticker, result, figs_for_pdf)
                     
                     if pdf_data:
                         st.download_button(label="Download PDF Now",
                                            data=pdf_data,
                                            file_name=f"{ticker}_Analysis_Report.pdf",
                                            mime="application/pdf")
                     else:
                         st.error("Failed to create PDF.")

# ───────────────────────────────
# Backtest Section (Auto-run or Triggered)
# ───────────────────────────────
if (submitted or ticker or run_bt) and ticker:
    # Always run backtest if analyzed, or if explicitly clicked
    st.divider()
    st.header(f"🛠️ Strategy Backtest Results: {ticker}")
    st.info("Strategy: Buy when Fast EMA > Slow EMA (Trend) AND OBV > OBV_MA (Volume Support). Sell when trend weakens.")
    
    with st.spinner("Running Backtest Simulation..."):
        bt_df, metrics, bt_error = run_backtest_strategy(ticker, 
                                                         ema_fast=ema_fast_param, 
                                                         ema_slow=ema_slow_param, 
                                                         obv_ma=obv_ma_param, 
                                                         capital=capital_param)

    if bt_error:
        st.error(f"Backtest Failed: {bt_error}")
    elif bt_df is not None:
        # 1. Metrics Display
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("CAGR (Annual Return)", f"{metrics.cagr:.2f}%")
        m_col2.metric("Max Drawdown (MDD)", f"{metrics.mdd:.2f}%")
        m_col3.metric("Sharpe Ratio", f"{metrics.sharpe:.2f}")
        m_col4.metric("Current State", metrics.state, delta=f"Last Buy: {metrics.last_buy}")
        
        with st.expander("💡 백테스트 지표 가이드 (Performance Metrics)"):
            st.markdown("""
            전략 시뮬레이션 결과의 신뢰도를 판가름하는 지표입니다:
            
            - **CAGR (연평균 복리 수익률)**: 전략을 꾸준히 유지했을 때 매년 기대할 수 있는 평균 수익률입니다.
            - **MDD (최대 낙폭)**: 최고점에서 최저점까지 가장 많이 계좌가 줄어들었을 때의 비율입니다. **안정성**의 척도입니다.
            - **Sharpe Ratio (샤프 지수)**: 위험 한 단위를 감수했을 때 얻은 초과 수익입니다. 1.0 이상이면 우수하며, 숫자가 높을수록 효율적인 전략입니다.
            - **Current State**: 현재 전략이 해당 주식을 '보유(Hold)' 중인지 '현금(Cash)' 상태인지 보여줍니다.
            """)
        
        # 2. Equity Curve Chart
        st.subheader("💰 Equity Curve (Strategy vs Buy & Hold)")
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=bt_df.index, y=bt_df['Equity'], mode='lines', name='Strategy Equity', line=dict(color='chartreuse')))
        fig_eq.add_trace(go.Scatter(x=bt_df.index, y=bt_df['BuyHold'], mode='lines', name='Buy & Hold', line=dict(color='gray', dash='dash')))
        fig_eq.update_layout(template="plotly_dark", yaxis_title="Capital Value")
        st.plotly_chart(fig_eq, use_container_width=True, config={'scrollZoom': False})
        
        # 3. Signals Chart
        st.subheader("🚦 Trade Signals (Last 1 Year)")
        bt_fig, plot_err = get_backtest_fig(ticker, bt_df)
        if plot_err:
            st.error(plot_err)
        else:
            st.pyplot(bt_fig)

        # 4. Data Table
        with st.expander("View Detailed Log"):
            st.dataframe(bt_df[['Close', 'EMA_fast', 'EMA_slow', 'OBV', 'Position', 'Equity']].tail(100))
        
        # --- Enhanced: Backtest Interpretation ---
        st.success(get_backtest_interpretation(metrics, bt_df))
