from datetime import datetime
import pytest
from unittest.mock import MagicMock
import git
from agent.schemas import (
    FixAgentState,
    FixPlan,
    FileChange,
    FixResult,
    AgentEvent,
    FileContext,
    OracleResult,
    CurlConfig,
    BisectResult,
    RcaReport
)
import agent.fix.graph
from agent.fix.graph import should_retry, abort_fix, create_fix_graph

@pytest.fixture
def base_state():
    curl_config = CurlConfig(method="POST", url="http://localhost:8000/api/order")
    oracle_res = OracleResult(
        commit_hash="abc", status_code=200, response_body="OK", response_headers={}, verdict="good", latency_ms=1.0
    )
    bisect_res = BisectResult(
        faulty_commit_hash="badcommit12345",
        faulty_commit_message="msg",
        faulty_commit_author="auth",
        faulty_commit_timestamp=datetime.now(),
        diff="diff --git a/main.py b/main.py",
        iterations=1,
        oracle_results=[oracle_res]
    )
    rca_report = RcaReport(
        faulty_commit="badcommit12345",
        author="John Doe",
        timestamp=datetime.now(),
        commit_message="Introduce regression",
        root_cause="Null pointer dereference",
        breaking_change_summary="High-level break",
        transitive_path=[],
        files_analysed=["main.py"],
        confidence="HIGH",
        confidence_reasoning="Very clear traceback",
        suggested_next_steps="Revert changes"
    )
    
    state: FixAgentState = {
        "rca_report": rca_report,
        "bisect_result": bisect_res,
        "curl_config": curl_config,
        "repo_path": "/mock/repo",
        "file_contexts": [FileContext(path="main.py", content="print('hello')", relevance_score=0.9)],
        "fix_plan": None,
        "file_changes": [],
        "fix_result": None,
        "retry_count": 0,
        "last_verify_response": None,
        "events": []
    }
    return state

def test_routing_verdict_good(base_state):
    base_state["last_verify_response"] = OracleResult(
        commit_hash="abc", status_code=200, response_body="OK", response_headers={}, verdict="good", latency_ms=1.0
    )
    # Good verdict should route to commit_fix
    assert should_retry(base_state) == "commit_fix"

def test_routing_verdict_bad_retry_0(base_state):
    base_state["last_verify_response"] = OracleResult(
        commit_hash="abc", status_code=500, response_body="Error", response_headers={}, verdict="bad", latency_ms=1.0
    )
    base_state["retry_count"] = 0
    # Bad verdict with retry < MAX_FIX_RETRIES (2) should route to generate_fix
    assert should_retry(base_state) == "generate_fix"

def test_routing_verdict_bad_retry_1(base_state):
    base_state["last_verify_response"] = OracleResult(
        commit_hash="abc", status_code=500, response_body="Error", response_headers={}, verdict="bad", latency_ms=1.0
    )
    base_state["retry_count"] = 1
    # Bad verdict with retry < MAX_FIX_RETRIES (2) should route to generate_fix
    assert should_retry(base_state) == "generate_fix"

def test_routing_verdict_bad_retry_2(base_state):
    base_state["last_verify_response"] = OracleResult(
        commit_hash="abc", status_code=500, response_body="Error", response_headers={}, verdict="bad", latency_ms=1.0
    )
    base_state["retry_count"] = 2
    # Bad verdict with retry >= MAX_FIX_RETRIES (2) should route to abort_fix
    assert should_retry(base_state) == "abort_fix"

def test_abort_fix_logic(base_state, monkeypatch):
    # Mock GitRepo
    mock_repo = MagicMock()
    monkeypatch.setattr(git, "Repo", MagicMock(return_value=mock_repo))
    
    new_state = abort_fix(base_state)
    
    # Verify checkout and branch deletion were called
    mock_repo.git.checkout.assert_called_once_with("badcommit12345")
    mock_repo.git.branch.assert_called_once_with("-D", "fix/bisect-badcomm")
    
    # Verify error event is appended
    err_events = [e for e in new_state["events"] if e.event == "error"]
    assert len(err_events) == 1
    assert "Fix verification failed after max retries" in err_events[0].payload["message"]
    assert err_events[0].payload["retry_count"] == 0

def test_graph_compiles():
    graph = create_fix_graph()
    assert graph is not None
    # Check that all nodes are present in the compiled graph
    node_names = set(graph.nodes.keys())
    assert "plan_fix" in node_names
    assert "generate_fix" in node_names
    assert "apply_fix" in node_names
    assert "verify_fix" in node_names
    assert "commit_fix" in node_names
    assert "abort_fix" in node_names
    assert "increment_retry" in node_names
