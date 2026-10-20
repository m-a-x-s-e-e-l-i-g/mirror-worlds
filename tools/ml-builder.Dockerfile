FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc-arm-none-eabi binutils-arm-none-eabi make python3 gcc libc6-dev git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-distutils python3-docutils zip libnewlib-arm-none-eabi \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
RUN apt-get update && apt-get install -y --no-install-recommends libraw-bin \
    && rm -rf /var/lib/apt/lists/*
