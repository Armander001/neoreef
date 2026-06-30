FROM mcr.microsoft.com/devcontainers/python:3.11-bullseye

# Install Miniconda to /opt/conda (matches devcontainer.json interpreter path)
RUN curl -fsSL "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh" -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda init bash \
    && ln -s /opt/conda/bin/conda /usr/local/bin/conda

ENV PATH="/opt/conda/bin:$PATH"

# Install Node.js 22 + Claude Code CLI
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

# Claude Code OAuth callback port
EXPOSE 54545
