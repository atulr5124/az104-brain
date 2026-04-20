from flask import Flask, jsonify, request, send_from_directory
import json
import os
import subprocess
import sys

app = Flask(__name__, static_folder="public")

# ─── CONFIG ───────────────────────────────────────────────────────────────────

KNOWLEDGE_DIR = "knowledge/topics"
INDEX_FILE = "knowledge/index.json"
COMPARISONS_FILE = "knowledge/comparisons.json"
PROGRESS_FILE = "knowledge/progress.json"

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def load_json(path):
    """Loads and returns a JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    """Saves data to a JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def run_claude(prompt):
    """
    Runs Claude in headless mode with a prompt.
    Returns the raw text output.
    This is the bridge between the web server and Claude Code.
    """
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise Exception(f"Claude error: {result.stderr}")
    return result.stdout.strip()


def parse_json_response(output):
    """
    Extracts JSON from Claude output.
    Claude sometimes wraps JSON in markdown — this handles that.
    """
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        start = output.find("{")
        end = output.rfind("}") + 1
        return json.loads(output[start:end])


# ─── STATIC FILES ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serves the main HTML file from the public/ folder."""
    return send_from_directory("public", "index.html")


# ─── TOPICS API ───────────────────────────────────────────────────────────────

@app.route("/api/topics", methods=["GET"])
def get_topics():
    """Returns all ingested topics from the index."""
    index = load_json(INDEX_FILE)
    return jsonify(index["topics"])


@app.route("/api/topics/<topic_id>", methods=["GET"])
def get_topic(topic_id):
    """Returns structured knowledge for a specific topic."""
    path = os.path.join(KNOWLEDGE_DIR, f"{topic_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Topic not found"}), 404
    return jsonify(load_json(path))


# ─── QUIZ API ─────────────────────────────────────────────────────────────────

@app.route("/api/quiz/question", methods=["POST"])
def get_question():
    """
    Generates a quiz question for a given topic.
    Expects JSON body: { "topic_id": "virtual_networks" }
    """
    data = request.json
    topic_id = data.get("topic_id")

    path = os.path.join(KNOWLEDGE_DIR, f"{topic_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Topic not found"}), 404

    topic = load_json(path)

    prompt = f"""
You are an AZ-104 exam question writer.

Based on this topic knowledge, generate ONE multiple choice question
that could appear on the real AZ-104 exam.

TOPIC KNOWLEDGE:
{json.dumps(topic, indent=2)}

Return ONLY this JSON structure, no explanation, no markdown, no backticks:
{{
  "question": "the full question text",
  "options": {{
    "A": "first option",
    "B": "second option",
    "C": "third option",
    "D": "fourth option"
  }},
  "correct_answer": "A",
  "explanation": "detailed explanation of why the correct answer is right",
  "why_others_wrong": {{
    "B": "why B is wrong",
    "C": "why C is wrong",
    "D": "why D is wrong"
  }},
  "topic": "{topic['topic']}",
  "difficulty": "easy|medium|hard"
}}
"""

    try:
        output = run_claude(prompt)
        question = parse_json_response(output)
        return jsonify(question)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/quiz/answer", methods=["POST"])
def submit_answer():
    """
    Evaluates a submitted answer and records progress.
    Expects JSON body: { "topic_id", "question", "user_answer",
                         "correct_answer", "explanation",
                         "why_others_wrong", "difficulty" }
    """
    data = request.json
    topic_id = data["topic_id"]
    user_answer = data["user_answer"].strip().upper()
    correct_answer = data["correct_answer"].strip().upper()
    correct = user_answer == correct_answer

    # Record to progress.json
    progress = load_json(PROGRESS_FILE)

    entry = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "topic_id": topic_id,
        "topic_name": data.get("topic", topic_id),
        "question": data["question"],
        "correct_answer": correct_answer,
        "user_answer": user_answer,
        "correct": correct,
        "difficulty": data.get("difficulty", "medium")
    }

    progress["sessions"].append(entry)
    progress["total_questions_answered"] += 1
    if correct:
        progress["total_correct"] += 1

    # Recalculate weak areas
    topic_stats = {}
    for session in progress["sessions"]:
        tid = session["topic_id"]
        if tid not in topic_stats:
            topic_stats[tid] = {
                "correct": 0,
                "total": 0,
                "name": session["topic_name"]
            }
        topic_stats[tid]["total"] += 1
        if session["correct"]:
            topic_stats[tid]["correct"] += 1

    weak_areas = []
    for tid, stats in topic_stats.items():
        accuracy = stats["correct"] / stats["total"]
        if accuracy < 0.6:
            weak_areas.append({
                "topic_id": tid,
                "topic_name": stats["name"],
                "accuracy": round(accuracy * 100, 1),
                "questions_answered": stats["total"]
            })

    progress["weak_areas"] = weak_areas
    save_json(PROGRESS_FILE, progress)

    return jsonify({
        "correct": correct,
        "correct_answer": correct_answer,
        "explanation": data["explanation"],
        "why_others_wrong": data.get("why_others_wrong", {})
    })


# ─── COMPARE API ──────────────────────────────────────────────────────────────

@app.route("/api/compare", methods=["POST"])
def compare_topics():
    """
    Generates or retrieves a comparison between two topics.
    Checks comparisons.json first — only calls Claude if not cached.
    Expects JSON body: { "topic_a": "network_security_groups",
                         "topic_b": "azure_firewall" }
    """
    data = request.json
    topic_id_a = data["topic_a"]
    topic_id_b = data["topic_b"]

    # Check cache first
    comparisons = load_json(COMPARISONS_FILE)
    pair_key = f"{topic_id_a}||{topic_id_b}"
    reverse_key = f"{topic_id_b}||{topic_id_a}"

    existing = next(
        (c for c in comparisons["comparisons"]
         if f"{c['topic_a']}||{c['topic_b']}" in [pair_key, reverse_key]),
        None
    )

    if existing:
        return jsonify(existing)

    # Not cached — generate via Claude
    topic_a = load_json(os.path.join(KNOWLEDGE_DIR, f"{topic_id_a}.json"))
    topic_b = load_json(os.path.join(KNOWLEDGE_DIR, f"{topic_id_b}.json"))

    prompt = f"""
You are an AZ-104 exam preparation expert.

Compare these two Azure concepts for an exam candidate who confuses them.
Return ONLY a JSON object, no explanation, no markdown, no backticks:

TOPIC A: {json.dumps(topic_a, indent=2)}
TOPIC B: {json.dumps(topic_b, indent=2)}

{{
  "topic_a": "{topic_a['topic']}",
  "topic_b": "{topic_b['topic']}",
  "one_line_distinction": "single sentence capturing the core difference",
  "analogy": "real-world analogy that makes the distinction memorable",
  "key_differences": [
    {{
      "dimension": "aspect being compared",
      "topic_a": "how topic A behaves",
      "topic_b": "how topic B behaves"
    }}
  ],
  "when_to_use_a": "clear rule for when you choose topic A",
  "when_to_use_b": "clear rule for when you choose topic B",
  "exam_traps": ["how the exam tricks candidates on this pair"],
  "memory_tip": "short memorable trick to keep them straight"
}}
"""

    try:
        output = run_claude(prompt)
        comparison = parse_json_response(output)

        # Cache it
        comparison["generated_at"] = __import__(
            "datetime").datetime.now().isoformat()
        comparisons["comparisons"].append(comparison)
        save_json(COMPARISONS_FILE, comparisons)

        return jsonify(comparison)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── PROGRESS API ─────────────────────────────────────────────────────────────

@app.route("/api/progress", methods=["GET"])
def get_progress():
    """Returns the full progress object including weak areas."""
    return jsonify(load_json(PROGRESS_FILE))


# ─── CRAM SHEET API ───────────────────────────────────────────────────────────

@app.route("/api/cramsheet", methods=["POST"])
def generate_cramsheet():
    """
    Generates a personalised cram sheet based on weak areas and exam date.
    If no weak areas exist yet, generates a general priority cram sheet.
    """
    progress = load_json(PROGRESS_FILE)
    index = load_json(INDEX_FILE)

    weak_areas = progress.get("weak_areas", [])
    all_topics = index["topics"]

    prompt = f"""
You are an AZ-104 exam coach.

The exam is in the first week of May 2025. Today is approximately
{__import__("datetime").datetime.now().strftime("%B %d, %Y")}.

WEAK AREAS (topics below 60% quiz accuracy):
{json.dumps(weak_areas, indent=2)}

ALL INGESTED TOPICS:
{json.dumps([t["name"] for t in all_topics], indent=2)}

AZ-104 OFFICIAL DOMAIN WEIGHTINGS:
- Manage Azure identities and governance: 20-25%
- Implement and manage storage: 15-20%
- Deploy and manage Azure compute resources: 20-25%
- Implement and manage virtual networking: 15-20%
- Monitor and maintain Azure resources: 10-15%

Generate a personalised cram sheet. Return ONLY this JSON, no markdown:
{{
  "exam_date": "First week of May 2025",
  "days_remaining": "calculate from today",
  "priority_topics": [
    {{
      "topic": "topic name",
      "reason": "why this is priority",
      "key_points": ["point 1", "point 2", "point 3"],
      "time_suggested": "e.g. 30 minutes"
    }}
  ],
  "study_schedule": [
    {{
      "day": "Day 1",
      "focus": "what to study",
      "activities": ["activity 1", "activity 2"]
    }}
  ],
  "last_48_hours_tips": [
    "what to do in the final 48 hours before exam"
  ]
}}
"""

    try:
        output = run_claude(prompt)
        cramsheet = parse_json_response(output)
        return jsonify(cramsheet)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── START SERVER ─────────────────────────────────────────────────────────────

@app.route("/api/exams", methods=["GET"])
def get_exams():
    """Returns list of all past mock exam results."""
    exams_dir = "knowledge/exams"
    if not os.path.exists(exams_dir):
        return jsonify([])

    exams = []
    for filename in sorted(os.listdir(exams_dir), reverse=True):
        if filename.endswith(".json"):
            path = os.path.join(exams_dir, filename)
            with open(path, "r") as f:
                exam = json.load(f)
            # Return summary only — not all 50 questions
            exams.append({
                "filename": filename,
                "exam_date": exam["exam_date"],
                "score": exam["score"],
                "passed": exam["passed"],
                "correct": exam["correct"],
                "total_questions": exam["total_questions"],
                "time_taken": exam["time_taken"],
                "domain_scores": {
                    k: {"name": v["name"], "accuracy": v["accuracy"]}
                    for k, v in exam["domain_scores"].items()
                }
            })

    return jsonify(exams)

if __name__ == "__main__":
    print("az104-brain server starting...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)