Compare two AZ-104 concepts side by side to resolve confusion.

Arguments: $ARGUMENTS

- Expected format: "ConceptA vs ConceptB" or "ConceptA ConceptB"

Steps:

1. Parse the two concepts from: $ARGUMENTS
2. Check knowledge/comparisons.json — if cached, display that.
3. If not cached, run: bash compare.sh <concept1> <concept2>
4. Display a clear table: differences, when to use each, exam traps.
