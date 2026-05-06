#!/bin/bash
# Set a friendly terminal title and size, then launch the app
printf '\033]0;Vanito\007'
printf '\033[8;36;80t'   # resize to 80 cols × 36 rows
cd "$(dirname "$0")"
python3 sol_vanity.py
