import streamlit as st
import asyncio
import os
import random
from dotenv import load_dotenv
from supabase import create_client, Client
import yfinance as yf
import plotly.graph_objects as go
import time
import json
import pandas as pd
import requests
import io

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

# The hidden file where we will store the master list
POOL_FILE = "master_pool.json"

st.divider()
st.subheader("🎛️ Desk Control Panel")

# Create two columns to put the buttons side-by-side
col1, col2 = st.columns(2)

# --- BUTTON 1: THE DATA UPDATER ---
with col1:
    if st.button("🔄 1. Update Master Market List", use_container_width=True):
        with st.spinner("Bypassing NSE firewall and downloading live equities..."):
            try:
                url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
                
                # THE DISGUISE: Tell the NSE server we are a normal Chrome browser on Windows
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/csv,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
                
                # Fetch the data using our disguise (with a 15-second timeout so it never hangs forever)
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status() # Ensure we got a 200 OK success code
                
                # Convert the raw text response into a Pandas Dataframe
                df = pd.read_csv(io.StringIO(response.text))
                
                # Filter for standard stocks and format for Yahoo Finance
                df = df[df['SERIES'] == 'EQ']
                tickers = df['SYMBOL'].astype(str) + ".NS"
                ticker_list = tickers.tolist()
                
                # Save to the hidden server file
                with open(POOL_FILE, "w") as f:
                    json.dump(ticker_list, f)
                    
                st.success(f"✅ Master list updated! {len(ticker_list)} live stocks saved to server cache.")
                
            except Exception as e:
                st.error(f"⚠️ Failed to reach the Exchange servers. Error: {e}")
# --- BUTTON 2: THE AI SCANNER ---
with col2:
    if st.button("🚀 2. Run Daily Autonomous Scan", type="primary", use_container_width=True):
        
        # 1. Guardrail: Ensure the master list exists before scanning!
        if not os.path.exists(POOL_FILE):
            st.error("⚠️ Master list is empty! Please click 'Update Master Market List' first.")
            st.stop()
            
        # 2. Load the massive list out of the hidden JSON file
        with open(POOL_FILE, "r") as f:
            MARKET_POOL = json.load(f)
            
        st.divider()
        
        # 3. Pull our 15 random stocks
        BASKET = random.sample(MARKET_POOL, 15)
        st.info(f"🎲 Randomly selected 15 stocks from a pool of {len(MARKET_POOL)}: {', '.join([t.replace('.NS', '') for t in BASKET])}")
        
        candidates = [] 
        
        # --- THREAD 1: THE QUANTITATIVE SIFTER ---
        st.subheader("⚙️ Phase 1: Market-Wide Quantitative Sifting")
        my_bar = st.progress(0, text="Initializing scanners...")
        
        for i, ticker in enumerate(BASKET):
            # (Your existing Sifter loop code stays exactly the same from here down!)
            my_bar.progress((i + 1) / len(BASKET), text=f"Checking momentum for {ticker} ({i+1}/15)...")
            
            request = TickerRequest(symbol=ticker)
            sift_result = asyncio.run(sift_single_stock(request)) 

# 3. The Dynamic Master Market Pool
# @st.cache_data(ttl=86400)  # Cache the data for 24 hours so we don't spam the exchange
# def fetch_master_pool():


# # Load the dynamic pool (This will be over 2,000 live stocks!)
# MARKET_POOL = fetch_master_pool()

# 4. The Trigger
if st.button("🚀 Run Daily Autonomous Scan"):
    st.divider()
    
    # Randomly select exactly 15 stocks from the 2000+ live market pool
    BASKET = random.sample(MARKET_POOL, 15)
    
    st.info(f"🎲 Randomly selected 15 stocks for today's scan: {', '.join([t.replace('.BO', '') for t in BASKET])}")
    
    candidates = [] 
    
    # --- THREAD 1: THE QUANTITATIVE SIFTER ---
    st.subheader("⚙️ Phase 1: Market-Wide Quantitative Sifting")
    my_bar = st.progress(0, text="Initializing scanners...")
    
    for i, ticker in enumerate(BASKET):
        # Update UI Progress
        my_bar.progress((i + 1) / len(BASKET), text=f"Checking momentum for {ticker} ({i+1}/15)...")
        
        # Run Sifter
        request = TickerRequest(symbol=ticker)
        sift_result = asyncio.run(sift_single_stock(request))
        
        # Collect Winners
        if sift_result.get("is_candidate"):
            st.success(f"🔥 {ticker} Passed! Anomalous momentum detected.")
            candidates.append({"symbol": ticker, "metrics": sift_result["metrics"]})
        else:
            # We don't print every failure to avoid cluttering the screen
            pass
            
    if not candidates:
        st.warning("All 15 stocks failed the quantitative filter today. The market is quiet. Try scanning again!")
        st.stop()
        
    st.write(f"✅ Sifter complete. {len(candidates)} out of 15 stocks passed to the AI Analyst.")

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
            try:
                initial_state = {
                    "symbol": ticker,
                    "ticker_id": candidate["ticker_id"],
                    "quant_metrics": candidate["metrics"],
                    "retrieved_news": [],
                    "news_urls": {},  # <--- ADD THIS ONE LINE
                    "final_dossier": {}
                }
                
                # Call the AI
                final_state = app.invoke(initial_state)
                
                # Convert the object to a dictionary
                dossier_obj = final_state["final_dossier"]
                dossier = dossier_obj.dict() if hasattr(dossier_obj, "dict") else dossier_obj
                
                # Save to database
                db_payload = {
                    "ticker_id": candidate["ticker_id"], 
                    "signal": dossier.get("signal"),
                    "confidence_score": dossier.get("confidence_score"),
                    "entry_price": dossier.get("entry_price"),
                    "exit_price": dossier.get("exit_price"),
                    "dossier_json": dossier 
                }
                
                try:
                    supabase.table('recommendations').insert(db_payload).execute()
                except Exception as e:
                    st.warning(f"Failed to save {ticker} to database: {e}")
                    
                # THIS IS THE SAFE APPEND: It only runs if everything above succeeds!
                final_dossiers.append({"symbol": ticker, "dossier": dossier})
                
            except Exception as e:
                # If Groq crashes, print the error but keep the app alive
                st.error(f"⚠️ AI Analyst failed to process {ticker} due to an API Error: {e}")
            
            # Take a 15-second breath safely OUTSIDE the try/except blocks
            import time
            time.sleep(15)

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
                # Extract the newly separated headline and URL
                headline = cit.get("headline", "News Article")
                url = cit.get("url", "#")
                
                # Format as a clean, clickable Markdown hyperlink!
                st.markdown(f"- [{headline}]({url})")