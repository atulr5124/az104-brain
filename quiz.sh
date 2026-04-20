#!/bin/bash

# Usage: ./quiz.sh <topic_id>
# Example: ./quiz.sh virtual_networks

source venv/bin/activate
python quiz.py "$1"