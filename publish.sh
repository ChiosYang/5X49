#!/bin/bash

# Configuration
USERNAME="alicolia" # Replace with your actual Docker Hub username if different
VERSION="latest"

echo "🐳 Building and pushing images for $USERNAME..."

# 1. Login to Docker Hub
echo "🔑 Logging in to Docker Hub..."
docker login

# 2. Build and Push Backend
echo "📦 Building Backend..."
docker build -t $USERNAME/film-genealogy-backend:$VERSION ./backend
echo "pk Pushing Backend..."
docker push $USERNAME/film-genealogy-backend:$VERSION

# 3. Build and Push Frontend
echo "📦 Building Frontend..."
# Note: We need to pass NEXT_PUBLIC_API_URL as a build arg if we want it baked in, 
# but for runtime config we rely on the env var in docker-compose.
# However, Next.js 'standalone' mode with public env vars is tricky.
# For a generic image, we might need to rely on runtime config solutions or keep it simple.
# For now, we assume standard build.
docker build -t $USERNAME/film-genealogy-frontend:$VERSION ./frontend
echo "pk Pushing Frontend..."
docker push $USERNAME/film-genealogy-frontend:$VERSION

echo "✅ Done! Users can now deploy with docker-compose.release.yml"
