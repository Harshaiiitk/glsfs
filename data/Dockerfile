# Dockerfile for GLSFS Sandbox Environment
# This creates a safe, isolated container for executing filesystem commands

FROM ubuntu:22.04

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install essential tools for filesystem operations
RUN apt-get update && apt-get install -y \
    # Core utilities
    coreutils \
    findutils \
    grep \
    sed \
    gawk \
    # File management
    tree \
    file \
    less \
    # Text processing
    diffutils \
    patch \
    # Compression
    zip \
    unzip \
    gzip \
    bzip2 \
    xz-utils \
    # Disk utilities
    ncdu \
    # Additional useful tools
    bc \
    xxd \
    && rm -rf /var/lib/apt/lists/*

# Create user and directory structure
RUN useradd -m -s /bin/bash user

# Create the directories that will be mount points
RUN mkdir -p /home/user/Desktop \
    && mkdir -p /home/user/Documents \
    && mkdir -p /home/user/Downloads \
    && mkdir -p /home/user/workspace \
    && chown -R user:user /home/user

# Set working directory
WORKDIR /home/user

# Default command keeps container running
CMD ["/bin/bash"]
