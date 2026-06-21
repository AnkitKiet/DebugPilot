import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from agent.schemas import AgentState, BisectResult, CurlConfig, OracleResult, FileContext, RcaReport, AgentEvent
from agent.nodes import verify_with_curl, analyze_diff, correlate, fetch_imports, generate_rca

# Monkeypatch FakeMessagesListChatModel to support with_structured_output for our tests
FakeMessagesListChatModel.with_structured_output = lambda self, schema: MagicMock(
    invoke=MagicMock(return_value=RcaReport(
        faulty_commit="bad123",
        author="Author",
        timestamp=datetime.now(),
        commit_message="Message",
        root_cause="Root Cause",
        breaking_change_summary="Summary",
        transitive_path=[],
        files_analysed=[],
        confidence="HIGH",
        confidence_reasoning="Reasoning",
        suggested_next_steps="Next steps"
    ))
)

@pytest.fixture
def initial_state():
    config = CurlConfig(method="GET", url="http://example.com")
    oracle_res = OracleResult(
        commit_hash="abc", status_code=200, response_body="OK", response_headers={}, verdict="good", latency_ms=1.0
    )
    bisect_res = BisectResult(
        faulty_commit_hash="bad123",
        faulty_commit_message="msg",
        faulty_commit_author="auth",
        faulty_commit_timestamp=datetime.now(),
        diff="diff --git a/test.py b/test.py",
        iterations=1,
        oracle_results=[oracle_res]
    )
    
    return {
        "bisect_result": bisect_res,
        "curl_config": config,
        "curl_error_response": None,
        "diff_analysis": None,
        "suspected_files": [],
        "file_contexts": [],
        "correlation": None,
        "confidence": None,
        "import_fetch_count": 0,
        "rca_report": None,
        "events": []
    }

@patch("agent.nodes.run_curl")
def test_verify_with_curl(mock_run_curl, initial_state):
    mock_response = OracleResult(
        commit_hash="bad123", status_code=500, response_body="Error", response_headers={}, verdict="bad", latency_ms=10.0
    )
    mock_run_curl.invoke.return_value = mock_response
    
    res = verify_with_curl(initial_state)
    
    assert res["curl_error_response"] == mock_response
    assert len(res["events"]) == 4
    assert res["events"][0].event == "node_start"
    assert res["events"][1].event == "tool_call"
    assert res["events"][2].event == "tool_result"
    assert res["events"][3].event == "node_complete"

@patch("agent.nodes.ChatGoogleGenerativeAI")
def test_analyze_diff(mock_chat_openai, initial_state):
    # Mock LLM responses: 
    # 1st call: VERIFY_CURL_PROMPT (summary)
    # 2nd call: ANALYZE_DIFF_PROMPT (diff analysis with SUSPECTED_FILE paths)
    fake_llm = FakeMessagesListChatModel(responses=[
        AIMessage(content="Observed a connection error response body."),
        AIMessage(content="Detailed diff analysis.\nSUSPECTED_FILE: src/main.py\nSUSPECTED_FILE: src/utils.py")
    ])
    mock_chat_openai.return_value = fake_llm
    
    res = analyze_diff(initial_state)
    
    assert res["diff_analysis"] == "Detailed diff analysis.\nSUSPECTED_FILE: src/main.py\nSUSPECTED_FILE: src/utils.py"
    assert res["suspected_files"] == ["src/main.py", "src/utils.py"]
    assert len(res["events"]) == 2

@patch("agent.nodes.ChatGoogleGenerativeAI")
def test_correlate(mock_chat_openai, initial_state):
    initial_state["diff_analysis"] = "Diff analysis text"
    initial_state["file_contexts"] = [FileContext(path="src/main.py", content="code", relevance_score=0.9)]
    
    fake_llm = FakeMessagesListChatModel(responses=[
        AIMessage(content="Summary of error"),
        AIMessage(content="Correlation text.\nCONFIDENCE: HIGH\nREASONING: Code matches trace.")
    ])
    mock_chat_openai.return_value = fake_llm
    
    res = correlate(initial_state)
    
    assert res["correlation"] == "Correlation text.\nCONFIDENCE: HIGH\nREASONING: Code matches trace."
    assert res["confidence"] == "HIGH"
    assert len(res["events"]) == 2

@patch("agent.nodes.fetch_imports_tool")
def test_fetch_imports(mock_fetch_imports_tool, initial_state):
    mock_context = FileContext(path="pkg/sub.py", content="content", relevance_score=0.0)
    mock_fetch_imports_tool.invoke.return_value = [mock_context]
    
    res = fetch_imports(initial_state)
    
    assert res["import_fetch_count"] == 1
    assert len(res["file_contexts"]) == 1
    assert res["file_contexts"][0] == mock_context
    assert len(res["events"]) == 4
    assert res["events"][0].event == "node_start"
    assert res["events"][1].event == "tool_call"
    assert res["events"][2].event == "tool_result"
    assert res["events"][3].event == "node_complete"

@patch("agent.nodes.ChatGoogleGenerativeAI")
def test_generate_rca(mock_chat_openai, initial_state):
    # verify VERIFY_CURL_PROMPT summary is generated
    fake_llm = FakeMessagesListChatModel(responses=[
        AIMessage(content="Summary of error")
    ])
    mock_chat_openai.return_value = fake_llm
    
    res = generate_rca(initial_state)
    
    assert isinstance(res["rca_report"], RcaReport)
    assert res["rca_report"].faulty_commit == "bad123"
    # Verify rca_ready event and start/complete events are there (total 3 events)
    events = [e.event for e in res["events"]]
    assert "node_start" in events
    assert "rca_ready" in events
    assert "node_complete" in events
