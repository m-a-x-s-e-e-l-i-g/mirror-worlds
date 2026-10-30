"""Linux executor for run_camera_matrix; private card copies, bounded observations, QMP shutdown."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
if __package__:
    from .camera_abi import inspect_abi,compare_abi
    from .analyze_qemu_boot import analyze
    from .audit_module import inspect_module
else:
    from camera_abi import inspect_abi,compare_abi
    from analyze_qemu_boot import analyze
    from audit_module import inspect_module

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def local(name):
    path=(ROOT/name).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Path outside workspace')
    return path


def qmp(path,command):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(5);sock.connect(str(path));stream=sock.makefile('rwb',buffering=0);stream.readline()
        for request in ({'execute':'qmp_capabilities'},command):
            stream.write((json.dumps(request)+'\n').encode())
            while True:
                reply=json.loads(stream.readline())
                if 'error' in reply:raise RuntimeError(str(reply['error']))
                if 'return' in reply:break
        return reply['return']


def state_marker(text,name):
    rows=[json.loads(line[len(name)+1:]) for line in text.splitlines() if line.startswith(name+'=')]
    if len(rows)!=1:raise ValueError('Expected one '+name+' observation')
    return rows[0]


def run_target(row,report,output,offsets,module_abi):
    dest=output/row['target'];dest.mkdir()
    bundle=row['bundle'];artifacts=bundle['artifacts']
    for artifact in artifacts.values():
        if digest(local(artifact['path']))!=artifact['sha256']:raise ValueError('Bundle changed before run')
    core=local(artifacts['core']['path']);symbols=local(artifacts['symbols']['path'])
    row['actual_bundle_abi']=compare_abi(module_abi,inspect_abi(core))
    imports=set(inspect_module((output/'mirror.mo').read_bytes())['imports'])
    exports={line.split()[1] for line in symbols.read_text().splitlines()}
    row['actual_bundle_missing_imports']=sorted(imports-exports)
    if imports-exports or row['actual_bundle_abi']['result']!='checked_layouts_match':
        row['status']='failed_bundle_abi';return
    native=Path(tempfile.mkdtemp(prefix='mirror-matrix-',dir=Path.home()/'.cache/mirror-worlds'))
    row['private_virtual_cards']=str(native)
    rom=native/'roms'/row['qemu_model']/row['firmware'].replace('.','');rom.mkdir(parents=True)
    for item in row['roms']:
        src=local(item['path']);assert digest(src)==item['sha256']
        shutil.copyfile(src,rom/item['name'])
    for kind in ('sd','cf'):
        subprocess.run(['cp','--sparse=always',str(local(artifacts[kind]['path'])),str(native/(kind+'.raw'))],check=True)
    image=native/'sd.raw'
    with image.open('rb') as stream:sector=stream.read(512)
    assert sector[510:512]==b'\x55\xaa'
    partition=struct.unpack_from('<I',sector,454)[0]*512
    assert 512<=partition<image.stat().st_size
    target=str(image)+'@@'+str(partition)
    def mcopy(src,dst):subprocess.run(['mcopy','-o','-i',target,str(src),str(dst)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    # Verify the card's boot image/exports against its matching ELF cohort before replacement.
    for kind,card in (('autoexec','::/autoexec.bin'),('symbols','::/ML/modules/'+bundle['symbol_name'])):
        extracted=dest/(kind+'.from-card');mcopy(card,extracted)
        assert digest(extracted)==artifacts[kind]['sha256'],'Incoherent card '+kind
    subprocess.run(['mdel','-i',target,'::/ML/SETTINGS/*.en'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['mdel','-i',target,'::/ML/MODULES/LOADING.LCK'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for name in ('mirror0.prf','mirror1.prf'):
        subprocess.run(['mdel','-i',target,'::/ML/SETTINGS/'+name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for module in ('mirror','mxctl'):
        src=output/('mirror.mo' if module=='mirror' else 'mxctl.mo')
        mcopy(src,'::/ML/modules/'+module+'.mo')
        check=dest/(module+'.from-card');mcopy('::/ML/modules/'+module+'.mo',check)
        assert digest(check)==digest(src),'Card module differs from shared bytes'
        flag=dest/(module+'.en');flag.write_bytes(b'');mcopy(flag,'::/ML/SETTINGS/'+module+'.en')
    shutil.copyfile(core,dest/'core.elf')
    context={'debug':str(output/'mirror.debug.o'),'observer':str(ROOT/'tools/qemu_module_state.gdb.py'),**offsets}
    observer=dest/'observer-context.json'
    sock=native/'qmp.sock'
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    command=[str(local(report['qemu_binary']['path'])),'-M',row['qemu_model']+',firmware='+row['firmware'].replace('.','')+';boot=1',
        '-display','none','-monitor','none','-serial','file:'+str(dest/'serial.log'),'-no-reboot','-d','guest_errors',
        '-qmp','unix:'+str(sock)+',server,nowait','-gdb','tcp:127.0.0.1:'+str(port),
        '-drive','if=sd,format=raw,file='+str(image),'-drive','if=ide,format=raw,file='+str(native/'cf.raw')]
    def observe(label,action=0):
        observer.write_text(json.dumps({**context,'action':action}))
        result=subprocess.run(['gdb-multiarch','--nx','--batch','-ex','set pagination off','-ex','file '+str(dest/'core.elf'),
            '-ex','target remote 127.0.0.1:'+str(port),'-ex','source '+str(ROOT/'tools/qemu_matrix_state.gdb.py'),'-ex','detach'],
            env={**os.environ,'MIRROR_MATRIX_CONTEXT':str(observer)},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
        (dest/(label+'.log')).write_text(result.stdout)
        return result.stdout
    with (dest/'qemu.log').open('w') as log:
        process=subprocess.Popen(command,env={**os.environ,'QEMU_EOS_WORKDIR':str(native/'roms')},stdout=log,stderr=log)
        row['command']=command
        try:
            deadline=time.monotonic()+report['boot_seconds'];attempt=0
            row['status']='boot_observation_timeout'
            while process.poll() is None and time.monotonic()<deadline:
                time.sleep(2);attempt+=1
                try:
                    text=observe('boot-'+str(attempt));boot=state_marker(text,'MIRROR_QEMU_STATE')
                    if boot['ml_started']!=1:continue
                    measured=analyze((dest/'serial.log').read_text(errors='replace'),text,row['firmware'],bundle['canon_id'])
                    row['runtime']={**measured,'raw_capture':'not_run_no_delivered_preview'}
                    if not measured['module_initialization_observed']:
                        if measured['module_initialization_failed_observed']:
                            row['status']='module_initialization_failed';break
                        row['status']='module_initialization_pending';continue
                    row['status']='module_initialized'
                    # Normal virtual LiveView button and normal ML menu API; no synthetic frames/globals.
                    qmp(sock,{'execute':'send-key','arguments':{'keys':[{'type':'qcode','data':'l'}],'hold-time':100}})
                    observe('enable-effect',1);time.sleep(3)
                    live=observe('liveview');runtime=state_marker(live,'MIRROR_QEMU_STATE')
                    fx=state_marker(live,'MIRROR_MATRIX_STATE');ctl=state_marker(live,'MIRROR_MATRIX_CONTROL')
                    row['runtime'].update({'liveview_flag':bool(runtime['lv']),'preview_frames':fx['preview']['frames'],
                        'module_reports':fx,'effect_menu_command':ctl,'preview_rendering_observed':fx['preview']['frames']>0})
                    if not fx['preview']['frames'] and fx['preview']['running']:
                        row['runtime']['menu_waits_for_first_frame_observed']=ctl.get('menu_status')==2
                    row['status']='rendering_observed' if fx['preview']['frames'] else 'emulator_limit_no_preview_delivery'
                    if ctl['completed']!=0x4d570001 or ctl['result']!=1:row['status']='effect_menu_activation_failed'
                    if report.get('module_fixtures') and ctl['result']==1:
                        # The preceding Canon observations remain untouched. Fixture-induced
                        # canvas/frame counts are never promoted to normal LiveView evidence.
                        row['module_fixture']={'kind':'synthetic-buffers-through-actual-loaded-module','canon_liveview_delivery':False}
                        asserted=False
                        for action,label in ((3,'fixture-positive'),(4,'fixture-corrupted-output')):
                            observe(label+'-queued',action)
                            fixture_deadline=time.monotonic()+90;poll=0
                            while process.poll() is None and time.monotonic()<fixture_deadline:
                                time.sleep(2);poll+=1
                                observation=observe(label+'-'+str(poll))
                                result=state_marker(observation,'MIRROR_MATRIX_CONTROL')
                                if re.search(r'ASSERT\s*:',(dest/'serial.log').read_text(errors='replace')):
                                    row['module_fixture'][label]={'status':'canon_assert_observed'};asserted=True;break
                                if result['completed']==0x4d570000+action:
                                    row['module_fixture'][label]=result;break
                            else:row['module_fixture'][label]={'status':'observation_timeout'}
                            if asserted:break
                        positive=row['module_fixture'].get('fixture-positive',{})
                        negative=row['module_fixture'].get('fixture-corrupted-output',{})
                        row['module_fixture']['registered_raw_verified']=positive.get('raw_cases')==88 and positive.get('raw_checked')==88*32*24 and positive.get('raw_negative')==1
                        row['module_fixture']['verified']=positive.get('result')==1 and positive.get('fixture_layouts')==44 and positive.get('fixture_checked')==44*fx['vram']['height']*1440 and positive.get('fixture_delivery_checks')==3 and row['module_fixture']['registered_raw_verified'] and negative.get('result')==-15 and negative.get('fixture_layouts')==0 and negative.get('fixture_checked',0)>0
                        if asserted:row['status']='canon_assert_observed';break
                    observe('disable-effect',2);time.sleep(1);cleanup=observe('cleanup')
                    off=state_marker(cleanup,'MIRROR_MATRIX_STATE');off_ctl=state_marker(cleanup,'MIRROR_MATRIX_CONTROL')
                    row['runtime']['effect_off_cleanup_observed']=off_ctl['completed']==0x4d570002 and off_ctl['result']==1 and not off['preview']['running'] and not off['preview']['allocated']
                    break
                except (subprocess.TimeoutExpired,ValueError,OSError) as exc:
                    row.setdefault('observation_errors',[]).append(str(exc))
                    if row.get('runtime',{}).get('module_initialization_observed'):
                        row['status']='runtime_observation_failed';break
                    # Observation failure never starts another VM. Poll this same process until deadline.
            if row['status']=='module_initialization_pending':row['status']='module_initialization_observation_timeout'
            if process.poll() is not None:row['status']='emulator_exited';row['emulator_exit_code']=process.returncode
        finally:
            if process.poll() is None:
                try:qmp(sock,{'execute':'quit'});process.wait(timeout=5);row['shutdown']='qmp'
                except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired):
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                    row['shutdown']='forced_owned_process'
            row['emulator_exit_code']=process.returncode
    diagnostic=(dest/'qemu.log').read_text(errors='replace')+(dest/'serial.log').read_text(errors='replace')
    row['crash_observations']={'unmapped_reads':len(re.findall(r'MEMTX invalid read',diagnostic)),
        'canon_assert_lines':[s for s in diagnostic.splitlines() if re.search(r'ASSERT|assert failed|Assert failed',s)][:20]}
    row['evidence_files']={p.relative_to(ROOT).as_posix():digest(p) for p in dest.iterdir() if p.is_file()}


def main():
    plan=local(sys.argv[1]);output=plan.parent;report=json.loads(plan.read_text())
    for key,name in (('module','mirror.mo'),('controller','mxctl.mo')):
        src=local(report[key]['path']);assert digest(src)==report[key]['sha256'];shutil.copyfile(src,output/name)
    debug=local(report['module']['debug_path']);assert digest(debug)==report['module']['debug_sha256']
    shutil.copyfile(debug,output/'mirror.debug.o')
    stripped=output/'debug-check.mo'
    subprocess.run(['arm-none-eabi-strip','--strip-debug','--strip-unneeded','--discard-all','--discard-locals','-o',str(stripped),str(debug)],check=True)
    assert digest(stripped)==report['module']['sha256'],'Debug object differs from tested module'
    assert digest(local(report['qemu_binary']['path']))==report['qemu_binary']['sha256']
    nm=subprocess.check_output(['arm-none-eabi-nm',str(debug)],text=True)
    def offset(kind,name):
        matches=re.findall(r'^([0-9a-f]+) '+kind+' '+name+r'$',nm,re.M)
        if len(matches)!=1:raise ValueError('Missing or ambiguous observer symbol: '+name)
        return int(matches[0],16)
    offsets={'init_offset':offset('t','init'),'active_offset':offset('[bB]','mirror_active')}
    module_abi=inspect_abi(debug)
    for row in report['targets']:
        if row['status']=='ready':
            try:run_target(row,report,output,offsets,module_abi)
            except Exception as exc:row['status']='runner_failed';row['blockers'].append(type(exc).__name__+': '+str(exc))
        print(row['target']+': '+row['status'],flush=True)
        report['counts']=dict(Counter(r['status'] for r in report['targets']))
        (output/'results.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
