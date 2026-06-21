import os
import git
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
CompiledGraph = CompiledStateGraph
from agent.schemas import FixAgentState, AgentEvent
from agent.fix.nodes import plan_fix, generate_fix, apply_fix, verify_fix, commit_fix

MAX_FIX_RETRIES = int(os.getenv("MAX_FIX_RETRIES", "2"))

def should_retry(state: FixAgentState) -> str:
    """Routing condition based on the verification result and retry count."""
    resp = state["last_verify_response"]
    if not resp:
        # Fallback if verify response is missing
        return "abort_fix"
        
    if resp.verdict == "good":
        return "commit_fix"
        
    # If verdict is bad, check retries
    if state["retry_count"] < MAX_FIX_RETRIES:
        return "generate_fix"
        
    return "abort_fix"

def abort_fix(state: FixAgentState) -> FixAgentState:
    """Abort node to clean up the fix branch and record error when max retries are exceeded."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "abort_fix"}))
    
    try:
        repo = git.Repo(state["repo_path"])
        sha = state["bisect_result"].faulty_commit_hash[:7]
        branch_name = f"fix/bisect-{sha}"
        
        # Checkout the original faulty commit hash to detach HEAD from the branch we want to delete
        repo.git.checkout(state["bisect_result"].faulty_commit_hash)
        
        # Delete the branch
        repo.git.branch("-D", branch_name)
    except Exception as e:
        # Silently log errors if cleanup fails (e.g. branch didn't exist or git error)
        pass
        
    state["events"].append(AgentEvent(
        event="error",
        payload={
            "message": "Fix verification failed after max retries. Branch deleted. Manual intervention required.",
            "retry_count": state["retry_count"]
        }
    ))
    
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "abort_fix"}))
    return state

def increment_retry(state: FixAgentState) -> FixAgentState:
    """Helper node to increment retry count before routing back to generate_fix."""
    state["retry_count"] += 1
    return state

def create_fix_graph() -> CompiledGraph:
    """Builds and compiles the Fix Agent LangGraph state machine."""
    workflow = StateGraph(FixAgentState)
    
    # Add nodes
    workflow.add_node("plan_fix", plan_fix)
    workflow.add_node("generate_fix", generate_fix)
    workflow.add_node("apply_fix", apply_fix)
    workflow.add_node("verify_fix", verify_fix)
    workflow.add_node("commit_fix", commit_fix)
    workflow.add_node("abort_fix", abort_fix)
    workflow.add_node("increment_retry", increment_retry)
    
    # Add simple edges
    workflow.add_edge(START, "plan_fix")
    workflow.add_edge("plan_fix", "generate_fix")
    workflow.add_edge("generate_fix", "apply_fix")
    workflow.add_edge("apply_fix", "verify_fix")
    
    # Add conditional routing edge from verify_fix
    workflow.add_conditional_edges(
        "verify_fix",
        should_retry,
        {
            "commit_fix": "commit_fix",
            "generate_fix": "increment_retry",
            "abort_fix": "abort_fix"
        }
    )
    
    # increment_retry loops back to generate_fix
    workflow.add_edge("increment_retry", "generate_fix")
    
    # End node transitions
    workflow.add_edge("commit_fix", END)
    workflow.add_edge("abort_fix", END)
    
    return workflow.compile()

compiled_fix_graph = create_fix_graph()
