#!/bin/bash

# Visual Accessibility Auditor Runner
# Usage: ./audit_url.sh <URL>

if [ -z "$1" ]; then
  echo "Usage: ./audit_url.sh <URL>"
  echo "Example: ./audit_url.sh https://example.com"
  exit 1
fi

URL="$1"
echo "Starting Audit for: $URL"

# Run the Python crawler (which handles capturing + analysis)
python3 web_crawler.py --urls "$URL"

echo "Done. Check the 'output' directory for results."
