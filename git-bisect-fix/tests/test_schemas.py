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
    AgentState
)

def test_curl_config_valid():
    config = CurlConfig(
        method="GET",
        url="http://example.com",
        headers={"Content-Type": "application/json"},
        body="test-body",
        expected_status=200,
        expected_body_contains="success"
    )
    assert config.method == "GET"
    assert config.url == "http://example.com"
    assert config.headers == {"Content-Type": "application/json"}
    assert config.body == "test-body"
    assert config.expected_status == 200
    assert config.expected_body_contains == "success"

def test_curl_config_invalid_method():
    with pytest.raises(ValidationError):
        CurlConfig(
            method="INVALID", # type: ignore # invalid HTTP method
            url="http://example.com"
        )

def test_oracle_result_valid():
    result = OracleResult(
        commit_hash="abc1234",
        status_code=500,
        response_body="Internal error",
        response_headers={"server": "nginx"},
        verdict="bad",
        latency_ms=120.5
    )
    assert result.commit_hash == "abc1234"
    assert result.status_code == 500
    assert result.response_body == "Internal error"
    assert result.response_headers == {"server": "nginx"}
    assert result.verdict == "bad"
    assert result.latency_ms == 120.5

def test_oracle_result_invalid_verdict():
    with pytest.raises(ValidationError):
        OracleResult(
            commit_hash="abc1234",
            status_code=200,
            response_body="OK",
            response_headers={},
            verdict="invalid-verdict",  # type: ignore # Should be constrained to good/bad
            latency_ms=15.0
        )

def test_bisect_result_valid():
    oracle_res = OracleResult(
        commit_hash="abc1234",
        status_code=200,
        response_body="OK",
        response_headers={},
        verdict="good",
        latency_ms=10.0
    )
    res = BisectResult(
        faulty_commit_hash="badcommit123",
        faulty_commit_message="Fix bug",
        faulty_commit_author="John Doe",
        faulty_commit_timestamp=datetime.now(),
        diff="diff --git a/file.txt b/file.txt",
        iterations=5,
        oracle_results=[oracle_res]
    )
    assert res.faulty_commit_hash == "badcommit123"
    assert res.iterations == 5
    assert len(res.oracle_results) == 1

def test_file_context_valid():
    context = FileContext(
        path="src/main.py",
        content="print('hello')",
        relevance_score=0.85
    )
    assert context.path == "src/main.py"
    assert context.relevance_score == 0.85

def test_rca_report_valid():
    report = RcaReport(
        faulty_commit="badcommit123",
        author="John Doe",
        timestamp=datetime.now(),
        commit_message="Introduce regression",
        root_cause="Null pointer dereference",
        breaking_change_summary="High-level break",
        transitive_path=["tests", "main"],
        files_analysed=["src/main.py"],
        confidence="HIGH",
        confidence_reasoning="Very clear traceback",
        suggested_next_steps="Revert changes"
    )
    assert report.faulty_commit == "badcommit123"
    assert report.confidence == "HIGH"

def test_rca_report_invalid_confidence():
    with pytest.raises(ValidationError):
        RcaReport(
            faulty_commit="badcommit123",
            author="John Doe",
            timestamp=datetime.now(),
            commit_message="Introduce regression",
            root_cause="Null pointer",
            breaking_change_summary="Summary",
            transitive_path=[],
            files_analysed=[],
            confidence="VERY_HIGH",  # type: ignore # Should be Literal["HIGH", "MEDIUM", "LOW"]
            confidence_reasoning="None",
            suggested_next_steps="None"
        )

def test_agent_event_valid():
    event = AgentEvent(
        event="node_start",
        payload={"node": "bisect"}
    )
    assert event.event == "node_start"
    assert event.payload == {"node": "bisect"}

def test_agent_event_invalid():
    with pytest.raises(ValidationError):
        AgentEvent(
            event="invalid_phase",  # type: ignore # Should be Literal
            payload={}
        )

def test_agent_state_optional_fields():
    # Verify that TypedDict keys can be constructed with standard dict representation
    # and optional fields can be None
    config = CurlConfig(method="GET", url="http://example.com")
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
    
    state: AgentState = {
        "bisect_result": bisect_res,
        "curl_config": config,
        "curl_error_response": None,
        "diff_analysis": None,
        "suspected_files": ["src/main.py"],
        "file_contexts": [],
        "correlation": None,
        "confidence": None,
        "import_fetch_count": 0,
        "rca_report": None,
        "events": []
    }
    
    assert state["curl_error_response"] is None
    assert state["diff_analysis"] is None
    assert state["correlation"] is None
    assert state["confidence"] is None
    assert state["rca_report"] is None
