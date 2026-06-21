from datetime import datetime
import pytest
from unittest.mock import MagicMock, patch
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
from agent.fix.nodes import plan_fix, generate_fix, apply_fix, verify_fix, commit_fix

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

def test_plan_fix(base_state, monkeypatch):
    mock_plan = FixPlan(
        files_to_modify=["main.py"],
        changes_per_file={"main.py": "Change prints"},
        reasoning="fix bug",
        estimated_risk="LOW"
    )
    
    mock_invoke = MagicMock(return_value=mock_plan)
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke = mock_invoke
    
    mock_llm_inst = MagicMock()
    mock_llm_inst.with_structured_output.return_value = mock_structured_llm
    
    monkeypatch.setattr("agent.fix.nodes._get_llm", MagicMock(return_value=mock_llm_inst))
    
    new_state = plan_fix(base_state)
    assert new_state["fix_plan"] == mock_plan
    
    # Event verification
    events = new_state["events"]
    assert len(events) >= 2
    assert events[0].event == "node_start"
    assert events[0].payload["node"] == "plan_fix"
    assert events[-1].event == "node_complete"
    assert events[-1].payload["node"] == "plan_fix"

def test_generate_fix_retry_0(base_state, monkeypatch):
    plan = FixPlan(
        files_to_modify=["main.py"],
        changes_per_file={"main.py": "Change prints"},
        reasoning="fix bug",
        estimated_risk="LOW"
    )
    base_state["fix_plan"] = plan
    base_state["retry_count"] = 0
    
    # Mock read_file tool
    mock_file_ctx = FileContext(path="main.py", content="original code", relevance_score=0.0)
    mock_read_file = MagicMock()
    mock_read_file.invoke.return_value = mock_file_ctx
    monkeypatch.setattr("agent.fix.nodes.read_file", mock_read_file)
    
    # Mock LLM container output
    from agent.fix.nodes import FileChangesContainer
    mock_changes_container = FileChangesContainer(
        changes=[
            FileChange(
                path="main.py",
                original_content="original code",
                new_content="fixed code",
                change_summary="Fixed logic"
            )
        ]
    )
    
    mock_invoke = MagicMock(return_value=mock_changes_container)
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke = mock_invoke
    
    mock_llm_inst = MagicMock()
    mock_llm_inst.with_structured_output.return_value = mock_structured_llm
    
    monkeypatch.setattr("agent.fix.nodes._get_llm", MagicMock(return_value=mock_llm_inst))
    
    with patch("agent.fix.prompts.GENERATE_FIX_PROMPT", "GENERATE {fix_plan} {file_contexts} {root_cause} {diff}"):
        new_state = generate_fix(base_state)
        
        # Verify read_file was called
        mock_read_file.invoke.assert_called_once_with({"path": "main.py", "repo_path": "/mock/repo"})
        
        # Verify LLM invoke was called
        mock_invoke.assert_called_once()
        
        # Verify state populated
        assert len(new_state["file_changes"]) == 1
        assert new_state["file_changes"][0].new_content == "fixed code"
        
        # Verify events
        tool_calls = [e for e in new_state["events"] if e.event == "tool_call"]
        assert len(tool_calls) == 1
        assert tool_calls[0].payload["tool"] == "read_file"

def test_generate_fix_retry_1(base_state, monkeypatch):
    plan = FixPlan(
        files_to_modify=["main.py"],
        changes_per_file={"main.py": "Change prints"},
        reasoning="fix bug",
        estimated_risk="LOW"
    )
    base_state["fix_plan"] = plan
    base_state["retry_count"] = 1
    base_state["file_changes"] = [
        FileChange(
            path="main.py",
            original_content="original code",
            new_content="failed code",
            change_summary="Fixed logic"
        )
    ]
    base_state["last_verify_response"] = OracleResult(
        commit_hash="abc", status_code=500, response_body="SyntaxError", response_headers={}, verdict="bad", latency_ms=1.0
    )
    
    # Mock read_file tool
    mock_file_ctx = FileContext(path="main.py", content="original code", relevance_score=0.0)
    mock_read_file = MagicMock()
    mock_read_file.invoke.return_value = mock_file_ctx
    monkeypatch.setattr("agent.fix.nodes.read_file", mock_read_file)
    
    # Mock LLM container output
    from agent.fix.nodes import FileChangesContainer
    mock_changes_container = FileChangesContainer(
        changes=[
            FileChange(
                path="main.py",
                original_content="original code",
                new_content="revised fixed code",
                change_summary="Fixed SyntaxError"
            )
        ]
    )
    
    mock_invoke = MagicMock(return_value=mock_changes_container)
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke = mock_invoke
    
    mock_llm_inst = MagicMock()
    mock_llm_inst.with_structured_output.return_value = mock_structured_llm
    
    monkeypatch.setattr("agent.fix.nodes._get_llm", MagicMock(return_value=mock_llm_inst))
    
    with patch("agent.fix.prompts.RETRY_FIX_PROMPT", "RETRY {fix_plan} {file_contexts} {root_cause} {previous_new_content} {oracle_error} {retry_count}"):
        new_state = generate_fix(base_state)
        
        # Verify LLM invoke called
        mock_invoke.assert_called_once()
        
        # Verify state populated
        assert len(new_state["file_changes"]) == 1
        assert new_state["file_changes"][0].new_content == "revised fixed code"

def test_apply_fix(base_state, monkeypatch):
    base_state["file_changes"] = [
        FileChange(
            path="main.py",
            original_content="original code",
            new_content="fixed code",
            change_summary="Fixed logic"
        )
    ]
    
    # Mock git Repo
    mock_repo = MagicMock()
    mock_branch = MagicMock()
    mock_repo.heads = {}
    mock_repo.create_head.return_value = mock_branch
    monkeypatch.setattr(git, "Repo", MagicMock(return_value=mock_repo))
    
    # Mock write_file tool
    mock_write_file = MagicMock()
    mock_write_file.invoke.return_value = "Written 10 bytes to main.py"
    monkeypatch.setattr("agent.fix.nodes.write_file", mock_write_file)
    
    new_state = apply_fix(base_state)
    
    # Check branch creation and checkout
    mock_repo.create_head.assert_called_once_with("fix/bisect-badcomm")
    mock_branch.checkout.assert_called_once()
    
    # Check tool call
    mock_write_file.invoke.assert_called_once_with({
        "path": "main.py",
        "content": "fixed code",
        "repo_path": "/mock/repo"
    })
    
    # Check events
    tool_calls = [e for e in new_state["events"] if e.event == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].payload["tool"] == "write_file"

def test_verify_fix(base_state, monkeypatch):
    # Mock run_curl tool
    mock_oracle_res = OracleResult(
        commit_hash="fix/bisect-badcomm",
        status_code=200,
        response_body="OK",
        response_headers={},
        verdict="good",
        latency_ms=10.0
    )
    mock_run_curl = MagicMock()
    mock_run_curl.invoke.return_value = mock_oracle_res
    monkeypatch.setattr("agent.fix.nodes.run_curl", mock_run_curl)
    
    new_state = verify_fix(base_state)
    
    # Check verify response stored
    assert new_state["last_verify_response"] == mock_oracle_res
    
    # Check tool call
    mock_run_curl.invoke.assert_called_once_with({
        "curl_config": base_state["curl_config"],
        "commit_hash": "fix/bisect-badcomm"
    })
    
    # Check events
    tool_calls = [e for e in new_state["events"] if e.event == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].payload["tool"] == "run_curl"

def test_commit_fix(base_state, monkeypatch):
    base_state["file_changes"] = [
        FileChange(
            path="main.py",
            original_content="original code",
            new_content="fixed code",
            change_summary="Fixed logic"
        )
    ]
    base_state["last_verify_response"] = OracleResult(
        commit_hash="fix/bisect-badcomm",
        status_code=200,
        response_body="OK",
        response_headers={},
        verdict="good",
        latency_ms=10.0
    )
    
    # Mock git Repo
    mock_repo = MagicMock()
    mock_commit = MagicMock()
    mock_commit.hexsha = "commitsha123"
    mock_repo.index.commit.return_value = mock_commit
    mock_repo.git.diff.return_value = "mock patch diff"
    monkeypatch.setattr(git, "Repo", MagicMock(return_value=mock_repo))
    
    # Mock LLM for commit message
    mock_response = MagicMock()
    mock_response.content = "fix: repair null dereference"
    mock_llm_inst = MagicMock()
    mock_llm_inst.invoke.return_value = mock_response
    monkeypatch.setattr("agent.fix.nodes._get_llm", MagicMock(return_value=mock_llm_inst))
    
    new_state = commit_fix(base_state)
    
    # Check repo commit called with LLM message
    mock_repo.git.add.assert_called_once_with("main.py")
    mock_repo.index.commit.assert_called_once_with("fix: repair null dereference")
    mock_repo.git.diff.assert_called_once_with("HEAD^", "HEAD")
    
    # Check fix result
    res = new_state["fix_result"]
    assert isinstance(res, FixResult)
    assert res.branch_name == "fix/bisect-badcomm"
    assert res.commit_hash == "commitsha123"
    assert res.files_modified == ["main.py"]
    assert res.patch_diff == "mock patch diff"
    assert res.verification_passed is True
    
    # Check events
    assert any(e.event == "rca_ready" for e in new_state["events"])
