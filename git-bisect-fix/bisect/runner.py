import os
import re
import git
from agent.schemas import BisectResult, OracleResult
from bisect.oracle import CurlOracle

class BisectRunner:
    """Manages git bisect execution and interfaces with CurlOracle to identify faulty commits."""
    def __init__(
        self,
        repo_path: str,
        good_commit: str,
        bad_commit: str,
        oracle: CurlOracle
    ):
        self.repo_path = repo_path
        self.good_commit = good_commit
        self.bad_commit = bad_commit
        self.oracle = oracle

    def run(self, on_iteration=None) -> BisectResult:
        max_iterations = int(os.getenv("MAX_BISECT_ITERATIONS", "20"))
        repo = git.Repo(self.repo_path)

        # Clear any existing bisect state before starting
        try:
            repo.git.bisect("reset")
        except Exception:
            pass

        iterations = 0
        oracle_results = []
        faulty_commit_hash = None
        
        try:
            # Start the git bisection
            repo.git.bisect("start")
            repo.git.bisect("bad", self.bad_commit)
            # The next step starts testing
            output = repo.git.bisect("good", self.good_commit)

            while True:
                # Check if bisection has completed
                match = re.search(r"([0-9a-fA-F]{7,40})\s+is\s+the\s+first\s+bad\s+commit", output, re.IGNORECASE)
                if match:
                    faulty_commit_hash = match.group(1)
                    break

                if iterations >= max_iterations:
                    raise RuntimeError(
                        f"Bisection exceeded maximum iterations limit ({max_iterations}) without converging."
                    )

                # Get the current commit hash proposed by git bisect
                current_commit = repo.head.commit.hexsha

                # Run oracle and record result
                oracle_result = self.oracle.execute(current_commit)
                oracle_results.append(oracle_result)
                iterations += 1

                if on_iteration:
                    on_iteration(iterations, current_commit, oracle_result.verdict)

                # Feed verdict back to git bisect
                output = repo.git.bisect(oracle_result.verdict)

            # Retrieve details of the faulty commit
            commit_info = repo.commit(faulty_commit_hash)
            # Full hexsha for consistency
            faulty_commit_hash_full = commit_info.hexsha
            
            # Capture the diff of the faulty commit
            if commit_info.parents:
                diff_text = repo.git.diff(f"{faulty_commit_hash_full}^", faulty_commit_hash_full)
            else:
                # If first commit in the repository, diff against an empty tree SHA
                diff_text = repo.git.diff("4b825dc642cb6eb9a0f92e421402230000000000", faulty_commit_hash_full)

            result = BisectResult(
                faulty_commit_hash=faulty_commit_hash_full,
                faulty_commit_message=commit_info.message,
                faulty_commit_author=f"{commit_info.author.name} <{commit_info.author.email}>" if commit_info.author.email else commit_info.author.name,
                faulty_commit_timestamp=commit_info.committed_datetime,
                diff=diff_text,
                iterations=iterations,
                oracle_results=oracle_results
            )
            return result

        finally:
            # Always reset the git bisect state to clean up the repository
            try:
                repo.git.bisect("reset")
            except Exception:
                pass
