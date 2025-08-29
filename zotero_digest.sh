#!/bin/bash
# Source shell profile to get environment variables (ZOTERO_API_KEY, SLACK_WEBHOOK_URL)
source ~/.bashrc

set -a  # automatically export all variables
source zotero_digest.env
set +a

cd /home/raresambrus/code/apps/zotero
python3 zotero_app.py
