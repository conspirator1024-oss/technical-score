import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from utils import (
    calculate_score, get_technical_analysis_fig, get_roc_analysis_fig, 
    get_kama_analysis_fig, run_backtest_strategy, get_backtest_fig, 
    get_kr_stocks, create_pdf_report, get_stock_news, 
    generate_stock_summary_for_ai,
    get_score_interpretation, get_roc_interpretation, get_kama_interpretation,
    # New enhanced interpretation functions
    get_ema_chart_interpretation, get_rs_interpretation, get_roc_interpretation_enhanced,
    get_kama_interpretation_enhanced, get_backtest_interpretation, calculate_kama,
    # Overall sentiment analysis
    get_overall_sentiment_summary,
    # Multi-level interpretation and trading recommendation
    format_interpretation_multi_level, get_trading_recommendation,
    # New confluence analysis
    analyze_indicator_confluence,
    # Analyst Targets
    get_analyst_targets,
    # Time period enum
    TimePeriod
)

st.set_page_config(page_title="Stock Trend Scorer", layout="wide")

# Custom Apple-style CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #FBFBFB;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: #000000 !important;
    }

    /* Force global text color - ABSOLUTE BLACK */
    .stMarkdown, p, span, label, li, h1, h2, h3, h4, h5, h6, div, table, td, th {
        color: #000000 !important;
    }

    /* Specifically target metric labels and values */
    [data-testid="stMetricLabel"], [data-testid="stMetricValue"], [data-testid="stMetricDelta"] {
        color: #000000 !important;
    }

    /* Specifically target sidebar labels */
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
        color: #000000 !important;
    }

    /* Title Styling */
    h1 {
        font-weight: 600 !important;
        color: #1D1D1F !important;
        letter-spacing: -0.022em !important;
        margin-bottom: 2rem !important;
    }
    
    h2, h3 {
        font-weight: 500 !important;
        color: #1D1D1F !important;
        letter-spacing: -0.015em !important;
    }

    /* Block Styling - White Card with Shadow */
    div.stMetric, div[data-testid="stExpander"], div.stAlert, div.stMarkdown, div.stPlotlyChart {
         /* background: white; */
    }
    
    /* Metrics Styling */
    [data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 600 !important;
        color: #1D1D1F !important;
    }
    
    [data-testid="stMetric"] {
        background-color: #FFFFFF;
        padding: 1.5rem !important;
        border-radius: 18px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
        border: 1px solid rgba(0,0,0,0.03) !important;
    }

    /* Card Wrapper for various elements */
    .apple-card {
        background-color: #FFFFFF;
        padding: 2rem;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.04);
        margin-bottom: 2rem;
        border: 1px solid rgba(0,0,0,0.03);
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #F5F5F7;
        border-right: 1px solid #D2D2D7;
    }
    
    .stButton > button {
        border-radius: 12px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1.5rem !important;
        border: none !important;
        transition: all 0.3s ease !important;
    }

    /* Primary Button */
    .stButton > button[kind="primary"] {
        background-color: #0071E3 !important;
        color: white !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        background-color: #0077ED !important;
        transform: scale(1.02);
    }

    /* Customizing Success/Info/Warning/Error alerts */
    div.stAlert {
        border-radius: 16px !important;
        border: none !important;
        background-color: #FFFFFF !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
        padding: 1rem !important;
    }
    
    div.stAlert p, div.stAlert span, div.stAlert b, div.stAlert strong {
        color: #000000 !important;
    }
    
    /* Hide some default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    /* header {visibility: hidden;} Removed to allow mobile sidebar menu button */

    /* Sidebar Selectbox/Input Styling for visibility */
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border-radius: 8px !important;
        border: 1px solid #D2D2D7 !important;
    }
    
    [data-testid="stSidebar"] div[data-baseweb="select"] span {
        color: #000000 !important;
    }

    [data-testid="stSidebar"] input {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border-radius: 8px !important;
        border: 1px solid #D2D2D7 !important;
    }

    /* Custom Ticker Headline Styling */
    .ticker-headline {
        background-color: #FFFFFF;
        padding: 1.5rem 2rem;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.04);
        margin-bottom: 2rem;
        border: 1px solid rgba(0,0,0,0.03);
        text-align: center;
    }
    
    .ticker-headline h2 {
        margin: 0 !important;
        font-size: 2.5rem !important;
        font-weight: 700 !important;
        color: #1D1D1F !important;
    }

    /* News Card Styling */
    .news-card {
        background-color: #FFFFFF;
        padding: 1.2rem;
        border-radius: 16px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 1rem;
        border: 1px solid rgba(0,0,0,0.02);
        transition: transform 0.2s ease;
    }
    
    .news-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
    }
    
    .news-card a {
        text-decoration: none !important;
        color: #0071E3 !important;
        font-weight: 600 !important;
    }
    
    .news-card .source {
        font-size: 0.85rem;
        color: #86868B !important;
        margin-top: 0.5rem;
    }

    /* AI Tools Card */
    .ai-card {
        background-color: #F5F5F7;
        padding: 1.5rem;
        border-radius: 20px;
        border: 1px solid #D2D2D7;
        margin-top: 1rem;
        text-align: center;
    }

    .ai-card h4 {
        margin-top: 0 !important;
        color: #1D1D1F !important;
    }

    .ai-btn-container {
        display: flex;
        justify-content: center;
        gap: 15px;
        margin-top: 15px;
    }

    .ai-tool-link {
        text-decoration: none !important;
        background-color: #FFFFFF;
        padding: 8px 16px;
        border-radius: 10px;
        border: 1px solid #D2D2D7;
        color: #1D1D1F !important;
        font-size: 0.9rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }

    .ai-tool-link:hover {
        background-color: #0071E3;
        color: #FFFFFF !important;
        border-color: #0071E3;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 Stock Trend Scorer & Analyzer")
st.divider()
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
    display_name = ""
    benchmark_ticker = "SPY" # Default US Benchmark
    
    # Popular US Stocks Dictionary
    US_POPULAR_STOCKS = {
        "AAPL": "애플",
        "NVDA": "엔비디아",
        "TSLA": "테슬라",
        "MSFT": "마이크로소프트",
        "GOOGL": "알파벳 (구글)",
        "AMZN": "아마존",
        "META": "메타 (페이스북)",
        "BRK-B": "버크셔 해서웨이",
        "UNH": "유나이티드헬스",
        "V": "비자",
        "JNJ": "존슨앤드존슨",
        "WMT": "월마트",
        "LLY": "일라이 릴리",
        "JPM": "JP모건",
        "XOM": "엑슨모빌",
        "MA": "마스터카드",
        "AVGO": "브로드컴",
        "HD": "홈디포",
        "PG": "P&G",
        "COST": "코스트코"
    }
    
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
                display_name = selection
                # Extract code: "Name (Code)" -> "Code"
                ticker = selection.split('(')[-1].strip(')')
        else:
            st.error("Failed to load KR stock list.")
            ticker = st.text_input("Enter Stock Code (e.g. 005930)", value="005930")
            display_name = ticker
    else:
        # US Market
        us_search_mode = st.radio("Search Method / 검색 방식", ["Popular (인기 종목)", "Manual (직접 입력)"])
        
        if us_search_mode == "Popular (인기 종목)":
            us_options = [f"{t} ({n})" for t, n in US_POPULAR_STOCKS.items()]
            us_selection = st.selectbox("Select Popular US Stock", options=us_options)
            if us_selection:
                display_name = us_selection
                ticker = us_selection.split('(')[0].strip()
        else:
            ticker = st.text_input("Enter Ticker (e.g. AAPL)", value="AAPL").strip().upper()
            if ticker in US_POPULAR_STOCKS:
                display_name = f"{ticker} ({US_POPULAR_STOCKS[ticker]})"
            else:
                display_name = ticker

    submitted = st.button("Analyze Stock", type="primary")

    st.divider()
    
    # Interpretation Level Selection
    st.subheader("📊 Analysis Level / 분석 수준")
    interp_mode = st.radio(
        "해석 방식 선택",
        ["전문가용 (Expert)", "초보용 (Beginner)", "모두 보기 (Both)"],
        index=2  # Default to both
    )
    
    st.divider()


if submitted or ticker:
    if not ticker:
        st.warning("Please enter a ticker.")
    else:
        # Helper function for period selection
        def period_selector(section_name, default_index=1, key_suffix=""):
            """Create a period selector for a specific section"""
            period_options = {
                "6개월 (6M)": TimePeriod.MONTHS_6,
                "1년 (1Y)": TimePeriod.YEAR_1,
                "2년 (2Y)": TimePeriod.YEARS_2,
                "5년 (5Y)": TimePeriod.YEARS_5
            }
            selected = st.selectbox(
                f"⏱️ {section_name} 기간 선택",
                list(period_options.keys()),
                index=default_index,
                key=f"period_{key_suffix}"
            )
            return period_options[selected]
        
        # Prevent auto-run if just typing, usually 'submitted' or existing 'ticker' from selectbox triggers
        # For selectbox, it updates 'ticker' immediately.
        
        with st.spinner(f"Analyzing {ticker}..."):
            # Use default 1Y period for initial score calculation
            result = calculate_score(ticker, period=TimePeriod.YEAR_1)
            # ───────────────────────────────
            # Wall Street Analyst Targets (NEW Location: TOP)
            # ───────────────────────────────
            analyst_data = get_analyst_targets(ticker)
        
        if "error" in result:
            st.error(f"Error: {result['error']}")
        else:
            # Extract basic results early to avoid NameError
            score = result['score']
            df = result['df']
            details = result['details']

            # 1. Headline & Analyst Targets
            st.title(f"📈 {display_name} Analysis")
            
            if analyst_data.get('has_data'):
                targets = analyst_data['targets']
                curr_p = targets.get('current') if targets.get('current') else df['Adj Close'].iloc[-1]
                mean_p = targets['mean']
                upside = ((mean_p - curr_p) / curr_p * 100) if mean_p and curr_p else 0
                
                # Visual Metric Row for Analyst Consensus  
                a_col1, a_col2, a_col3 = st.columns(3)
                with a_col1:
                    st.metric("Consensus (의견)", targets['consensus'])
                with a_col2:
                    st.metric("Target (Mean)", f"{targets['currency']} {mean_p:,.2f}" if mean_p else "N/A")
                with a_col3:
                    st.metric("Potential Upside", f"{upside:+.1f}%" if mean_p else "N/A", 
                              delta=f"{upside:+.1f}%" if mean_p else None)
                
                # Prominent link to external detailed analysis
                if not ticker.isdigit():
                    # US Stock - TipRanks (Primary)
                    st.markdown(f"""
                    <div style="background-color: #F5F5F7; padding: 1.2rem; border-radius: 16px; margin-top: 1rem; text-align: center; border: 1px solid #D2D2D7;">
                        <p style="margin-bottom: 0.5rem; font-size: 0.9rem; color: #86868B;">📊 애널리스트 의견을 시각적 그래프로 확인하세요 (추천)</p>
                        <a href="https://www.tipranks.com/stocks/{ticker.lower()}/forecast" target="_blank" 
                           style="display: inline-block; background-color: #00D09C; color: white !important; padding: 12px 28px; 
                                  border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 1rem; 
                                  transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(0, 208, 156, 0.3);">
                            📈 TipRanks에서 자세히 보기
                        </a>
                        <p style="margin-top: 1rem; margin-bottom: 0.3rem; font-size: 0.85rem; color: #86868B;">추가 분석 사이트:</p>
                        <div style="display: flex; justify-content: center; gap: 12px; flex-wrap: wrap;">
                            <a href="https://finviz.com/quote.ashx?t={ticker}" target="_blank" 
                               title="스크리너 및 기업 검색"
                               style="color: #0071E3 !important; text-decoration: none; font-size: 0.9rem; padding: 6px 12px; border: 1px solid #D2D2D7; border-radius: 8px; background: white;">
                                🔍 Finviz<br><span style="font-size: 0.75rem; color: #86868B;">스크리너</span>
                            </a>
                            <a href="https://www.marketscreener.com/search/?q={ticker}" target="_blank" 
                               title="상세 재무제표 및 애널리스트 컨센서스"
                               style="color: #0071E3 !important; text-decoration: none; font-size: 0.9rem; padding: 6px 12px; border: 1px solid #D2D2D7; border-radius: 8px; background: white;">
                                📊 MarketScreener<br><span style="font-size: 0.75rem; color: #86868B;">재무제표</span>
                            </a>
                            <a href="https://www.macrotrends.net/stocks/charts/{ticker.upper()}" target="_blank" 
                               title="10년+ 장기 재무 추세 그래프"
                               style="color: #0071E3 !important; text-decoration: none; font-size: 0.9rem; padding: 6px 12px; border: 1px solid #D2D2D7; border-radius: 8px; background: white;">
                                📈 Macrotrends<br><span style="font-size: 0.75rem; color: #86868B;">장기 추세</span>
                            </a>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Korean Stock - Naver Finance
                    st.markdown(f"""
                    <div style="background-color: #F5F5F7; padding: 1.2rem; border-radius: 16px; margin-top: 1rem; text-align: center; border: 1px solid #D2D2D7;">
                        <p style="margin-bottom: 0.5rem; font-size: 0.9rem; color: #86868B;">📊 자세한 증권사 의견 및 목표주가 차트는 아래 사이트에서 확인하세요</p>
                        <a href="https://finance.naver.com/item/main.naver?code={ticker}" target="_blank" 
                           style="display: inline-block; background-color: #28CD41; color: white !important; padding: 12px 28px; 
                                  border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 1rem; 
                                  transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(40, 205, 65, 0.3);">
                            🔍 네이버 금융에서 자세히 보기
                        </a>
                    </div>
                    """, unsafe_allow_html=True)


            else:
                st.warning("⚠️ 애널리스트 목표가격 데이터를 현재 불러올 수 없습니다.")
                # Show link anyway for manual check
                if not ticker.isdigit():
                    st.markdown(f"""
                    <div style="background-color: #FFF3CD; padding: 1.2rem; border-radius: 16px; margin-top: 1rem; text-align: center; border: 1px solid #FFC107;">
                        <p style="margin-bottom: 0.5rem; font-size: 0.9rem; color: #856404;">📊 애널리스트 의견을 아래 사이트에서 직접 확인하세요</p>
                        <a href="https://www.tipranks.com/stocks/{ticker.lower()}/forecast" target="_blank" 
                           style="display: inline-block; background-color: #00D09C; color: white !important; padding: 12px 28px; 
                                  border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 1rem;">
                            📈 TipRanks에서 보기
                        </a>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="background-color: #FFF3CD; padding: 1.2rem; border-radius: 16px; margin-top: 1rem; text-align: center; border: 1px solid #FFC107;">
                        <p style="margin-bottom: 0.5rem; font-size: 0.9rem; color: #856404;">📊 증권사 의견을 아래 사이트에서 직접 확인하세요</p>
                        <a href="https://finance.naver.com/item/main.naver?code={ticker}" target="_blank" 
                           style="display: inline-block; background-color: #28CD41; color: white !important; padding: 12px 28px; 
                                  border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 1rem;">
                            🔍 네이버 금융에서 보기
                        </a>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.divider()

            # Placeholder for recommendation and confidence, will be filled after get_trading_recommendation
            rec_placeholder = st.empty()
            
            # 2. Tech Score Metrics Row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(label="Total Trend Score (/6)", value=score)
            with col2:
                st.metric(label="EMA Score (/4)", value=details.get('EMA Score', 0))
            with col3:
                st.metric(label="PPO Score (/1)", value=details.get('PPO Score', 0))
            with col4:
                st.metric(label="RSI Score (/1)", value=details.get('RSI Score', 0))

            # ───────────────────────────────
            # PDF Report Generation
            # ───────────────────────────────
            pdf_placeholder = st.empty()
            with pdf_placeholder:
                st.info("⌛ Complete all analysis to enable PDF download.")
            
            # This dict will store all figures for the PDF report
            figs_for_pdf = {}
            st.divider()

            # 4. Methodology & Indicators

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
            
            # ───────────────────────────────
            # Confluence Analysis (Internal)
            # ───────────────────────────────
            # Pre-calculate what we need for confluence
            with st.spinner("Analyzing Technical Confluence..."):
                # Technical Analysis Chart returns rs_data
                tech_fig, rs_data, tech_error = get_technical_analysis_fig(ticker, benchmark_ticker=benchmark_ticker, period=TimePeriod.YEAR_1)
                # ROC Analysis returns roc_df
                roc_fig_main, roc_df_main, roc_error_main = get_roc_analysis_fig(ticker, period=TimePeriod.YEAR_1)
                
                kama_series_main = calculate_kama(df['Close']) if 'Close' in df.columns else None
                
                confluence_results = analyze_indicator_confluence(
                    df=df, 
                    result=result, 
                    rs_data=rs_data, 
                    roc_df=roc_df_main, 
                    kama_series=kama_series_main
                )

            # Display Confluence Results if any
            if confluence_results:
                st.markdown("### 🏹 Multi-Indicator Confluence (복합 지표 분석)")
                for conf in confluence_results:
                    sentiment_color = "success" if conf['sentiment'] == 'positive' else "error"
                    getattr(st, sentiment_color)(f"**{conf['title']}**\n\n{conf['desc']}")
                    
            st.divider()
            
            # --- New: Interpretation Text ---
            rec_text = get_score_interpretation(result)
            st.success(rec_text)

            # --- AI Discussion Tool (Consolidated) ---
            ai_summary = generate_stock_summary_for_ai(display_name, result, recommendation_text=rec_text, confluence_data=confluence_results)
            
            # Show the Copy button first as the entry point
            if st.button("📋 분석 요약 및 추천 내용 복사 (AI Prompt Copy)", use_container_width=True, key="main_ai_copy"):
                st.code(ai_summary, language="text")
                st.toast("추천 내용이 포함된 요약이 생성되었습니다!")
                
                # Encode for URL to pass directly to ChatGPT
                from urllib.parse import quote
                encoded_prompt = quote(ai_summary)
                
                st.markdown(f"""
                <div class="ai-card" style="margin-top: 1rem; margin-bottom: 2rem; background-color: #FBFBFB; border: 1px dashed #D2D2D7;">
                    <h4 style="font-size: 1.1rem; margin-bottom: 0.5rem;">🤖 Talk with ChatGPT</h4>
                    <p style="font-size: 0.85rem; color: #86868B; margin-bottom: 1rem;">아래 버튼을 누르면 복사된 내용이 포함된 상태로 ChatGPT가 열립니다.</p>
                    <div class="ai-btn-container">
                        <a href="https://chatgpt.com/?q={encoded_prompt}" target="_blank" class="ai-tool-link" style="background-color: #10a37f; color: white !important; border: none; padding: 10px 24px; font-weight: 600;">💬 Analyze on ChatGPT</a>
                        <a href="https://www.google.com/search?q={display_name}+주가+전망" target="_blank" class="ai-tool-link">🔍 Google Search</a>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("💡 위 버튼을 눌러 분석 요약을 생성하면 ChatGPT 상담 도구가 나타납니다.")

            # --- New: News & Reports Section ---
            st.markdown("### 📰 Latest News & Insights")
            
            col_news_kr, col_news_us = st.columns(2)
            
            with col_news_kr:
                st.markdown("#### 🇰🇷 대한민국 소식")
                with st.spinner("KR 소식 로드 중..."):
                    kr_news = get_stock_news(ticker, display_name, source_type='KR')
                if kr_news:
                    for item in kr_news:
                        st.markdown(f"""
                        <div class="news-card">
                            <a href="{item['link']}" target="_blank">{item['title']}</a>
                            <div class="source">{item['source']} • {item['date']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("국내 소식이 없습니다.")

            with col_news_us:
                st.markdown("#### 🌐 Global Insights")
                with st.spinner("Global 소식 로드 중..."):
                    us_news = get_stock_news(ticker, display_name, source_type='US')
                if us_news:
                    for item in us_news:
                        st.markdown(f"""
                        <div class="news-card">
                            <a href="{item['link']}" target="_blank">{item['title']}</a>
                            <div class="source">{item['source']} • {item['date']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("글로벌 소식이 없습니다.")
            
            st.divider()

            # Charting Section 1: Price & EMA
            st.subheader(f"Price & EMA Chart: {ticker}")
            period_ema = period_selector("Price & EMA", default_index=1, key_suffix="ema")
            
            # Create Plotly Figure with Enhanced Styling
            fig = go.Figure()
            
            # Close Price with improved styling - FIX: CHANGED FROM WHITE TO DARK
            fig.add_trace(go.Scatter(
                x=df.index, 
                y=df['Adj Close'], 
                mode='lines', 
                name='Close Price', 
                line=dict(color='#1D1D1F', width=2.5, shape='spline'), # Apple Dark Grey
                hovertemplate='<b>Close</b>: $%{y:.2f}<extra></extra>'
            ))
            
            # EMAs with enhanced colors and styling (Apple-inspired palette)
            ema_styles = {
                '20_day_ema': {'color': '#0071E3', 'name': '20 EMA', 'width': 2.2},  # Apple Blue
                '50_day_ema': {'color': '#5FC9F8', 'name': '50 EMA', 'width': 2.0},  # Apple Sky
                '125_day_ema': {'color': '#FF9500', 'name': '125 EMA', 'width': 1.8}, # Apple Orange
                '200_day_ema': {'color': '#FF3B30', 'name': '200 EMA', 'width': 1.8}  # Apple Red
            }
            
            for col, style in ema_styles.items():
                if col in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df.index, 
                        y=df[col], 
                        mode='lines', 
                        name=style['name'],
                        line=dict(color=style['color'], width=style['width'], shape='spline'),
                        hovertemplate=f"<b>{style['name']}</b>: $%{{y:.2f}}<extra></extra>"
                    ))

            # Enhanced Layout - APPLE STYLE WHITE (EXPLICIT CONTRAST FIX)
            fig.update_layout(
                template="plotly_white",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Inter, sans-serif", size=12, color='#000000'),
                hovermode="x unified",
                hoverlabel=dict(bgcolor="#FFFFFF", font_size=13, font_color="#000000"),
                xaxis=dict(
                    title=dict(text="Date", font=dict(color='#000000')),
                    tickfont=dict(color='#000000'),
                    gridcolor='#F5F5F7',
                    gridwidth=1,
                    showgrid=True,
                    fixedrange=True,
                    linecolor='#1D1D1F'
                ),
                yaxis=dict(
                    title=dict(text="Price ($)", font=dict(color='#000000')),
                    tickfont=dict(color='#000000'),
                    gridcolor='#F5F5F7',
                    gridwidth=1,
                    showgrid=True,
                    fixedrange=True,
                    linecolor='#1D1D1F'
                ),
                margin=dict(l=60, r=40, t=80, b=60),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    bgcolor='rgba(255,255,255,0)',
                    bordercolor='rgba(0,0,0,0)',
                    borderwidth=0,
                    font=dict(color='#000000')
                ),
                dragmode=False
            )
            
            # Mobile-Optimized Chart Display
            st.plotly_chart(
                fig, 
                use_container_width=True, 
                config={
                    'scrollZoom': False,
                    'displayModeBar': False,
                    'staticPlot': False,
                    'doubleClick': False
                }
            )
            
            # --- EMA Chart Interpretation (MOVED BELOW CHART) ---
            st.success(get_ema_chart_interpretation(df))
            
            st.info("""
            **EMA (지수이동평균)**: 최근 가격에 더 높은 가중치를 두어 추세를 파악하는 지표입니다. 
            - **골든크로스**: 단기 선이 장기 선을 뚫고 올라올 때 상승 신호가 강화됩니다.
            """)

            # Data Table (Optional)
            with st.expander("See raw data"):
                st.dataframe(df.tail(200))
                
            # ───────────────────────────────
            # Section 2: Technical Analysis Chart (EMA + RS)
            # ───────────────────────────────
            st.divider()
            st.subheader(f"📊Advanced Technical Analysis: {ticker}")
            period_tech = period_selector("Technical Analysis", default_index=1, key_suffix="tech")
            st.markdown(f"This chart shows **Price with EMAs (10, 21)** and **Relative Strength (RS) vs {'KOSPI 200' if 'Korea' in market else 'SPY'}**.")
            
            # Store Price & EMA figure for PDF
            figs_for_pdf['Price Chart'] = fig
            
            with st.spinner("Generating Technical Chart..."):
                # Pass period and benchmark ticker
                tech_fig, rs_data, error_msg = get_technical_analysis_fig(ticker, benchmark_ticker=benchmark_ticker, period=period_tech)
                
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
            # Section 3: ROC & Delta ROC Analysis
            # ───────────────────────────────
            st.divider()
            st.subheader(f"🚀 ROC (Velocity) & Delta ROC (Acceleration): {ticker}")
            period_roc = period_selector("ROC Analysis", default_index=1, key_suffix="roc")
            st.markdown("""
            This section analyzes the **Velocity** (Speed of price change) and **Acceleration** (Change in velocity).
            
            이 섹션은 **속도** (가격 변화의 빠르기)와 **가속도** (속도의 변화)를 분석합니다.
            
            - **ROC (Velocity)**: Measures how fast the price is changing over 20 days.
            - **ROC (속도)**: 20일 동안 가격이 얼마나 빠르게 변하는지를 측정합니다.
            
            - **Delta ROC (Acceleration)**: Measures how fast the ROC itself is changing. Increasing acceleration often precedes strong moves.
            - **Delta ROC (가속도)**: ROC 자체가 얼마나 빠르게 변하는지를 측정합니다. 가속도가 증가하면 종종 강한 움직임이 나타납니다.
            """)

            with st.spinner("Calculating Momentum Indicators..."):
                # Pass period parameter
                roc_fig, roc_df, roc_error = get_roc_analysis_fig(ticker, period=period_roc)
            
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
            # Section 4: KAMA Analysis
            # ───────────────────────────────
            st.divider()
            st.subheader(f"🦎 Kaufman Adaptive Moving Average (KAMA): {ticker}")
            period_kama = period_selector("KAMA Analysis", default_index=1, key_suffix="kama")
            st.markdown("""
            **Kaufman Adaptive Moving Average (KAMA)** accounts for market noise or volatility.
            
            **카우프만 적응형 이동평균(KAMA)**은 시장의 노이즈 또는 변동성을 고려합니다.
            
            - It closely follows prices when noise is low.
            - 노이즈가 낮을 때는 가격을 밀접하게 따릅니다.
            
            - It smooths out the noise when prices fluctuate significantly.
            - 가격이 크게 변동할 때는 노이즈를 평활화합니다.
            """)

            with st.spinner("Calculating KAMA..."):
                kama_fig, kama_error = get_kama_analysis_fig(ticker, period=period_kama)
            
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
            # OVERALL SENTIMENT SUMMARY
            # ───────────────────────────────
            st.divider()
            st.header("📊 종합 분석 요약")
            st.markdown("""
            모든 차트의 해석을 종합하여 전반적인 의견과 차트 간 불일치를 감지합니다.
            """)
            
            # Collect all interpretations (store them as we generate)
            # Need to re-generate each because we display them inline
            # For efficiency, we could store them in session state, but for simplicity:
            try:
                interpretations_summary = {
                    'ema': get_ema_chart_interpretation(df) if df is not None else "",
                    'rs': get_rs_interpretation(**rs_data) if rs_data else "",
                    'roc': get_roc_interpretation_enhanced(roc_df) if roc_df is not None and not roc_df.empty else "",
                    'kama': get_kama_interpretation_enhanced(df, calculate_kama(df['Close'])) if 'Close' in df.columns else ""
                }
                
                overall_summary = get_overall_sentiment_summary(interpretations_summary)
                st.info(overall_summary)
                
            except Exception as e:
                st.warning(f"종합 분석 생성 중 오류: {str(e)}")
            
            # ───────────────────────────────
            # COMPREHENSIVE TRADING RECOMMENDATION
            # ───────────────────────────────
            st.divider()
            st.header("🎯 최종 매매 추천 / Final Trading Recommendation")
            st.markdown("""
            모든 기술적 지표를 종합하여 최종 매매 의견을 제시합니다.
            """)
            
            try:
                # Collect backtest metrics if available (we'll run it later in the page)
                # For now, pass None - we'll enhance this later
                recommendation = get_trading_recommendation(
                    score_data=result,
                    interpretations_dict=interpretations_summary,
                    backtest_metrics=None,  # Will be populated if backtest was run
                    confluence_data=confluence_results
                )
                
                # Add weight explanation
                st.info("""
                📊 **가중치 설명 (Weight Explanation)**
                
                각 지표의 가중치는 투자 결정에서의 중요도를 반영합니다:
                
                - **EMA Score (25%)**: 기본 추세 방향을 결정하는 가장 기초적인 지표
                - **백테스트 (25%)**: 실제 전략 성과를 반영하여 높은 비중 부여
                - **RS Analysis (20%)**: 시장 대비 상대적 강도를 평가하는 중요 요소
                - **ROC/Momentum (15%)**: 단기 변화 속도를 보조적으로 고려
                - **KAMA (15%)**: 변동성 조정 지표로 보조적 역할
                
                총 가중치: 100%
                """)
                
                # Display based on selected interpretation mode
                action_colors = {
                    "BUY": "success",
                    "SELL": "error",
                    "HOLD": "warning"
                }
                
                # Main recommendation badge
                if recommendation['action'] in action_colors:
                    getattr(st, action_colors[recommendation['action']])(
                        f"{recommendation['emoji']} **{recommendation['action_kr']}** 추천 (Confidence: {recommendation['confidence']:.1f}%)"
                    )
                
                # Show interpretations based on mode
                if interp_mode == "전문가용 (Expert)":
                    with st.expander("💼 전문가 분석 (Expert Analysis)", expanded=True):
                        st.markdown(recommendation['reasoning_expert'])
                elif interp_mode == "초보용 (Beginner)":
                    with st.expander("🎓 초보자 가이드 (Beginner Guide)", expanded=True):
                        st.markdown(recommendation['reasoning_beginner'])
                else:  # Both
                    col_exp, col_beg = st.columns(2)
                    with col_exp:
                        with st.expander("💼 전문가 분석 (Expert)", expanded=True):
                            st.markdown(recommendation['reasoning_expert'])
                    with col_beg:
                        with st.expander("🎓 초보자 가이드 (Beginner)", expanded=True):
                            st.markdown(recommendation['reasoning_beginner'])
                
                # Risk warnings (always show)
                st.warning(recommendation['risk_warning'])
                
                # Confidence meter visualization
                st.progress(recommendation['confidence'] / 100)
                
            except Exception as e:
                st.error(f"매매 추천 생성 중 오류 발생: {str(e)}")
            
            
            # PDF button moved to top, remove from here
            # (Actual PDF generation happens at bottom after all charts)

# ───────────────────────────────
# Backtest Section (Auto-run or Triggered)
# ───────────────────────────────
if ticker:
    st.divider()
    st.header(f"🛠️ Strategy Backtest Results: {ticker}")
    
    # Horizontal layout for parameters
    st.subheader("Strategy Parameters & Controls")
    col_p1, col_p2, col_p3, col_p4, col_btn = st.columns([1, 1, 1, 1, 1])
    
    with col_p1:
        ema_fast_param = st.number_input("Fast EMA", value=20, key="ema_fast")
    with col_p2:
        ema_slow_param = st.number_input("Slow EMA", value=50, key="ema_slow")
    with col_p3:
        obv_ma_param = st.number_input("OBV MA", value=50, key="obv_ma")
    with col_p4:
        capital_param = st.number_input("Capital ($)", value=100000, key="capital")
    with col_btn:
        st.write("") # Padding
        st.write("") # Padding
        run_bt = st.button("🚀 Run Strategy", type="primary", use_container_width=True)

    st.info("Strategy: Buy when Fast EMA > Slow EMA (Trend) AND OBV > OBV_MA (Volume Support). Sell when trend weakens.")
    
    if run_bt or "bt_run_init" not in st.session_state:
        st.session_state["bt_run_init"] = True
    
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
        fig_eq.add_trace(go.Scatter(x=bt_df.index, y=bt_df['Equity'], mode='lines', name='Strategy Equity', line=dict(color='#28CD41'))) # Apple Green
        fig_eq.add_trace(go.Scatter(x=bt_df.index, y=bt_df['BuyHold'], mode='lines', name='Buy & Hold', line=dict(color='#86868B', dash='dash'))) # Apple Gray
        fig_eq.update_layout(
            template="plotly_white", 
            yaxis_title="Capital Value",
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#000000')
        )
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
        
        # Add Backtest Figures to PDF
        figs_for_pdf['Backtest Equity Curve'] = fig_eq
        if 'bt_fig' in locals() and bt_fig is not None:
             figs_for_pdf['Backtest Trade Signals'] = bt_fig

# ───────────────────────────────
# FINAL PDF GENERATION (Update Top Placeholder)
# ───────────────────────────────
if ticker and 'figs_for_pdf' in locals() and figs_for_pdf:
    try:
        # Generate the PDF content
        pdf_content = create_pdf_report(ticker, result, figs_for_pdf)
        
        if pdf_content:
            with pdf_placeholder:
                st.download_button(
                    label="📄 Download Full Analysis Report (PDF)",
                    data=pdf_content,
                    file_name=f"Stock_Analysis_{ticker}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary"
                )
        else:
            with pdf_placeholder:
                st.error("❌ PDF generation failed. Check logic or data.")
    except Exception as e:
        with pdf_placeholder:
            st.error(f"❌ PDF Error: {str(e)}")
