import json
import os
import sys
import subprocess
from datetime import datetime
from tracker import claude_call

# ─── CONFIG ───────────────────────────────────────────────────────────────────

KNOWLEDGE_DIR = "knowledge/topics"
COMPARISONS_FILE = "knowledge/comparisons.json"

# ─── LOAD ─────────────────────────────────────────────────────────────────────

def load_topic(topic_id):
    """
    Loads structured knowledge for a topic from its JSON file.
    topic_id is the sanitised filename — e.g. "virtual_networks"
    """
    path = os.path.join(KNOWLEDGE_DIR, f"{topic_id}.json")

    if not os.path.exists(path):
        print(f"Topic not found: {topic_id}")
        print("Run ingest.sh first for this topic.")
        sys.exit(1)

    with open(path, "r") as f:
        return json.load(f)


def list_available_topics():
    """
    Lists all ingested topic IDs so the user knows what's available.
    """
    files = [f.replace(".json", "") for f in os.listdir(KNOWLEDGE_DIR)
             if f.endswith(".json")]
    return files


# ─── COMPARE ──────────────────────────────────────────────────────────────────

def generate_comparison(topic_a, topic_b):
    """
    Sends both topics to Claude and asks it to produce a structured
    comparison focused on AZ-104 exam distinctions.
    Returns a JSON comparison object.
    """
    print(f"Comparing: {topic_a['topic']} vs {topic_b['topic']}")

    prompt = f"""
You are an AZ-104 exam preparation expert.

Compare these two Azure concepts and return ONLY a JSON object.
Focus on what confuses candidates most and how the exam tests the difference.

TOPIC A:
{json.dumps(topic_a, indent=2)}

TOPIC B:
{json.dumps(topic_b, indent=2)}

Return ONLY this JSON structure, no explanation, no markdown, no backticks:
{{
  "topic_a": "{topic_a['topic']}",
  "topic_b": "{topic_b['topic']}",
  "one_line_distinction": "single sentence capturing the core difference",
  "analogy": "a real-world analogy that makes the distinction memorable",
  "key_differences": [
    {{
      "dimension": "what aspect is being compared",
      "topic_a": "how topic A behaves on this dimension",
      "topic_b": "how topic B behaves on this dimension"
    }}
  ],
  "when_to_use_a": "clear rule for when you would choose topic A",
  "when_to_use_b": "clear rule for when you would choose topic B",
  "exam_traps": [
    "specific way the exam tricks candidates into confusing these two"
  ],
  "memory_tip": "a short memorable trick to keep them straight"
}}
"""

    result = claude_call(prompt, operation_name="generate_comparison")

    if result.returncode != 0:
        print(f"Claude error: {result.stderr}")
        sys.exit(1)

    output = result.stdout.strip()

    try:
        comparison = json.loads(output)
    except json.JSONDecodeError:
        start = output.find("{")
        end = output.rfind("}") + 1
        comparison = json.loads(output[start:end])

    return comparison


# ─── SAVE ─────────────────────────────────────────────────────────────────────

def save_comparison(comparison):
    """
    Saves the comparison to comparisons.json.
    Uses a composite key (topic_a + topic_b) to avoid duplicates.
    """
    with open(COMPARISONS_FILE, "r") as f:
        data = json.load(f)

    # Build a unique key for this pair
    pair_key = f"{comparison['topic_a']}||{comparison['topic_b']}"

    # Check if this comparison already exists — update if so
    existing = next((c for c in data["comparisons"]
                     if f"{c['topic_a']}||{c['topic_b']}" == pair_key), None)

    entry = {
        **comparison,
        "generated_at": datetime.now().isoformat()
    }

    if existing:
        data["comparisons"] = [entry if f"{c['topic_a']}||{c['topic_b']}"
                                == pair_key else c
                                for c in data["comparisons"]]
        print("Updated existing comparison.")
    else:
        data["comparisons"].append(entry)
        print("Saved new comparison.")

    with open(COMPARISONS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ─── DISPLAY ──────────────────────────────────────────────────────────────────

def display_comparison(comparison):
    """
    Prints the comparison in a readable format to the terminal.
    """
    print("\n" + "="*60)
    print(f"{comparison['topic_a']} vs {comparison['topic_b']}")
    print("="*60)

    print(f"\nCORE DISTINCTION:\n{comparison['one_line_distinction']}")
    print(f"\nANALOGY:\n{comparison['analogy']}")

    print("\nKEY DIFFERENCES:")
    for diff in comparison["key_differences"]:
        print(f"\n  {diff['dimension'].upper()}")
        print(f"  {comparison['topic_a']}: {diff['topic_a']}")
        print(f"  {comparison['topic_b']}: {diff['topic_b']}")

    print(f"\nUSE {comparison['topic_a'].upper()} WHEN:\n{comparison['when_to_use_a']}")
    print(f"\nUSE {comparison['topic_b'].upper()} WHEN:\n{comparison['when_to_use_b']}")

    print("\nEXAM TRAPS:")
    for trap in comparison["exam_traps"]:
        print(f"  - {trap}")

    print(f"\nMEMORY TIP:\n{comparison['memory_tip']}")
    print("="*60 + "\n")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    """
    Entry point. Expects two topic IDs as arguments.
    Example: python compare.py network_security_groups azure_firewall
    """
    if len(sys.argv) < 3:
        available = list_available_topics()
        print("Usage: python compare.py <topic_id_a> <topic_id_b>")
        print(f"\nAvailable topics: {', '.join(available)}")
        sys.exit(1)

    topic_id_a = sys.argv[1]
    topic_id_b = sys.argv[2]

    # Load both topics from knowledge base
    topic_a = load_topic(topic_id_a)
    topic_b = load_topic(topic_id_b)

    # Generate comparison via Claude
    comparison = generate_comparison(topic_a, topic_b)

    # Save to comparisons.json
    save_comparison(comparison)

    # Print to terminal
    display_comparison(comparison)


if __name__ == "__main__":
    main()