#!/bin/bash

cd ~/code/apps/zotero_digest

set -a  # automatically export all variables
source zotero_digest.env
set +a

python3 zotero_app.py
