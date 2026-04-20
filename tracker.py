import json
import os
import subprocess
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────

COST_LOG_FILE = ".claude/cost.log"
COST_SUMMARY_FILE = ".claude/cost_summary.json"


# ─── TRACKED CLAUDE CALL ──────────────────────────────────────────────────────

def claude_call(prompt, operation_name="unknown"):
    """
    Drop-in replacement for subprocess.run(["claude", "-p", prompt]).
    Does everything the original does, plus captures and logs token usage.

    Usage:
        # Before (untracked):
        result = subprocess.run(["claude", "-p", prompt], ...)

        # After (tracked):
        result = claude_call(prompt, operation_name="generate_question")

    Returns the same dict as subprocess.run result, plus adds:
        result.cost_usd
        result.input_tokens
        result.output_tokens
    """
    os.makedirs(".claude", exist_ok=True)

    # Run Claude with JSON output format to capture token usage
    raw = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True,
        text=True
    )

    if raw.returncode != 0:
        # Return a minimal error object matching expected interface
        raw.cost_usd = 0
        raw.input_tokens = 0
        raw.output_tokens = 0
        return raw

    # Parse the JSON response
    try:
        data = json.loads(raw.stdout)
    except json.JSONDecodeError:
        raw.cost_usd = 0
        raw.input_tokens = 0
        raw.output_tokens = 0
        return raw

    # Extract the actual text result
    result_text = data.get("result", "")

    # Extract cost and token data
    cost_usd = data.get("total_cost_usd", 0)
    duration_ms = data.get("duration_ms", 0)
    usage = data.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read_tokens = usage.get("cache_read_input_tokens", 0)
    cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)

    # Log this call
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": operation_name,
        "cost_usd": round(cost_usd, 6),
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "total_tokens": input_tokens + output_tokens
    }

    # Append to cost log file
    with open(COST_LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Update running summary
    update_summary(log_entry)

    # Build a result object that matches subprocess.run interface
    # so callers don't need to change how they use the return value
    class TrackedResult:
        def __init__(self):
            self.returncode = raw.returncode
            self.stdout = result_text  # actual text, not raw JSON
            self.stderr = raw.stderr
            self.cost_usd = cost_usd
            self.input_tokens = input_tokens
            self.output_tokens = output_tokens

    return TrackedResult()


# ─── SUMMARY ──────────────────────────────────────────────────────────────────

def update_summary(log_entry):
    """
    Maintains a running summary JSON with totals per operation type.
    This is what the report command reads to show you totals fast
    without parsing every log line.
    """
    if os.path.exists(COST_SUMMARY_FILE):
        with open(COST_SUMMARY_FILE, "r") as f:
            summary = json.load(f)
    else:
        summary = {
            "total_cost_usd": 0,
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "by_operation": {}
        }

    # Update totals
    summary["total_cost_usd"] = round(
        summary["total_cost_usd"] + log_entry["cost_usd"], 6)
    summary["total_calls"] += 1
    summary["total_input_tokens"] += log_entry["input_tokens"]
    summary["total_output_tokens"] += log_entry["output_tokens"]
    summary["last_updated"] = datetime.now().isoformat()

    # Update per-operation breakdown
    op = log_entry["operation"]
    if op not in summary["by_operation"]:
        summary["by_operation"][op] = {
            "calls": 0,
            "cost_usd": 0,
            "total_tokens": 0
        }

    summary["by_operation"][op]["calls"] += 1
    summary["by_operation"][op]["cost_usd"] = round(
        summary["by_operation"][op]["cost_usd"] + log_entry["cost_usd"], 6)
    summary["by_operation"][op]["total_tokens"] += log_entry["total_tokens"]

    with open(COST_SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)


# ─── REPORT ───────────────────────────────────────────────────────────────────

def print_cost_report():
    """
    Prints a formatted cost report to the terminal.
    Run this standalone: python tracker.py
    """
    if not os.path.exists(COST_SUMMARY_FILE):
        print("No cost data yet. Run some operations first.")
        return

    with open(COST_SUMMARY_FILE, "r") as f:
        summary = json.load(f)

    print("\n" + "="*55)
    print("COST REPORT — az104-brain")
    print("="*55)
    print(f"Total spent    : ${summary['total_cost_usd']:.4f} USD")
    print(f"Total calls    : {summary['total_calls']}")
    print(f"Input tokens   : {summary['total_input_tokens']:,}")
    print(f"Output tokens  : {summary['total_output_tokens']:,}")

    print(f"\nBY OPERATION:")
    # Sort by cost descending
    ops = sorted(
        summary["by_operation"].items(),
        key=lambda x: x[1]["cost_usd"],
        reverse=True
    )
    for op_name, stats in ops:
        avg_cost = stats["cost_usd"] / stats["calls"] if stats["calls"] else 0
        print(f"  {op_name:<30} "
              f"{stats['calls']:>4} calls  "
              f"${stats['cost_usd']:.4f} total  "
              f"(avg ${avg_cost:.4f})")

    print("="*55)

    # Recent calls from log
    if os.path.exists(COST_LOG_FILE):
        print("\nLAST 5 CALLS:")
        with open(COST_LOG_FILE, "r") as f:
            lines = f.readlines()
        recent = lines[-5:]
        for line in recent:
            entry = json.loads(line)
            ts = entry["timestamp"][:16].replace("T", " ")
            print(f"  {ts}  {entry['operation']:<28}  "
                  f"${entry['cost_usd']:.4f}  "
                  f"{entry['total_tokens']} tokens  "
                  f"{entry['duration_ms']}ms")

    print()


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print_cost_report()