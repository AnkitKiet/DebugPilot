from datetime import datetime
import pytest
from pydantic import ValidationError
from agent.schemas import (
    CurlConfig,
    OracleResult,
    BisectResult,
    FileContext,
    RcaReport,
    AgentEvent,
    FileChange,
    FixPlan,
    FixResult,
    FixAgentState
)

def test_file_change_valid():
    change = FileChange(
        path="src/main.py",
        original_content="def hello(): pass",
        new_content="def hello(): print('hello')",
        change_summary="Add print statement to hello function"
    )
    assert change.path == "src/main.py"
    assert change.original_content == "def hello(): pass"
    assert change.new_content == "def hello(): print('hello')"
    assert change.change_summary == "Add print statement to hello function"

def test_fix_plan_valid():
    plan = FixPlan(
        files_to_modify=["src/main.py"],
        changes_per_file={"src/main.py": "Add print statement"},
        reasoning="The function should log hello",
        estimated_risk="LOW"
    )
    assert plan.files_to_modify == ["src/main.py"]
    assert plan.changes_per_file == {"src/main.py": "Add print statement"}
    assert plan.reasoning == "The function should log hello"
    assert plan.estimated_risk == "LOW"

def test_estimated_risk_invalid():
    with pytest.raises(ValidationError):
        FixPlan(
            files_to_modify=["src/main.py"],
            changes_per_file={"src/main.py": "Add print statement"},
            reasoning="The function should log hello",
            estimated_risk="VERY_HIGH"  # type: ignore
        )

def test_fix_result_valid():
    oracle_res = OracleResult(
        commit_hash="abc1234",
        status_code=200,
        response_body="OK",
        response_headers={},
        verdict="good",
        latency_ms=15.5
    )
    result = FixResult(
        branch_name="fix/bisect-abc1234",
        commit_hash="fixcommit123",
        files_modified=["src/main.py"],
        patch_diff="diff --git a/src/main.py b/src/main.py",
        verification_passed=True,
        verification_response=oracle_res
    )
    assert result.branch_name == "fix/bisect-abc1234"
    assert result.commit_hash == "fixcommit123"
    assert result.files_modified == ["src/main.py"]
    assert result.patch_diff == "diff --git a/src/main.py b/src/main.py"
    assert result.verification_passed is True
    assert result.verification_response.status_code == 200

def test_verification_passed_is_bool_not_string():
    oracle_res = OracleResult(
        commit_hash="abc1234",
        status_code=200,
        response_body="OK",
        response_headers={},
        verdict="good",
        latency_ms=15.5
    )
    with pytest.raises(ValidationError):
        FixResult(
            branch_name="fix/bisect-abc1234",
            commit_hash="fixcommit123",
            files_modified=["src/main.py"],
            patch_diff="diff --git a/src/main.py b/src/main.py",
            verification_passed="true",  # type: ignore # should fail because it's a string, not a bool
            verification_response=oracle_res
        )

def test_fix_agent_state_holds_none_for_optional_fields():
    curl_config = CurlConfig(method="GET", url="http://example.com")
    oracle_res = OracleResult(
        commit_hash="abc", status_code=200, response_body="OK", response_headers={}, verdict="good", latency_ms=1.0
    )
    bisect_res = BisectResult(
        faulty_commit_hash="bad",
        faulty_commit_message="msg",
        faulty_commit_author="auth",
        faulty_commit_timestamp=datetime.now(),
        diff="",
        iterations=1,
        oracle_results=[oracle_res]
    )
    rca_report = RcaReport(
        faulty_commit="badcommit123",
        author="John Doe",
        timestamp=datetime.now(),
        commit_message="Introduce regression",
        root_cause="Null pointer dereference",
        breaking_change_summary="High-level break",
        transitive_path=[],
        files_analysed=[],
        confidence="HIGH",
        confidence_reasoning="Very clear traceback",
        suggested_next_steps="Revert changes"
    )

    state: FixAgentState = {
        "rca_report": rca_report,
        "bisect_result": bisect_res,
        "curl_config": curl_config,
        "repo_path": "/path/to/repo",
        "file_contexts": [],
        "fix_plan": None,
        "file_changes": [],
        "fix_result": None,
        "retry_count": 0,
        "last_verify_response": None,
        "events": []
    }

    assert state["fix_plan"] is None
    assert state["fix_result"] is None
    assert state["last_verify_response"] is None
    assert state["retry_count"] == 0
    assert len(state["file_changes"]) == 0
    assert len(state["events"]) == 0
