"""Compare the one-shot EOSM mirrored rectangle with its original CR2, read-only.

Strict logged readback and decoded-file observations are separate. A fitted CFA
offset is descriptive, not firmware ownership/coherence or Canon review proof.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
if __package__:
    from .analyze_mirror_capture_gate import analyze as analyze_gate,parse
    from .analyze_mirror_native_trace import analyze_trace
else:
    from analyze_mirror_capture_gate import analyze as analyze_gate,parse
    from analyze_mirror_native_trace import analyze_trace


def unpack(words):
    out=[]
    for row in range(2):
        bits=sum(words[row*7+i]<<(16*(6-i)) for i in range(7))
        out.append([(bits>>(14*(7-i)))&16383 for i in range(8)])
    return out


def analyze(path,gate_path,trace_path=None,cr2=None):
    data=path.read_bytes();lines=data.decode('ascii').splitlines()
    full=(lines[:2]==['Mirror native mirror TEST v2 / EOSM202 / ML ed3e7c0',
            'Experimental ONE-shot full active image; centered 90/2 only'])
    if len(data)>32768 or len(lines)!=69 or (not full and lines[:2]!=[
            'Mirror native patch TEST v1 / EOSM202 / ML ed3e7c0',
            'Experimental ONE-shot rectangle; not full-frame native Mirror']):
        raise ValueError('Unsupported/truncated patch log')
    match=re.fullmatch(r'gate=(ML/LOGS/MCG\d{3}\.LOG) (.+)',lines[2])
    if not match or Path(match[1]).name!=gate_path.name:raise ValueError('Patch log requires its named gate log')
    status=parse(match[2],'phase error source job origin_offset width height pitch')
    if (status['origin_offset'],status['width'],status['height'],status['pitch'])!=(0x4830,5280,3528,9240):
        raise ValueError('Unsupported sensor layout')
    region=parse(lines[3],'top left bottom right params')
    expected_region=dict(zip(('top','left','bottom','right'),(64,84,3520,5268) if full else (1536,2160,2048,3184)))
    expected_region['params']=[90,2,500,500]
    if region!=expected_region:
        raise ValueError('Unsupported patch geometry/controls')
    commit=parse(lines[4],'started done transform_us verified_words mismatching_words changed_expected_words')
    if not 0<=commit['done']<=commit['started']<=1 or not 0<=commit['mismatching_words']<=commit['verified_words']<=896 or commit['changed_expected_words']>896:
        raise ValueError('Invalid patch counters')
    patches=[]
    for i,line in enumerate(lines[5:]):
        m=re.fullmatch(r'patch=(\d+) y=(\d+) x=(\d+) before=([0-9a-f]{56}) expected=([0-9a-f]{56}) after=([0-9a-f]{56})',line)
        y=64+(i//8*1727//7)*2 if full else 1536+(i//8*255//7)*2
        x=88+(i%8*646//7)*8 if full else 2160+(i%8*127//7)*8
        if not m or tuple(map(int,m.group(1,2,3)))!=(i,y,x):raise ValueError('Invalid/duplicate/out-of-order patch')
        patches.append({'y':y,'x':x,**{name:[int(m[k][n:n+4],16) for n in range(0,56,4)] for k,name in enumerate(('before','expected','after'),4)}})
    changed=sum(a!=b for p in patches for a,b in zip(p['before'],p['expected']))
    differing=sum(a!=b for p in patches for a,b in zip(p['after'],p['expected']))
    if commit['done'] and (changed!=commit['changed_expected_words'] or differing!=commit['mismatching_words']):
        raise ValueError('Patch samples disagree with counters')
    gate=analyze_gate(gate_path,analyze_trace(trace_path) if trace_path else None)
    paired=(gate['experimental_patch_mode'] and gate['experimental_full_mirror_mode']==full and all(status[k]==gate['status'][k] for k in ('phase','error')) and
            all(status[k]==gate['context'][k] for k in ('source','job')) and gate['shutter_latch']['params']==region['params'])
    readback=(paired and gate['requested_hold_completed_without_observed_overlap'] and
              commit['started']==commit['done']==1 and commit['verified_words']==896 and differing==0 and changed>0)
    comparison=None
    if cr2 is not None:
        if not readback:raise ValueError('CR2 comparison requires a completed changed patch and exact logged readback')
        import rawpy
        digest=hashlib.sha256(cr2.read_bytes()).hexdigest()
        with rawpy.imread(str(cr2)) as raw:
            mosaic=raw.raw_image.copy();cfa=raw.raw_pattern.tolist()
        if mosaic.shape!=(3528,5280):raise ValueError('CR2 sensor dimensions differ')
        roots=[[] for _ in range(4)];all_pairs=[[] for _ in range(4)];raw_differences=0
        changed_values=0
        for p in patches:
            before=unpack(p['before']);after=unpack(p['after']);expected=unpack(p['expected'])
            for row in range(2):
                for col in range(8):
                    a=after[row][col];b=int(mosaic[p['y']+row,p['x']+col]);phase=row*2+col%2
                    all_pairs[phase].append((a,b));raw_differences+=a!=b
                    changed_values+=before[row][col]!=expected[row][col]
                    if p['x']<(region['left']+region['right'])//2:
                        if before[row][col]!=expected[row][col]:raise ValueError('Fixed source half changed in log')
                        roots[phase].append((a,b))
        phases=[];explained=True;fitted_mismatches=0
        for phase in range(4):
            offsets={b-a for a,b in roots[phase] if 0<a<16383 and 0<b<16383}
            delta=next(iter(offsets)) if len(offsets)==1 else None
            mismatches=sum(max(0,min(16383,a+delta))!=b for a,b in all_pairs[phase]) if delta is not None else len(all_pairs[phase])
            fitted_mismatches+=mismatches;explained=explained and delta is not None and mismatches==0
            phases.append({'row_parity':phase//2,'column_parity':phase%2,'fitted_from_unchanged_half_only':True,
                           'offset':delta,'compared_values':len(all_pairs[phase]),'mismatches':mismatches,
                           'decoded_minus_after_histogram':dict(sorted(Counter(b-a for a,b in all_pairs[phase]).items()))})
        if hashlib.sha256(cr2.read_bytes()).hexdigest()!=digest:raise ValueError('Original CR2 changed')
        rectangle=mosaic[region['top']:region['bottom'],region['left']:region['right']]
        cells=rectangle.reshape(rectangle.shape[0],rectangle.shape[1]//2,2);half=cells.shape[1]//2
        import numpy as np
        symmetry_mismatches=int(np.count_nonzero(cells[:,half:,:]!=cells[:,:half,:][:,::-1,:]))
        comparison={'file':cr2.name,'sha256':digest,'CFA':cfa,'sampled_values':1024,'changed_values':changed_values,
            'exact_value_mismatches':raw_differences,'phase_fit_mismatches':fitted_mismatches,
            'whole_mirrored_half_values':int(cells[:,half:,:].size),'whole_half_symmetry_mismatches':symmetry_mismatches,
            'whole_half_exactly_mirrored':symmetry_mismatches==0,
            'phase_offsets_from_unchanged_half_explain_all_patch_values':explained,'phases':phases,
            'input_unchanged':True,'same_physical_shot_independently_attested':False}
    return {'kind':'EOSM-one-shot-native-patch-analysis','provenance':{'file':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},
        'status':status,'region':region,'commit':commit,'paired_gate':paired,'logged_changed_patch_readback_matches':readback,
        'gate':gate,'CR2_comparison':comparison,'full_active_area_mode':full,
        'full_active_area_CR2_evidence':bool(full and comparison and comparison['phase_offsets_from_unchanged_half_explain_all_patch_values'] and comparison['whole_half_exactly_mirrored']),
        'full_frame_native_Mirror_verified':False,'Canon_review_verified':False,
        'exclusive_source_ownership_verified':False,'full_frame_cache_coherence_verified':False,
        'limits':['Sparse patches only; fitted CFA offsets do not identify their firmware cause.',
                  'A changed rectangle is not full-frame native capture or review acceptance.',
                  'Filenames do not attest a physical shot; camera ownership/coherence/runtime remain experimental.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('patch',type=Path);p.add_argument('--gate',type=Path,required=True)
    p.add_argument('--trace',type=Path);p.add_argument('--cr2',type=Path);args=p.parse_args()
    try:print(json.dumps(analyze(args.patch,args.gate,args.trace,args.cr2),indent=2))
    except (OSError,UnicodeError,ValueError) as e:p.exit(2,f'Patch comparison refused: {e}\n')
if __name__=='__main__':main()
