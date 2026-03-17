import asyncio
import httpx
import os
from sentence_transformers import SentenceTransformer
from supabase import create_client, Client
import yfinance as yf
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

# 1. Initialize Supabase Client and the local Embedding Model
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

model = SentenceTransformer('all-MiniLM-L6-v2')

async def fetch_news_for_ticker(symbol: str) -> list:
    print(f"📡 Fetching LIVE Google News for {symbol}...")
    
    # 1. Clean the ticker name for the search engine (e.g., "RELIANCE.BO" -> "RELIANCE")
    clean_name = symbol.replace(".BO", "").replace(".NS", "")
    
    # 2. Build the Google News RSS Search URL specific to the Indian Market
    query = urllib.parse.quote(f"{clean_name} stock market news India")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    articles = []
    
    try:
        # 3. Disguise our Python script as a normal web browser so Google doesn't block us
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            
        # 4. Parse the raw XML data
        root = ET.fromstring(xml_data)
        
        # 5. Extract the Top 5 most recent articles
        for item in root.findall('./channel/item')[:5]:
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text
            
            # Inject the actual, clickable Google News URL directly into the snippet!
            articles.append({
                "headline": title,
                "snippet": f"Published on {pub_date}. Source URL: {link}"
            })
            
    except Exception as e:
        print(f"⚠️ Error fetching news for {symbol}: {e}")
        
    # 6. Fallback if the company literally has zero news on Google
    if not articles:
        articles.append({
            "headline": f"No recent news found for {symbol}.",
            "snippet": "Market is currently quiet regarding this ticker. Source URL: N/A"
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