FROM glitchlock-ml-builder:bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config libglib2.0-dev libpixman-1-dev zlib1g-dev \
    libjpeg-dev libpng-dev flex bison python3-pil \
    mtools qemu-utils gdb-multiarch xz-utils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
