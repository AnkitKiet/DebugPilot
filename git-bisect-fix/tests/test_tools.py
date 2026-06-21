import os
import tempfile
import pytest
from unittest.mock import MagicMock
from agent.schemas import CurlConfig, FileContext, OracleResult
from agent.tools import read_file, fetch_imports, run_curl, safe_resolve_path
from bisect.oracle import CurlOracle

def test_read_file_valid():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "test.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("print('hello')")
            
        result = read_file.invoke({"path": "test.py", "repo_path": tmpdir})
        assert isinstance(result, FileContext)
        assert result.path == "test.py"
        assert result.content == "print('hello')"
        assert result.relevance_score == 0.0

def test_read_file_path_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError):
            read_file.invoke({"path": "../outside.txt", "repo_path": tmpdir})

def test_read_file_truncated():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "large.txt")
        large_content = "x" * 60000
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(large_content)
            
        result = read_file.invoke({"path": "large.txt", "repo_path": tmpdir})
        assert "[TRUNCATED... File exceeded 50KB limit]" in result.content
        assert len(result.content) > 50000
        assert len(result.content) == 51200 + len("\n\n[TRUNCATED... File exceeded 50KB limit]")

def test_fetch_imports_parsing():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "pkg"))
        
        main_content = """
import pkg.sub
from pkg.other import func
from .local import helper
"""
        main_path = os.path.join(tmpdir, "main.py")
        with open(main_path, "w", encoding="utf-8") as f:
            f.write(main_content)
            
        with open(os.path.join(tmpdir, "pkg", "sub.py"), "w") as f:
            f.write("sub")
        with open(os.path.join(tmpdir, "pkg", "other.py"), "w") as f:
            f.write("other")
        with open(os.path.join(tmpdir, "local.py"), "w") as f:
            f.write("local")
            
        diff = """
diff --git a/main.py b/main.py
--- a/main.py
+++ b/main.py
@@ -1,1 +1,4 @@
+import pkg.sub
+from pkg.other import func
+from .local import helper
"""
        results = fetch_imports.invoke({"diff": diff, "repo_path": tmpdir, "already_fetched": []})
        
        paths = {r.path for r in results}
        assert "pkg/sub.py" in paths
        assert "pkg/other.py" in paths
        assert "local.py" in paths
        assert len(results) == 3

def test_fetch_imports_skips_already_fetched():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "dep.py"), "w") as f:
            f.write("dep")
        with open(os.path.join(tmpdir, "main.py"), "w") as f:
            f.write("import dep")
            
        diff = """
diff --git a/main.py b/main.py
+++ b/main.py
@@ -1,1 +1,1 @@
+import dep
"""
        results = fetch_imports.invoke({"diff": diff, "repo_path": tmpdir, "already_fetched": ["dep.py"]})
        assert len(results) == 0

def test_run_curl(monkeypatch):
    config = CurlConfig(method="GET", url="http://test")
    expected_result = OracleResult(
        commit_hash="abc",
        status_code=200,
        response_body="OK",
        response_headers={},
        verdict="good",
        latency_ms=5.0
    )
    
    mock_execute = MagicMock(return_value=expected_result)
    monkeypatch.setattr(CurlOracle, "execute", mock_execute)
    
    result = run_curl.invoke({"curl_config": config, "commit_hash": "abc"})
    assert result == expected_result
    mock_execute.assert_called_once_with("abc")
