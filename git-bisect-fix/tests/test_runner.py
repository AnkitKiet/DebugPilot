import os
import tempfile
import pytest
import git
from agent.schemas import CurlConfig, OracleResult
from bisect.oracle import CurlOracle
from bisect.runner import BisectRunner

class MockCurlOracle(CurlOracle):
    def __init__(self, good_commits, bad_commits):
        super().__init__(CurlConfig(method="GET", url="http://dummy"))
        self.good_commits = set(good_commits)
        self.bad_commits = set(bad_commits)

    def execute(self, commit_hash: str) -> OracleResult:
        verdict = "good" if commit_hash in self.good_commits else "bad"
        return OracleResult(
            commit_hash=commit_hash,
            status_code=200 if verdict == "good" else 500,
            response_body="OK" if verdict == "good" else "Error",
            response_headers={},
            verdict=verdict,
            latency_ms=1.0
        )

@pytest.fixture
def temp_git_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = git.Repo.init(tmpdir)
        # Configure user for temp repo commits
        with repo.config_writer() as writer:
            writer.set_value("user", "name", "Test Author")
            writer.set_value("user", "email", "test@example.com")
            
        commits = []
        for i in range(1, 9):
            file_path = os.path.join(tmpdir, "code.txt")
            with open(file_path, "a") as f:
                f.write(f"Line {i}\n")
            repo.index.add([file_path])
            commit = repo.index.commit(f"Commit {i}")
            commits.append(commit.hexsha)
            
        yield tmpdir, commits

def test_runner_identifies_faulty_commit(temp_git_repo):
    tmpdir, commits = temp_git_repo
    # Commit 5 is at index 4
    # Commits 1, 2, 3, 4 (indexes 0, 1, 2, 3) are good
    # Commits 5, 6, 7, 8 (indexes 4, 5, 6, 7) are bad
    good_commits = commits[:4]
    bad_commits = commits[4:]
    
    oracle = MockCurlOracle(good_commits, bad_commits)
    runner = BisectRunner(
        repo_path=tmpdir,
        good_commit=commits[0], # Commit 1
        bad_commit=commits[7],  # Commit 8
        oracle=oracle
    )
    
    result = runner.run()
    
    # Test 1: runner identifies commit 5 as faulty
    assert result.faulty_commit_hash == commits[4]
    assert "Commit 5" in result.faulty_commit_message
    assert result.faulty_commit_author == "Test Author <test@example.com>"
    
    # Test 2: BisectResult.iterations is correct
    assert result.iterations > 0
    assert len(result.oracle_results) == result.iterations

    # Test 3: BisectResult.diff is non-empty
    assert result.diff != ""
    assert "Line 5" in result.diff

    # Test 4: repo is left in clean state after run (not in bisect mode)
    repo = git.Repo(tmpdir)
    with pytest.raises(git.exc.GitCommandError):
        repo.git.bisect("log")

def test_runner_limit_exceeded(temp_git_repo, monkeypatch):
    tmpdir, commits = temp_git_repo
    good_commits = commits[:4]
    bad_commits = commits[4:]
    
    oracle = MockCurlOracle(good_commits, bad_commits)
    runner = BisectRunner(
        repo_path=tmpdir,
        good_commit=commits[0],
        bad_commit=commits[7],
        oracle=oracle
    )
    
    # Set MAX_BISECT_ITERATIONS to 1 to trigger limit
    monkeypatch.setenv("MAX_BISECT_ITERATIONS", "1")
    
    # Test 5: RuntimeError raised when iteration limit exceeded
    with pytest.raises(RuntimeError) as exc_info:
        runner.run()
        
    assert "exceeded maximum iterations limit" in str(exc_info.value)
    
    # Verify even on failure, the repo is left in clean state
    repo = git.Repo(tmpdir)
    with pytest.raises(git.exc.GitCommandError):
        repo.git.bisect("log")
