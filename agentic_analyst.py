import os
from typing import TypedDict, List
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate # <-- The missing piece!
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from supabase import create_client, Client

# Initialize Supabase inside the agent file
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))


# 1. Define the Structured Output (The final JSON Dossier)
# 1. Define the Structured Output
class Citation(BaseModel):
    headline: str = Field(description="The exact news headline")
    url: str = Field(description="The exact Source URL provided in the context")

class InvestmentDossier(BaseModel):
    signal: str = Field(description="Strictly 'BUY', 'SELL', or 'HOLD'")
    confidence_score: float = Field(description="Confidence from 0.0 to 1.0")
    entry_price: float = Field(description="Suggested entry price target")
    exit_price: float = Field(description="Suggested exit price target")
    # THE FIX: Force the AI to use the nested Citation object
    citations: List[Citation] = Field(description="List of sources used to make the decision")
    reasoning: str = Field(description="Short paragraph explaining the thesis")

# 2. Define the Graph State (The "Shared Clipboard")
class AgentState(TypedDict):
    symbol: str
    ticker_id: int  # <-- NEW: The agent needs to know which database ID to look up
    quant_metrics: dict
    retrieved_news: List[str]
    final_dossier: dict

# 3. Node 1: The Researcher Agent
def researcher_agent(state: AgentState):
    print(f"🕵️ Researcher: Searching news vault for {state['symbol']} (ID: {state['ticker_id']})...")
    
    # Query the database (with just the limit 5 safeguard)
    resp = supabase.table("news_vault").select("headline, snippet").eq("ticker_id", state["ticker_id"]).limit(5).execute()
    
    news_string = ""
    
    if resp.data:
        # Python-level backup limit: Strictly process only 5 rows
        for row in resp.data[:5]:
            # Cleanse the data: Chop off abnormally long headlines (max 200 chars) or snippets (max 400 chars)
            head = str(row.get('headline', ''))[:200]
            snip = str(row.get('snippet', ''))[:400]
            news_string += f"Headline: {head} | Context: {snip}\n"
    else:
        news_string = "No recent news context available in the vault."
        
    # THE IRONCLAD WALL: Force the total final prompt payload to be under 2,500 characters (approx 600 tokens).
    # If the database returns 10,000 words of junk, Python slices it down to the safe limit instantly.
    safe_news = news_string[:2500]
        
    return {"retrieved_news": [safe_news]}

# 4. Node 2: The Lead Analyst Agent
def lead_analyst_agent(state: AgentState):
    print(f"👔 Lead Analyst: Reconciling quant data and news for {state['symbol']}...")
    
    # Initialize the LLM and bind our strict JSON schema to it
    # llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.1)
    # Initialize the Free Meta Llama 3.1 model via Groq!
    llm = ChatGroq(
        model="llama-3.1-8b-instant", 
        temperature=0.1,
        max_tokens=800
    )

    structured_llm = llm.with_structured_output(InvestmentDossier)

    
    # Create the prompt combining Math (Quant) and Context (News)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a ruthless, highly logical Senior Quant Analyst at a BSE hedge fund. Combine the numerical metrics and news context to output a structured investment dossier."),
        ("human", "Ticker: {symbol}\nQuant Metrics: {metrics}\nNews Context: {news}")
    ])
    
    # Pipe the prompt into the LLM
    chain = prompt | structured_llm
    
    # Execute the LLM call
    dossier = chain.invoke({
        "symbol": state["symbol"],
        "metrics": state["quant_metrics"],
        "news": state["retrieved_news"]
    })
    
    # Convert the Pydantic object to a standard dictionary to store in the state
    return {"final_dossier": dossier.dict()}

# 5. Build and Compile the LangGraph
def build_analyst_graph():
    workflow = StateGraph(AgentState)
    
    # Add our agent nodes
    workflow.add_node("researcher", researcher_agent)
    workflow.add_node("lead_analyst", lead_analyst_agent)
    
    # Define the flow (The Directed Acyclic Graph - DAG)
    workflow.set_entry_point("researcher")
    workflow.add_edge("researcher", "lead_analyst")
    workflow.add_edge("lead_analyst", END)
    
    # Compile the graph into an executable application
    return workflow.compile()

# Example Execution:
# app = build_analyst_graph()
# initial_state = {
#     "symbol": "TCS.BO", 
#     "quant_metrics": {"close": 3500, "ema_200": 3400, "vol_z_score": 2.5}
# }
# result = app.invoke(initial_state)
# print(result["final_dossier"])