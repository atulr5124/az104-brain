import os
import sys
import time
import subprocess
import json
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ─── CONFIG ───────────────────────────────────────────────────────────────────

INPUTS_DIR = "inputs"
KNOWLEDGE_DIR = "knowledge/topics"
INDEX_FILE = "knowledge/index.json"
WATCH_LOG = ".claude/watch.log"

# File extensions we can process
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def log(message):
    """
    Logs a timestamped message to both terminal and watch.log.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(WATCH_LOG, "a") as f:
        f.write(line + "\n")


def is_already_ingested(filepath):
    """
    Checks if a file has already been ingested by looking at the index.
    """
    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    filename = os.path.basename(filepath)
    topic_id = os.path.splitext(filename)[0].lower().replace(" ", "_").replace("-", "_")
    return any(t["id"] == topic_id for t in index["topics"])

def extract_topic_name(filepath):
    """
    Derives a human-readable topic name from the filename.
    'azure_load_balancer.md' -> 'Azure Load Balancer'
    """
    filename = os.path.basename(filepath)
    name = os.path.splitext(filename)[0]
    # Replace underscores and hyphens with spaces, title case
    return name.replace("_", " ").replace("-", " ").title()


def ingest_file(filepath):
    """
    Ingests a file from inputs/ into the knowledge base.

    For .md and .txt files: reads content directly and sends to Claude
    for structuring — no URL needed, Claude reads the raw text.

    This is different from URL-based ingest — instead of fetching
    from MS Learn, we use the file content directly as the source.
    """
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    topic_name = extract_topic_name(filepath)
    safe_name = topic_name.lower().replace(" ", "_")

    log(f"New file detected: {filename}")
    log(f"Topic name derived: {topic_name}")

    if ext not in SUPPORTED_EXTENSIONS:
        log(f"Skipping unsupported file type: {ext}")
        return

    if is_already_ingested(filepath):
        log(f"Already ingested: {topic_name} — skipping")
        return

    # Read file content
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        log(f"Could not read file (encoding issue): {filename}")
        return

    if len(content.strip()) < 100:
        log(f"File too short to ingest meaningfully: {filename}")
        return

    log(f"Ingesting: {topic_name}...")

    # Send content directly to Claude for structuring
    prompt = f"""
You are an AZ-104 exam preparation assistant.

Below is study material about the topic: {topic_name}

Extract and return ONLY a JSON object with this exact structure:
{{
  "topic": "{topic_name}",
  "summary": "2-3 sentence plain English summary",
  "key_concepts": [
    {{"concept": "name", "explanation": "plain English explanation"}}
  ],
  "exam_focus_points": [
    "specific thing likely to be tested in AZ-104 exam"
  ],
  "similar_concepts": [
    "name of another Azure concept commonly confused with this one"
  ],
  "common_mistakes": [
    "common misconception candidates make about this topic"
  ]
}}

Return ONLY the JSON. No explanation, no markdown, no backticks.

STUDY MATERIAL:
{content[:8000]}
"""

    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        log(f"Claude error for {topic_name}: {result.stderr[:100]}")
        return

    output = result.stdout.strip()

    # Parse JSON response
    try:
        knowledge = json.loads(output)
    except json.JSONDecodeError:
        start = output.find("{")
        end = output.rfind("}") + 1
        try:
            knowledge = json.loads(output[start:end])
        except json.JSONDecodeError:
            log(f"Failed to parse Claude response for {topic_name}")
            return

    # Save raw content
    raw_path = os.path.join(KNOWLEDGE_DIR, f"{safe_name}.txt")
    with open(raw_path, "w") as f:
        f.write(content)

    # Save structured knowledge
    json_path = os.path.join(KNOWLEDGE_DIR, f"{safe_name}.json")
    with open(json_path, "w") as f:
        json.dump(knowledge, f, indent=2)

    # Update index
    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    index["topics"].append({
        "id": safe_name,
        "name": topic_name,
        "url": f"inputs/{filename}",
        "ingested_at": datetime.now().isoformat(),
        "source": "file_watch"
    })
    index["last_updated"] = datetime.now().isoformat()

    with open(INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)

    log(f"Successfully ingested: {topic_name}")


# ─── FILE SYSTEM HANDLER ──────────────────────────────────────────────────────

class InputsFolderHandler(FileSystemEventHandler):
    """
    Watchdog event handler — fires when files are created or modified in inputs/.
    """

    def process(self, filepath):
        """
        Central processing function called by all event types.
        Waits 2 seconds to ensure file is fully written before reading.
        """
        if not os.path.isfile(filepath):
            return

        # Wait for file to be fully written
        time.sleep(2)

        # Check size again after waiting
        if os.path.getsize(filepath) < 100:
            log(f"File too small after wait: {filepath}")
            return

        ingest_file(filepath)

    def on_created(self, event):
        if event.is_directory:
            return
        self.process(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self.process(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if event.dest_path.startswith(os.path.abspath(INPUTS_DIR)):
            self.process(event.dest_path)

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    """
    Starts the file watcher. Runs indefinitely until Ctrl+C.
    Uses watchdog's Observer which runs in a background thread —
    the main thread just sleeps in a loop keeping the process alive.
    """
    # Ensure inputs directory exists
    os.makedirs(INPUTS_DIR, exist_ok=True)
    os.makedirs(".claude", exist_ok=True)

    log(f"Watching {INPUTS_DIR}/ for new files...")
    log(f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}")
    log("Drop any study material into inputs/ to auto-ingest it.")
    log("Press Ctrl+C to stop.\n")

    # Set up the observer
    event_handler = InputsFolderHandler()
    observer = Observer()

    # Schedule watching the inputs directory recursively
    observer.schedule(event_handler, INPUTS_DIR, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        log("Watcher stopped.")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()