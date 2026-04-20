import json
import os
import sys
import subprocess
from datetime import datetime
from tracker import claude_call

# ─── CONFIG ───────────────────────────────────────────────────────────────────

KNOWLEDGE_DIR = "knowledge/topics"
PROGRESS_FILE = "knowledge/progress.json"

# ─── LOAD ─────────────────────────────────────────────────────────────────────

def load_topic(topic_id):
    """
    Loads structured knowledge for a topic.
    Returns None if topic hasn't been ingested yet.
    """
    path = os.path.join(KNOWLEDGE_DIR, f"{topic_id}.json")

    if not os.path.exists(path):
        return None

    with open(path, "r") as f:
        return json.load(f)


def load_progress():
    """
    Loads the current progress file.
    This is our persistent record of every question answered.
    """
    with open(PROGRESS_FILE, "r") as f:
        return json.load(f)


def save_progress(progress):
    """
    Saves updated progress back to progress.json.
    Called after every question answered.
    """
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ─── GENERATE QUESTION ────────────────────────────────────────────────────────

def generate_question(topic):
    """
    Asks Claude to generate one AZ-104 style multiple choice question
    based on the topic knowledge. Returns a structured JSON question object.
    """
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
    "A": "why this option is wrong (skip if this is correct answer)",
    "B": "why this option is wrong (skip if this is correct answer)",
    "C": "why this option is wrong (skip if this is correct answer)",
    "D": "why this option is wrong (skip if this is correct answer)"
  }},
  "topic": "{topic['topic']}",
  "difficulty": "easy|medium|hard"
}}
"""

    result = claude_call(prompt, operation_name="generate_question")

    if result.returncode != 0:
        print(f"Claude error: {result.stderr}")
        sys.exit(1)

    output = result.stdout.strip()

    try:
        question = json.loads(output)
    except json.JSONDecodeError:
        start = output.find("{")
        end = output.rfind("}") + 1
        question = json.loads(output[start:end])

    return question


# ─── EVALUATE ANSWER ──────────────────────────────────────────────────────────

def evaluate_answer(question, user_answer):
    """
    Checks if user answer is correct.
    Returns a result dict with correct flag, explanation, and study tip.
    No Claude call needed here — the question already has all the info.
    """
    user_answer = user_answer.strip().upper()
    correct = user_answer == question["correct_answer"]

    result = {
        "correct": correct,
        "user_answer": user_answer,
        "correct_answer": question["correct_answer"],
        "explanation": question["explanation"],
        "why_others_wrong": question.get("why_others_wrong", {})
    }

    return result


# ─── RECORD PROGRESS ──────────────────────────────────────────────────────────

def record_result(topic_id, question, result):
    """
    Saves the question result to progress.json.
    Tracks topic-level accuracy so we can identify weak areas.
    """
    progress = load_progress()

    # Build a session entry for this question
    entry = {
        "timestamp": datetime.now().isoformat(),
        "topic_id": topic_id,
        "topic_name": question["topic"],
        "question": question["question"],
        "correct_answer": question["correct_answer"],
        "user_answer": result["user_answer"],
        "correct": result["correct"],
        "difficulty": question.get("difficulty", "medium")
    }

    progress["sessions"].append(entry)
    progress["total_questions_answered"] += 1

    if result["correct"]:
        progress["total_correct"] += 1

    # Recalculate weak areas — topics where accuracy < 60%
    topic_stats = {}
    for session in progress["sessions"]:
        tid = session["topic_id"]
        if tid not in topic_stats:
            topic_stats[tid] = {"correct": 0, "total": 0, "name": session["topic_name"]}
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
    save_progress(progress)

    return entry


# ─── DISPLAY ──────────────────────────────────────────────────────────────────

def display_question(question):
    """
    Prints the question and options to terminal in a readable format.
    """
    print("\n" + "="*60)
    print(f"TOPIC: {question['topic']} | DIFFICULTY: {question.get('difficulty','medium').upper()}")
    print("="*60)
    print(f"\n{question['question']}\n")
    for key, value in question["options"].items():
        print(f"  {key}) {value}")
    print()


def display_result(question, result):
    """
    Prints the answer evaluation — correct/wrong, explanation, why others wrong.
    """
    print("="*60)
    if result["correct"]:
        print("✓ CORRECT")
    else:
        print(f"✗ WRONG — Correct answer: {result['correct_answer']}")

    print(f"\nEXPLANATION:\n{result['explanation']}")

    if not result["correct"] and result["why_others_wrong"]:
        wrong_key = result["user_answer"]
        why = result["why_others_wrong"].get(wrong_key)
        if why:
            print(f"\nWHY YOUR ANSWER ({wrong_key}) WAS WRONG:\n{why}")

    print("="*60 + "\n")

def update_claude_memory(progress):
    """
    Updates ~/.claude/CLAUDE.md with current weak areas after every session.
    This means Claude knows your weak areas in any project, not just this one.

    We read the existing memory file, find and replace the az104 weak areas
    section, and write it back. If the section doesn't exist yet, we append it.
    """
    memory_file = os.path.expanduser("~/.claude/CLAUDE.md")
    weak_areas = progress.get("weak_areas", [])

    # Build the memory block we want to maintain
    if weak_areas:
        weak_list = "\n".join(
            f"- {w['topic_name']}: {w['accuracy']}% accuracy"
            for w in weak_areas
        )
        memory_block = f"""## AZ-104 Study — Current Weak Areas
Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
{weak_list}
"""
    else:
        memory_block = f"""## AZ-104 Study — Current Weak Areas
Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
No weak areas identified yet. Keep quizzing.
"""

    # Read existing memory file
    if os.path.exists(memory_file):
        with open(memory_file, "r") as f:
            existing = f.read()
    else:
        existing = ""

    # Replace existing weak areas block if present, otherwise append
    marker = "## AZ-104 Study — Current Weak Areas"
    if marker in existing:
        # Find and replace the entire block
        start = existing.find(marker)
        # Find the next ## heading or end of file
        next_section = existing.find("\n## ", start + 1)
        if next_section == -1:
            # No next section — replace to end of file
            updated = existing[:start] + memory_block
        else:
            updated = existing[:start] + memory_block + existing[next_section:]
    else:
        # Append to existing memory
        updated = existing.rstrip() + "\n\n" + memory_block

    with open(memory_file, "w") as f:
        f.write(updated)

    print(f"\nClaude memory updated with {len(weak_areas)} weak area(s).")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    """
    Entry point. Runs an interactive quiz session for a given topic.
    Keeps asking questions until user types 'q' to quit.
    Usage: python quiz.py <topic_id>
    Example: python quiz.py virtual_networks
    """
    if len(sys.argv) < 2:
        available = [f.replace(".json", "") for f in os.listdir(KNOWLEDGE_DIR)
                     if f.endswith(".json")]
        print("Usage: python quiz.py <topic_id>")
        print(f"\nAvailable topics: {', '.join(available)}")
        sys.exit(1)

    topic_id = sys.argv[1]
    topic = load_topic(topic_id)

    if not topic:
        print(f"Topic '{topic_id}' not found. Run ingest.sh first.")
        sys.exit(1)

    print(f"\nStarting quiz: {topic['topic']}")
    print("Type A, B, C, or D to answer. Type 'q' to quit.\n")

    questions_asked = 0
    questions_correct = 0

    while True:
        # Generate a fresh question each round
        print("Generating question...")
        question = generate_question(topic)

        # Display it
        display_question(question)

        # Get user answer
        answer = input("Your answer: ").strip()

        if answer.lower() == "q":
            break

        if answer.upper() not in ["A", "B", "C", "D"]:
            print("Please enter A, B, C, or D.")
            continue

        # Evaluate
        result = evaluate_answer(question, answer)

        # Display result
        display_result(question, result)

        # Record to progress.json
        record_result(topic_id, question, result)

        questions_asked += 1
        if result["correct"]:
            questions_correct += 1

        # Show running score
        accuracy = round((questions_correct / questions_asked) * 100, 1)
        print(f"Session score: {questions_correct}/{questions_asked} ({accuracy}%)\n")

        input("Press Enter for next question...")

    # Session summary
    if questions_asked > 0:
        print(f"\nSession complete: {questions_correct}/{questions_asked} correct")
        progress = load_progress()
        if progress["weak_areas"]:
            print("\nCurrent weak areas:")
            for area in progress["weak_areas"]:
                print(f"  - {area['topic_name']}: {area['accuracy']}% accuracy")

    # Update global Claude memory with current weak areas
    update_claude_memory(progress)

if __name__ == "__main__":
    main()