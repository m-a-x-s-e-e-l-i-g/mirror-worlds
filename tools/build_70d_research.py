"""Build the unshipped 70D QEMU hook probe without replacing mirror.mo or a candidate.

Requires the pinned upstream checkout and identified 70D ROM1 in the local cache.
The ROM is used only to verify and generate fixed instruction guards, never packaged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.linux_runtime import LinuxRuntime
from tools.build_module import UPSTREAM_REVISION, audit_module_headers, normalize_module_metadata, DEFAULT_SOURCE_DATE_EPOCH


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',choices=('wsl','docker'),default='wsl')
    parser.add_argument('--distro',default='Ubuntu')
    args=parser.parse_args()
    source=ROOT/'.cache/ml-upstream'
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    assert revision==UPSTREAM_REVISION
    rom=(ROOT/'.cache/roms/70D/112/ROM1.BIN').read_bytes()
    sha=hashlib.sha256(rom).hexdigest()
    assert sha=='3fe42299deb577b269b6901f40597a1939ac5876f22c8c3a0b6ee47219fdd42e'
    module=source/'modules/m70raw';module.mkdir(exist_ok=True)
    files=list((ROOT/'targets/70D.112/research').glob('*'))
    for p in files:
        if p.is_file():shutil.copy2(p,module/p.name)
    guards=[0xff361910,0xff2229b0,0xff222964,0xff41ea90,0xff437d58,0xff16ceb4]
    header='/* Generated from the identified 70D.112 ROM, not from a signature search. */\n'
    header+='static const struct {unsigned pc,words[4];} m70_guards[]={\n'
    for pc in guards:
        words=struct.unpack_from('<4I',rom,pc-0xff000000)
        header+='{'+hex(pc)+'u,{'+','.join(hex(w)+'u' for w in words)+'}},\n'
    header+='};\n#define M70_GUARDS (sizeof(m70_guards)/sizeof(m70_guards[0]))\n'
    (module/'rom_guards.h').write_text(header,newline='\n')
    (module/'shared').mkdir(exist_ok=True);(module/'engine').mkdir(exist_ok=True)
    shared=list((ROOT/'modules/fx_common').glob('*'))
    engine=[ROOT/'core/glitchlock.h',ROOT/'modules/glock/gl_format.c',ROOT/'modules/glock/gl_format.h']
    for p in shared:
        if p.is_file():shutil.copy2(p,module/'shared'/p.name)
    for p in engine:shutil.copy2(p,module/'engine'/p.name)
    runtime=LinuxRuntime(ROOT,args.runtime,distro=args.distro,wsl_user='root')
    directory='.cache/ml-upstream/modules/m70raw'
    runtime.run('make','-B','build/module_strings.h',cwd=directory)
    normalize_module_metadata(module/'build/module_strings.h',DEFAULT_SOURCE_DATE_EPOCH)
    runtime.run('make','-j2','FATAL_WARNINGS=y',cwd=directory)
    runtime.run('make','build/m70raw.debug.o','FATAL_WARNINGS=y',cwd=directory)
    runtime.run('arm-none-eabi-strip','--strip-debug','--strip-unneeded','--discard-all','--discard-locals',
        '-o','build/m70raw.debug-check.mo','build/m70raw.debug.o',cwd=directory)
    assert (module/'build/m70raw.debug-check.mo').read_bytes()==(module/'build/m70raw.mo').read_bytes()
    audit_module_headers(module)
    output=ROOT/'build/70d-native-probe';output.mkdir(exist_ok=True)
    for name in ('m70raw.mo','m70raw.dep','m70raw.sym','m70raw.debug.o'):
        shutil.copy2(module/'build'/name,output/name)
    shutil.copy2(module/'rom_guards.h',output/'rom_guards.h')
    inputs=[p for p in files+shared+engine if p.is_file()]+[Path(__file__)]
    exports={line.split()[1] for line in (ROOT/'.cache/70d-probe/card/ML/modules/70D_112.sym').read_text().splitlines() if len(line.split())==2}
    imports=(output/'m70raw.dep').read_text().splitlines()
    assert set(imports)<=exports,'Research module has unresolved 70D core imports'
    record={'kind':'unshipped-qemu-70d-raw-probe','model':'70D','firmware':'1.1.2',
        'ml_revision':revision,'rom1_sha256':sha,'native_backend_enabled':False,'hardware_test':False,
        'imports':imports,'exact_70d_core_imports_verified':True,'no_platform_headers':True,'debug_types_match_module':True,
        'source_files':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.suffix in ('.mo','.dep','.sym','.o','.h')}}
    (output/'build.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Built isolated research probe:',output/'m70raw.mo')


if __name__=='__main__':main()
