"""Verify immutable public downloads and their corresponding source snapshot."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
EXPECTED_MODULE='000f575d5c30bdac15feff6dcb095cf1f93fd49b3c905baf262994bea2594737'
EXPECTED_ZIP='78f3e67894dd5329afd41cbcaea5726638e3718d4f18c246e0ed2295a7120957'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
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
            assert sha((ROOT/name).read_bytes())==digest,'Source differs from 0.2.0: '+name
    print('0.2.0 module, ZIP, every archive member and corresponding source: verified')
if __name__=='__main__':main()
