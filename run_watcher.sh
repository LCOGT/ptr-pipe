#!/usr/bin/env bash
#
# run_watcher.sh
# ——————————
# simple wrapper to launch thewatcher.py

# Absolute path to your ptr-pipe project:
#PROJECT_DIR="/home/ecopipeline/PycharmProjects/ptr-pipe"

# Jump into that folder (exit if it fails):
#cd /home/ecopipeline/PycharmProjects/ptr-pipe

# (optional:) load any env vars you need
# source ~/.bash_profile
# source .env

# Exec the watcher by absolute path (just to be extra safe):
exec python3 thewatcher.py
