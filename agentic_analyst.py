import os
from typing import TypedDict, List
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from supabase import create_client, Client

# Initialize Supabase inside the agent file
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))


# 1. Define the Structured Output (The final JSON Dossier)
class InvestmentDossier(BaseModel):
    signal: str = Field(description="Strictly 'BUY', 'SELL', or 'HOLD'")
    confidence_score: float = Field(description="Confidence from 0.0 to 1.0")
    entry_price: float = Field(description="Suggested entry price target")
    exit_price: float = Field(description="Suggested exit price target")
    # NEW: Force the AI to output the URL
    citations: List[str] = Field(description="Exact headlines AND their Source URLs used to make the decision")
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
    
    # Query the database for the news we just scraped
    resp = supabase.table("news_vault").select("headline, snippet").eq("ticker_id", state["ticker_id"]).execute()
    
    news_items = []
    if resp.data:
        for row in resp.data:
            # Combine the headline and the snippet (which now contains the Google News URL)
            news_items.append(f"Headline: {row['headline']} | Context: {row['snippet']}")
    else:
        news_items.append("No recent news context available in the vault.")
        
    return {"retrieved_news": news_items}

# 4. Node 2: The Lead Analyst Agent
def lead_analyst_agent(state: AgentState):
    print(f"👔 Lead Analyst: Reconciling quant data and news for {state['symbol']}...")
    
    # Initialize the LLM and bind our strict JSON schema to it
    # llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.1)
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.1)
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