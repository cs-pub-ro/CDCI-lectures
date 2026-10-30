#!/bin/bash
set -e

LECTURE=${1:-"01-introduction"}

if [ ! -d "lectures/$LECTURE" ]; then
    echo "❌ Error: Lecture 'lectures/$LECTURE' not found!"
    echo "Available lectures:"
    ls -1 lectures/ | grep -v "\."
    exit 1
fi

echo "🐳 Ensuring Docker container is running..."
cd local_env
docker compose up -d
cd ..

echo "🚀 Starting Slidev interactive Dev Server for $LECTURE..."
echo "👉 Open http://localhost:3030 in your browser."
echo "Press Ctrl+C to stop the server."
echo ""

# Run the dev server interactively inside the container
docker exec -it cdci-slidev-build-docker npx slidev "lectures/$LECTURE/slides.md" --remote --port 3030
