PLAN_FIX_PROMPT = """You are an expert software engineer.
Analyze the following Root Cause Analysis (RCA) and identify a fix strategy.

Root Cause:
{root_cause}

Breaking Change Summary:
{breaking_change_summary}

Faulty Commit Hash: {faulty_commit}
Diff of the Faulty Commit:
{diff}

Below are the contents of the relevant files:
{file_contexts}

Design a conceptual plan to fix the regression. Do NOT generate code implementations yet. Only identify:
1. Which files need to be modified (as relative paths).
2. The high-level description of changes for each file.
3. The reasoning behind this fix.
4. An estimated risk level of applying this fix ("LOW", "MEDIUM", "HIGH").

Return your response strictly as a JSON object matching this schema:
{{
  "files_to_modify": ["path/to/file1.py", "path/to/file2.py"],
  "changes_per_file": {{
    "path/to/file1.py": "Description of change 1",
    "path/to/file2.py": "Description of change 2"
  }},
  "reasoning": "Reasoning for the fix plan",
  "estimated_risk": "LOW" | "MEDIUM" | "HIGH"
}}
Do NOT wrap the response in markdown code blocks.
"""

GENERATE_FIX_PROMPT = """You are an expert software engineer.
Generate the actual code changes based on the proposed fix plan.

Fix Plan:
{fix_plan}

Root Cause:
{root_cause}

Faulty Commit Diff:
{diff}

Below is the context of all relevant files:
{file_contexts}

Rules for generating the fix:
1. Provide the COMPLETE file content for each file in the fix plan. Never output partial code or diff markers.
2. Preserve all existing logic and functionality not related to the bug.
3. Match the coding style, imports, indentation, and formatting of the original file exactly.
4. Output one FileChange object for each file listed in the fix plan's `files_to_modify`.

Return your response strictly as a JSON list of objects matching this schema:
[
  {{
    "path": "relative/path/to/file.py",
    "original_content": "Original complete content",
    "new_content": "Replacement complete content containing the fix",
    "change_summary": "One-line summary of what changed"
  }}
]
Do NOT wrap the response in markdown code blocks.
"""

RETRY_FIX_PROMPT = """You are an expert software engineer.
A previous attempt to fix the bug failed the validation test (oracle run).
You need to revise the fix to resolve the error.

Fix Plan:
{fix_plan}

Root Cause:
{root_cause}

Previous Generated File Changes:
{previous_new_content}

Oracle Verification Error:
{oracle_error}

Current Retry Attempt Count: {retry_count}

Below is the context of all relevant files:
{file_contexts}

Revise the code changes.
Rules:
1. Provide the COMPLETE file content for each file in the fix plan. Never output partial code.
2. Preserve all existing logic not related to the bug.
3. Match the coding style of the original file exactly.
4. Output one FileChange object for each file listed in the fix plan's `files_to_modify`.

Return your response strictly as a JSON list of objects matching this schema:
[
  {{
    "path": "relative/path/to/file.py",
    "original_content": "Original complete content",
    "new_content": "Replacement complete content containing the revised fix",
    "change_summary": "One-line summary of revised changes"
  }}
]
Do NOT wrap the response in markdown code blocks.
"""

COMMIT_MESSAGE_PROMPT = """Generate a concise, conventional-commits-style commit message for the following fix.

Root Cause:
{root_cause}

Files Modified:
{files_modified}

Faulty Commit Hash: {faulty_commit}

Rules:
1. Output format: fix: <description>
2. Maximum 72 characters.
3. Do NOT include any body, explanation, markdown, or extra text. Only return the commit message string.
"""
