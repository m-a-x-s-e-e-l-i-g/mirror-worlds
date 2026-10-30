"""Audit the owner's official camera scope against actual ML/QEMU sources and local inputs."""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

if __package__:
    from .linux_runtime import LinuxRuntime
    from .build_qemu_eos import REVISION as QEMU_REVISION
else:
    from linux_runtime import LinuxRuntime
    from build_qemu_eos import REVISION as QEMU_REVISION

ROOT = Path(__file__).resolve().parents[1]


def load_scope(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    models = data["models"]
    if len(models) != 21 or len({item["model"] for item in models}) != 21:
        raise ValueError("The approved scope must contain exactly 21 unique models")
    for item in models:
        if not re.fullmatch(r"[A-Za-z0-9]+", item["model"]) or not re.fullmatch(r"[A-Za-z0-9]+", item["qemu"]):
            raise ValueError("Invalid camera identifier")
    return data


def launcher_models(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "known_cams" for t in node.targets):
            names = ast.literal_eval(node.value)
            if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                break
            return set(names)
    raise ValueError("Could not read the upstream launcher model list")


def module_profiles(path, *, research_70d=False):
    source = Path(path).read_text(encoding="utf-8")
    table = source.split("static const camera_profile profiles[]={", 1)[1].split("};", 1)[0]
    return [{"model": model, "firmware": firmware,
             "native_raw": research_70d if backend == "MIRROR_70D_NATIVE" else backend != "0"}
            for model, firmware, backend in re.findall(r'\{"([A-Za-z0-9]+)","([0-9.]+)",(0|&[a-z0-9_]+|MIRROR_70D_NATIVE)\}', table)]


def active_defines(path):
    # A source audit, not a C preprocessor or a runtime capability check.
    source = re.sub(r"/\*.*?\*/", "", Path(path).read_text(encoding="utf-8"), flags=re.S)
    return set(re.findall(r"^\s*#define\s+(CONFIG_[A-Z0-9_]+)\b", source, re.M))


def ml_ports(source, model):
    platform = Path(source) / "platform"
    result = []
    for folder in sorted(platform.glob(model + ".[0-9]*")) + sorted((platform / "unmaintained").glob(model + ".[0-9]*")):
        if not folder.is_dir() or not (folder / "internals.h").is_file():
            continue
        defines = active_defines(folder / "internals.h")
        version = folder.name.split(".", 1)[1]
        makefile = (folder / "Makefile").read_text(encoding="utf-8")
        arch = re.search(r"^PLATFORM_ARCH\s*=\s*(\S+)", makefile, re.M)
        result.append({"directory": folder.relative_to(source).as_posix(), "firmware_code": version,
                       "firmware": ".".join(version), "display_filters_in_source": "CONFIG_DISPLAY_FILTERS" in defines,
                       "raw_photo_in_source": "CONFIG_RAW_PHOTO" in defines, "vxworks": "CONFIG_VXWORKS" in defines,
                       "architecture": arch[1] if arch else None})
    return result


def required_roms(descriptor):
    return [{"name": name, "expected_bytes": descriptor[field]}
            for name, field in (("ROM0.BIN", "rom0_bytes"), ("ROM1.BIN", "rom1_bytes"), ("SFDATA.BIN", "serial_flash_bytes"))
            if descriptor[field]]


def inspect_roms(root, qemu_model, firmware_code, required):
    # Firmware-separated folders prevent accidentally combining models/versions.
    folder = Path(root) / qemu_model / firmware_code
    records = []
    for item in required:
        path = folder / item["name"]
        record = {**item, "path": str(path), "present": path.is_file(), "size_matches": False}
        if record["present"]:
            record["actual_bytes"] = path.stat().st_size
            record["size_matches"] = record["actual_bytes"] == item["expected_bytes"]
            data = path.read_bytes()
            record["sha256"] = hashlib.sha256(data).hexdigest()
            # A correctly sized/hashable file may still be an empty placeholder.
            # This rejects padding/marker fixtures; it does not authenticate ROMs.
            meaningful = len(data) - data.count(0) - data.count(255)
            record["nontrivial_content"] = meaningful > max(64, len(data) // 10000)
            record["placeholder_suspected"] = not record["nontrivial_content"]
        records.append(record)
    return {"files": records, "available": bool(records) and all(r["present"] and r["size_matches"] and r["nontrivial_content"] for r in records),
            "firmware_identity_verified": False}


def reference_ports(root=ROOT):
    references = json.loads((root / "targets/camera-source-references.json").read_text(encoding="utf-8"))["references"]
    result = {}
    for item in references:
        path = root / ".cache/camera-source-references" / item["model"] / item["firmware_code"] / "internals.h"
        if not path.is_file():
            with urllib.request.urlopen(item["internals_url"], timeout=30) as response:
                data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024 or hashlib.sha256(data).hexdigest() != item["internals_sha256"]:
                raise ValueError("Reference header checksum mismatch: " + item["model"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["internals_sha256"]:
            raise ValueError("Cached reference header checksum mismatch: " + item["model"])
        defines = active_defines(path)
        result.setdefault(item["model"], []).append({
            "directory": None, "source_url": item["internals_url"], "source_revision": item["revision"],
            "source_kind": item["source_kind"], "firmware_code": item["firmware_code"], "firmware": item["firmware"],
            "display_filters_in_source": "CONFIG_DISPLAY_FILTERS" in defines,
            "raw_photo_in_source": "CONFIG_RAW_PHOTO" in defines,
            "vxworks": "CONFIG_VXWORKS" in defines, "architecture": None})
    return result


def create_matrix(scope, descriptors, launcher, ml_source, profiles, rom_root, references=None):
    allowed = {item["model"] for item in scope["models"]}
    outside = {p["model"] for p in profiles} - allowed
    if outside:
        raise ValueError("Module enables models outside the approved scope: " + ", ".join(sorted(outside)))
    rows = []
    for item in scope["models"]:
        name, qemu = item["model"], item["qemu"]
        descriptor = descriptors.get(qemu)
        ports = ml_ports(ml_source, name) or (references or {}).get(name, [])
        supported = [p for p in profiles if p["model"] == name]
        eligible = any(p["display_filters_in_source"] for p in ports) if ports else None
        if supported and eligible is False:
            raise ValueError("Module enables a model without ML display-filter support: " + name)
        firmware_codes = sorted({p["firmware_code"] for p in ports} | {p["firmware"].replace(".", "") for p in supported})
        # Missing ML source is a real gap; do not invent a firmware version.
        firmware_inputs = {code: inspect_roms(rom_root, qemu, code, required_roms(descriptor))
                           for code in firmware_codes} if descriptor else {}
        blockers = []
        if eligible is not False:
            if not ports: blockers.append("ML target source is absent; LiveView-effect eligibility is unresolved")
            if not descriptor or qemu not in launcher: blockers.append("QEMU model is absent from the pinned emulator")
            if not supported: blockers.append("Module integration is not implemented for this model")
            if not any(p["native_raw"] for p in supported): blockers.append("Native RAW capture backend is not implemented")
            if not firmware_inputs or not any(f["available"] for f in firmware_inputs.values()): blockers.append("Camera ROM inputs are missing, have unexpected sizes, or look like placeholders")
        rows.append({"model": name, "qemu_model": qemu, "qemu_descriptor": descriptor, "ml_ports": ports,
                     "liveview_effect_eligible": eligible,
                     "scope_status": "eligible" if eligible else "excluded_no_liveview_effects" if eligible is False else "eligibility_unresolved",
                     "module_profiles": supported, "firmware_inputs": firmware_inputs,
                     "emulator_boot": "not_run", "module_loaded_in_emulator": "not_verified",
                     "raw_capture_in_emulator": "not_verified", "candidate_hardware_test": "not_tested",
                     "blockers": blockers})
    return {"scope": scope, "qemu_revision": QEMU_REVISION, "models": rows,
            "counts": {"official_models_reviewed": len(rows), "eligible_models": sum(r["liveview_effect_eligible"] is True for r in rows),
                       "excluded_models": sum(r["liveview_effect_eligible"] is False for r in rows),
                       "unresolved_models": sum(r["liveview_effect_eligible"] is None for r in rows),
                       "native_raw_implemented": sum(any(p["native_raw"] for p in r["module_profiles"]) for r in rows),
                       "preview_candidates": sum(bool(r["module_profiles"]) for r in rows),
                       "emulator_boots_verified": 0, "hardware_tests_verified": 0},
            "evidence_limit": "Static source/input audit only. ROM size/hash, compilation and model names do not prove a successful firmware boot, module load or capture."}


def markdown_report(report):
    lines = ["# Official-camera development matrix", "", report["evidence_limit"], "",
             "| Model | ML source firmware | Module candidate | Source core imports / fields | Distributed imports / peer API | ROMs available | Emulator / hardware |",
             "|---|---|---|---|---|---|---|"]
    for row in report["models"]:
        versions = ", ".join(p["firmware"] for p in row["ml_ports"]) or "Source missing"
        capability = ("Excluded: no ML LiveView effects" if row["liveview_effect_eligible"] is False else
                      "Eligibility unresolved" if row["liveview_effect_eligible"] is None else
                      "Native RAW + preview" if any(p["native_raw"] for p in row["module_profiles"]) else "Preview only" if row["module_profiles"] else "Port needed")
        available = ", ".join(code for code, state in row["firmware_inputs"].items() if state["available"]) or "No"
        state = "Outside requested support" if row["liveview_effect_eligible"] is False else (
            "ML + module init observed; preview / RAW / hardware untested" if row["module_loaded_in_emulator"] == "initialization_observed" else "Not tested")
        if row.get("experimental_canon_cr2") == "verified_generated_frame":
            state = "Patched emulator: generated Canon CR2 pixels verified; module RAW / hardware untested"
        if row.get("experimental_arm_mirror_probe") == "two_settings_verified":
            state = "Patched emulator: ARM mirror probe pixels verified; mirror.mo native / hardware untested"
        if row.get("research_main_module_capture"):
            state = "Research mirror.mo: saved mirrored CR2 pixels verified; synthetic input/software shutter; normal native / hardware untested"
        if row.get("research_main_module_sequence"):
            state = "Research mirror.mo: 3 saved CR2s + cancellation verified; synthetic/software inputs; normal native / hardware untested"
        checks = row.get("source_core_checks", [])
        core = "Not checked" if not checks else "Match" if all(c["result"] == "imports_and_checked_fields_match" for c in checks) else "; ".join(sorted({c["result"] for c in checks}))
        if row["liveview_effect_eligible"] is False: core = "Outside scope"
        distributed = "; ".join(c["target"] + " " + c["kind"].removesuffix("-distribution") + ": " + c["result"]
                                for c in row.get("distribution_checks", [])) or "Not checked"
        if row["liveview_effect_eligible"] is False: distributed = "Outside scope"
        lines.append(f'| {row["model"]} | {versions} | {capability} | {core} | {distributed} | {available} | {state} |')
    if "distribution_evidence_limit" in report:
        lines += ["", report["distribution_evidence_limit"]]
    if "synthetic_arm_binary_evidence_limit" in report:
        lines += ["", str(report["counts"]["synthetic_arm_binary_profile_runs_verified"]) +
                  " synthetic ARM module profile runs verified. " + report["synthetic_arm_binary_evidence_limit"]]
    lines += ["", "## Remaining work", ""]
    for reason, count in Counter(reason for row in report["models"] for reason in row["blockers"]).items():
        lines.append(f"- {count} models: {reason}.")
    lines += ["", "Firmware folders: `ROM_ROOT/QEMU_MODEL/FIRMWARE_CODE/` (for example `roms/EOSM/202/`).",
              "The report includes expected ROM filenames, sizes and any supplied-file hashes in its JSON companion.", ""]
    return "\n".join(lines)


def attach_core_checks(report, evidence, candidate_hashes):
    if evidence["revision"] != report["ml_source_revision"]:
        raise ValueError("Core audit ML source revision mismatch")
    records = {record["target"]: record for record in evidence["targets"]}
    if len(records) != len(evidence["targets"]):
        raise ValueError("Duplicate core audit targets")
    passed = 0
    for row in report["models"]:
        checks = []
        for profile in row["module_profiles"]:
            key = profile["model"] + "." + profile["firmware"].replace(".", "")
            record = records.get(key)
            check = {"target": key, "result": "not_checked"}
            if record:
                check["result"] = "core_build_failed"
                if record["build_result"] == "passed":
                    audits = record["candidate_audits"]
                    if set(audits) != set(candidate_hashes):
                        raise ValueError("Core audit candidate set mismatch")
                    for name, audit in audits.items():
                        if audit["module_sha256"] != candidate_hashes[name]:
                            raise ValueError("Stale core audit for " + name)
                    check["candidates"] = audits
                    check["result"] = "imports_and_checked_fields_match" if all(
                        a["result"] == "imports_resolve" and a["checked_struct_layouts"]["result"] == "checked_layouts_match"
                        for a in audits.values()) else "import_or_field_mismatch"
                    passed += check["result"] == "imports_and_checked_fields_match"
                if check["result"] != "imports_and_checked_fields_match":
                    row["blockers"].append(key + ": " + check["result"])
            checks.append(check)
        row["source_core_checks"] = checks
    report["counts"]["source_core_profiles_matching"] = passed
    report["core_evidence_limit"] = evidence["evidence_limit"]


def load_distribution_evidence(path):
    path = Path(path).resolve()
    evidence = json.loads(path.read_text(encoding="utf-8"))
    files = evidence["artifact_files"]
    if not {"mirror.mo", "input-receipt.json"} <= files.keys():
        raise ValueError("Distribution evidence lacks candidate/input snapshots")
    for name, expected in files.items():
        artifact = (path.parent / name).resolve()
        if not artifact.is_relative_to(path.parent) or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
            raise ValueError("Changed distribution evidence artifact: " + name)
    if files["mirror.mo"] != evidence["module_sha256"]:
        raise ValueError("Distribution candidate snapshot mismatch")
    for record in evidence["archives"]:
        if record["audit_result"] == "audited" and files.get(record["symbol_snapshot"]) != record["imports"]["symbol_table_sha256"]:
            raise ValueError("Distribution export snapshot mismatch")
    return evidence


def attach_distribution_checks(report, evidence, candidate_hashes):
    if evidence["kind"] != "static-distribution-audit" or evidence["module_sha256"] not in candidate_hashes.values():
        raise ValueError("Stale or unexpected distribution evidence")
    expected = {p["model"] + "." + p["firmware"].replace(".", "") for r in report["models"] for p in r["module_profiles"]}
    if len(evidence["eligible_profiles"]) != len(expected) or set(evidence["eligible_profiles"]) != expected:
        raise ValueError("Distribution audit scope mismatch")
    seen = set()
    counts = Counter()
    for record in evidence["archives"]:
        target, kind = record["target"], record["kind"]
        if target not in expected or kind not in ("official-distribution", "community-distribution"):
            raise ValueError("Distribution target/provenance outside scope")
        key = (target, kind, record.get("archive_sha256"))
        if key in seen:
            raise ValueError("Duplicate distribution check")
        seen.add(key)
        row = next(r for r in report["models"] if r["model"] == target.split(".")[0])
        check = {"target": target, "kind": kind, "result": "input_rejected"}
        if record["audit_result"] == "audited":
            if (record["imports"]["module_sha256"] != evidence["module_sha256"] or
                    record["module_initialization_verified"] or record["raw_capture_verified"] or record["hardware_verified"] or
                    record["imports"]["module_load_verified"] or record["imports"]["native_capture_verified"] or
                    record["core_field_layouts"] != "not_verified_no_dwarf"):
                raise ValueError("Distribution audit contains incompatible runtime/layout claims")
            check.update(imports=record["imports"], peer_api_result=record["peer_api_result"],
                         archive_sha256=record["archive_sha256"])
            match = record["imports"]["result"] == "imports_resolve" and record["peer_api_result"] == "peer_api_metadata_matches"
            check["result"] = "names_and_peer_metadata_match" if match else "import_or_peer_api_mismatch"
            counts[kind + "_archives_audited"] += 1
            counts[kind + "_archives_matching"] += match
        if check["result"] != "names_and_peer_metadata_match":
            row["blockers"].append(target + " " + kind + ": " + check["result"])
        row.setdefault("distribution_checks", []).append(check)
    audited = {r["target"] for r in evidence["archives"] if r["audit_result"] == "audited"}
    for target in sorted(expected - audited):
        row = next(r for r in report["models"] if r["model"] == target.split(".")[0])
        row.setdefault("distribution_checks", []).append({"target": target, "kind": "unavailable",
                                                         "result": "no_audited_archive"})
    for kind in ("official-distribution", "community-distribution"):
        for suffix in ("archives_audited", "archives_matching"):
            name = kind + "_" + suffix
            report["counts"][name] = counts[name]
    report["distribution_evidence_limit"] = evidence["evidence_limit"]


def attach_emulator_observation(report, observation, candidate_hashes):
    if observation["kind"] != "observed-qemu-module-initialization":
        raise ValueError("Unexpected emulator observation kind")
    row = next((r for r in report["models"] if r["model"] == observation["model"]), None)
    if not row or row["liveview_effect_eligible"] is not True or not any(p["firmware"] == observation["firmware"] for p in row["module_profiles"]):
        raise ValueError("Emulator observation is outside the eligible firmware scope")
    row.setdefault("emulator_observations", []).append(observation)
    if observation["artifacts"]["module"]["sha256"] not in candidate_hashes.values():
        return  # Retain historical evidence without claiming a current build passed.
    if observation["ml_startup_observed"]:
        row["emulator_boot"] = "ml_startup_observed"
    if observation["module_initialization_observed"]:
        if not observation["ml_startup_observed"]:
            raise ValueError("Module observation lacks ML startup evidence")
        row["module_loaded_in_emulator"] = "initialization_observed"
    report["counts"]["emulator_boots_verified"] = sum(r["emulator_boot"] == "ml_startup_observed" for r in report["models"])
    report["counts"]["emulator_module_initializations_observed"] = sum(r["module_loaded_in_emulator"] == "initialization_observed" for r in report["models"])


def attach_automated_matrix(report, observation, candidate_hashes):
    if observation['kind'] != 'automated-universal-module-matrix' or observation['hardware_test']:
        raise ValueError('Unexpected automated matrix kind/claims')
    if observation['module']['sha256'] not in candidate_hashes.values():
        raise ValueError('Automated matrix describes a different module')
    expected={p['model']+'.'+p['firmware'].replace('.','') for r in report['models'] for p in r['module_profiles']}
    targets=[r['target'] for r in observation['targets']]
    if len(set(targets))!=len(targets) or set(targets)!=expected:
        raise ValueError('Automated matrix does not match eligible firmware scope')
    for tested in observation['targets']:
        if tested['target']!=tested['model']+'.'+tested['firmware'].replace('.',''):
            raise ValueError('Automated model/firmware identity mismatch')
        row=next(r for r in report['models'] if r['model']==tested['model'])
        runtime=tested.get('runtime',{})
        if runtime.get('native_raw_capture_verified') or runtime.get('hardware_tested'):
            raise ValueError('Automated baseline cannot attest native capture or hardware')
        if runtime.get('module_initialization_observed') and not runtime.get('ml_startup_observed'):
            raise ValueError('Module initialization lacks ML startup evidence')
        row.setdefault('automated_firmware_results',[]).append({
            'target':tested['target'],'status':tested['status'],'runtime':runtime,
            'synthetic_module_fixture':tested.get('module_fixture'),
            'blockers':tested['blockers'],'crash_observations':tested.get('crash_observations',{})})
        if runtime.get('ml_startup_observed'):row['emulator_boot']='ml_startup_observed'
        if runtime.get('module_initialization_observed'):row['module_loaded_in_emulator']='initialization_observed'
    report['counts']['emulator_boots_verified']=sum(r['emulator_boot']=='ml_startup_observed' for r in report['models'])
    report['counts']['emulator_module_initializations_observed']=sum(r['module_loaded_in_emulator']=='initialization_observed' for r in report['models'])
    report['counts']['automated_profiles_enumerated']=len(targets)
    report['counts']['automated_on_off_cleanup_verified']=sum(bool(r.get('runtime',{}).get('effect_off_cleanup_observed')) for r in observation['targets'])
    report['counts']['synthetic_loaded_module_fixture_profiles_verified']=sum(bool(r.get('module_fixture',{}).get('verified')) for r in observation['targets'])


def attach_capture_research(report, observation, candidate_hashes):
    if observation["kind"] != "experimental-canon-cr2-output":
        raise ValueError("Unexpected capture research kind")
    row = next((r for r in report["models"] if r["model"] == observation["model"]), None)
    if not row or row["liveview_effect_eligible"] is not True or not any(
            p["firmware"] == observation["firmware"] for p in row["module_profiles"]):
        raise ValueError("Capture research is outside the eligible firmware scope")
    if observation["module"]["sha256"] not in candidate_hashes.values():
        return
    if not (observation["patched_emulator"] and observation["completed_canon_cr2_verified"] and
            observation["cr2"]["cr2_pixels_equal_sensor_roi"] and
            not observation["native_mirror_verified"] and not observation["hardware_test"]):
        raise ValueError("Capture research lacks generated-frame evidence or has incompatible claims")
    row["experimental_canon_cr2"] = "verified_generated_frame"
    row["capture_research"] = {"qemu_revision": observation["qemu_revision"],
        "cr2_sha256": observation["cr2"]["sha256"], "raw_pixels_checked": observation["cr2"]["raw_pixels_checked"],
        "synthetic_previews": True, "native_mirror_verified": False, "hardware_test": False}
    report["counts"]["experimental_generated_cr2_models_verified"] = sum(
        r.get("experimental_canon_cr2") == "verified_generated_frame" for r in report["models"])


def attach_arm_mirror_probe(report, observation, candidate_hashes):
    if observation["kind"] != "isolated-70d-arm-mirror-probe":
        raise ValueError("Unexpected ARM mirror probe kind")
    row = next((r for r in report["models"] if r["model"] == observation["model"]), None)
    if not row or row["liveview_effect_eligible"] is not True or not any(
            p["firmware"] == observation["firmware"] for p in row["module_profiles"]):
        raise ValueError("ARM mirror probe is outside the eligible firmware scope")
    if observation["mirror_module_sha256"] not in candidate_hashes.values():
        return
    mirrored = [r for r in observation["validation"]["runs"] if r["mode"] == 2]
    if not (observation["isolated_arm_mirror_probe_verified"] and observation["two_mirrored_shots_in_one_boot"] and
            not observation["normal_mirror_module_native_backend_tested"] and not observation["hardware_test"] and
            len(mirrored) == 2 and len({tuple(r["params"]) for r in mirrored}) == 2 and
            all(r["independent_expected_pixels_match"] and
                r["raw_pixels_checked"] == 20646144 for r in mirrored)):
        raise ValueError("ARM probe lacks pixel evidence or has incompatible support claims")
    row["experimental_arm_mirror_probe"] = "two_settings_verified"
    row["arm_mirror_probe"] = {"probe_module_sha256": observation["probe_module_sha256"],
        "params": [r["params"] for r in mirrored], "repeated_shot_verified": True,
        "normal_module_native_backend_tested": False, "hardware_test": False}
    report["counts"]["experimental_arm_mirror_probe_models_verified"] = sum(
        r.get("experimental_arm_mirror_probe") == "two_settings_verified" for r in report["models"])


def attach_main_module_research(report, observation, candidate_hashes):
    if observation["kind"] != "research-main-module-registered-cr2":
        raise ValueError("Unexpected research main-module capture kind")
    row = next((r for r in report["models"] if r["model"] == observation["model"]), None)
    if not row or row["liveview_effect_eligible"] is not True or not any(
            p["firmware"] == observation["firmware"] for p in row["module_profiles"]):
        raise ValueError("Research main-module capture is outside the eligible firmware scope")
    if observation["normal_module_sha256"] not in candidate_hashes.values():
        return
    if not (observation["main_saved_mirrored_cr2_verified"] and observation["off_cleanup_verified"] and
            observation["patched_emulator"] and observation["completion_only_preprocessing_model"] and
            observation["synthetic_preview_injected"] and observation["synthetic_sensor_input"] and
            observation["software_full_press_injected"] and not observation["real_liveview_delivery_verified"] and
            not observation["hardware_test"] and not observation["native_backend_enabled_in_normal_module"] and
            observation["module_sha256"] != observation["normal_module_sha256"] and
            observation["raw_pixels_checked"] == 20646144 and observation["raw_pixel_mismatches"] == 0 and
            observation["changed_pixels"] > 1000000 and observation["unchanged_margin_pixels"] == 684288 and
            observation["params"] == [180, 2, 2, 2]):
        raise ValueError("Research capture lacks pixel evidence or has incompatible support claims")
    row["research_main_module_capture"] = {key: observation[key] for key in (
        "module_sha256", "normal_module_sha256", "module_version", "qemu_revision", "qemu_sha256",
        "cr2_sha256", "params", "raw_pixels_checked", "raw_pixel_mismatches", "changed_pixels",
        "unchanged_margin_pixels", "observed_latch_to_stage_ms", "synthetic_preview_injected",
        "synthetic_sensor_input", "software_full_press_injected", "completion_only_preprocessing_model",
        "real_liveview_delivery_verified", "native_backend_enabled_in_normal_module", "hardware_test", "evidence_limit")}
    report["counts"]["research_main_module_cr2_models_verified"] = sum(
        bool(r.get("research_main_module_capture")) for r in report["models"])


def attach_native_sequence_research(report, observation, candidate_hashes):
    if observation["kind"] != "research-main-module-native-sequence-verified":
        raise ValueError("Unexpected research native sequence kind")
    row = next((r for r in report["models"] if r["model"] == observation["model"]), None)
    if not row or row["liveview_effect_eligible"] is not True or not any(
            p["firmware"] == observation["firmware"] for p in row["module_profiles"]):
        raise ValueError("Research native sequence is outside the eligible firmware scope")
    if observation["normal_module_sha256"] not in candidate_hashes.values():
        return
    shots = observation["shots"]
    if not (observation["consecutive_shots_in_one_boot_verified"] and observation["cancellation_before_mutation_verified"] and
            observation["off_cleanup_verified"] and observation["qmp_shutdown_verified"] and
            observation["synthetic_preview_injected"] and observation["synthetic_sensor_input"] and
            observation["software_full_press_injected"] and observation["software_liveview_start_injected"] and
            observation["completion_only_preprocessing_model"] and not observation["hardware_test"] and
            not observation["real_liveview_delivery_verified"] and not observation["native_backend_enabled_in_normal_module"] and
            observation["module_sha256"] != observation["normal_module_sha256"] and
            observation["raw_pixels_checked"] == 61938432 and observation["raw_pixel_mismatches"] == 0 and
            [shot["params"] for shot in shots] == [[180, 2, 2, 2], [180, 15, 3, 3], [180, 4, 2, 2]] and
            len({shot["cr2_sha256"] for shot in shots}) == 3 and
            all(shot["raw_pixels_checked"] == 20646144 and shot["raw_pixel_mismatches"] == 0 and
                shot["unchanged_margin_pixels"] == 684288 and shot["changed_pixels"] > 1000000 for shot in shots)):
        raise ValueError("Research native sequence lacks pixel/lifecycle evidence or has incompatible support claims")
    row["research_main_module_sequence"] = {key: observation[key] for key in (
        "module_sha256", "normal_module_sha256", "shots", "raw_pixels_checked", "raw_pixel_mismatches",
        "cancellation_before_mutation_verified", "consecutive_shots_in_one_boot_verified", "off_cleanup_verified",
        "qmp_shutdown_verified", "synthetic_preview_injected", "synthetic_sensor_input", "software_full_press_injected",
        "software_liveview_start_injected", "completion_only_preprocessing_model", "real_liveview_delivery_verified",
        "native_backend_enabled_in_normal_module", "hardware_test", "evidence_limit")}
    report["counts"]["research_main_module_sequence_models_verified"] = sum(
        bool(r.get("research_main_module_sequence")) for r in report["models"])


def frozen_research(path):
    observation = json.loads(path.read_text(encoding="utf-8"))
    if not observation.get("files") or "evidence_storage" not in observation:
        raise ValueError("Research evidence must be frozen before attaching")
    for name, expected in observation["files"].items():
        artifact = (ROOT / name).resolve()
        if not artifact.is_relative_to(ROOT) or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
            raise ValueError("Changed frozen research evidence: " + name)
    return observation


def attach_arm_binary_fixtures(report, observation, candidate_hashes):
    if observation["kind"] != "synthetic-arm-module-binaries" or any(observation[key] for key in (
            "canon_firmware_booted", "ml_loader_tested", "installed_core_layout_verified", "native_capture_verified",
            "hardware_tested", "module_source_recompiled")):
        raise ValueError("Synthetic ARM module result has incompatible claims")
    variants = observation["variants"]
    if len(variants) != 2 or {v["api_major"] for v in variants} != {7, 8} or not observation["deliberate_corruption_rejected"]:
        raise ValueError("Expected both API variants and a rejected corruption fixture")
    normal = next(v for v in variants if v["api_major"] == 8)
    if normal["module_sha256"] not in candidate_hashes.values():
        return
    expected = {(r["model"], p["firmware"]) for r in report["models"] for p in r["module_profiles"]}
    planned = {(p["model"], p["firmware"]) for p in observation["profiles"]}
    if planned != expected or len(observation["profiles"]) != len(expected):
        raise ValueError("Synthetic ARM result does not match eligible firmware scope")
    validated = []
    for variant in variants:
        if variant["preview_only"] != (variant["api_major"] == 7) or len(variant["cpus"]) != 2 or {
                cpu["cpu"] for cpu in variant["cpus"]} != {"arm946-eos", "arm946-eos5"}:
            raise ValueError("Missing ARM CPU or incorrect variant capability")
        for cpu in variant["cpus"]:
            profiles = cpu["profiles"]
            if (len(profiles) != len(expected) or {(p["model"], p["firmware"]) for p in profiles} != expected or
                    not all(cpu[k] for k in ("unsupported_firmware_refused", "preview_source_and_destination_checked",
                                            "off_on_and_cleanup_verified", "initial_review_seed_verified", "review_invalidates_delivery")) or
                    cpu["forbidden_sensor_reads"] != 0):
                raise ValueError("Incomplete synthetic ARM profile/lifecycle evidence")
            for profile in profiles:
                if not profile["passed"] or profile["height"] != (240 if profile["model"] == "1100D" else 480) or (
                        profile["native_backend_selected"] != (variant["api_major"] == 8 and profile["model"] == "EOSM")):
                    raise ValueError("Incorrect synthetic ARM profile result")
                validated.append((profile, variant["api_major"], variant["module_sha256"], cpu["cpu"]))
    if observation["profile_runs_verified"] != len(validated):
        raise ValueError("Synthetic ARM profile total mismatch")
    # Attach only after every variant/CPU passes; never modify Canon/core/hardware status.
    for profile, api, sha, cpu in validated:
        row = next(r for r in report["models"] if r["model"] == profile["model"])
        row.setdefault("synthetic_arm_module_binary", []).append({**profile, "api_major": api, "module_sha256": sha, "cpu": cpu})
    report["counts"]["synthetic_arm_binary_profile_runs_verified"] = len(validated)
    report["synthetic_arm_binary_evidence_limit"] = observation["evidence_limit"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("wsl", "docker"), default="wsl")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--rom-root", type=Path, default=ROOT / ".cache/roms")
    parser.add_argument("--automation-report", type=Path, help="Hash-verified automated results for the current shared module")
    parser.add_argument("--distribution-report", type=Path, help="Static cached-distribution audit; separate from runtime support")
    parser.add_argument("--main-capture-report", type=Path, help="Snapshot-backed research main-module CR2 result; never promotes normal native support")
    parser.add_argument("--native-sequence-report", type=Path, help="Snapshot-backed research consecutive CR2/cancellation result")
    parser.add_argument("--arm-binary-report", type=Path, help="Synthetic SDK ARM tests of actual API-8/API-7 module files; no Canon support promotion")
    args = parser.parse_args()
    scope = load_scope(ROOT / "targets/official-cameras.json")
    qemu = ROOT / ".cache/qemu-eos"
    revision = subprocess.check_output(["git", "-C", str(qemu), "rev-parse", "HEAD"], text=True).strip()
    if revision != QEMU_REVISION: raise RuntimeError("QEMU source revision mismatch")
    output = ROOT / "build/qemu-eos"
    output.mkdir(parents=True, exist_ok=True)
    runtime = LinuxRuntime(ROOT, args.runtime, "mirror-worlds-qemu-eos:bookworm", args.distro)
    runtime.run("gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I.cache/qemu-eos/hw/eos",
                "tools/qemu_model_inventory.c", ".cache/qemu-eos/hw/eos/model_list.c", "-o", "build/qemu-eos/model-inventory")
    descriptors = json.loads(runtime.output("build/qemu-eos/model-inventory"))
    (output / "model-inventory.json").write_text(json.dumps(descriptors, indent=2) + "\n", encoding="utf-8")
    report = create_matrix(scope, {d["model"]: d for d in descriptors}, launcher_models(qemu / "magiclantern/run_qemu.py"),
                           ROOT / ".cache/ml-upstream", module_profiles(ROOT / "modules/mirror/mirror_camera.c"), args.rom_root.resolve(), reference_ports())
    report["ml_source_revision"] = subprocess.check_output(["git", "-C", str(ROOT / ".cache/ml-upstream"), "rev-parse", "HEAD"], text=True).strip()
    core_evidence = ROOT / "build/camera-cores/import-audit.json"
    if core_evidence.is_file():
        hashes = {name: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for name, path in
                  (("legacy", "build/modules/mirror/mirror.mo"), ("upstream", "build/upstream/mirror/mirror.mo"))}
        attach_core_checks(report, json.loads(core_evidence.read_text(encoding="utf-8")), hashes)
    for path in sorted(output.glob("*-observation.json")):
        observation = json.loads(path.read_text(encoding="utf-8"))
        for artifact in observation["artifacts"].values():
            if hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() != artifact["sha256"]:
                raise ValueError("Changed emulator evidence artifact: " + artifact["path"])
        hashes = {name: hashlib.sha256((ROOT / candidate).read_bytes()).hexdigest() for name, candidate in
                  (("legacy", "build/modules/mirror/mirror.mo"), ("upstream", "build/upstream/mirror/mirror.mo"))}
        attach_emulator_observation(report, observation, hashes)
    capture_research = ROOT / "build/qemu-eos-70d-cr2/70D.112-cr2-observation.json"
    if capture_research.is_file():
        observation = json.loads(capture_research.read_text(encoding="utf-8"))
        for name, expected in observation["files"].items():
            artifact = (ROOT / name).resolve()
            if not artifact.is_relative_to(ROOT) or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
                raise ValueError("Changed capture research evidence: " + name)
        hashes = {name: hashlib.sha256((ROOT / candidate).read_bytes()).hexdigest() for name, candidate in
                  (("legacy", "build/modules/mirror/mirror.mo"), ("upstream", "build/upstream/mirror/mirror.mo"))}
        attach_capture_research(report, observation, hashes)
    arm_probe = ROOT / "build/70d-native-probe/70D.112-probe-observation.json"
    if arm_probe.is_file():
        observation = json.loads(arm_probe.read_text(encoding="utf-8"))
        for name, expected in observation["files"].items():
            artifact = (ROOT / name).resolve()
            if not artifact.is_relative_to(ROOT) or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
                raise ValueError("Changed ARM probe evidence: " + name)
        hashes = {name: hashlib.sha256((ROOT / candidate).read_bytes()).hexdigest() for name, candidate in
                  (("legacy", "build/modules/mirror/mirror.mo"), ("upstream", "build/upstream/mirror/mirror.mo"))}
        attach_arm_mirror_probe(report, observation, hashes)
    if args.automation_report:
        observation=json.loads(args.automation_report.read_text(encoding='utf-8'))
        for name,expected in observation['artifact_files'].items():
            artifact=(ROOT/name).resolve()
            if not artifact.is_relative_to(ROOT) or hashlib.sha256(artifact.read_bytes()).hexdigest()!=expected:
                raise ValueError('Changed automated evidence: '+name)
        hashes={name:hashlib.sha256((ROOT/candidate).read_bytes()).hexdigest() for name,candidate in
                (('legacy','build/modules/mirror/mirror.mo'),('upstream','build/upstream/mirror/mirror.mo'))}
        attach_automated_matrix(report,observation,hashes)
    if args.main_capture_report:
        observation = frozen_research(args.main_capture_report)
        hashes = {name: hashlib.sha256((ROOT / candidate).read_bytes()).hexdigest() for name, candidate in
                  (("legacy", "build/modules/mirror/mirror.mo"), ("upstream", "build/upstream/mirror/mirror.mo"))}
        attach_main_module_research(report, observation, hashes)
    if args.native_sequence_report:
        observation = frozen_research(args.native_sequence_report)
        hashes = {name: hashlib.sha256((ROOT / candidate).read_bytes()).hexdigest() for name, candidate in
                  (("legacy", "build/modules/mirror/mirror.mo"), ("upstream", "build/upstream/mirror/mirror.mo"))}
        attach_native_sequence_research(report, observation, hashes)
    if args.distribution_report:
        hashes = {name: hashlib.sha256((ROOT / candidate).read_bytes()).hexdigest() for name, candidate in
                  (("legacy", "build/modules/mirror/mirror.mo"), ("upstream", "build/upstream/mirror/mirror.mo"))}
        attach_distribution_checks(report, load_distribution_evidence(args.distribution_report), hashes)
    if args.arm_binary_report:
        observation = json.loads(args.arm_binary_report.read_text(encoding="utf-8"))
        for name, expected in observation["artifact_files"].items():
            artifact = (ROOT / name).resolve()
            if not artifact.is_relative_to(ROOT) or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
                raise ValueError("Changed synthetic ARM evidence: " + name)
        for variant in observation["variants"]:
            if observation["artifact_files"].get(variant["module_path"]) != variant["module_sha256"]:
                raise ValueError("Synthetic ARM module is not hash-bound to its input")
        hashes = {name: hashlib.sha256((ROOT / candidate).read_bytes()).hexdigest() for name, candidate in
                  (("legacy", "build/modules/mirror/mirror.mo"), ("upstream", "build/upstream/mirror/mirror.mo"))}
        attach_arm_binary_fixtures(report, observation, hashes)
    (output / "camera-matrix.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "camera-matrix.md").write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps(report["counts"]))
    print("Camera matrix: " + str(output / "camera-matrix.md"))

if __name__ == "__main__":
    main()
