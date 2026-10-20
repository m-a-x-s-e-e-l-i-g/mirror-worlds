# Developer notes

Photographers can use the [prebuilt release](https://github.com/m-a-x-s-e-e-l-i-g/mirror-worlds/releases/tag/v0.2.0). Building is optional.

## What is in this repo?

- `modules/mirror/` — camera menu, persistent preferences and guarded native capture integration.
- `modules/fx_common/` — shared pixel/mirror/camera code used by the released module.
- `targets/EOSM.202/` — pinned public target symbol table and provenance.
- `downloads/` — exact published 0.2.0 module and full ZIP.
- `release-manifests/` — original build metadata and checksums.
- `site/` — photographer-facing landing page and local-only browser demo.
- `scripts/` — website assembly, integrity checks and build-input fetcher.

The repository starts with the 0.2.0 source snapshot. It deliberately does not publish development camera photos, ROM dumps, logs, unrelated effects releases or local credentials.

## Rebuild the camera module

Requirements: Python 3, Git and Docker with Linux containers. The module builder uses a Debian Bookworm image with GNU ARM tools. No Python dependencies are needed for the build/audit scripts.

```sh
python scripts/fetch_ml_build.py
python tools/build_module.py --module mirror
```

The fetcher downloads only the public, hash-verified ML build ZIP. The builder obtains Magic Lantern source at commit `ed3e7c0dfacfdeaf3349dee73edf9e3621217462` and writes `build/modules/mirror/mirror.mo` plus its audit/manifest.

The original tool also supports module names from its shared development environment; **this standalone repository ships only Mirror Worlds**, so use `--module mirror`.

The published module SHA-256 is:

```text
000f575d5c30bdac15feff6dcb095cf1f93fd49b3c905baf262994bea2594737
```

Original module/ZIP/source integrity checks:

```sh
python scripts/verify_release.py
node --test scripts/site.test.mjs
```

## Evidence scope

The module was developed on and tested on the original EOS M; that is the only camera validated for this release. Development included independent preview/packed-RAW pixel oracles, all 44 exposed capture combinations with synthetic full-sized transport, persistence/restart checks and ARM execution checks. Local fixture checks are not described as camera tests on additional hardware.

`release-manifests/BUILD.json` is the untouched **build-time** manifest. Its camera-test flags describe the moment the binary was built, before subsequent camera feedback; publication does not alter that historical metadata. No claim is made that every camera mode or other hardware has been tested.

## Future releases

Preserve published release bytes. Use a new version for changed firmware code, keep the preview and native RAW composition consistent, and check the camera before expanding hardware support. Prefer normal shooting controls over separate diagnostic workflows.
