import json
import os
import sys
import subprocess
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tracker import claude_call

# ─── CONFIG ───────────────────────────────────────────────────────────────────

KNOWLEDGE_DIR = "knowledge/topics"
INDEX_FILE = "knowledge/index.json"
PROGRESS_FILE = "knowledge/progress.json"
EXAMS_DIR = "knowledge/exams"

# AZ-104 official domain weightings
# These determine how many questions come from each domain
DOMAINS = {
    "identities_governance": {
        "name": "Manage Azure identities and governance",
        "weight": 0.225,  # 20-25% — use midpoint
        "keywords": ["active directory", "role based", "policy",
                     "subscription", "management group", "rbac"]
    },
    "storage": {
        "name": "Implement and manage storage",
        "weight": 0.175,  # 15-20%
        "keywords": ["storage", "blob", "file", "queue", "table", "disk"]
    },
    "compute": {
        "name": "Deploy and manage Azure compute resources",
        "weight": 0.225,  # 20-25%
        "keywords": ["virtual machine", "app service", "kubernetes",
                     "container", "function", "scale set"]
    },
    "networking": {
        "name": "Implement and manage virtual networking",
        "weight": 0.175,  # 15-20%
        "keywords": ["virtual network", "network security", "firewall",
                     "load balancer", "vpn", "dns", "expressroute"]
    },
    "monitoring": {
        "name": "Monitor and maintain Azure resources",
        "weight": 0.125,  # 10-15%
        "keywords": ["monitor", "backup", "recovery", "alert", "log"]
    }
}

TOTAL_QUESTIONS = 50
EXAM_DURATION_MINUTES = 150
PASS_SCORE = 700  # Microsoft's passing threshold out of 1000
OS_MAKEDIRS = os.makedirs(EXAMS_DIR, exist_ok=True)


# ─── TOPIC MAPPING ────────────────────────────────────────────────────────────

def map_topics_to_domains():
    """
    Maps ingested topics to AZ-104 domains based on keyword matching.
    Returns a dict of domain_id -> list of topic file paths.
    This determines which topics are available for each domain's questions.
    """
    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    domain_topics = {domain_id: [] for domain_id in DOMAINS}

    for topic in index["topics"]:
        topic_name_lower = topic["name"].lower()
        topic_path = os.path.join(KNOWLEDGE_DIR, f"{topic['id']}.json")

        if not os.path.exists(topic_path):
            continue

        # Match topic to domain by keyword
        matched = False
        for domain_id, domain in DOMAINS.items():
            if any(kw in topic_name_lower for kw in domain["keywords"]):
                domain_topics[domain_id].append(topic_path)
                matched = True
                break

        # If no keyword match, add to closest domain by position
        if not matched:
            domain_topics["compute"].append(topic_path)

    return domain_topics


# ─── QUESTION GENERATION ──────────────────────────────────────────────────────

def calculate_question_distribution():
    """
    Calculates how many questions to generate per domain based on weights.
    Ensures total adds up to exactly TOTAL_QUESTIONS.
    """
    distribution = {}
    total_assigned = 0

    for i, (domain_id, domain) in enumerate(DOMAINS.items()):
        if i == len(DOMAINS) - 1:
            # Last domain gets remainder to ensure exact total
            distribution[domain_id] = TOTAL_QUESTIONS - total_assigned
        else:
            count = round(domain["weight"] * TOTAL_QUESTIONS)
            distribution[domain_id] = count
            total_assigned += count

    return distribution


def generate_questions_for_domain(domain_id, topic_paths, count):
    """
    Generates `count` questions for a domain using available topics.
    Called in parallel — one worker per domain.

    If a domain has multiple topics, questions are spread across them.
    If a domain has no topics ingested yet, returns placeholder questions.
    """
    domain = DOMAINS[domain_id]
    questions = []

    if not topic_paths:
        print(f"  [WARN] No topics ingested for domain: {domain['name']}")
        return questions

    # Distribute questions across available topics
    topics_cycle = topic_paths * (count // len(topic_paths) + 1)

    for i in range(count):
        topic_path = topics_cycle[i]

        with open(topic_path, "r") as f:
            topic = json.load(f)

        prompt = f"""
You are an AZ-104 exam question writer. Generate ONE exam-style question.

IMPORTANT RULES:
- Question must be answerable in under 2 minutes
- All 4 options must be plausible — no obviously wrong answers
- Test understanding, not memorisation
- Match real AZ-104 exam style exactly

TOPIC: {json.dumps(topic, indent=2)}
DOMAIN: {domain['name']}

Return ONLY this JSON, no markdown, no backticks:
{{
  "question": "full question text",
  "options": {{
    "A": "option text",
    "B": "option text",
    "C": "option text",
    "D": "option text"
  }},
  "correct_answer": "A",
  "explanation": "why correct answer is right and others are wrong",
  "topic": "{topic['topic']}",
  "domain": "{domain['name']}",
  "domain_id": "{domain_id}",
  "difficulty": "easy|medium|hard"
}}
"""
        result = claude_call(prompt, operation_name="generate_exam_question")

        if result.returncode != 0:
            print(f"  [FAIL] Question {i+1} for {topic['topic']}: {result.stderr[:80]}")
            continue

        output = result.stdout.strip()

        try:
            question = json.loads(output)
        except json.JSONDecodeError:
            start = output.find("{")
            end = output.rfind("}") + 1
            try:
                question = json.loads(output[start:end])
            except json.JSONDecodeError:
                print(f"  [FAIL] Could not parse question for {topic['topic']}")
                continue

        questions.append(question)
        print(f"  [Q{len(questions):02d}] {domain['name'][:30]}... generated")

    return questions


def generate_all_questions():
    """
    Generates all 50 questions in parallel — one thread per domain.
    All 5 domains generate questions simultaneously, then results are merged.

    This is where parallel sub-agents shine — 50 sequential Claude calls
    would take ~10 minutes. Parallel across 5 domains takes ~2 minutes.
    """
    distribution = calculate_question_distribution()
    domain_topics = map_topics_to_domains()

    print(f"\nGenerating {TOTAL_QUESTIONS} questions across 5 domains in parallel...")
    print("Domain distribution:")
    for domain_id, count in distribution.items():
        print(f"  {DOMAINS[domain_id]['name'][:45]}: {count} questions")
    print()

    all_questions = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(
                generate_questions_for_domain,
                domain_id,
                domain_topics[domain_id],
                distribution[domain_id]
            ): domain_id
            for domain_id in DOMAINS
        }

        for future in as_completed(futures):
            domain_id = futures[future]
            questions = future.result()
            all_questions.extend(questions)
            print(f"Domain complete: {DOMAINS[domain_id]['name'][:45]} "
                  f"({len(questions)} questions)")

    # Shuffle questions so domains aren't grouped
    import random
    random.shuffle(all_questions)

    return all_questions


# ─── EXAM SESSION ─────────────────────────────────────────────────────────────

def run_exam(questions):
    """
    Runs the interactive exam session in the terminal.
    Timer runs in background. No hints, no explanations during exam.
    Returns list of answered question results.
    """
    total = len(questions)
    start_time = time.time()
    deadline = start_time + (EXAM_DURATION_MINUTES * 60)
    answers = []

    print("\n" + "="*60)
    print("AZ-104 MOCK EXAM")
    print("="*60)
    print(f"Questions : {total}")
    print(f"Time      : {EXAM_DURATION_MINUTES} minutes")
    print(f"Passing   : {PASS_SCORE}/1000")
    print("\nNo hints or explanations during the exam.")
    print("Type A, B, C, or D. Type 'q' to quit early.")
    print("="*60)
    input("\nPress Enter to begin...")

    for i, question in enumerate(questions):
        # Check time remaining
        remaining = deadline - time.time()
        if remaining <= 0:
            print("\nTime's up!")
            break

        remaining_min = int(remaining // 60)
        remaining_sec = int(remaining % 60)

        print(f"\n{'='*60}")
        print(f"Question {i+1}/{total} | "
              f"Time remaining: {remaining_min:02d}:{remaining_sec:02d} | "
              f"Domain: {question.get('domain_id','').replace('_',' ').title()}")
        print(f"{'='*60}")
        print(f"\n{question['question']}\n")

        for key, val in question["options"].items():
            print(f"  {key}) {val}")

        print()

        # Get answer with input validation
        while True:
            answer = input("Answer: ").strip().upper()
            if answer == "Q":
                print("\nExam ended early.")
                # Record as skipped
                answers.append({
                    "question_num": i + 1,
                    "question": question["question"],
                    "topic": question.get("topic", ""),
                    "domain": question.get("domain", ""),
                    "domain_id": question.get("domain_id", ""),
                    "correct_answer": question["correct_answer"],
                    "user_answer": "SKIPPED",
                    "correct": False,
                    "explanation": question.get("explanation", ""),
                    "difficulty": question.get("difficulty", "medium")
                })
                return answers
            if answer in ["A", "B", "C", "D"]:
                break
            print("Please enter A, B, C, or D.")

        correct = answer == question["correct_answer"]

        answers.append({
            "question_num": i + 1,
            "question": question["question"],
            "topic": question.get("topic", ""),
            "domain": question.get("domain", ""),
            "domain_id": question.get("domain_id", ""),
            "correct_answer": question["correct_answer"],
            "user_answer": answer,
            "correct": correct,
            "explanation": question.get("explanation", ""),
            "difficulty": question.get("difficulty", "medium")
        })

        # Minimal feedback during exam — just correct/wrong, no explanation
        print("✓ Correct" if correct else "✗ Wrong")

    return answers


# ─── SCORING ──────────────────────────────────────────────────────────────────

def calculate_score(answers):
    """
    Calculates the exam score scaled to Microsoft's 1000-point system.

    Microsoft doesn't use simple percentage — they use a scaled score.
    We approximate: raw percentage mapped linearly to 1000 points.
    700+ is passing.
    """
    total = len(answers)
    if total == 0:
        return 0

    correct = sum(1 for a in answers if a["correct"])
    raw_percentage = correct / total
    scaled_score = round(raw_percentage * 1000)

    return scaled_score


def calculate_domain_scores(answers):
    """
    Breaks down performance per domain.
    This is the most useful part of the report — shows exactly which
    exam domains need more work.
    """
    domain_stats = {}

    for answer in answers:
        domain_id = answer.get("domain_id", "unknown")
        if domain_id not in domain_stats:
            domain_stats[domain_id] = {
                "name": answer.get("domain", domain_id),
                "correct": 0,
                "total": 0,
                "questions": []
            }
        domain_stats[domain_id]["total"] += 1
        if answer["correct"]:
            domain_stats[domain_id]["correct"] += 1
        domain_stats[domain_id]["questions"].append(answer)

    # Calculate accuracy per domain
    for domain_id in domain_stats:
        stats = domain_stats[domain_id]
        stats["accuracy"] = round(
            (stats["correct"] / stats["total"]) * 100, 1
        ) if stats["total"] > 0 else 0

    return domain_stats

def update_claude_memory_from_exam(progress):
    """
    Same as quiz.py's update_claude_memory — updates global memory
    after a mock exam completes. Kept separate to avoid import coupling.
    """
    memory_file = os.path.expanduser("~/.claude/CLAUDE.md")
    weak_areas = progress.get("weak_areas", [])

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

    if os.path.exists(memory_file):
        with open(memory_file, "r") as f:
            existing = f.read()
    else:
        existing = ""

    marker = "## AZ-104 Study — Current Weak Areas"
    if marker in existing:
        start = existing.find(marker)
        next_section = existing.find("\n## ", start + 1)
        if next_section == -1:
            updated = existing[:start] + memory_block
        else:
            updated = existing[:start] + memory_block + existing[next_section:]
    else:
        updated = existing.rstrip() + "\n\n" + memory_block

    with open(memory_file, "w") as f:
        f.write(updated)

    print(f"\nClaude memory updated with {len(weak_areas)} weak area(s).")


# ─── REPORT ───────────────────────────────────────────────────────────────────

def generate_report(answers, elapsed_seconds):
    """
    Generates the full post-exam analysis report.
    Saves to knowledge/exams/ with timestamp.
    Prints summary to terminal.
    Also updates progress.json so the web UI reflects exam results.
    """
    score = calculate_score(answers)
    domain_scores = calculate_domain_scores(answers)
    passed = score >= PASS_SCORE
    total = len(answers)
    correct = sum(1 for a in answers if a["correct"])
    elapsed_min = int(elapsed_seconds // 60)
    elapsed_sec = int(elapsed_seconds % 60)

    # Build report object
    report = {
        "exam_date": datetime.now().isoformat(),
        "total_questions": total,
        "correct": correct,
        "score": score,
        "passed": passed,
        "time_taken": f"{elapsed_min}m {elapsed_sec}s",
        "domain_scores": domain_scores,
        "answers": answers
    }

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(EXAMS_DIR, f"exam_{timestamp}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Update progress.json with exam session
    with open(PROGRESS_FILE, "r") as f:
        progress = json.load(f)

    for answer in answers:
        progress["sessions"].append({
            "timestamp": datetime.now().isoformat(),
            "topic_id": answer["topic"].lower().replace(" ", "_"),
            "topic_name": answer["topic"],
            "question": answer["question"],
            "correct_answer": answer["correct_answer"],
            "user_answer": answer["user_answer"],
            "correct": answer["correct"],
            "difficulty": answer["difficulty"],
            "source": "mock_exam"
        })

    progress["total_questions_answered"] += total
    progress["total_correct"] += correct

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

    progress["weak_areas"] = [
        {
            "topic_id": tid,
            "topic_name": stats["name"],
            "accuracy": round((stats["correct"] / stats["total"]) * 100, 1),
            "questions_answered": stats["total"]
        }
        for tid, stats in topic_stats.items()
        if stats["correct"] / stats["total"] < 0.6
    ]

    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

    # Print terminal report
    print("\n" + "="*60)
    print("EXAM COMPLETE — RESULTS")
    print("="*60)
    print(f"Score     : {score}/1000")
    print(f"Result    : {'PASS ✓' if passed else 'FAIL ✗'} (passing: {PASS_SCORE})")
    print(f"Correct   : {correct}/{total}")
    print(f"Time taken: {elapsed_min}m {elapsed_sec}s")
    print(f"\nDOMAIN BREAKDOWN:")

    for domain_id, stats in domain_scores.items():
        bar_filled = int(stats["accuracy"] / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        status = "✓" if stats["accuracy"] >= 70 else "✗"
        print(f"  {status} {stats['name'][:42]:<42} "
              f"{bar} {stats['accuracy']}%")

    if not passed:
        print(f"\nWEAK DOMAINS (need improvement):")
        for domain_id, stats in domain_scores.items():
            if stats["accuracy"] < 70:
                print(f"  - {stats['name']}: {stats['accuracy']}%")

    print(f"\nFull report saved: {report_path}")
    print("="*60)

    # Update global Claude memory with weak areas from this exam
    update_claude_memory_from_exam(progress)

    return report


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    """
    Entry point. Orchestrates the full exam flow:
    1. Generate questions in parallel
    2. Run interactive exam
    3. Generate analysis report
    """
    os.makedirs(EXAMS_DIR, exist_ok=True)

    print("AZ-104 Mock Exam Generator")
    print("This will generate 50 questions — takes ~2 minutes.")
    print("Press Ctrl+C to cancel.\n")

    # Step 1: Generate questions in parallel
    gen_start = time.time()
    questions = generate_all_questions()
    gen_time = round(time.time() - gen_start, 1)

    if not questions:
        print("No questions generated. Make sure topics are ingested.")
        sys.exit(1)

    print(f"\n{len(questions)} questions generated in {gen_time}s")

    # Step 2: Run exam
    exam_start = time.time()
    answers = run_exam(questions)
    elapsed = time.time() - exam_start

    if not answers:
        print("No answers recorded.")
        sys.exit(0)

    # Step 3: Generate report
    generate_report(answers, elapsed)


if __name__ == "__main__":
    main()