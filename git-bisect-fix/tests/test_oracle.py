import pytest
import respx
import httpx
from agent.schemas import CurlConfig
from bisect.oracle import CurlOracle

def test_oracle_correct_status_matching_body():
    config = CurlConfig(
        method="GET",
        url="http://mock-service/test",
        expected_status=200,
        expected_body_contains="all good"
    )
    oracle = CurlOracle(config)
    
    with respx.mock:
        respx.get("http://mock-service/test").respond(status_code=200, text="everything is all good here")
        result = oracle.execute("commit-1")
        
        assert result.commit_hash == "commit-1"
        assert result.status_code == 200
        assert result.verdict == "good"
        assert result.response_body == "everything is all good here"

def test_oracle_correct_status_non_matching_body():
    config = CurlConfig(
        method="GET",
        url="http://mock-service/test",
        expected_status=200,
        expected_body_contains="all good"
    )
    oracle = CurlOracle(config)
    
    with respx.mock:
        respx.get("http://mock-service/test").respond(status_code=200, text="broken status message")
        result = oracle.execute("commit-2")
        
        assert result.commit_hash == "commit-2"
        assert result.status_code == 200
        assert result.verdict == "bad"

def test_oracle_wrong_status_code():
    config = CurlConfig(
        method="GET",
        url="http://mock-service/test",
        expected_status=200,
        expected_body_contains=None
    )
    oracle = CurlOracle(config)
    
    with respx.mock:
        respx.get("http://mock-service/test").respond(status_code=500, text="Server Error")
        result = oracle.execute("commit-3")
        
        assert result.commit_hash == "commit-3"
        assert result.status_code == 500
        assert result.verdict == "bad"

def test_oracle_connection_error():
    config = CurlConfig(
        method="POST",
        url="http://mock-service/test",
        headers={"Content-Type": "application/json"},
        body="{}",
        expected_status=201
    )
    oracle = CurlOracle(config)
    
    with respx.mock:
        respx.post("http://mock-service/test").mock(side_effect=httpx.ConnectError("Connection refused"))
        result = oracle.execute("commit-4")
        
        assert result.commit_hash == "commit-4"
        assert result.status_code == 0
        assert result.verdict == "bad"
        assert "Connection refused" in result.response_body

def test_oracle_latency_populated():
    config = CurlConfig(
        method="GET",
        url="http://mock-service/test",
        expected_status=200
    )
    oracle = CurlOracle(config)
    
    with respx.mock:
        respx.get("http://mock-service/test").respond(status_code=200, text="OK")
        result = oracle.execute("commit-5")
        
        assert result.commit_hash == "commit-5"
        assert result.latency_ms > 0.0

def test_oracle_expected_headers_match():
    config = CurlConfig(
        method="GET",
        url="http://mock-service/test",
        expected_status=200,
        expected_headers={"X-Trace-Id": "", "Content-Type": "application/json"}
    )
    oracle = CurlOracle(config)
    
    with respx.mock:
        respx.get("http://mock-service/test").respond(
            status_code=200, 
            headers={"x-trace-id": "uuid-12345", "Content-Type": "application/json; charset=utf-8"},
            text="OK"
        )
        result = oracle.execute("commit-6")
        
        assert result.commit_hash == "commit-6"
        assert result.verdict == "good"

def test_oracle_expected_headers_missing():
    config = CurlConfig(
        method="GET",
        url="http://mock-service/test",
        expected_status=200,
        expected_headers={"X-Trace-Id": ""}
    )
    oracle = CurlOracle(config)
    
    with respx.mock:
        respx.get("http://mock-service/test").respond(
            status_code=200, 
            headers={"Content-Type": "application/json"},
            text="OK"
        )
        result = oracle.execute("commit-7")
        
        assert result.commit_hash == "commit-7"
        assert result.verdict == "bad"

def test_oracle_expected_headers_value_mismatch():
    config = CurlConfig(
        method="GET",
        url="http://mock-service/test",
        expected_status=200,
        expected_headers={"X-Trace-Id": "expected-uuid"}
    )
    oracle = CurlOracle(config)
    
    with respx.mock:
        respx.get("http://mock-service/test").respond(
            status_code=200, 
            headers={"x-trace-id": "wrong-uuid"},
            text="OK"
        )
        result = oracle.execute("commit-8")
        
        assert result.commit_hash == "commit-8"
        assert result.verdict == "bad"

