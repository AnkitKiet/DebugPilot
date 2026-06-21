import os
import tempfile
import pytest
from agent.schemas import FileContext
from agent.tools import write_file, read_file

def test_write_file_valid():
    with tempfile.TemporaryDirectory() as tmpdir:
        content = "print('hello world')"
        result = write_file.invoke({"path": "app.py", "content": content, "repo_path": tmpdir})
        
        # Test confirmation string
        expected_bytes = len(content.encode("utf-8"))
        assert result == f"Written {expected_bytes} bytes to app.py"
        
        # Test file actually exists on disk and has correct content
        full_path = os.path.join(tmpdir, "app.py")
        assert os.path.isfile(full_path)
        with open(full_path, "r", encoding="utf-8") as f:
            assert f.read() == content

def test_write_file_read_back():
    with tempfile.TemporaryDirectory() as tmpdir:
        content = "class A: pass"
        write_file.invoke({"path": "models.py", "content": content, "repo_path": tmpdir})
        
        # Use read_file tool to read it back
        read_result = read_file.invoke({"path": "models.py", "repo_path": tmpdir})
        assert isinstance(read_result, FileContext)
        assert read_result.path == "models.py"
        assert read_result.content == content

def test_write_file_path_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="Path traversal attempt detected"):
            write_file.invoke({"path": "../outside.txt", "content": "hack", "repo_path": tmpdir})

def test_write_file_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        content = "config = {}"
        result = write_file.invoke({"path": "config/prod/settings.py", "content": content, "repo_path": tmpdir})
        
        expected_bytes = len(content.encode("utf-8"))
        assert result == f"Written {expected_bytes} bytes to config/prod/settings.py"
        
        full_path = os.path.join(tmpdir, "config/prod/settings.py")
        assert os.path.isfile(full_path)
        with open(full_path, "r", encoding="utf-8") as f:
            assert f.read() == content

def test_write_file_overwrites():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = "data.json"
        write_file.invoke({"path": path, "content": '{"status": "ok"}', "repo_path": tmpdir})
        
        # Overwrite it
        new_content = '{"status": "error"}'
        write_file.invoke({"path": path, "content": new_content, "repo_path": tmpdir})
        
        full_path = os.path.join(tmpdir, path)
        with open(full_path, "r", encoding="utf-8") as f:
            assert f.read() == new_content

def test_write_file_confirmation_unicode():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = "unicode.txt"
        unicode_content = "🚀 Gemini 2.5!"
        result = write_file.invoke({"path": path, "content": unicode_content, "repo_path": tmpdir})
        
        # len(unicode_content) is 14 characters, but 🚀 takes 4 bytes.
        # So len(unicode_content.encode("utf-8")) is 4 + 1 + 6 + 1 + 3 + 1 + 1 = 17 bytes.
        expected_bytes = len(unicode_content.encode("utf-8"))
        assert expected_bytes == 16
        assert result == f"Written 16 bytes to unicode.txt"
