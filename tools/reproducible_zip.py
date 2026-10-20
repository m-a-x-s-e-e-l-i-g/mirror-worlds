"""Portable release ZIP profile; no filesystem timestamps or zlib dependency."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

PROFILE = "zip-stored-utc-v1"


def member_name(value):
    """Require one canonical, relative POSIX spelling on every host."""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\0" in value:
        raise ValueError("Non-canonical release member name")
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or path.as_posix() != value or ".." in path.parts:
        raise ValueError("Non-canonical release member name: " + value)
    return value


def zip_time(epoch):
    if isinstance(epoch, bool) or not isinstance(epoch, int):
        raise ValueError("source_date_epoch must be an integer")
    date = datetime.fromtimestamp(epoch, timezone.utc)
    if not 1980 <= date.year <= 2107:
        raise ValueError("source_date_epoch must fit ZIP's 1980-2107 UTC range")
    # DOS timestamps represent even seconds. Never consult the local timezone.
    return (date.year, date.month, date.day, date.hour, date.minute, date.second // 2 * 2)


def write_archive(tree, output, epoch):
    tree, output = Path(tree).resolve(), Path(output).absolute()
    timestamp = zip_time(epoch)
    if not tree.is_dir():
        raise ValueError("Release tree is not a directory")
    if output.resolve().is_relative_to(tree):
        raise ValueError("Archive output must be outside its input tree")
    members = []
    for path in tree.rglob("*"):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Release tree contains a link: " + str(path.relative_to(tree)))
        if path.is_file():
            members.append((member_name(path.relative_to(tree).as_posix()), path))
        elif not path.is_dir():
            raise ValueError("Release tree contains a non-regular entry")
    names = [name.casefold() for name, _ in members]
    if len(names) != len(set(names)):
        raise ValueError("Release member names collide on case-insensitive filesystems")
    # Open exclusively before entering cleanup: an existing published ZIP is
    # never ours to remove. Close the handle before unlinking on Windows.
    handle = output.open("xb")
    try:
        with handle, zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, path in sorted(members):
                info = zipfile.ZipInfo(name, timestamp)
                info.create_system = 3  # Fixed Unix regular-file permissions on all hosts.
                info.create_version = info.extract_version = 20
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.internal_attr = 0
                info.extra = info.comment = b""
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, path.read_bytes())
    except BaseException:
        handle.close()
        output.unlink()
        raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-date-epoch", type=int)
    args = parser.parse_args()
    try:
        epoch = args.source_date_epoch
        if epoch is None:
            recipe = json.loads((args.tree / "PACKAGE.json").read_text(encoding="utf-8"))
            if recipe["archive_profile"] != PROFILE:
                raise ValueError("Unknown archive profile")
            epoch = recipe["source_date_epoch"]
        result = write_archive(args.tree, args.output, epoch)
    except (ValueError, KeyError, OSError, OverflowError) as error:
        parser.exit(2, f"Archive refused: {error}\n")
    print(result)


if __name__ == "__main__":
    main()
