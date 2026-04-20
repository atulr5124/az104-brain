import requests
from bs4 import BeautifulSoup
import json
import os
import sys
import subprocess
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────

KNOWLEDGE_DIR = "knowledge/topics"
INDEX_FILE = "knowledge/index.json"

# ─── FETCH ────────────────────────────────────────────────────────────────────

def fetch_ms_learn(url):
    """
    Fetches a Microsoft Learn page and returns clean plain text.
    BeautifulSoup parses the HTML and we extract only the main article body,
    stripping away navigation, headers, footers, and ads.
    """
    print(f"Fetching: {url}")

    headers = {
        # Identifies us as a browser — some sites block requests without this
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    }

    response = requests.get(url, headers=headers, timeout=15)

    if response.status_code != 200:
        print(f"Failed to fetch page. Status code: {response.status_code}")
        sys.exit(1)

    soup = BeautifulSoup(response.text, "html.parser")

    # MS Learn puts the main content inside <main> or a div with id="main"
    main_content = soup.find("main") or soup.find(id="main")

    if not main_content:
        # Fallback: grab the whole body
        main_content = soup.find("body")

    # Remove script and style tags — we only want readable text
    for tag in main_content(["script", "style", "nav", "footer"]):
        tag.decompose()

    # Get clean text, collapse whitespace
    text = main_content.get_text(separator="\n", strip=True)

    # Remove excessive blank lines
    lines = [line for line in text.splitlines() if line.strip()]
    clean_text = "\n".join(lines)

    return clean_text


# ─── STRUCTURE ────────────────────────────────────────────────────────────────

def extract_knowledge(topic_name, raw_text):
    """
    Sends raw text to Claude via headless mode.
    Claude extracts structured knowledge and returns JSON.
    We save this as the permanent knowledge entry for the topic.
    """
    print(f"Extracting structured knowledge for: {topic_name}")

    prompt = f"""
You are an AZ-104 exam preparation assistant.

Below is raw documentation text about the topic: {topic_name}

Extract and return ONLY a JSON object with this exact structure:
{{
  "topic": "{topic_name}",
  "summary": "2-3 sentence plain English summary of what this topic is",
  "key_concepts": [
    {{"concept": "name", "explanation": "plain English explanation"}}
  ],
  "exam_focus_points": [
    "specific thing likely to be tested in AZ-104 exam"
  ],
  "similar_concepts": [
    "name of another Azure concept that is commonly confused with this one"
  ],
  "common_mistakes": [
    "common misconception or mistake candidates make about this topic"
  ]
}}

Return ONLY the JSON. No explanation, no markdown, no backticks.

DOCUMENTATION TEXT:
{raw_text[:8000]}
"""
    # Call Claude in headless mode with -p flag
    # --output-format json tells Claude Code to return clean output
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Claude error: {result.stderr}")
        sys.exit(1)

    output = result.stdout.strip()

    # Parse the JSON Claude returned
    try:
        knowledge = json.loads(output)
    except json.JSONDecodeError:
        # Sometimes Claude adds a tiny bit of wrapper text — try to extract JSON
        start = output.find("{")
        end = output.rfind("}") + 1
        knowledge = json.loads(output[start:end])

    return knowledge


# ─── SAVE ─────────────────────────────────────────────────────────────────────

def save_topic(topic_name, raw_text, structured_knowledge):
    """
    Saves both the raw text and structured knowledge for a topic.
    Raw text is kept so we can re-process it later if needed.
    Structured JSON is what the quiz engine and compare engine use.
    """
    # Sanitise topic name for use as filename
    safe_name = topic_name.lower().replace(" ", "_")

    # Save raw text
    raw_path = os.path.join(KNOWLEDGE_DIR, f"{safe_name}.txt")
    with open(raw_path, "w") as f:
        f.write(raw_text)

    # Save structured knowledge
    json_path = os.path.join(KNOWLEDGE_DIR, f"{safe_name}.json")
    with open(json_path, "w") as f:
        json.dump(structured_knowledge, f, indent=2)

    print(f"Saved: {json_path}")
    return safe_name


# ─── INDEX ────────────────────────────────────────────────────────────────────

def update_index(topic_name, safe_name, url):
    """
    Updates the master index.json with the newly ingested topic.
    The index is what the UI uses to know what topics are available.
    """
    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    # Check if topic already exists in index — update rather than duplicate
    existing = next((t for t in index["topics"] if t["id"] == safe_name), None)

    entry = {
        "id": safe_name,
        "name": topic_name,
        "url": url,
        "ingested_at": datetime.now().isoformat()
    }

    if existing:
        index["topics"] = [entry if t["id"] == safe_name else t
                           for t in index["topics"]]
        print(f"Updated existing index entry for: {topic_name}")
    else:
        index["topics"].append(entry)
        print(f"Added new index entry for: {topic_name}")

    index["last_updated"] = datetime.now().isoformat()

    with open(INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    """
    Entry point. Expects two arguments: topic name and MS Learn URL.
    Example: python ingest.py "Virtual Networks" https://learn.microsoft.com/...
    """
    if len(sys.argv) < 3:
        print("Usage: python ingest.py <topic_name> <ms_learn_url>")
        print('Example: python ingest.py "Virtual Networks" https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview')
        sys.exit(1)

    topic_name = sys.argv[1]
    url = sys.argv[2]

    # Step 1: Fetch
    raw_text = fetch_ms_learn(url)
    print(f"Fetched {len(raw_text)} characters")

    # Step 2: Structure via Claude
    structured = extract_knowledge(topic_name, raw_text)

    # Step 3: Save
    safe_name = save_topic(topic_name, raw_text, structured)

    # Step 4: Update index
    update_index(topic_name, safe_name, url)

    print(f"\nDone. Topic '{topic_name}' ingested successfully.")


if __name__ == "__main__":
    main()