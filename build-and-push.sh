#!/bin/bash

# Initialize a variable to track if we should run tests
RUN_TESTS=true

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -nt|--no-test) RUN_TESTS=false ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# Execute tests unless the flag was used
if [ "$RUN_TESTS" = true ]; then
    echo "Running tests..."
    pytest
    if [ $? -ne 0 ]; then
        echo "Tests failed. Aborting build."
        exit 1
    fi
else
    echo "Skipping tests as requested."
fi

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