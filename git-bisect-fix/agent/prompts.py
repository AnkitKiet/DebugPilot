# agent/prompts.py

VERIFY_CURL_PROMPT = """You are analyzing a failed HTTP request to understand the regression symptoms.

Curl command executed:
{curl_command}

Observed Status Code: {status_code}
Expected Status Code: {expected_status}

Observed Response Body:
{response_body}

Summarize what this curl error tells us about the failure (e.g., error type, exception messages, schema mismatches). Keep it concise but detailed enough for root cause analysis."""

ANALYZE_DIFF_PROMPT = """You are analyzing a git diff that introduced a regression.

Git Diff:
{diff}

Curl Error Summary:
{curl_error_summary}

Based on this diff and the observed error:
1. What contracts or interfaces changed?
2. What is the suspected breaking change?
3. Which files in the repository are most suspicious and should be read to understand the issue?

Output your analysis. At the end of your response, list the suspected file paths relative to repository root, one per line, starting with 'SUSPECTED_FILE: '."""

CORRELATE_PROMPT = """You are correlating a code diff analysis with a test failure to determine if the changes explain the bug.

Diff Analysis:
{diff_analysis}

Curl Error Summary:
{curl_error_summary}

File Contexts (code of suspected files):
{file_contexts}

Analyze if the changes in the diff and the code in the file contexts explain the observed curl failure.
Output your analysis of the correlation.
At the end of your response, specify the confidence level as HIGH, MEDIUM, or LOW in this format:
CONFIDENCE: <HIGH/MEDIUM/LOW>
REASONING: <your reasoning for this confidence rating>"""

GENERATE_RCA_PROMPT = """You are generating the final Root Cause Analysis (RCA) report for a git regression.

Diff Analysis:
{diff_analysis}

Correlation Narrative:
{correlation}

Bisection Result:
{bisect_result}

File Contexts:
{file_contexts}

Curl Error Summary:
{curl_error_summary}

Produce the final structured RCA report. Be specific and concise. Do not hedge."""
