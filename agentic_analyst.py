import os
from typing import TypedDict, List
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from supabase import create_client, Client

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# 1. Update Schema: AI only outputs the Source ID now, not the massive URL
class Citation(BaseModel):
    headline: str = Field(description="The exact news headline")
    source_id: str = Field(description="The exact Source ID (e.g., 'Source_1')")

class InvestmentDossier(BaseModel):
    signal: str = Field(description="Strictly 'BUY', 'SELL', or 'HOLD'")
    confidence_score: float = Field(description="Confidence from 0.0 to 1.0")
    entry_price: float = Field(description="Suggested entry price target")
    exit_price: float = Field(description="Suggested exit price target")
    citations: List[Citation] = Field(description="List of sources used to make the decision")
    reasoning: str = Field(description="Short paragraph explaining the thesis")

# 2. Add 'news_urls' dictionary to the Agent's clipboard
class AgentState(TypedDict):
    symbol: str
    ticker_id: int
    quant_metrics: dict
    retrieved_news: List[str]
    news_urls: dict  # <--- NEW: Python's secret hiding spot for the real URLs
    final_dossier: dict

# 3. Researcher Agent extracts the URLs and hides them
def researcher_agent(state: AgentState):
    resp = supabase.table("news_vault").select("headline, snippet").eq("ticker_id", state["ticker_id"]).limit(5).execute()
    
    news_string = ""
    url_map = {}
    
    if resp.data:
        for i, row in enumerate(resp.data[:5]):
            head = str(row.get('headline', ''))[:200]
            raw_snip = str(row.get('snippet', ''))
            
            # 1. Extract the full, uncut URL FIRST
            url = "#"
            if "Source URL: " in raw_snip:
                parts = raw_snip.split("Source URL: ")
                snip_text = parts[0].strip()
                url = parts[1].strip() # Saves the entire, uncut URL safely!
            else:
                snip_text = raw_snip
                
            # 2. NOW we safely truncate the text to protect the AI's token limit
            safe_snip = snip_text[:250]
            
            source_id = f"Source_{i+1}"
            news_string += f"[{source_id}] Headline: {head} | Context: {safe_snip}\n"
            url_map[source_id] = url # Hide the uncut URL in Python memory
    else:
        news_string = "No recent news context available in the vault."
        
    safe_news = news_string[:2500]
    return {"retrieved_news": [safe_news], "news_urls": url_map}

# 4. Lead Analyst Agent runs the AI, then swaps the URLs back
def lead_analyst_agent(state: AgentState):
    llm = ChatGroq(
        model="llama-3.1-8b-instant", 
        temperature=0.1,
        max_tokens=800 # We can safely lower this back to 800 now!
    )

    structured_llm = llm.with_structured_output(InvestmentDossier)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a ruthless, highly logical Senior Quant Analyst at a BSE hedge fund. 
        Combine the numerical metrics and news context to output a structured investment dossier. 
        Always cite the exact Source ID provided. 
        CRITICAL FORMATTING RULE: The 'citations' field MUST be a valid JSON array of objects. Do NOT wrap the array in string quotes."""),
        ("human", "Ticker: {symbol}\nQuant Metrics: {metrics}\nNews Context: {news}")
    ])
    
    chain = prompt | structured_llm
    
    dossier = chain.invoke({
        "symbol": state["symbol"],
        "metrics": state["quant_metrics"],
        "news": state["retrieved_news"]
    })
    
    dossier_dict = dossier.dict() if hasattr(dossier, "dict") else dossier
    
    # --- THE MAGIC TRICK ---
    # Swap the AI's "Source_1" tag for the real, uncorrupted URL before saving!
    for cit in dossier_dict.get("citations", []):
        sid = cit.get("source_id", "")
        cit["url"] = state.get("news_urls", {}).get(sid, "#")
        
    return {"final_dossier": dossier_dict}

def build_analyst_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("researcher", researcher_agent)
    workflow.add_node("lead_analyst", lead_analyst_agent)
    workflow.set_entry_point("researcher")
    workflow.add_edge("researcher", "lead_analyst")
    workflow.add_edge("lead_analyst", END)
    return workflow.compile()

# Example Execution:
# app = build_analyst_graph()
# initial_state = {
#     "symbol": "TCS.BO", 
#     "quant_metrics": {"close": 3500, "ema_200": 3400, "vol_z_score": 2.5}
# }
# result = app.invoke(initial_state)
# print(result["final_dossier"])