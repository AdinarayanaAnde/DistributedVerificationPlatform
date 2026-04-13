#!/bin/bash
# ============================================
#  DVP - Build and Export Docker Images
#  Run this on your current machine
# ============================================

set -e

echo "[1/3] Building images..."
docker compose build

echo "[2/3] Saving images to dvp-images.tar..."
docker save dvp-backend:latest dvp-frontend:latest postgres:16 -o dvp-images.tar

echo "[3/3] Done!"
echo ""
echo "Copy these 2 files to your other laptop:"
echo "  1. dvp-images.tar"
echo "  2. docker-compose.portable.yml"
echo ""
echo "On the other laptop run:"
echo "  docker load -i dvp-images.tar"
echo "  docker compose -f docker-compose.portable.yml up"
