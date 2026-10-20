"""Fetch the public ML build required by the pinned import audit."""
from pathlib import Path
import hashlib,urllib.request
ROOT=Path(__file__).resolve().parents[1]
url='https://builds.magiclantern.fm/builds/dev/magiclantern.2025-06-20.EOSM.202.zip'
expected='152f2ab46b83f45b978bcb704bda976849aa9d06b08fb70448f69be3ebfc44fb'
path=ROOT/'.cache/magiclantern.2025-06-20.EOSM.202.zip'
if path.exists():data=path.read_bytes()
else:data=urllib.request.urlopen(url,timeout=120).read()
if hashlib.sha256(data).hexdigest()!=expected:raise SystemExit('ML build checksum mismatch; not written')
path.parent.mkdir(exist_ok=True);path.write_bytes(data)
print('Pinned public ML build verified:',path)
