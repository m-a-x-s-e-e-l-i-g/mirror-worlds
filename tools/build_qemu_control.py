"""Build the generic unshipped menu driver used by automated QEMU tests."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tools.build_module import UPSTREAM_REVISION, DEFAULT_SOURCE_DATE_EPOCH, normalize_module_metadata
from tools.linux_runtime import LinuxRuntime

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'.cache/ml-upstream'
    assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==UPSTREAM_REVISION
    stage=source/'modules/mxctl';stage.mkdir(exist_ok=True)
    inputs=sorted((ROOT/'tests/qemu_control').glob('*'))
    inputs += [ROOT/'modules/fx_common'/name for name in ('fx_effect.h','fx_pixels.h','fx_namespace.h','fx_mirror_registered.h','fx_mirror_raw.h')]
    inputs += [ROOT/'core/glitchlock.h']
    for path in inputs:shutil.copy2(path,stage/path.name)
    runtime=LinuxRuntime(ROOT,'wsl',wsl_user='root')
    relative=stage.relative_to(ROOT).as_posix()
    runtime.run('make','-B','build/module_strings.h',cwd=relative)
    normalize_module_metadata(stage/'build/module_strings.h',DEFAULT_SOURCE_DATE_EPOCH)
    runtime.run('make','-j2','FATAL_WARNINGS=y',cwd=relative)
    dest=ROOT/'build/qemu-control';dest.mkdir(exist_ok=True)
    for name in ('mxctl.mo','mxctl.sym','mxctl.dep'):shutil.copy2(stage/'build'/name,dest/name)
    imports=set((dest/'mxctl.dep').read_text().splitlines())
    module_imports={'mirror_controls','mirror_filter','mirror_delivered_state','mirror_gate_automatic','mirror_canon_gui',
        'mirror_mirror_raw_prepare','mirror_mirror_registered_workspace','mirror_mirror_registered_apply'}
    module_symbols={line.split()[1] for line in (ROOT/'build/modules/mirror/mirror.sym').read_text().splitlines()}
    assert module_imports<=module_symbols
    audit=json.loads((ROOT/'build/camera-cores/import-audit.json').read_text())
    targets=[]
    for record in audit['targets']:
        if record['build_result']!='passed':continue
        symbols=ROOT/'build/camera-cores'/record['target']/'magiclantern.sym'
        assert hashlib.sha256(symbols.read_bytes()).hexdigest()==record['symbol_table_sha256']
        exports={line.split()[1] for line in symbols.read_text().splitlines()}
        assert imports<=exports|module_imports,(record['target'],imports-exports-module_imports)
        targets.append(record['target'])
    report={'kind':'unshipped-generic-qemu-menu-driver','module_sha256':hashlib.sha256((dest/'mxctl.mo').read_bytes()).hexdigest(),
        'imports':sorted(imports),'cross_module_imports':sorted(module_imports),
        'source_files':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        'core_imports_verified':targets,'hardware_test':False}
    (dest/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Generic menu driver imports verified against',len(targets),'cores')


if __name__=='__main__':main()
