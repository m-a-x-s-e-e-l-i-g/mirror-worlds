"""Verify the isolated 70D readout contract and Canon-saved probe photos.

The probe uses actual ARM Mirror transform code at a firmware hook. This does
not test the main mirror.mo controls/backend, a physical camera, or a sensor lease.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.linux_runtime import LinuxRuntime
from test_qemu_cr2 import tiff_ifds


def sensor_oracle(np):
    period=np.empty(1<<20,dtype=np.uint16)
    seed=0x12345678&((1<<20)-1)
    for i in range(len(period)):
        seed=(seed*1103515245+12345)&((1<<20)-1)
        period[i]=2048+((seed>>16)&15)-8
    pixels=np.empty((3708,5568),dtype=np.uint16)
    x=np.arange(5568,dtype=np.uint32)
    for y in range(3708):pixels[y]=period[((y+10)*5648+72+x)&((1<<20)-1)]
    return pixels


def axis(extent,divisor,low,high,np):
    positions=np.arange(extent,dtype=np.int32)
    border=extent//divisor
    # The oracle works in Bayer cells, independently of the packed C engine.
    return np.where((positions<border)&bool(low),2*border-1-positions,
                    np.where((positions>=extent-border)&bool(high),2*(extent-border)-1-positions,positions))


def check_run(run,np,rawpy):
    from PIL import Image
    states=re.findall(r'^M70RAW_STATE=(.+)$',(run/'gdb-probe-status.log').read_text(),re.M)
    assert len(states)==1
    state=json.loads(states[0])
    assert state['phase']==3 and state['error']==0 and state['installed']==63
    assert state['overlaps']==0 and state['before_hash']==state['after_hash'] and state['before_hash']
    assert 100000<=state['hold_us']<250000
    assert state['consumer_events']>=3 and 0xff437d58 in state['consumer_pc']
    assert state['binding']['xn']==3719 and state['binding']['yb']==0
    log=(run/'qemu.log').read_text(errors='replace')
    assert 'ASSERT :' not in log and 'MEMTX invalid' not in log
    files=list(run.glob('*.CR2'));assert len(files)==1
    assert files[0].name+' write done' in log
    data=files[0].read_bytes();tables=tiff_ifds(data)
    assert tables[3][0xc640]==[1,2784,2784]
    start,size=tables[3][273][0],tables[3][279][0]
    assert data[start:start+size]==(run/'jp57-output.ljpeg').read_bytes()
    baseline=sensor_oracle(np);expected=baseline.copy()
    mode=state['mode'];params=state['params']['value']
    assert params[0]==180
    if mode==2:
        assert state['changed']==1 and state['transform_us']>0
        edges,dx,dy=params[1:4]
        assert edges in (1,2,4,8,3,12,15) and 2<=dx<=6 and 2<=dy<=6
        cx=axis(2736,dx,edges&1,edges&2,np)
        cy=axis(1824,dy,edges&4,edges&8,np)
        xs=84+np.repeat(cx,2)*2+np.tile([0,1],2736)
        ys=50+np.repeat(cy,2)*2+np.tile([0,1],1824)
        expected[50:3698,84:5556]=baseline[ys[:,None],xs[None,:]]
    else:
        assert mode==1 and state['changed']==0 and state['transform_us']==0
    with rawpy.imread(str(files[0])) as raw:
        decoded=raw.raw_image.copy();preview=raw.extract_thumb().data
    thm_start,thm_size=tables[1][513][0],tables[1][514][0]
    for jpeg,dimensions in ((preview,(5472,3648)),(data[thm_start:thm_start+thm_size],(160,120))):
        with Image.open(io.BytesIO(jpeg)) as image:
            image.load();assert image.size==dimensions and image.mode=='L' and image.getextrema()==(128,128)
    assert decoded.shape==expected.shape
    mismatch=int(np.count_nonzero(decoded!=expected))
    assert mismatch==0,'Canon CR2 differs from the independent expected mirror: '+str(mismatch)
    changed=int(np.count_nonzero(decoded!=baseline))
    assert (changed>1000000) if mode==2 else changed==0
    margin=np.ones(decoded.shape,dtype=bool);margin[50:3698,84:5556]=False
    assert np.array_equal(decoded[margin],baseline[margin])
    return {'run':run.relative_to(ROOT).as_posix(),'mode':mode,'params':params[:4],
        'raw_pixels_checked':int(decoded.size),'independent_expected_pixels_match':True,
        'unchanged_margin_pixels':int(np.count_nonzero(margin)),'changed_pixels':changed,
        'hold_us':state['hold_us'],'transform_us':state['transform_us'],
        'consumer_overlap_observed':False,'cr2_sha256':hashlib.sha256(data).hexdigest(),
        'synthetic_previews_decode':True,
        'probe_module_sha256':hashlib.sha256((run/'image-m70raw.mo').read_bytes()).hexdigest(),
        'mirror_module_native_backend_tested':False,'hardware_test':False}


def check_refusal(run,np,rawpy):
    states=re.findall(r'^M70RAW_STATE=(.+)$',(run/'gdb-probe-status.log').read_text(),re.M)
    assert len(states)==1
    state=json.loads(states[0])
    assert state['phase']==4 and state['error']==2 and state['changed']==0
    assert state['before_hash']==state['after_hash']==state['hold_us']==state['transform_us']==0
    files=list(run.glob('*.CR2'));assert len(files)==1
    with rawpy.imread(str(files[0])) as raw:decoded=raw.raw_image.copy()
    assert np.array_equal(decoded,sensor_oracle(np))
    return {'run':run.relative_to(ROOT).as_posix(),'readout_mismatch_refused_before_sampling':True,
        'original_cr2_pixels_checked':int(decoded.size),'original_pixels_unchanged':True,
        'probe_module_sha256':hashlib.sha256((run/'image-m70raw.mo').read_bytes()).hexdigest(),
        'hardware_test':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',choices=('wsl','docker'),default='wsl')
    parser.add_argument('--distro',default='Ubuntu')
    parser.add_argument('--qemu-run',type=Path,action='append',default=[])
    parser.add_argument('--refused-run',type=Path)
    args=parser.parse_args()
    out=ROOT/'build/tests/70d-raw-probe';out.mkdir(parents=True,exist_ok=True)
    runtime=LinuxRuntime(ROOT,args.runtime,distro=args.distro)
    runtime.run('gcc','-std=c99','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-fno-sanitize-recover=all','-no-pie','-O1','-g','tests/70d_raw_contract.c','-o','build/tests/70d-raw-probe/contract')
    runtime.run('build/tests/70d-raw-probe/contract')
    result={'kind':'isolated-70d-arm-mirror-research','readout_contract_sanitizers_passed':True,
        'mirror_module_native_backend_tested':False,'hardware_test':False,'runs':[]}
    if args.qemu_run or args.refused_run:
        import numpy as np
        import rawpy
        for path in args.qemu_run:
            run=path.resolve()
            if not run.is_relative_to(ROOT):parser.error('QEMU run must remain inside the workspace')
            result['runs'].append(check_run(run,np,rawpy))
        if args.refused_run:
            run=args.refused_run.resolve()
            if not run.is_relative_to(ROOT):parser.error('QEMU run must remain inside the workspace')
            result['refusal']=check_refusal(run,np,rawpy)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
