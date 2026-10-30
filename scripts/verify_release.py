"""Verify immutable downloads, including the source snapshot inside the ZIP."""
from pathlib import Path
import argparse,hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
EXPECTED_MODULE='000f575d5c30bdac15feff6dcb095cf1f93fd49b3c905baf262994bea2594737'
EXPECTED_ZIP='78f3e67894dd5329afd41cbcaea5726638e3718d4f18c246e0ed2295a7120957'
CURRENT_MODULE='fa2c5cc253a18a7b53dee3d3f10170e8ac0811f80fa38e1855c8bef17a022c12'
CURRENT_ZIP='cb2b3bdad7f9df106c57993e8f819450a8e719dcd887441d34a57b10a7344b48'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-snapshot',type=Path,help='Also compare an original 0.2.0 source checkout; development sources may differ')
    args=parser.parse_args()
    archive=ROOT/'downloads/MIRROR-0.2.0-EOSM202.zip'
    assert sha(archive.read_bytes())==EXPECTED_ZIP,'Release ZIP changed'
    assert sha((ROOT/'downloads/mirror.mo').read_bytes())==EXPECTED_MODULE,'Module changed'
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert z.read('ML/MODULES/mirror.mo')==(ROOT/'downloads/mirror.mo').read_bytes()
        for line in z.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1);assert sha(z.read(name))==digest,name
        manifest=json.loads(z.read('BUILD.json'))
        assert manifest==json.loads((ROOT/'release-manifests/BUILD.json').read_text(encoding='utf-8'))
        for name,digest in manifest['source_files'].items():
            assert sha(z.read('source/'+name))==digest,name
            if args.source_snapshot:
                assert sha((args.source_snapshot/name).read_bytes())==digest,'Source differs from 0.2.0: '+name
    print('0.2.0 module, ZIP, every archive member and archived source: verified')
    current=ROOT/'downloads/0.3.0'
    archive=current/'MIRROR-0.3.0-EOSM202.zip'
    assert sha(archive.read_bytes())==CURRENT_ZIP,'0.3.0 ZIP changed'
    assert sha((current/'mirror.mo').read_bytes())==CURRENT_MODULE,'0.3.0 module changed'
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert z.read('ML/MODULES/mirror.mo')==(current/'mirror.mo').read_bytes()
        for line in z.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1);assert sha(z.read(name))==digest,name
        manifest=json.loads(z.read('BUILD.json'))
        assert manifest['version']=='0.3.0'
        assert manifest==json.loads((ROOT/'release-manifests/0.3.0/BUILD.json').read_text())
        for name,digest in manifest['source_files'].items():
            assert sha(z.read('source/'+name))==digest,name
    for line in (current/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);assert sha((current/name).read_bytes())==digest,name
    receipt=json.loads((ROOT/'release-manifests/0.3.0/VALIDATION.json').read_text())
    assert receipt['module_sha256']==CURRENT_MODULE and receipt['zip_sha256']==CURRENT_ZIP
    print('0.3.0 module, ZIP, all members, archived source and acceptance receipt: verified')
if __name__=='__main__':main()
