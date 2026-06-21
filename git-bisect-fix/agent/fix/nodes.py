import os
import json
import git
from typing import List, Dict, Optional, Annotated
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from agent.schemas import (
    FixAgentState,
    FixPlan,
    FileChange,
    FixResult,
    AgentEvent,
    FileContext,
    OracleResult
)
from agent.fix import prompts
from agent.tools import read_file, write_file, run_curl

def _get_llm() -> ChatGoogleGenerativeAI:
    """Helper to instantiate the Gemini LLM with default settings."""
    return ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_NAME", "gemini-3.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0,
    )

class FileChangesContainer(BaseModel):
    """Helper container to receive structured list of FileChanges from LLM."""
    changes: List[FileChange] = Field(description="List of file changes to apply")

def plan_fix(state: FixAgentState) -> FixAgentState:
    """Uses LLM to propose a conceptual plan to fix the regression."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "plan_fix"}))
    
    file_contexts_str = ""
    for fc in state["file_contexts"]:
        file_contexts_str += f"File: {fc.path}\nRelevance: {fc.relevance_score}\nContent:\n{fc.content}\n---\n"
        
    prompt = prompts.PLAN_FIX_PROMPT.format(
        root_cause=state["rca_report"].root_cause,
        breaking_change_summary=state["rca_report"].breaking_change_summary,
        diff=state["bisect_result"].diff,
        file_contexts=file_contexts_str,
        faulty_commit=state["bisect_result"].faulty_commit_hash
    )
    
    llm = _get_llm()
    structured_llm = llm.with_structured_output(FixPlan)
    fix_plan = structured_llm.invoke(prompt)
    
    state["fix_plan"] = fix_plan
    
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "plan_fix"}))
    return state

def generate_fix(state: FixAgentState) -> FixAgentState:
    """Retrieves original contents and invokes LLM to generate the replacement files."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "generate_fix"}))
    
    fix_plan = state["fix_plan"]
    if not fix_plan:
        raise ValueError("No fix plan found in state.")
        
    # 1. Call read_file tool for each file in files_to_modify to ensure we have original content
    # and update our file contexts list
    original_contents_map = {}
    for path in fix_plan.files_to_modify:
        state["events"].append(AgentEvent(
            event="tool_call",
            payload={"tool": "read_file", "args": {"path": path, "repo_path": state["repo_path"]}}
        ))
        try:
            file_ctx = read_file.invoke({"path": path, "repo_path": state["repo_path"]})
            original_contents_map[path] = file_ctx.content
            
            # Add to file_contexts if not already present or update
            exists = False
            for fc in state["file_contexts"]:
                if fc.path == path:
                    fc.content = file_ctx.content
                    exists = True
                    break
            if not exists:
                state["file_contexts"].append(file_ctx)
        except Exception:
            # File does not exist yet (or read error), treat as new file with empty content
            original_contents_map[path] = ""
            state["file_contexts"].append(FileContext(path=path, content="", relevance_score=0.0))
            
    # 2. Build file contexts prompt context
    file_contexts_str = ""
    for fc in state["file_contexts"]:
        file_contexts_str += f"File: {fc.path}\nRelevance: {fc.relevance_score}\nContent:\n{fc.content}\n---\n"
        
    # 3. Call LLM to generate fix changes
    llm = _get_llm()
    structured_llm = llm.with_structured_output(FileChangesContainer)
    
    if state["retry_count"] == 0:
        prompt = prompts.GENERATE_FIX_PROMPT.format(
            fix_plan=fix_plan.model_dump_json(),
            file_contexts=file_contexts_str,
            root_cause=state["rca_report"].root_cause,
            diff=state["bisect_result"].diff
        )
    else:
        # Construct previous changes representation
        prev_str = ""
        for chg in state["file_changes"]:
            prev_str += f"File: {chg.path}\nNew Content:\n{chg.new_content}\n---\n"
            
        oracle_error = "Unknown error"
        if state["last_verify_response"]:
            oracle_error = state["last_verify_response"].response_body
            
        prompt = prompts.RETRY_FIX_PROMPT.format(
            fix_plan=fix_plan.model_dump_json(),
            file_contexts=file_contexts_str,
            root_cause=state["rca_report"].root_cause,
            previous_new_content=prev_str,
            oracle_error=oracle_error,
            retry_count=state["retry_count"]
        )
        
    container = structured_llm.invoke(prompt)
    
    # 4. Fill in or ensure original content matches actual files on disk
    file_changes = []
    for change in container.changes:
        # Override original_content with the actual tool-read content if available
        actual_orig = original_contents_map.get(change.path)
        if actual_orig is not None:
            change.original_content = actual_orig
        file_changes.append(change)
        
    state["file_changes"] = file_changes
    
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "generate_fix"}))
    return state

def apply_fix(state: FixAgentState) -> FixAgentState:
    """Creates a fix branch and writes the modified files to disk."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "apply_fix"}))
    
    repo = git.Repo(state["repo_path"])
    sha = state["bisect_result"].faulty_commit_hash[:7]
    branch_name = f"fix/bisect-{sha}"
    
    # Create or checkout the branch
    if branch_name in repo.heads:
        new_branch = repo.heads[branch_name]
    else:
        new_branch = repo.create_head(branch_name)
    new_branch.checkout()
    
    # Apply each file change
    for change in state["file_changes"]:
        state["events"].append(AgentEvent(
            event="tool_call",
            payload={
                "tool": "write_file",
                "args": {"path": change.path, "content": change.new_content, "repo_path": state["repo_path"]}
            }
        ))
        write_file.invoke({
            "path": change.path,
            "content": change.new_content,
            "repo_path": state["repo_path"]
        })
        
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "apply_fix"}))
    return state

def verify_fix(state: FixAgentState) -> FixAgentState:
    """Runs verification curl against the modified workspace files."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "verify_fix"}))
    
    sha = state["bisect_result"].faulty_commit_hash[:7]
    branch_name = f"fix/bisect-{sha}"
    
    state["events"].append(AgentEvent(
        event="tool_call",
        payload={"tool": "run_curl", "args": {"curl_config": state["curl_config"].model_dump(), "commit_hash": branch_name}}
    ))
    
    result = run_curl.invoke({
        "curl_config": state["curl_config"],
        "commit_hash": branch_name
    })
    
    state["last_verify_response"] = result
    
    state["events"].append(AgentEvent(
        event="tool_result",
        payload={"tool": "run_curl", "result": result.model_dump()}
    ))
    
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "verify_fix"}))
    return state

def commit_fix(state: FixAgentState) -> FixAgentState:
    """Stages, commits the fix, and compiles the final FixResult."""
    state["events"].append(AgentEvent(event="node_start", payload={"node": "commit_fix"}))
    
    # 1. Ask LLM to generate conventional commit message
    files_modified = [fc.path for fc in state["file_changes"]]
    prompt = prompts.COMMIT_MESSAGE_PROMPT.format(
        root_cause=state["rca_report"].root_cause,
        files_modified=", ".join(files_modified),
        faulty_commit=state["bisect_result"].faulty_commit_hash
    )
    
    llm = _get_llm()
    res = llm.invoke(prompt)
    commit_msg = str(res.content).strip()
    
    # Normalize message
    commit_msg = commit_msg.strip("'\"` \n")
    if not commit_msg.startswith("fix:"):
        commit_msg = f"fix: {commit_msg}"
    if len(commit_msg) > 72:
        commit_msg = commit_msg[:72]
        
    # 2. Git stage and commit
    repo = git.Repo(state["repo_path"])
    for path in files_modified:
        repo.git.add(path)
        
    commit = repo.index.commit(commit_msg)
    commit_hash = commit.hexsha
    
    # 3. Capture patch diff
    patch_diff = repo.git.diff("HEAD^", "HEAD")
    
    # 4. Build FixResult
    sha = state["bisect_result"].faulty_commit_hash[:7]
    branch_name = f"fix/bisect-{sha}"
    
    verification_passed = False
    if state["last_verify_response"]:
        verification_passed = (state["last_verify_response"].verdict == "good")
        
    fix_result = FixResult(
        branch_name=branch_name,
        commit_hash=commit_hash,
        files_modified=files_modified,
        patch_diff=patch_diff,
        verification_passed=verification_passed,
        verification_response=state["last_verify_response"]
    )
    
    state["fix_result"] = fix_result
    
    state["events"].append(AgentEvent(event="node_complete", payload={"node": "commit_fix"}))
    state["events"].append(AgentEvent(event="rca_ready", payload={"fix_result": fix_result.model_dump()}))
    
    return state
