Run a quiz session for AZ-104 exam prep.

Arguments: $ARGUMENTS

- If arguments provided, focus quiz on that topic or domain.
- If no arguments, select questions from weak areas in knowledge/progress.json first, then random topics.

Steps:

1. Read knowledge/progress.json to identify weak areas (score < 70%).
2. Run: bash quiz.sh $ARGUMENTS
3. After quiz completes, summarize: topics covered, score, updated weak areas.
4. Recommend what to study next based on results.
