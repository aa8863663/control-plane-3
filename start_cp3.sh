#!/bin/zsh
cd ~/Projects/control-plane-3 || exit 1
export $(grep -v '^#' .env | xargs)
echo "Project: $(pwd)"
echo "Python: $(python3 --version)"
echo "DATABASE_URL loaded: ${DATABASE_URL:+yes}"

