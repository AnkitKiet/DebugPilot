import os
import re
from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI
from agent.schemas import AgentState, AgentEvent, RcaReport
from agent.tools import run_curl, fetch_imports as fetch_imports_tool
from agent import prompts

def _find_repo_path() -> str:
    """Find the root repository path dynamically."""
    curr = os.path.abspath(os.getcwd())
    for _ in range(5):
        if os.path.isdir(os.path.join(curr, ".git")):
            return curr
        # Check if git-bisect-fix subdirectory has .git
        candidate = os.path.join(curr, "git-bisect-fix")
        if os.path.isdir(os.path.join(candidate, ".git")):
            return candidate
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    return os.path.abspath(os.getcwd())

def _get_curl_error_summary(state: AgentState, llm: ChatGoogleGenerativeAI) -> str:
    """Helper to generate curl error summary using VERIFY_CURL_PROMPT."""
    config = state["curl_config"]
    resp = state["curl_error_response"]
    
    headers_str = " ".join([f"-H '{k}: {v}'" for k, v in config.headers.items()])
    body_str = f"-d '{config.body}'" if config.body else ""
    curl_cmd = f"curl -X {config.method} {headers_str} {body_str} '{config.url}'".strip()
    
    prompt = prompts.VERIFY_CURL_PROMPT.format(
        curl_command=curl_cmd,
        status_code=resp.status_code if resp else 0,
        response_body=resp.response_body if resp else "No response",
        expected_status=config.expected_status
    )
    response = llm.invoke(prompt)
    return str(response.content)

def verify_with_curl(state: AgentState) -> AgentState:
    """Runs target curl configuration and stores the oracle response."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "verify_with_curl"}))
    
    commit_hash = state["bisect_result"].faulty_commit_hash
    state["events"].append(AgentEvent(
        event="tool_call",
        payload={"tool": "run_curl", "args": {"curl_config": state["curl_config"].model_dump(), "commit_hash": commit_hash}}
    ))
    
    result = run_curl.invoke({
        "curl_config": state["curl_config"],
        "commit_hash": commit_hash
    })
    
    state["curl_error_response"] = result
    
    state["events"].append(AgentEvent(
        event="tool_result",
        payload={"tool": "run_curl", "result": result.model_dump()}
    ))
    
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "verify_with_curl"}))
    return state

def analyze_diff(state: AgentState) -> AgentState:
    """Invokes LLM to analyze the bisection diff and determine suspected files."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "analyze_diff"}))
    
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_NAME", "gemini-3.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0,
    )
    
    # 1. Summarize curl error
    curl_error_summary = _get_curl_error_summary(state, llm)
    
    # 2. Analyze diff
    prompt = prompts.ANALYZE_DIFF_PROMPT.format(
        diff=state["bisect_result"].diff,
        curl_error_summary=curl_error_summary
    )
    response = llm.invoke(prompt)
    diff_analysis = str(response.content)
    state["diff_analysis"] = diff_analysis
    
    # 3. Parse suspected files
    suspected_files = []
    for line in diff_analysis.splitlines():
        line = line.strip()
        if "SUSPECTED_FILE:" in line:
            path = line.split("SUSPECTED_FILE:", 1)[1].strip()
            path = path.strip("`'\" ")
            if path:
                suspected_files.append(path)
                
    state["suspected_files"] = suspected_files
    
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "analyze_diff"}))
    return state

def correlate(state: AgentState) -> AgentState:
    """Invokes LLM to correlate diff analysis with the failure symptom to assign confidence."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "correlate"}))
    
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_NAME", "gemini-3.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0,
    )
    
    # 1. Summarize curl error
    curl_error_summary = _get_curl_error_summary(state, llm)
    
    # 2. Format file contexts
    file_contexts_str = ""
    for fc in state["file_contexts"]:
        file_contexts_str += f"File: {fc.path}\nRelevance: {fc.relevance_score}\nContent:\n{fc.content}\n---\n"
        
    # 3. Correlation check
    prompt = prompts.CORRELATE_PROMPT.format(
        diff_analysis=state["diff_analysis"] or "No diff analysis available",
        curl_error_summary=curl_error_summary,
        file_contexts=file_contexts_str or "No file contexts retrieved"
    )
    response = llm.invoke(prompt)
    correlation = str(response.content)
    state["correlation"] = correlation
    
    # 4. Parse confidence (Literal["HIGH", "MEDIUM", "LOW"])
    match = re.search(r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", correlation, re.IGNORECASE)
    if match:
        state["confidence"] = match.group(1).upper() # type: ignore
    else:
        state["confidence"] = "MEDIUM"
        
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "correlate"}))
    return state

def fetch_imports(state: AgentState) -> AgentState:
    """Invokes fetch_imports tool to query and load imported file contexts."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "fetch_imports"}))
    
    repo_path = _find_repo_path()
    already_fetched = [fc.path for fc in state["file_contexts"]]
    
    # We display diff length or a placeholder for args
    state["events"].append(AgentEvent(
        event="tool_call",
        payload={"tool": "fetch_imports", "args": {"diff_len": len(state["bisect_result"].diff), "already_fetched": already_fetched}}
    ))
    
    results = fetch_imports_tool.invoke({
        "diff": state["bisect_result"].diff,
        "repo_path": repo_path,
        "already_fetched": already_fetched
    })
    
    state["import_fetch_count"] += 1
    state["file_contexts"].extend(results)
    
    state["events"].append(AgentEvent(
        event="tool_result",
        payload={"tool": "fetch_imports", "result": {"fetched_count": len(results), "fetched_paths": [r.path for r in results]}}
    ))
    
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "fetch_imports"}))
    return state

def generate_rca(state: AgentState) -> AgentState:
    """Produces the final structured Root Cause Analysis report."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "generate_rca"}))
    
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_NAME", "gemini-3.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0,
    )
    
    curl_error_summary = _get_curl_error_summary(state, llm)
    
    file_contexts_str = ""
    for fc in state["file_contexts"]:
        file_contexts_str += f"File: {fc.path}\nRelevance: {fc.relevance_score}\nContent:\n{fc.content}\n---\n"
        
    prompt = prompts.GENERATE_RCA_PROMPT.format(
        diff_analysis=state["diff_analysis"] or "",
        correlation=state["correlation"] or "",
        bisect_result=str(state["bisect_result"]),
        file_contexts=file_contexts_str,
        curl_error_summary=curl_error_summary
    )
    
    structured_llm = llm.with_structured_output(RcaReport)
    rca_report = structured_llm.invoke(prompt)
    state["rca_report"] = rca_report
    
    # Emit rca_ready event
    if rca_report:
        state["events"].append(AgentEvent(
            event="rca_ready",
            payload={"rca_report": rca_report.model_dump()}
        ))
        
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "generate_rca"}))
    return state
