#!/bin/bash
set -e

echo "🚀 Starting PGSync entrypoint script..."
echo "📋 Config: ${SCHEMA}"
echo "✅ All services are healthy (verified by Docker health checks)"

# Create checkpoint directory
mkdir -p /tmp/.pgsync
chmod 777 /tmp/.pgsync

# Check if this is first run (bootstrap needed)
BOOTSTRAP_FLAG="/app/.pgsync_bootstrapped"

if [ ! -f "$BOOTSTRAP_FLAG" ]; then
  echo "🔧 Running bootstrap and starting daemon (first time)..."
  # Run with bootstrap (-b) and daemon (-d) flags
  pgsync -c "${SCHEMA}" -d -b
  
  # If successful, mark as bootstrapped
  if [ $? -eq 0 ]; then
    touch "$BOOTSTRAP_FLAG"
  fi
else
  echo "✅ Bootstrap already completed"
  echo "🔄 Starting PGSync daemon..."
  # Run in daemon mode only
  exec pgsync -c "${SCHEMA}" -d
fi
