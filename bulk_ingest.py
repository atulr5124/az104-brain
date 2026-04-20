import json
import os
import sys
import subprocess
import tempfile
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── CONFIG ───────────────────────────────────────────────────────────────────

TOPICS_FILE = "topics.json"
KNOWLEDGE_DIR = "knowledge/topics"
INDEX_FILE = "knowledge/index.json"

# Maximum parallel workers — Claude Pro can handle this comfortably
MAX_WORKERS = 5

# ─── LOAD ─────────────────────────────────────────────────────────────────────

def load_topics_list():
    """
    Loads the master topics.json list.
    Filters out topics that are already ingested to avoid re-processing.
    """
    with open(TOPICS_FILE, "r") as f:
        data = json.load(f)

    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    already_ingested = {t["id"] for t in index["topics"]}

    # Filter to only topics not yet ingested
    pending = []
    for topic in data["topics"]:
        safe_name = topic["name"].lower().replace(" ", "_")
        if safe_name not in already_ingested:
            pending.append(topic)
        else:
            print(f"Skipping (already ingested): {topic['name']}")

    return pending


# ─── SINGLE TOPIC INGEST ──────────────────────────────────────────────────────

def ingest_single(topic):
    """
    Ingests a single topic by calling ingest.py as a subprocess.
    This is what each parallel worker runs — completely independent.
    Returns a result dict so we can track success/failure per topic.

    Why subprocess instead of importing ingest.py directly:
    Each worker gets its own isolated Python process. No shared state,
    no race conditions on file writes. Like hiring separate contractors
    rather than asking one person to multitask.
    """
    name = topic["name"]
    url = topic["url"]

    print(f"[START] {name}")

    result = subprocess.run(
        ["python", "ingest.py", name, url],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"[DONE]  {name}")
        return {"topic": name, "success": True, "output": result.stdout}
    else:
        print(f"[FAIL]  {name}: {result.stderr[:100]}")
        return {"topic": name, "success": False, "error": result.stderr}


# ─── PARALLEL ORCHESTRATOR ────────────────────────────────────────────────────

def run_parallel_ingest(topics):
    """
    Runs multiple ingest_single calls in parallel using ThreadPoolExecutor.

    ThreadPoolExecutor is Python's built-in thread pool.
    Think of it as a manager who hands out tasks to a fixed number of workers.
    MAX_WORKERS=5 means 5 topics process simultaneously.

    as_completed() yields results as each worker finishes —
    so we see output in real time, not all at the end.
    """
    results = {"success": [], "failed": []}

    print(f"\nIngesting {len(topics)} topics with {MAX_WORKERS} parallel workers...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all jobs to the pool at once
        future_to_topic = {
            executor.submit(ingest_single, topic): topic
            for topic in topics
        }

        # Process results as they complete (not in submission order)
        for future in as_completed(future_to_topic):
            result = future.result()
            if result["success"]:
                results["success"].append(result["topic"])
            else:
                results["failed"].append(result)

    return results


# ─── REPORT ───────────────────────────────────────────────────────────────────

def print_report(results, start_time):
    """
    Prints a summary of what was ingested, what failed, and how long it took.
    """
    elapsed = round((datetime.now() - start_time).total_seconds(), 1)

    print("\n" + "="*60)
    print("BULK INGEST COMPLETE")
    print("="*60)
    print(f"Time taken:  {elapsed} seconds")
    print(f"Successful:  {len(results['success'])}")
    print(f"Failed:      {len(results['failed'])}")

    if results["success"]:
        print("\nIngested:")
        for t in results["success"]:
            print(f"  ✓ {t}")

    if results["failed"]:
        print("\nFailed:")
        for f in results["failed"]:
            print(f"  ✗ {f['topic']}: {f['error'][:80]}")

    print("="*60)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    """
    Entry point. Loads pending topics and runs parallel ingest.
    Optional argument: path to a different topics file.
    Usage: python bulk_ingest.py
           python bulk_ingest.py custom_topics.json
    """
    global TOPICS_FILE
    if len(sys.argv) > 1:
        TOPICS_FILE = sys.argv[1]

    if not os.path.exists(TOPICS_FILE):
        print(f"Topics file not found: {TOPICS_FILE}")
        sys.exit(1)

    # Load pending topics
    pending = load_topics_list()

    if not pending:
        print("All topics already ingested. Nothing to do.")
        sys.exit(0)

    print(f"Found {len(pending)} topics to ingest.")

    start_time = datetime.now()

    # Run parallel ingest
    results = run_parallel_ingest(pending)

    # Print summary
    print_report(results, start_time)


if __name__ == "__main__":
    main()