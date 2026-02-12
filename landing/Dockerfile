# Use English comments as requested
FROM alpine:latest

# Set working directory
WORKDIR /src

# Copy local landing files into the image during build time
COPY . /src

# Command to sync files to the host directory
CMD sh -c "cp -rp /src/. /dest/ && chown -R 33:33 /dest/ && echo 'Sync complete'"