FROM ubuntu:22.04

# Install basic utilities
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    findutils \
    grep \
    sed \
    gawk \
    tree \
    file \
    coreutils \
    && rm -rf /var/lib/apt/lists/*

# Create workspace directory
RUN mkdir -p /workspace /home/user/Desktop /home/user/Documents /home/user/Downloads

# Create some sample files for testing
RUN echo "Sample file 1" > /home/user/Desktop/sample1.txt && \
    echo "Sample file 2" > /home/user/Desktop/sample2.txt && \
    mkdir -p /home/user/Desktop/projects && \
    echo "#!/bin/bash" > /home/user/Desktop/projects/script.sh && \
    echo "print('Hello')" > /home/user/Desktop/test.py

# Set working directory
WORKDIR /home/user

# Set non-root user for safety
RUN useradd -m -s /bin/bash safeuser
USER safeuser

CMD ["/bin/bash"]
