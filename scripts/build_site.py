"""Assemble the static Netlify site. Standard Python only; no dependencies."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'.site-build'
output.mkdir(exist_ok=True)
shutil.copytree(ROOT/'site',output,dirs_exist_ok=True)
shutil.copytree(ROOT/'downloads',output/'downloads',dirs_exist_ok=True)
shutil.copyfile(ROOT/'COPYING',output/'LICENSE.txt')
print('Static site ready:',output)
