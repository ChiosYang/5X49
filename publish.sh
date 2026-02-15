#!/bin/bash

# Configuration
USERNAME="alicolia" # Replace with your actual Docker Hub username if different

# 获取当前时间作为唯一版本号 (格式: 年月日-时分，例如 20260215-1842)
TIMESTAMP=$(date +"%Y%m%d-%H%M")
# 如果你在运行脚本时传入了参数 (例如 ./push.sh v1.0.0)，就用传入的参数；否则用时间戳
VERSION=${1:-$TIMESTAMP} 

echo "🐳 Building and pushing images for $USERNAME..."
echo "🏷️  Version tag: $VERSION AND latest"

# 1. Login to Docker Hub
echo "🔑 Logging in to Docker Hub..."
docker login

# 2. Build and Push Backend
echo "📦 Building Backend..."
# 使用 -t 两次，同时打上版本号标签和 latest 标签
docker build -t $USERNAME/5x49-backend:$VERSION -t $USERNAME/5x49-backend:latest ./backend

echo "🚀 Pushing Backend..."
# 将两个标签都推送到 Docker Hub
docker push $USERNAME/5x49-backend:$VERSION
docker push $USERNAME/5x49-backend:latest

# 3. Build and Push Frontend
echo "📦 Building Frontend..."
# 同样打上两个标签
docker build -t $USERNAME/5x49-frontend:$VERSION -t $USERNAME/5x49-frontend:latest ./frontend

echo "🚀 Pushing Frontend..."
docker push $USERNAME/5x49-frontend:$VERSION
docker push $USERNAME/5x49-frontend:latest

echo "✅ Done!"
echo "📌 Your specific version is: $VERSION"
echo "Users can now deploy with 'latest', or rollback using the specific version tag."