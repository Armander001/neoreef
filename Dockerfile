FROM node:22-slim

# Optional proxy build args — pass with --build-arg when inside the lab:
#   docker build --build-arg HTTP_PROXY=http://proxy.noc.titech.ac.jp:3128 ...
# Leave unset outside the lab; the ARGs will be empty and have no effect.
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY="localhost,127.0.0.1"
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# Install useful tools
RUN apt-get update && apt-get install -y git bash curl && rm -rf /var/lib/apt/lists/*

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Claude Code OAuth callback port
EXPOSE 54545

WORKDIR /workspace

# ANTHROPIC_API_KEY should be passed at runtime:
#   docker run -e ANTHROPIC_API_KEY=... -p 54545:54545 -it <image>
ENTRYPOINT ["claude"]
