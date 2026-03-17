import asyncio
import httpx
import os
from sentence_transformers import SentenceTransformer
from supabase import create_client, Client
import yfinance as yf

# 1. Initialize Supabase Client and the local Embedding Model
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

model = SentenceTransformer('all-MiniLM-L6-v2')

async def fetch_news_for_ticker(symbol: str) -> list:
    print(f"Fetching LIVE news for {symbol}...")
    
    # 1. Fetch live news using yfinance
    stock = yf.Ticker(symbol)
    raw_news = stock.news
    
    articles = []
    
    # 2. Extract the top 5 most recent articles
    for item in raw_news[:5]:
        headline = item.get("title", "No Title Available")
        publisher = item.get("publisher", "Unknown Publisher")
        link = item.get("link", "No Link Available") # <-- NEW: Grab the URL
        
        articles.append({
            "headline": headline,
            # NEW: Hide the URL inside the snippet text so the AI sees it
            "snippet": f"Published by {publisher}. Source URL: {link}" 
        })
        
    # 3. Fallback if the stock has no recent news
    if not articles:
        articles.append({
            "headline": f"No recent news found for {symbol}.",
            "snippet": "Market is currently quiet regarding this ticker."
        })
        
    return articles
async def process_and_store_news(symbol: str, ticker_id: int):
    # 4. Fetch the articles
    articles = await fetch_news_for_ticker(symbol)
    
    for article in articles:
        # 5. Concatenate headline and snippet for maximum context
        text_to_embed = f"{article['headline']}. {article['snippet']}"
        
        # 6. Convert the text into a 384-dimensional vector and cast to a Python list
        embedding = model.encode(text_to_embed).tolist()
        
        # 7. Insert the structured data and the vector into Supabase
        supabase.table('news_vault').insert({
            "ticker_id": ticker_id,
            "headline": article['headline'],
            "snippet": article['snippet'],
            "embedding": embedding
        }).execute()
        
    print(f"Stored {len(articles)} vector records for {symbol}")

async def run_news_scavenger(candidates: list[dict]):
    # 8. Create a list of tasks to run concurrently
    tasks = [process_and_store_news(c['symbol'], c['ticker_id']) for c in candidates]
    
    # 9. Execute all tasks in parallel
    await asyncio.gather(*tasks)

# Example execution:
# asyncio.run(run_news_scavenger([{"symbol": "RELIANCE.BO", "ticker_id": 1}]))