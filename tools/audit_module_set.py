"""Check independently built modules before loading them into shared TinyCC state."""
import argparse
from pathlib import Path
if __package__:
    from .audit_module import inspect_module
else:
    from audit_module import inspect_module
def inspect_set(paths):
    owners={};reports=[]
    for path in paths:
        r=inspect_module(path.read_bytes());reports.append(r)
        for symbol in r['defined_symbols']:
            if symbol in owners:raise ValueError(f'Duplicate module symbol {symbol}: {owners[symbol]} / {path}')
            owners[symbol]=str(path)
    return reports
def main():
    parser=argparse.ArgumentParser();parser.add_argument('modules',nargs='+',type=Path);args=parser.parse_args()
    reports=inspect_set(args.modules)
    print('No shared-link global collisions: '+', '.join(r['module_name'] for r in reports))
    print('This does not prove actual TinyCC loading or camera coexistence.')
if __name__=='__main__':main()
