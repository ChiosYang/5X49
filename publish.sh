#!/bin/bash

# Configuration
USERNAME="alicolia"
TIMESTAMP=$(date +"%Y%m%d-%H%M")
DEFAULT_VERSION=$TIMESTAMP

# 1. Version Selection
echo "🚀 5X49 Release Manager"
echo "--------------------------------"
echo "Current Timestamp: $TIMESTAMP"
echo ""

# Check if version was passed as argument
if [ -n "$1" ]; then
    VERSION=$1
    echo "📌 Using version from argument: $VERSION"
else
    # Prompt for version
    read -p "📝 Enter version to release (default: $DEFAULT_VERSION): " INPUT_VERSION
    VERSION=${INPUT_VERSION:-$DEFAULT_VERSION}
    echo "� Target Version: $VERSION"
fi

echo ""
echo "--------------------------------"
echo "Preparing to release $VERSION"
echo "--------------------------------"

# 2. Docker Push Confirmation
echo "🐳 Docker Operations:"
echo "   - Build & Push $USERNAME/5x49-backend:$VERSION (Multi-arch)"
echo "   - Build & Push $USERNAME/5x49-frontend:$VERSION (Multi-arch)"
echo "   - Update 'latest' tags for both"
echo ""

read -p "❓ Proceed with Docker Build & Push? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted Docker operations."
else
    echo "🔑 Logging in to Docker Hub..."
    docker login

    # Ensure buildx is ready
    docker buildx create --use --name multi-arch-builder 2>/dev/null || docker buildx use multi-arch-builder

    # Backend
    echo "📦 Building and Pushing Backend (Multi-arch)..."
    docker buildx build --platform linux/amd64,linux/arm64 \
        -t $USERNAME/5x49-backend:$VERSION \
        -t $USERNAME/5x49-backend:latest \
        --push ./backend

    # Frontend
    echo "📦 Building and Pushing Frontend (Multi-arch)..."
    docker buildx build --platform linux/amd64,linux/arm64 \
        -t $USERNAME/5x49-frontend:$VERSION \
        -t $USERNAME/5x49-frontend:latest \
        --push ./frontend
    
    echo "✅ Docker Images Pushed Successfully!"
fi

echo ""
echo "--------------------------------"

# 3. Git Release Confirmation
echo "🐙 GitHub Operations:"
echo "   - Create Git Tag: $VERSION"
echo "   - Push Tag to Origin"
echo "   - Generate Release Draft URL"
echo ""

read -p "❓ Proceed with GitHub Release? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Check for uncommitted changes
    if [[ -n $(git status -s) ]]; then
        echo "⚠️  Warning: You have uncommitted changes."
        git status -s
        echo ""
        read -p "⚠️  Continue anyway? (y/n) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "❌ Aborted git tagging."
            exit 1
        fi
    fi

    echo "🏷️  Creating git tag: $VERSION"
    git tag -a "$VERSION" -m "Release $VERSION"
    
    echo "⬆️  Pushing tag to origin..."
    git push origin "$VERSION"
    
    echo "✅ Git Tag Pushed!"
    
    # Generate GitHub Release URL
    REPO_URL=$(git config --get remote.origin.url)
    if [[ $REPO_URL == git@github.com:* ]]; then
        REPO_URL=${REPO_URL//:/\/}
        REPO_URL=${REPO_URL//git@/https:\/\/}
    fi
    REPO_URL=${REPO_URL%.git}
    
    RELEASE_URL="$REPO_URL/releases/new?tag=$VERSION&title=Release%20$VERSION"
    
    echo ""
    echo "🎉 Release Draft Ready!"
    echo "👉 $RELEASE_URL"
else
    echo "⏭️  Skipping GitHub operations."
fi

echo ""
echo "✅ Done!"