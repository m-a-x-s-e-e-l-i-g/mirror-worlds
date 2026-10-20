"""Read-only scheduling-test log analysis. Never grants a RAW write lease."""
import argparse
import hashlib
import json
from pathlib import Path
import re
if __package__:
    from .analyze_mirror_native_trace import analyze_trace, canonical
else:
    from analyze_mirror_native_trace import analyze_trace, canonical
MASK=0xffffffff
HEX=set('core_error cpsr lr task context source job dma_address dma_pointer first_overlap_pc origin_offset'.split())
SETS=['phase error installed core_error requested_ms armed_ms requested_hold_us',
      'latched full_ms preview_ms params',
      'enter_us release_us held_us sleeps cpsr lr task context source job',
      'dma_before dma_after dma_address dma_pointer overlaps first_overlap_pc first_overlap_us']


def parse(line,expected):
    out={}
    for item in line.split():
        k,sep,v=item.partition('=')
        if not sep or k in out:raise ValueError('Malformed/duplicate gate field')
        if k=='params':
            if not re.fullmatch(r'\d+,\d+,\d+,\d+',v):raise ValueError('Invalid gate controls')
            out[k]=[int(x) for x in v.split(',')]
        else:
            if not re.fullmatch(r'[0-9a-fA-F]+' if k in HEX else r'[0-9]+',v):raise ValueError('Invalid gate number')
            out[k]=int(v,16 if k in HEX else 10)
        if any(x>MASK for x in (out[k] if isinstance(out[k],list) else [out[k]])):raise ValueError('Gate field exceeds ARM32')
    if set(out)!=set(expected.split()):raise ValueError('Missing/unknown gate fields')
    return out


def analyze(path,trace=None):
    data=path.read_bytes()
    if len(data)>8192:raise ValueError('Gate log exceeds 8KiB')
    lines=data.decode('ascii').splitlines()
    if len(lines)!=6 or lines[0]!='Mirror capture scheduling TEST / EOSM202 / ML ed3e7c0' or lines[1] not in (
            'No sensor access or pixel changes; no owned RAW lease or mirrored CR2',
            'Read-only sensor samples; no owned RAW lease or mirrored CR2',
            'Experimental mirrored sensor patch; restart removes hooks',
            'Experimental full active-area mirror; max_hold_us=2000000'):
        raise ValueError('Unsupported/truncated scheduling-test log')
    status,latch,context,dma=[parse(lines[i+2],keys) for i,keys in enumerate(SETS)]
    if status['phase']>5 or status['error']>18 or status['installed']>1 or status['requested_hold_us']!=100000 or latch['latched']>1 or context['sleeps']>20:
        raise ValueError('Invalid gate state')
    if (context['release_us'] or context['held_us']) and context['held_us']!=(context['release_us']-context['enter_us'])&MASK:
        raise ValueError('Gate duration disagrees with timestamps')
    p=latch['params']
    if latch['latched'] and (p[0]>179 or p[1] not in (2,4,6,8,10,12) or max(p[2:])>1000):
        raise ValueError('Invalid latched Mirror controls')
    full_mode=lines[1]=='Experimental full active-area mirror; max_hold_us=2000000'
    maximum_hold=2000000 if full_mode else 250000
    completed=(status['phase']==4 and status['error']==0 and status['installed']==1 and latch['latched']==1 and
               100000<=context['held_us']<=maximum_hold and dma['overlaps']==0 and
               context['cpsr']&31==0x13 and not context['cpsr']&0xc0 and
               context['lr']==0xff152238 and context['context']==0x3f3d4 and
               canonical(context['source']) is not None and canonical(context['job']) is not None and
               dma['dma_before']==dma['dma_after']==0 and
               canonical(dma['dma_address'])==canonical(context['source'])+0x9060 and
               canonical(dma['dma_pointer'])==canonical(dma['dma_address'])+32607960)
    paired=False;starts=[];readers_after=False
    if trace is not None:
        paired=(trace['status']['requested_ms']-status['requested_ms'])&MASK<=5
        clean=(trace['status']['phase']==3 and trace['status']['error']==0 and trace['status']['installed']==255 and trace['status']['starts']==2 and
               trace['status']['dropped']==trace['status']['skipped']==0)
        for event in trace['events']:
            r,d=event['record'],event['descriptor']
            if r['kind']!=3 or r['desc'] not in (0x6fd8c,0x6fce4):continue
            starts.append({'event':r['event'],'path':event['path'],
                           'same_numeric_job_source':d['context_job']==context['job'] and event['source_canonical']==canonical(context['source']),
                           'within_full_press_window':(r['ms']-latch['full_ms'])&MASK<=5000,
                           'after_release_within_5s':(r['us']-context['release_us'])&MASK<=5000000,
                           'us_after_release_mod32':(r['us']-context['release_us'])&MASK})
        readers_after=(completed and paired and clean and len(starts)==2 and
                       {s['path'] for s in starts}=={'candidate JPEG','SSS RAW'} and
                       all(s['same_numeric_job_source'] and s['within_full_press_window'] and s['after_release_within_5s'] for s in starts))
    return {'kind':'EOSM-native-patch-gate-analysis' if lines[1].startswith('Experimental') else 'read-only-EOSM-scheduling-test-analysis',
            'provenance':{'file':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},
            'data_origin':'Log headers do not independently attest camera execution.',
            'status':status,'shutter_latch':latch,'context':context,'DMA_and_overlap':dma,
            'sensor_sample_mode':lines[1].startswith('Read-only sensor samples;'),
            'experimental_patch_mode':lines[1].startswith('Experimental'),
            'experimental_full_mirror_mode':full_mode,'maximum_hold_us':maximum_hold,
            'requested_hold_completed_without_observed_overlap':completed,
            'paired_request_clocks':paired,'observed_starts':starts,
            'observed_JPEG_and_RAW_started_after_release':readers_after,
            'exclusive_source_ownership_verified':False,'cache_coherence_verified':False,'mirrored_CR2_saved':False,
            'limits':['Only instrumented paths are observed; unobserved consumers are not excluded.',
                      'Task-context yielding and this short hold do not establish a full processing deadline.',
                      'No Canon review-source relationship is verified; sample mode also requires its matching MSR log and CR2.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('gate',type=Path);parser.add_argument('--trace',type=Path)
    args=parser.parse_args()
    try:print(json.dumps(analyze(args.gate,analyze_trace(args.trace) if args.trace else None),indent=2))
    except (OSError,UnicodeError,ValueError) as e:parser.exit(2,f'Gate analysis refused: {e}\n')
if __name__=='__main__':main()
