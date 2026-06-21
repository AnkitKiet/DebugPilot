import os
import ast
from typing import List, Optional
from langchain_core.tools import tool
from agent.schemas import FileContext, CurlConfig, OracleResult
from bisect.oracle import CurlOracle

def safe_resolve_path(path: str, repo_path: str) -> str:
    """Resolves target path under repo_path and checks for path traversal violations."""
    abs_repo = os.path.normpath(os.path.abspath(repo_path))
    abs_target = os.path.normpath(os.path.abspath(os.path.join(abs_repo, path)))
    
    try:
        common = os.path.commonpath([abs_repo, abs_target])
    except ValueError:
        raise ValueError(f"Security error: path {path} is outside the repository")
        
    if common != abs_repo:
        raise ValueError(f"Security error: path {path} is outside the repository")
        
    return abs_target

@tool
def read_file(path: str, repo_path: str) -> FileContext:
    """Read the content of a file from the repository.

    Args:
        path: Relative path to the file from the repository root.
        repo_path: Absolute path to the repository directory.

    Returns:
        FileContext containing the file contents.
    """
    target_path = safe_resolve_path(path, repo_path)
    
    if not os.path.isfile(target_path):
        raise FileNotFoundError(f"File not found: {path}")
        
    MAX_SIZE = 51200  # 50KB
    
    with open(target_path, "rb") as f:
        file_bytes = f.read()
        
    if len(file_bytes) > MAX_SIZE:
        truncated_bytes = file_bytes[:MAX_SIZE]
        content = truncated_bytes.decode("utf-8", errors="replace") + "\n\n[TRUNCATED... File exceeded 50KB limit]"
    else:
        content = file_bytes.decode("utf-8", errors="replace")
        
    return FileContext(
        path=path,
        content=content,
        relevance_score=0.0
    )

def _extract_imports_from_file(content: str, file_relpath: str) -> List[str]:
    """Parse AST of Python file to extract all absolute and relative imports."""
    try:
        tree = ast.parse(content)
    except Exception:
        return []

    imports = []
    dir_parts = [p for p in file_relpath.replace("\\", "/").split("/")[:-1] if p]
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            level = node.level
            module = node.module or ""
            if level > 0:
                # Relative import mapping
                if level <= len(dir_parts):
                    base_parts = dir_parts[:len(dir_parts) - level + 1]
                else:
                    base_parts = []
                base_module = ".".join(base_parts)
                full_module = f"{base_module}.{module}" if (base_module and module) else (base_module or module)
            else:
                # Absolute import mapping
                full_module = module
                
            if full_module:
                imports.append(full_module)
                for alias in node.names:
                    imports.append(f"{full_module}.{alias.name}")
    return imports

def _resolve_module_to_file(module_name: str, repo_path: str) -> Optional[str]:
    """Map dotted Python module name to a relative file path inside the repository if it exists."""
    rel_path = module_name.replace(".", "/")
    
    candidates = [
        f"{rel_path}.py",
        f"{rel_path}/__init__.py"
    ]
    
    for candidate in candidates:
        try:
            full_path = safe_resolve_path(candidate, repo_path)
            if os.path.isfile(full_path):
                return candidate
        except ValueError:
            pass
    return None

@tool
def fetch_imports(diff: str, repo_path: str, already_fetched: List[str]) -> List[FileContext]:
    """Parse the diff to extract changed files, read them, and extract their one-level import files.

    Args:
        diff: Git diff text.
        repo_path: Absolute path to the repository directory.
        already_fetched: List of relative file paths that have already been retrieved to avoid fetching again.

    Returns:
        List of FileContext objects for the discovered import files.
    """
    # 1. Parse diff to find changed files
    changed_files = set()
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            if path != "/dev/null":
                changed_files.add(path)

    discovered_files = set()
    results = []
    already_fetched_set = set(already_fetched)

    # 2. Extract and resolve imports for each changed file
    for rel_path in sorted(changed_files):
        # Exclude files already fetched or already in results
        if rel_path in already_fetched_set or rel_path in discovered_files:
            continue
            
        try:
            target_path = safe_resolve_path(rel_path, repo_path)
            if not os.path.isfile(target_path) or not rel_path.endswith(".py"):
                continue
                
            # Read contents
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                
            # Extract import modules
            modules = _extract_imports_from_file(content, rel_path)
            
            # Resolve each module to file path
            for module in modules:
                resolved_rel = _resolve_module_to_file(module, repo_path)
                if resolved_rel and resolved_rel not in already_fetched_set and resolved_rel not in discovered_files:
                    discovered_files.add(resolved_rel)
                    
                    # Read the imported file and create FileContext
                    # We can use the read_file tool logic or call read_file.invoke directly
                    # Invoking the tool keeps standard tool execution tracking
                    file_ctx = read_file.invoke({"path": resolved_rel, "repo_path": repo_path})
                    results.append(file_ctx)
        except Exception:
            # Silently skip any missing or unresolvable files
            pass

    return results

@tool
def run_curl(curl_config: CurlConfig, commit_hash: str) -> OracleResult:
    """Execute the configured HTTP request oracle against a target commit hash.

    Args:
        curl_config: Configuration dict containing method, URL, expected status, etc.
        commit_hash: Git commit hash to run the test against.

    Returns:
        OracleResult with status, response body, latency, and verdict.
    """
    oracle = CurlOracle(curl_config)
    return oracle.execute(commit_hash)


from pathlib import Path

@tool
def write_file(path: str, content: str, repo_path: str) -> str:
    """Write content to a file within the repository.
     Creates the file if it does not exist.
     Overwrites the file if it does exist.
     Returns confirmation message with path and bytes written.
     Will raise ValueError if path resolves outside repo_path."""
    base_repo = Path(repo_path).resolve()
    resolved_path = (base_repo / path).resolve()
    
    try:
        resolved_path.relative_to(base_repo)
    except ValueError:
        raise ValueError("Path traversal attempt detected")
        
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(content, encoding="utf-8")
    
    bytes_written = len(content.encode())
    return f"Written {bytes_written} bytes to {path}"

