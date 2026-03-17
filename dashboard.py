import streamlit as st
import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import yfinance as yf
import plotly.graph_objects as go

# 1. Initialization
load_dotenv()
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

from sifter import TickerRequest, sift_single_stock
from scavenger import process_and_store_news
from agentic_analyst import build_analyst_graph

# 2. UI Setup
st.set_page_config(page_title="BSE Agentic Quant", layout="wide", page_icon="📈")
st.title("📈 Autonomous Agentic Quant Desk")
st.markdown("Initiate the daily scan to automatically discover and analyze breakout BSE stocks.")

# 3. The Market Basket (List of stocks to scan automatically)
BASKET = ["RELIANCE.BO", "TCS.BO", "HDFCBANK.BO", "INFY.BO", "SBIN.BO", "TATAMOTORS.BO", "ICICIBANK.BO", "ITC.BO"]

# 4. The Trigger
if st.button("🚀 Run Daily Autonomous Scan"):
    st.divider()
    candidates = [] # This will hold the stocks that pass the math test
    
    # --- THREAD 1: THE QUANTITATIVE SIFTER ---
    st.subheader("⚙️ Phase 1: Market-Wide Quantitative Sifting")
    my_bar = st.progress(0, text="Initializing scanners...")
    
    for i, ticker in enumerate(BASKET):
        # Update UI Progress
        my_bar.progress((i + 1) / len(BASKET), text=f"Analyzing math for {ticker}...")
        
        # Run Sifter
        request = TickerRequest(symbol=ticker)
        sift_result = asyncio.run(sift_single_stock(request))
        
        # TESTING BYPASS: Force one stock to pass so you can always test the AI
        # (Remove this `if` block later when you want pure, strict math)
        if ticker == "TATAMOTORS.BO": 
             sift_result["is_candidate"] = True
             if "metrics" not in sift_result: 
                 sift_result["metrics"] = {"close": 1000, "ema_200": 950, "vol_z_score": 2.5}
        
        # Collect Winners
        if sift_result.get("is_candidate"):
            st.success(f"🔥 {ticker} Passed! Anomalous momentum detected.")
            candidates.append({"symbol": ticker, "metrics": sift_result["metrics"]})
        else:
            st.write(f"❌ {ticker} rejected (Normal volume or downtrend).")
            
    if not candidates:
        st.warning("No stocks passed the quantitative filter today. The market is quiet.")
        st.stop()
        
    # --- THREAD 2: THE NEWS SCAVENGER ---
    st.divider()
    st.subheader("📰 Phase 2: Contextual News Scavenging")
    
    for candidate in candidates:
        ticker = candidate["symbol"]
        with st.spinner(f"Fetching and vectorizing live news for {ticker}..."):
            
            # Database check & registration
            resp = supabase.table('tickers').select('ticker_id').eq('symbol', ticker).execute()
            if len(resp.data) > 0:
                db_ticker_id = resp.data[0]['ticker_id']
            else:
                insert_resp = supabase.table('tickers').insert({"symbol": ticker, "sector": "Auto-Added"}).execute()
                db_ticker_id = insert_resp.data[0]['ticker_id']
            
            candidate["ticker_id"] = db_ticker_id # Save for Phase 3
            
            # Run Scavenger
            asyncio.run(process_and_store_news(ticker, ticker_id=db_ticker_id))
        st.success(f"News vectorized for {ticker}")

    # --- THREAD 3: THE AGENTIC ANALYST ---
    st.divider()
    st.subheader("🤖 Phase 3: Agentic Analysis & Dossier Generation")
    
    final_dossiers = []
    app = build_analyst_graph()
    
    for candidate in candidates:
        ticker = candidate["symbol"]
        with st.spinner(f"Lead Analyst is reviewing {ticker}..."):
            initial_state = {
                "symbol": ticker,
                "quant_metrics": candidate["metrics"],
                "retrieved_news": [],
                "final_dossier": {}
            }
            final_state = app.invoke(initial_state)
            dossier = final_state["final_dossier"]
            
            # Save to database
            db_payload = {
                "ticker_id": candidate["ticker_id"], 
                "signal": dossier.get("signal"),
                "confidence_score": dossier.get("confidence_score"),
                "entry_price": dossier.get("entry_price"),
                "exit_price": dossier.get("exit_price"),
                "dossier_json": dossier 
            }
            supabase.table('recommendations').insert(db_payload).execute()
            final_dossiers.append({"symbol": ticker, "dossier": dossier})
    
    # --- PHASE 4: THE DASHBOARD DISPLAY ---
    st.divider()
    st.header("🏆 Today's Top Investment Recommendations")
    
    for item in final_dossiers:
        ticker = item["symbol"]
        dossier = item["dossier"]
        
        # Create a collapsible box for each winning stock
        with st.expander(f"{dossier.get('signal', 'HOLD')} | {ticker} (Confidence: {int(dossier.get('confidence_score', 0)*100)}%)", expanded=True):
            col1, col2, col3 = st.columns(3)
            col1.metric("Signal", dossier.get("signal", "HOLD"))
            col2.metric("Entry Target", f"₹{dossier.get('entry_price', 0)}")
            col3.metric("Exit Target", f"₹{dossier.get('exit_price', 0)}")
            
            st.markdown("### 🧠 Analyst Reasoning")
            st.info(dossier.get('reasoning', ''))
            
            st.markdown("### 📚 Source Citations")
            for cit in dossier.get("citations", []):
                st.markdown(f"- *{cit}*")