import time
import httpx
from agent.schemas import CurlConfig, OracleResult

class CurlOracle:
    """An oracle that executes HTTP requests using a CurlConfig to determine commit regression status."""
    def __init__(self, curl_config: CurlConfig):
        self.curl_config = curl_config

    def execute(self, commit_hash: str) -> OracleResult:
        start_time = time.perf_counter()
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.request(
                    method=self.curl_config.method,
                    url=self.curl_config.url,
                    headers=self.curl_config.headers,
                    content=self.curl_config.body
                )
                response_body = response.text
                status_code = response.status_code
                response_headers = dict(response.headers)
        except Exception as e:
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000.0
            return OracleResult(
                commit_hash=commit_hash,
                status_code=0,
                response_body=str(e),
                response_headers={},
                verdict="bad",
                latency_ms=latency_ms
            )

        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000.0

        # Determine verdict:
        # "good" if status_code == expected_status AND (expected_body_contains is None OR expected_body_contains in response_body)
        # "bad" otherwise
        status_match = (status_code == self.curl_config.expected_status)
        body_match = (
            self.curl_config.expected_body_contains is None or
            self.curl_config.expected_body_contains in response_body
        )
        
        headers_match = True
        if self.curl_config.expected_headers:
            for expected_k, expected_v in self.curl_config.expected_headers.items():
                found_val = None
                for actual_k, actual_v in response_headers.items():
                    if actual_k.lower() == expected_k.lower():
                        found_val = actual_v
                        break
                if found_val is None or (expected_v and expected_v not in found_val):
                    headers_match = False
                    break

        verdict = "good" if (status_match and body_match and headers_match) else "bad"

        return OracleResult(
            commit_hash=commit_hash,
            status_code=status_code,
            response_body=response_body,
            response_headers=response_headers,
            verdict=verdict,
            latency_ms=latency_ms
        )
