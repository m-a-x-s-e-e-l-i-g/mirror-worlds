"""Snapshot hash-linked local research evidence so later working-file edits retain history."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
ROOT=Path(__file__).resolve().parents[1]


def freeze(path):
    path=path.resolve()
    if not path.is_relative_to(ROOT/'build'):raise ValueError('Receipt must be within workspace build/')
    original=path.read_bytes();receipt=json.loads(original)
    if receipt.get('kind') not in ('experimental-canon-cr2-output','isolated-70d-arm-mirror-probe',
                                   'research-main-module-expired-latch-refusal','research-main-module-registered-cr2',
                                   'research-main-module-native-sequence-verified'):
        raise ValueError('Unexpected research receipt kind')
    snapshot=path.parent/'evidence'
    if snapshot.exists():raise FileExistsError(snapshot)
    sources={}
    for name,expected in receipt['files'].items():
        source=(ROOT/name).resolve()
        if not source.is_relative_to(ROOT):raise ValueError('Evidence path escapes workspace')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise ValueError('Changed evidence: '+name)
        sources[name]=source
    snapshot.mkdir()
    updated={}
    for name,source in sources.items():
        target=snapshot/'files'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        assert hashlib.sha256(target.read_bytes()).hexdigest()==receipt['files'][name]
        updated[target.relative_to(ROOT).as_posix()]=receipt['files'][name]
    historical=snapshot/'receipt-original.json';historical.write_bytes(original)
    updated[historical.relative_to(ROOT).as_posix()]=hashlib.sha256(original).hexdigest()
    receipt['original_files']=receipt['files'];receipt['files']=updated
    receipt['evidence_storage']='Byte-exact snapshots; original receipt and source-path/hash mapping retained.'
    path.write_text(json.dumps(receipt,indent=2)+'\n')
    print('Preserved',len(sources),'evidence files and the original receipt; hashes unchanged.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path)
    freeze(parser.parse_args().receipt)
