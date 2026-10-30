# Developer notes

Photographers can use the [prebuilt release](https://github.com/m-a-x-s-e-e-l-i-g/mirror-worlds/releases/tag/v0.3.0). Building is optional.

## What is in this repo?

- `modules/mirror/` — camera menu, persistent preferences and guarded native capture integration.
- `modules/fx_common/` — shared pixel/mirror/camera code used by the released module.
- `targets/EOSM.202/` — pinned public target symbol table and provenance.
- `downloads/0.3.0/` — current release; the root 0.2.0 files remain immutable.
- `release-manifests/0.3.0/` — current metadata and acceptance receipt; original 0.2.0 metadata remains at the root.
- `site/` — photographer-facing landing page and local-only browser demo.
- `scripts/` — website assembly, integrity checks and build-input fetcher.

The published 0.2.0 source snapshot remains inside the immutable release ZIP. Working sources contain the 0.3.0 release, promoted from the owner-accepted dev14 candidate; experimental additional-camera profiles are described in [portability](portability.md). The repository does not publish development camera photos, ROM dumps, logs, unrelated effects releases or local credentials.

See [emulator validation](emulation.md) for the WSL build commands, per-camera core import/struct checks, ROM requirements and actual emulator limitations. The [usage guide](usage.md) describes the release; the [candidate owner guide](candidate-test.md) retains the dev14 test procedure.

## Rebuild the camera module

Requirements: Python 3, Git and Docker with Linux containers. The module builder uses a Debian Bookworm image with GNU ARM tools. No Python dependencies are needed for the build/audit scripts.

```sh
python scripts/fetch_ml_build.py
python tools/build_module.py --module mirror
python tools/build_module.py --module mirror --upstream
```

The fetcher downloads only the public, hash-verified ML build ZIP. The default builder obtains Magic Lantern source at commit `ed3e7c0dfacfdeaf3349dee73edf9e3621217462` and writes `build/modules/mirror/mirror.mo` plus its audit/manifest. `--upstream` uses the reviewed upstream revision `142472e95054d73640f50789ac0fd66325499d82` and writes `build/upstream/mirror/` instead. Neither command overwrites the published downloads. Both audit imports against the pinned EOS M core symbol table; that is not a load test on other cores.

The original tool also supports module names from its shared development environment; **this standalone repository ships only Mirror Worlds**, so use `--module mirror`.

The preserved 0.2.0 module SHA-256 is:

```text
000f575d5c30bdac15feff6dcb095cf1f93fd49b3c905baf262994bea2594737
```

Original module/ZIP/archived-source integrity checks and development tests:

```sh
python scripts/verify_release.py
python scripts/test_portability.py
python -m unittest discover -s tests -p test_*.py
node --test scripts/site.test.mjs
```

To additionally compare an original source checkout with 0.2.0, use `python scripts/verify_release.py --source-snapshot /path/to/original-checkout`. The working development sources are expected to differ from the archived release.

## Upstream source handoff

After building the normal upstream module, run `python -m tools.export_upstream_module` to create a fresh source/patch bundle under `build/upstream-export/`. It gathers the actual default compiler dependency closure into one `modules/mirror/` subtree, checks the staged bytes against the audited source manifest, and excludes generated build files and unused camera probes. It applies the patch to a clean pinned upstream tree and requires the rebuilt `.mo` to match the candidate exactly. This lets a reviewer build the module without this development repository's sibling source folders. See the [upstream contribution guide](upstream-contribution.md).

## Evidence scope

The module was developed on and tested on the original EOS M; that is the only camera validated for this release. Development included independent preview/packed-RAW pixel oracles, all 44 exposed capture combinations with synthetic full-sized transport, persistence/restart checks and ARM execution checks. Local fixture checks are not described as camera tests on additional hardware.

`release-manifests/BUILD.json` is the untouched **build-time** manifest. Its camera-test flags describe the moment the binary was built, before subsequent camera feedback; publication does not alter that historical metadata. No claim is made that every camera mode or other hardware has been tested.

## Future releases

Preserve published release bytes. Use a new version for changed firmware code, keep the preview and native RAW composition consistent, and check the camera before expanding hardware support. Prefer normal shooting controls over separate diagnostic workflows.

## Candidate source validation

The dev9 r2 ZIP contains the same camera module as dev9 and refreshed validation sources. The packager follows local Python imports from the included tools/tests, and includes the Makefiles, metadata and emulator model sources those tools use. It does not execute imported source while constructing the package.

To check the extracted package, enter its `source/` directory and run `python -B -m unittest discover -s tests -p 'test_*.py'`. The unit suite requires NumPy; saved-CR2 verifiers additionally require rawpy and Pillow. With the documented WSL/toolchain setup, `python scripts/test_portability.py --runtime wsl --sanitize` checks the actual C sources. Build and emulator commands still require the pinned upstream tools/SDK and separately supplied camera inputs where stated.

`ARM-BINARY-FIXTURE.json` and `evidence/arm-module/` identify the exact normal/API-7 modules and synthetic CPU observations. The report retains hashes of development artifacts, including ELF fixtures, which are not all bundled. The package carries the source and logs, with one camera payload under `ML/MODULES/`; it does not contain a replacement core, ROM or emulator helper executable. Source/fixture results do not establish additional hardware support.
