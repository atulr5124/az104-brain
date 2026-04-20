# az104-brain

A personal exam study intelligence system powered by Claude Code. It ingests official documentation, builds a persistent knowledge base, quizzes you interactively, tracks your progress, and generates a personalised cram sheet — all through a clean web UI.

Built originally for the **AZ-104 Microsoft Azure Administrator** exam, but designed to be adapted to any certification or study topic.

![Python](https://img.shields.io/badge/python-3.9+-blue) ![Flask](https://img.shields.io/badge/flask-3.x-lightgrey) ![Claude Code](https://img.shields.io/badge/claude--code-required-orange)

---

## What it does

| Feature | Description |
|---|---|
| **Ingest** | Pulls documentation from any URL and structures it into a knowledge base via Claude |
| **Bulk Ingest** | Ingests multiple topics simultaneously using parallel workers |
| **File Watch** | Drop any `.md` or `.txt` file into `inputs/` and it auto-ingests |
| **Compare** | Side-by-side explanation of two commonly confused concepts |
| **Quiz** | Generates exam-style questions on demand, evaluates answers, explains why |
| **Mock Exam** | Full timed exam drawn proportionally across all domains with a pass/fail score |
| **Progress Tracking** | Tracks every answer, surfaces weak areas automatically |
| **Cram Sheet** | Personalised study plan generated from your weak areas and exam date |

---

## Why this is different from just using Claude chat

Claude chat requires you to be present — you paste, it responds, you read. This system:

- Runs scripts **unattended** — generate 50 questions while you make coffee
- Maintains a **persistent knowledge base** that survives sessions
- **Tracks your performance** over time and surfaces exactly what to study
- **Watches your folder** and ingests new material automatically
- Serves a **local web UI** you open in your browser like a real app

---

## Requirements

- Python 3.9 or higher
- A Claude Pro or Max subscription at [claude.ai](https://claude.ai)
- Claude Code installed (`npm install -g @anthropic-ai/claude-code`)
- Node.js 18+ (for Claude Code)
- Git

---

## Installation

### 1. Clone the repo

```bash
git clone git@github.com:atulr5124/az104-brain.git
cd az104-brain
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

> Every time you open a new terminal to work on this project, run `source venv/bin/activate` first. You will see `(venv)` in your prompt when it is active.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Authenticate Claude Code

```bash
claude
```

This opens a browser window. Log in with your Anthropic account. Once authenticated, type `/exit` to quit the session.

### 5. Start the web server

```bash
./start.sh
```

Open `http://127.0.0.1:5000` in your browser.

> **macOS note:** Use `http://127.0.0.1:5000` not `http://localhost:5000`. On macOS Monterey and later, `localhost` on port 5000 is intercepted by AirPlay Receiver and returns a 403 error.

---

## Usage

### Ingest a single topic

```bash
./ingest.sh "Topic Name" "https://docs-url-here.com/topic"
```

Example:

```bash
./ingest.sh "Virtual Networks" "https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview"
```

### Bulk ingest all topics from topics.json

```bash
./bulk_ingest.sh
```

Edit `topics.json` to add or remove topics before running.

### Auto-ingest by dropping files

Start the file watcher in a separate terminal:

```bash
./watch.sh
```

Then drop any `.md` or `.txt` file into the `inputs/` folder. It gets ingested automatically.

### Quiz on a topic (terminal)

```bash
./quiz.sh virtual_networks
```

Use the topic ID — the filename without `.json` from `knowledge/topics/`.

### Compare two topics (terminal)

```bash
./compare.sh network_security_groups azure_firewall
```

### Run a mock exam (terminal)

```bash
./exam.sh
```

Generates 50 questions in parallel across all domains. Takes approximately 2 minutes to generate, then 150 minutes to complete.

### Web UI

Everything above is also accessible through the browser at `http://127.0.0.1:5000`.

---

## Adapting this for a different exam or study topic

This system is not AZ-104 specific. Here is how to repurpose it for any certification or subject.

### Step 1 — Update `CLAUDE.md`

Open `CLAUDE.md` and change:

- The project description to reflect your topic
- The exam name and date
- The domain weightings (replace the 5 AZ-104 domains with your exam's sections)
- Any subject-specific context

### Step 2 — Update `topics.json`

Replace the URLs with documentation pages relevant to your exam. Each entry needs a `name` and a `url`:

```json
{
  "topics": [
    {
      "name": "Your Topic Name",
      "url": "https://official-docs-url-for-this-topic.com"
    }
  ]
}
```

### Step 3 — Update domain weightings in `exam.py`

Open `exam.py` and find the `DOMAINS` dictionary near the top. Replace the 5 AZ-104 domains with your exam's sections, their official weightings, and relevant keywords:

```python
DOMAINS = {
    "your_domain_id": {
        "name": "Your Domain Name",
        "weight": 0.25,  # percentage as decimal — all weights must sum to 1.0
        "keywords": ["keyword1", "keyword2", "keyword3"]
    },
    ...
}
```

Keywords are used to automatically map ingested topics to domains. Make them match words likely to appear in topic names.

### Step 4 — Update the exam date in `server.py`

Find the cram sheet prompt in `server.py` and update the exam date reference:

```python
"The exam is in [YOUR EXAM DATE]."
```

### Step 5 — Ingest your topics

```bash
./bulk_ingest.sh
```

Then open the web UI and start quizzing.

---

## Project structure

```
az104-brain/
├── CLAUDE.md                  # Claude's project memory — context and rules
├── topics.json                # Master list of topics to bulk ingest
├── requirements.txt           # Python dependencies
├── server.py                  # Flask web server and REST API
├── ingest.py / ingest.sh      # Single topic ingest from URL
├── bulk_ingest.py / bulk_ingest.sh   # Parallel bulk ingest
├── watch.py / watch.sh        # File watcher for auto-ingest
├── compare.py / compare.sh    # Concept comparison engine
├── quiz.py / quiz.sh          # Terminal quiz engine
├── exam.py / exam.sh          # Mock exam with domain scoring
├── start.sh                   # Starts the web server
├── public/
│   └── index.html             # Web UI — single page app
├── knowledge/
│   ├── index.json             # Master topic index
│   ├── comparisons.json       # Cached concept comparisons
│   ├── progress.json          # Quiz history and weak areas
│   ├── topics/                # Structured knowledge per topic
│   └── exams/                 # Past mock exam results
└── inputs/                    # Drop files here for auto-ingest
```

---

## How it works under the hood

Every intelligence feature runs Claude in **headless mode**:

```bash
claude -p "your prompt here"
```

Scripts send structured prompts, Claude returns JSON, the app saves and serves it. No API key required — it runs through your Claude Pro subscription via Claude Code.

The Flask server exposes a REST API that the browser frontend calls. All knowledge is stored as plain JSON files — no database required.

---

## Troubleshooting

**`Topics file not found` when running shell scripts**

Make sure you are running scripts from the project root directory, not a subdirectory. Run `pwd` to confirm.

**`command not found: claude`**

Claude Code is not in your PATH. Run:

```bash
export PATH="$(npm bin -g):$PATH"
```

Add that line to your `~/.zshrc` to make it permanent.

**Web UI shows `loading topics...` indefinitely**

Open browser developer console (`Cmd + Option + J` on Mac) and check for JavaScript errors. Restart the server and refresh.

**`conda` environment interfering with venv**

The shell scripts run `conda deactivate` automatically before activating the venv. If you still get issues, manually run `conda deactivate` before running any script.

---

## Contributing

This is a personal study tool. If you adapt it for another exam and want to share your `topics.json` and domain configuration, pull requests are welcome.

---

## License

MIT — do whatever you want with it.
