#!/bin/sh
set -eu
qemu_source=$1
qemu_output=$2
qemu_build=$3
qemu_jobs=$4
mkdir -p "$qemu_build" "$qemu_output/plugins"
cd "$qemu_build"
if [ ! -f config-host.mak ]; then
    "$qemu_source/configure" --target-list=arm-softmmu --enable-plugins \
        --disable-docs --enable-vnc --disable-gtk --disable-sdl --disable-vte \
        --disable-slirp --disable-capstone --disable-werror
fi
make -j "$qemu_jobs"
make plugins
cp arm-softmmu/qemu-system-arm "$qemu_output/qemu-system-arm"
cp tests/plugin/libmagiclantern.so "$qemu_output/plugins/"
