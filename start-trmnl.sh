#!/bin/bash
set -e
echo "Starting TRMNL dev server..."
echo "  http://localhost:4567/full"
echo "  http://localhost:4567/half_horizontal"
echo "  http://localhost:4567/half_vertical"
echo "  http://localhost:4567/quadrant"

docker run --rm -it \
  --pull always \
  -p 4567:4567 \
  -v "$(pwd):/plugin" \
  trmnl/trmnlp serve
