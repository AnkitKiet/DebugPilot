import argparse
import os
import sys
import json
import shlex
import re
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Expose standard library bisect patching to prevent import errors
import agent  # This triggers __init__.py patching

from dotenv import load_dotenv
load_dotenv()

from agent.schemas import CurlConfig, AgentState, AgentEvent, RcaReport, FixAgentState
from bisect.oracle import CurlOracle
from bisect.runner import BisectRunner
from agent.graph import create_graph
from agent.fix.graph import compiled_fix_graph

def parse_curl_command(curl_str: str) -> CurlConfig:
    """Parses a curl command string into a CurlConfig Pydantic model."""
    curl_str = curl_str.strip()
    # Strip wrapping quotes if present
    if (curl_str.startswith("'") and curl_str.endswith("'")) or (curl_str.startswith('"') and curl_str.endswith('"')):
        curl_str = curl_str[1:-1].strip()
        
    try:
        tokens = shlex.split(curl_str)
    except Exception as e:
        raise ValueError(f"Failed to parse curl command: {e}")
        
    if tokens and tokens[0].lower() == "curl":
        tokens = tokens[1:]
        
    method = "GET"
    url = ""
    headers = {}
    body = None
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("-X", "--request"):
            if i + 1 < len(tokens):
                method = tokens[i+1].upper()
                i += 2
            else:
                raise ValueError("Missing value for -X/--request flag")
        elif token in ("-H", "--header"):
            if i + 1 < len(tokens):
                header_val = tokens[i+1]
                if ":" in header_val:
                    k, v = header_val.split(":", 1)
                    headers[k.strip()] = v.strip()
                i += 2
            else:
                raise ValueError("Missing value for -H/--header flag")
        elif token in ("-d", "--data", "--data-raw", "--data-binary"):
            if i + 1 < len(tokens):
                body = tokens[i+1]
                if method == "GET":
                    method = "POST"
                i += 2
            else:
                raise ValueError("Missing value for data flag")
        elif token.startswith("-"):
            # Skip unrecognized options
            i += 1
        else:
            url = token
            i += 1
            
    if not url:
        raise ValueError("No URL found in curl command")
        
    return CurlConfig(
        method=method,
        url=url,
        headers=headers,
        body=body
    )

def main():
    parser = argparse.ArgumentParser(description="git-bisect-fix: Automated regression root cause analysis.")
    parser.add_argument("--good", required=True, help="Good commit hash")
    parser.add_argument("--bad", required=True, help="Bad commit hash")
    parser.add_argument("--curl", required=True, help="Curl command string to test regression")
    parser.add_argument("--expected-headers", help="JSON string of expected response headers")
    parser.add_argument("--repo", required=True, help="Path to repository")
    parser.add_argument("--headless", action="store_true", help="Print NDJSON events to stdout only")
    parser.add_argument("--output", help="Write final RCA report JSON to file")
    
    args = parser.parse_args()
    
    console = Console(file=sys.stderr if args.headless else sys.stdout)
    
    try:
        # 1. Parse curl command
        curl_config = parse_curl_command(args.curl)
        if args.expected_headers:
            try:
                parsed_headers = json.loads(args.expected_headers)
                if not isinstance(parsed_headers, dict):
                    raise ValueError("Must be a JSON object (key-value dictionary)")
                curl_config.expected_headers = {str(k): str(v) for k, v in parsed_headers.items()}
            except Exception as e:
                raise ValueError(f"Invalid --expected-headers JSON format: {e}")
        
        # 2. Render Header if not headless
        if not args.headless:
            header_text = Text("git-bisect-fix", style="bold white")
            console.print(Panel(header_text, border_style="blue", expand=False))
            console.print("\n[bold]Phase 1 — Bisect[/bold]")
            
        # 3. Setup Bisection Runner
        oracle = CurlOracle(curl_config)
        runner = BisectRunner(
            repo_path=args.repo,
            good_commit=args.good,
            bad_commit=args.bad,
            oracle=oracle
        )
        
        def on_iteration(iteration_num, commit_hash, verdict):
            if args.headless:
                print(json.dumps({
                    "event": "bisect_iteration",
                    "payload": {
                        "iteration": iteration_num,
                        "commit_hash": commit_hash[:7],
                        "verdict": verdict
                    }
                }), flush=True)
            else:
                console.print(f"  ├── [{iteration_num}] checking {commit_hash[:7]}... {verdict}")
                
        # 4. Run bisection
        bisect_result = runner.run(on_iteration=on_iteration)
        
        if args.headless:
            print(json.dumps({
                "event": "bisect_complete",
                "payload": {
                    "faulty_commit": bisect_result.faulty_commit_hash[:7]
                }
            }), flush=True)
        else:
            console.print(f"  └── ✓ Faulty commit: {bisect_result.faulty_commit_hash[:7]}")
            console.print("\n[bold]Phase 2 — RCA Agent[/bold]")
            
        # 5. Build initial AgentState
        state: AgentState = {
            "bisect_result": bisect_result,
            "curl_config": curl_config,
            "curl_error_response": None,
            "diff_analysis": None,
            "suspected_files": [],
            "file_contexts": [],
            "correlation": None,
            "confidence": None,
            "import_fetch_count": 0,
            "rca_report": None,
            "events": []
        }
        
        # 6. Instantiate and compile LangGraph
        graph = create_graph()
        
        printed_events_count = 0
        
        # 7. Run graph and stream events
        for output in graph.stream(state):
            for node_name, state_update in output.items():
                new_events = state_update.get("events", [])
                
                while printed_events_count < len(new_events):
                    evt = new_events[printed_events_count]
                    printed_events_count += 1
                    
                    if args.headless:
                        # Print raw event dictionary to stdout
                        event_dict = {
                            "event": evt.event,
                            "payload": evt.payload
                        }
                        print(json.dumps(event_dict), flush=True)
                    else:
                        # Render event nicely with rich
                        if evt.event == "node_start":
                            console.print(f"  ├── ▶ {evt.payload.get('node')}")
                        elif evt.event == "tool_call":
                            tool_name = evt.payload.get("tool")
                            tool_args = evt.payload.get("args", {})
                            console.print(f"  ├──   ⤷ tool: {tool_name}({tool_args})", style="dim")
                        elif evt.event == "tool_result":
                            tool_name = evt.payload.get("tool")
                            tool_res = evt.payload.get("result", {})
                            console.print(f"  ├──   ⤷ result: {tool_res}", style="dim")
                        elif evt.event == "node_complete":
                            node = evt.payload.get("node")
                            # If correlate completed, print confidence context
                            if node == "correlate":
                                confidence = state_update.get("confidence", "MEDIUM")
                                # Read current fetch count to print if we are loop backing
                                fetch_count = state_update.get("import_fetch_count", 0)
                                max_depth = int(os.getenv("MAX_IMPORT_DEPTH", "3"))
                                if confidence != "HIGH" and fetch_count < max_depth:
                                    console.print(f"  ├── ▶ correlate  (confidence: {confidence} — fetching imports)")
                                else:
                                    console.print(f"  ├── ▶ correlate  (confidence: {confidence})")
            
            # Keep updating our local state dict
            for node_name, state_update in output.items():
                for k, v in state_update.items():
                    state[k] = v
                    
        # 8. Render final report
        rca_report = state.get("rca_report")
        if not rca_report:
            raise RuntimeError("RCA Agent failed to generate RcaReport.")
            
        if not args.headless:
            report_text = (
                f"Commit:  {rca_report.faulty_commit[:7]}\n"
                f"Author:  {rca_report.author}\n"
                f"Date:    {rca_report.timestamp}\n"
                f"Message: {rca_report.commit_message.strip()}\n\n"
                f"[bold]Root Cause:[/bold]\n{rca_report.root_cause}\n\n"
                f"[bold]Breaking Change Summary:[/bold]\n{rca_report.breaking_change_summary}\n\n"
                f"[bold]Transitive Path:[/bold]\n{' -> '.join(rca_report.transitive_path) if rca_report.transitive_path else 'None'}\n\n"
                f"[bold]Files Analysed:[/bold]\n{', '.join(rca_report.files_analysed)}\n\n"
                f"[bold]Confidence:[/bold] {rca_report.confidence} ({rca_report.confidence_reasoning})\n\n"
                f"[bold]Suggested Next Steps:[/bold]\n{rca_report.suggested_next_steps}"
            )
            console.print("\n")
            console.print(Panel(report_text, title="Root Cause Analysis", border_style="green", expand=False))
            
        # 9. Human Gate
        proceed = False
        if args.headless:
            print("[WARNING] Headless mode: Auto-approving human gate for fix agent.", file=sys.stderr)
            proceed = True
        else:
            gate_text = (
                f"RCA complete. Confidence: {rca_report.confidence}\n"
                f"Faulty commit: {rca_report.faulty_commit[:7]}\n"
                f"Root cause: {rca_report.root_cause.strip()}"
            )
            console.print("\n")
            console.print(Panel(gate_text, title="Human Gate", border_style="yellow", expand=False))
            try:
                user_input = input("\nProceed to automated fix on new branch? [y/N]: ").strip().lower()
                if user_input == "y":
                    proceed = True
            except (KeyboardInterrupt, EOFError):
                proceed = False
                
        if not proceed:
            console.print("Exiting. RCA written to disk.")
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump({
                        "rca": rca_report.model_dump(),
                        "fix": None
                    }, f, indent=2, default=str)
            sys.exit(0)
            
        # 10. Fix Agent Trigger
        if not args.headless:
            console.print("\n[bold]Phase 3 — Fix Agent[/bold]")
            
        fix_state: FixAgentState = {
            "rca_report": rca_report,
            "bisect_result": state["bisect_result"],
            "curl_config": state["curl_config"],
            "repo_path": args.repo,
            "file_contexts": state["file_contexts"],
            "fix_plan": None,
            "file_changes": [],
            "fix_result": None,
            "retry_count": 0,
            "last_verify_response": None,
            "events": []
        }
        
        printed_fix_events = 0
        for output in compiled_fix_graph.stream(fix_state):
            for node_name, state_update in output.items():
                new_events = state_update.get("events", [])
                
                while printed_fix_events < len(new_events):
                    evt = new_events[printed_fix_events]
                    printed_fix_events += 1
                    
                    if args.headless:
                        event_dict = {
                            "event": evt.event,
                            "payload": evt.payload
                        }
                        print(json.dumps(event_dict), flush=True)
                    else:
                        if evt.event == "node_start":
                            node = evt.payload.get("node")
                            if node == "plan_fix":
                                console.print("  ├── ▶ plan_fix")
                            elif node == "generate_fix":
                                console.print("  ├── ▶ generate_fix")
                            elif node == "apply_fix":
                                console.print("  ├── ▶ apply_fix")
                                sha = fix_state["bisect_result"].faulty_commit_hash[:7]
                                console.print(f"  │     ⤷ branch: fix/bisect-{sha} created", style="dim")
                            elif node == "verify_fix":
                                console.print("  ├── ▶ verify_fix")
                            elif node == "commit_fix":
                                console.print("  └── ▶ commit_fix")
                        elif evt.event == "node_complete":
                            node = evt.payload.get("node")
                            if node == "plan_fix":
                                plan = state_update.get("fix_plan") or fix_state.get("fix_plan")
                                if plan:
                                    console.print(f"  │     Risk: {plan.estimated_risk}", style="dim")
                                    files_str = ", ".join(plan.files_to_modify)
                                    console.print(f"  │     Files: {files_str}", style="dim")
                        elif evt.event == "tool_call":
                            tool_name = evt.payload.get("tool")
                            tool_args = evt.payload.get("args", {})
                            if tool_name == "read_file":
                                console.print(f"  │     ⤷ tool: read_file({tool_args.get('path')})", style="dim")
                            elif tool_name == "write_file":
                                console.print(f"  │     ⤷ tool: write_file({tool_args.get('path')})", style="dim")
                            elif tool_name == "run_curl":
                                console.print(f"  │     ⤷ tool: run_curl", style="dim")
                        elif evt.event == "tool_result":
                            tool_name = evt.payload.get("tool")
                            tool_res = evt.payload.get("result", {})
                            if tool_name == "run_curl":
                                verdict_mark = "✓" if tool_res.get("verdict") == "good" else "✗"
                                console.print(f"  │     ⤷ oracle: {fix_state['curl_config'].method} {fix_state['curl_config'].url} → {tool_res.get('status_code')} {verdict_mark}", style="dim")
                        elif evt.event == "error":
                            console.print(f"  └── ✗ Fix failed after {evt.payload.get('retry_count')} attempts. Branch deleted.\n        Manual intervention required.", style="bold red")

            # Check if increment_retry was just executed in this turn of the stream
            if "increment_retry" in output:
                retry_count = fix_state.get("retry_count", 0)
                max_retries = int(os.getenv("MAX_FIX_RETRIES", "2"))
                if not args.headless:
                    console.print(f"  ├── ⚠ verify_fix failed (attempt {retry_count}/{max_retries}) — retrying", style="yellow")
                    
            # Keep updating our local state dict
            for node_name, state_update in output.items():
                for k, v in state_update.items():
                    fix_state[k] = v
                    
        # 11. Render final fix report
        fix_result = fix_state.get("fix_result")
        if not args.headless and fix_result:
            files_mod_str = ", ".join(fix_result.files_modified)
            oracle_status = "PASS" if fix_result.verification_passed else "FAIL"
            fix_report_text = (
                f"Branch:  {fix_result.branch_name}\n"
                f"Commit:  {fix_result.commit_hash[:7]}\n"
                f"Files:   {files_mod_str}\n"
                f"Oracle:  {oracle_status}"
            )
            console.print("\n")
            console.print(Panel(fix_report_text, title="Fix Applied", border_style="green", expand=False))
            
        # 12. Write final output file if requested
        if args.output:
            output_data = {
                "rca": rca_report.model_dump(),
                "fix": fix_result.model_dump() if fix_result else None
            }
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, default=str)
                
        sys.exit(0)
        
    except Exception as e:
        if args.headless:
            print(json.dumps({
                "event": "error",
                "payload": {"message": str(e)}
            }), flush=True)
        else:
            console.print(f"\n[bold red]Error: {e}[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
