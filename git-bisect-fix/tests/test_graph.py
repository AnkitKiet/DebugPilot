import pytest
from agent.schemas import AgentState
from agent.graph import should_fetch_imports, create_graph

def test_routing_confidence_high(monkeypatch):
    monkeypatch.setenv("MAX_IMPORT_DEPTH", "3")
    state: AgentState = {
        "confidence": "HIGH",
        "import_fetch_count": 0,
    }  # type: ignore
    
    route = should_fetch_imports(state)
    assert route == "generate_rca"

def test_routing_confidence_low_fetch_0(monkeypatch):
    monkeypatch.setenv("MAX_IMPORT_DEPTH", "3")
    state: AgentState = {
        "confidence": "LOW",
        "import_fetch_count": 0,
    }  # type: ignore
    
    route = should_fetch_imports(state)
    assert route == "fetch_imports"

def test_routing_confidence_low_fetch_limit_hit(monkeypatch):
    monkeypatch.setenv("MAX_IMPORT_DEPTH", "3")
    state: AgentState = {
        "confidence": "LOW",
        "import_fetch_count": 3,
    }  # type: ignore
    
    route = should_fetch_imports(state)
    assert route == "generate_rca"

def test_routing_confidence_medium_fetch_2(monkeypatch):
    monkeypatch.setenv("MAX_IMPORT_DEPTH", "3")
    state: AgentState = {
        "confidence": "MEDIUM",
        "import_fetch_count": 2,
    }  # type: ignore
    
    route = should_fetch_imports(state)
    assert route == "fetch_imports"

def test_graph_compiles():
    graph = create_graph()
    assert graph is not None
    assert "verify_with_curl" in graph.nodes
    assert "analyze_diff" in graph.nodes
    assert "correlate" in graph.nodes
    assert "fetch_imports" in graph.nodes
    assert "generate_rca" in graph.nodes
