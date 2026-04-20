#!/bin/bash

# Usage: ./compare.sh <topic_id_a> <topic_id_b>
# Example: ./compare.sh network_security_groups azure_firewall

source venv/bin/activate
python compare.py "$1" "$2"