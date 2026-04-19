# az104-brain

## What this project is

A personal AZ-104 Microsoft Azure exam study assistant with a web UI.
It ingests Microsoft Learn documentation, builds a persistent knowledge
index, quizzes the user interactively, tracks progress, and generates
a personalised cram sheet.

## Exam context

- Target exam: AZ-104 Microsoft Azure Administrator
- Exam date target: First week of May 2025
- Current status: MS Learn docs read, going through John Savill cram video
- Time remaining: approximately 2 weeks

## User context

- Weak areas: to be populated as quiz progress is tracked
- Study priority: retention and distinguishing similar concepts

## AZ-104 topic domains (official weighting)

- Manage Azure identities and governance (20-25%)
- Implement and manage storage (15-20%)
- Deploy and manage Azure compute resources (20-25%)
- Implement and manage virtual networking (15-20%)
- Monitor and maintain Azure resources (10-15%)

## Tech stack

- Backend: Python 3.9 with Flask
- Frontend: Single HTML file with vanilla JS (no frameworks)
- Knowledge store: JSON files in knowledge/
- Claude integration: headless mode via shell scripts

## Project structure

- ingest.sh: pulls MS Learn docs for a topic
- quiz.sh: launches quiz on a topic
- compare.sh: explains differences between two similar concepts
- cramsheet.sh: generates personalised cram sheet based on weak areas
- server.py: Flask web server serving the UI

## Code style

- Keep code simple and readable
- Comment every function explaining what it does
- Prefer clarity over cleverness
