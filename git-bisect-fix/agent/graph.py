import os
from langgraph.graph import StateGraph, START, END
from agent.schemas import AgentState
from agent.nodes import verify_with_curl, analyze_diff, correlate, fetch_imports, generate_rca

def should_fetch_imports(state: AgentState) -> str:
    """Routing function to decide whether to fetch more imports or generate the final report.

    Returns:
        "generate_rca" to stop loop and generate report, "fetch_imports" to fetch next level of imports.
    """
    max_import_depth = int(os.getenv("MAX_IMPORT_DEPTH", "3"))
    confidence = state.get("confidence")
    fetch_count = state.get("import_fetch_count", 0)
    
    if confidence == "HIGH" or fetch_count >= max_import_depth:
        return "generate_rca"
    return "fetch_imports"

def create_graph():
    """Builds and compiles the LangGraph state machine graph workflow."""
    workflow = StateGraph(AgentState)
    
    # Add all 5 nodes
    workflow.add_node("verify_with_curl", verify_with_curl)
    workflow.add_node("analyze_diff", analyze_diff)
    workflow.add_node("correlate", correlate)
    workflow.add_node("fetch_imports", fetch_imports)
    workflow.add_node("generate_rca", generate_rca)
    
    # Add graph edges
    workflow.add_edge(START, "verify_with_curl")
    workflow.add_edge("verify_with_curl", "analyze_diff")
    workflow.add_edge("analyze_diff", "correlate")
    
    # Add conditional routing edge from correlate
    workflow.add_conditional_edges(
        "correlate",
        should_fetch_imports,
        {
            "generate_rca": "generate_rca",
            "fetch_imports": "fetch_imports"
        }
    )
    
    # Loop back edge
    workflow.add_edge("fetch_imports", "correlate")
    
    # End edge
    workflow.add_edge("generate_rca", END)
    
    return workflow.compile()

compiled_graph = create_graph()
