"""Run one actual Mirror module across the eligible firmware matrix in isolated QEMU cards.

Missing inputs are explicit skips. Source ABI, measured runtime state and hardware
validation remain separate. Input bundles live at .cache/qemu-inputs/TARGET.json.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import uuid
from tools.camera_matrix import create_matrix, load_scope, launcher_models, module_profiles, reference_ports
from tools.build_qemu_eos import REVISION
from tools.linux_runtime import LinuxRuntime

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def workspace_path(name, root=ROOT):
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Input must stay inside workspace: '+str(name))
    return path


def plan_targets(matrix, bundles, root=ROOT):
    rows=[]
    for model in matrix['models']:
        for profile in model['module_profiles']:
            target=profile['model']+'.'+profile['firmware'].replace('.','')
            inputs=model['firmware_inputs'].get(profile['firmware'].replace('.',''),{})
            row={'target':target,'model':profile['model'],'firmware':profile['firmware'],
                 'qemu_model':model['qemu_model'],'native_backend_implemented':profile['native_raw'],
                 'status':'ready','blockers':[],'roms':[{**item,'path':workspace_path(item['path'],root).relative_to(root).as_posix()} for item in inputs.get('files',[])]}
            bundle=Path(bundles)/(target+'.json')
            if not inputs.get('available'):
                row['status']='skipped_missing_roms';row['blockers'].append('Required non-placeholder ROM inputs unavailable')
            elif not bundle.is_file():
                row['status']='skipped_missing_core_card_bundle';row['blockers'].append('Matching core ELF, boot image, symbols and virtual cards unavailable')
            else:
                try:
                    data=json.loads(bundle.read_text(encoding='utf-8'))
                    if data.get('target')!=target:raise ValueError('Core/card bundle target mismatch: '+target)
                    if not data.get('canon_id') or not data.get('symbol_name'):raise ValueError('Bundle identity is incomplete')
                    if '/' in data['symbol_name'] or '\\' in data['symbol_name']:raise ValueError('Invalid card symbol filename')
                    for name in ('core','autoexec','symbols','sd','cf'):
                        artifact=data['artifacts'][name]
                        if digest(workspace_path(artifact['path'],root))!=artifact['sha256']:
                            raise ValueError('Core/card bundle changed: '+target+' / '+name)
                    row['bundle']=data
                except (KeyError,ValueError,OSError) as exc:
                    row['status']='skipped_invalid_core_card_bundle';row['blockers'].append(str(exc))
            rows.append(row)
    return rows


def markdown_report(report):
    lines=['# Universal Mirror Worlds compatibility run','',
        'One module SHA-256: `'+report['module']['sha256']+'`','',
        '| Firmware | Source ABI | Emulator | Module init | LiveView | Canon frames | RAW integration | Module buffer fixture |',
        '|---|---|---|---|---|---|---|---|']
    for row in report['targets']:
        stages=row.get('runtime',{})
        lines.append('| '+ ' | '.join(str(v) for v in [row['target'],row.get('source_abi','not_checked'),
            row['status'],stages.get('module_initialization_observed',False),stages.get('liveview_flag',False),
            stages.get('preview_frames',0),stages.get('raw_capture','not_run'),
            '44 layouts + corruption rejection' if row.get('module_fixture',{}).get('verified') else 'Not verified'])+' |')
    lines+=['','Skipped inputs and emulator limits do not establish camera incompatibility.',
        'Frame counters are runtime observations; independent pixel oracles and physical camera tests are separate.',
        'Hardware validation remains required on every candidate firmware.','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--host-tests',action='store_true',help='Also run sanitizer fixtures and both QEMU ARM CPU preview oracles')
    parser.add_argument('--module-fixtures',action='store_true',help='Exercise the actual loaded module with owned synthetic image buffers, separately from Canon LiveView')
    parser.add_argument('--distro',default='Ubuntu')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--boot-seconds',type=int,default=45)
    args=parser.parse_args()
    if not 5<=args.boot_seconds<=180:parser.error('Boot observation budget must be 5..180 seconds')
    source=ROOT/'.cache/qemu-eos'
    actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if actual!=REVISION:raise ValueError('Pinned QEMU source revision mismatch')
    subprocess.run(['git','-C',str(source),'diff','--quiet','HEAD','--'],check=True)
    inventory=json.loads((ROOT/'build/qemu-eos/model-inventory.json').read_text())
    matrix=create_matrix(load_scope(ROOT/'targets/official-cameras.json'),{r['model']:r for r in inventory},
        launcher_models(source/'magiclantern/run_qemu.py'),ROOT/'.cache/ml-upstream',
        module_profiles(ROOT/'modules/mirror/mirror_camera.c'),ROOT/'.cache/roms',reference_ports())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    output=workspace_path(args.output or Path('build/compatibility')/stamp)
    output.mkdir(parents=True,exist_ok=False)
    candidate=ROOT/'build/modules/mirror/mirror.mo'
    manifest=json.loads(candidate.with_name('build.json').read_text())
    if manifest.get('research_70d'):raise ValueError('Universal baseline must use the normal shared module')
    report={'kind':'automated-universal-module-matrix','qemu_revision':REVISION,'hardware_test':False,
        'module':{'path':candidate.relative_to(ROOT).as_posix(),'sha256':digest(candidate),
                  'debug_path':candidate.with_name('mirror.debug.o').relative_to(ROOT).as_posix(),
                  'debug_sha256':digest(candidate.with_name('mirror.debug.o'))},
        'identical_upstream_binary':candidate.read_bytes()==(ROOT/'build/upstream/mirror/mirror.mo').read_bytes(),
        'scope_counts':matrix['counts'],'excluded_models':[r['model'] for r in matrix['models'] if r['liveview_effect_eligible'] is False],
        'boot_seconds':args.boot_seconds,'targets':plan_targets(matrix,ROOT/'.cache/qemu-inputs'),
        'module_fixtures':args.module_fixtures,
        'qemu_binary':{'path':'build/qemu-eos/qemu-system-arm','sha256':digest(ROOT/'build/qemu-eos/qemu-system-arm')},
        'controller':{'path':'build/qemu-control/mxctl.mo','sha256':digest(ROOT/'build/qemu-control/mxctl.mo')}}
    source_names=['tools/run_camera_matrix.py','tools/run_camera_matrix_linux.py','tools/qemu_matrix_state.gdb.py',
        'tools/qemu_module_state.gdb.py','tools/camera_abi.py','tools/analyze_qemu_boot.py','tools/audit_module.py',
        'tools/camera_matrix.py','tools/build_qemu_control.py','scripts/test_portability.py','scripts/test_arm_preview.py']
    source_names += [p.relative_to(ROOT).as_posix() for p in (ROOT/'tests/qemu_control').iterdir() if p.is_file()]
    source_names += ['modules/fx_common/'+name for name in ('fx_effect.h','fx_pixels.h','fx_namespace.h')]
    source_names += [p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').rglob('*') if p.is_file() and p.suffix in ('.c','.h')]
    for name,expected in manifest['source_files'].items():
        if digest(ROOT/name)!=expected:raise ValueError('Module source changed since build: '+name)
        source_names.append(name)
    source_names=sorted(set(source_names))
    report['runner_sources']={name:digest(ROOT/name) for name in source_names}
    audits=json.loads((ROOT/'build/camera-cores/import-audit.json').read_text())
    for row in report['targets']:
        record=next((r for r in audits['targets'] if r['target']==row['target']),{})
        audit=record.get('candidate_audits',{}).get('legacy',{})
        if record.get('build_result')=='passed':
            if audit.get('module_sha256')!=report['module']['sha256']:raise ValueError('Stale source ABI audit')
            row['source_abi']='checked_fields_match' if audit['result']=='imports_resolve' and audit['checked_struct_layouts']['result']=='checked_layouts_match' else 'failed'
        else:row['source_abi']='core_build_failed'
    plan=output/'plan.json';plan.write_text(json.dumps(report,indent=2)+'\n')
    if not args.plan_only:
        host_results={}
        if args.host_tests:
            for name,script,options in [('sanitizers','scripts/test_portability.py',['--sanitize']),('arm_preview','scripts/test_arm_preview.py',[])]:
                print('Running '+name+' oracles',flush=True)
                with (output/(name+'.log')).open('w') as log:
                    subprocess.run([sys.executable,script,'--runtime','wsl','--distro',args.distro,*options],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
                host_results[name]={'passed':True,'log_sha256':digest(output/(name+'.log')),
                    'evidence_limit':'Actual shared-code pixel/control fixtures; not Canon firmware/module/hardware proof'}
            shutil.copyfile(ROOT/'build/tests/arm-preview.json',output/'arm-preview.json')
        LinuxRuntime(ROOT,'wsl',distro=args.distro).run('python3','tools/run_camera_matrix_linux.py',plan.relative_to(ROOT).as_posix())
        report=json.loads((output/'results.json').read_text())
        report['host_tests']=host_results
        for name,expected in report['runner_sources'].items():
            if digest(ROOT/name)!=expected:raise ValueError('Runner changed during test: '+name)
            dest=output/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(ROOT/'build/camera-cores/import-audit.json',output/'source-core-audit.json')
        shutil.copyfile(candidate.with_name('build.json'),output/'module-build.json')
        report['artifact_files']={p.relative_to(ROOT).as_posix():digest(p) for p in output.rglob('*') if p.is_file() and p.name not in ('results.json','results.md')}
        (output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    else:report['counts']=dict(Counter(r['status'] for r in report['targets']))
    (output/'results.md').write_text(markdown_report(report),encoding='utf-8')
    print(json.dumps(report['counts']))
    print('Compatibility report:',output/'results.md')


if __name__=='__main__':main()
