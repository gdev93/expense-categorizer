#!/bin/bash

pytest
# Set repository name
REPO="giacomodev93/expense-categorizer"

# Read VERSION from file, default to 1.0.0 if file doesn't exist
if [ -f VERSION ]; then
    VERSION=$(cat VERSION)
else
    VERSION="1.0.0"
    echo $VERSION > VERSION
    echo "Created VERSION file with initial version: $VERSION"
fi

echo "Building version: $VERSION"

# Ensure buildx is available and create builder if it doesn't exist
if ! docker buildx ls | grep -q multiplatform-builder; then
    echo "Creating multiplatform builder..."
    docker buildx create --name multiplatform-builder --use
else
    echo "Using existing multiplatform builder..."
    docker buildx use multiplatform-builder
fi

# Build and push for amd64 only (remote server architecture)
echo "Building and pushing $REPO:v$VERSION for linux/amd64..."
docker buildx build --platform linux/amd64 \
  -t $REPO:v$VERSION \
  -t $REPO:latest \
  --push .

echo "Build and push completed successfully!"
echo "Tagged as: $REPO:v$VERSION and $REPO:latest"