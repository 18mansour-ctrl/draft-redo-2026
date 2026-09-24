#!/usr/bin/env python3
"""Headshots for the redo pool. Every row already carries its real Sleeper id,
so there is no name matching to get wrong this time."""
import json, os, sys, base64, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import png
from multiprocessing import Pool
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = '/tmp/redoheads'; os.makedirs(CACHE + '/raw', exist_ok=True)
d = json.load(open(os.path.join(ROOT, 'redo-2026.json')))
jobs = []
for p in d['players']:
    if p['pos'] == 'DEF':
        ab = (p['nfl'] or '').lower()
        jobs.append((p['name'], 'https://sleepercdn.com/images/team_logos/nfl/%s.png' % ab, 'logo'))
    else:
        jobs.append((p['name'], 'https://sleepercdn.com/content/nfl/players/%s.jpg' % p['sid'], 'head'))
cfg = CACHE + '/curl.txt'
with open(cfg, 'w') as f:
    for i, (n, u, k) in enumerate(jobs):
        f.write('url = "%s"\noutput = "%s/raw/%d.png"\n' % (u, CACHE, i))
subprocess.run(['curl', '-s', '--parallel', '--parallel-max', '16', '--config', cfg], check=True)
def work(a):
    i, name, kind = a
    try:
        raw = open('%s/raw/%d.png' % (CACHE, i), 'rb').read()
        out = png.shrink(raw, 84 if kind == 'head' else 64)
        return (name, 'data:image/png;base64,' + base64.b64encode(out).decode(), None)
    except Exception as e:
        return (name, None, '%s: %s' % (type(e).__name__, e))
if __name__ == '__main__':
    with Pool(8) as pool:
        res = pool.map(work, [(i, n, k) for i, (n, u, k) in enumerate(jobs)])
    ok = {n: u for n, u, e in res if u}
    bad = [(n, e) for n, u, e in res if e]
    out = os.path.join(ROOT, 'headshots.json')
    json.dump(ok, open(out, 'w'), separators=(',', ':'), sort_keys=True)
    print('%d of %d images, %.0f KB' % (len(ok), len(jobs), os.path.getsize(out) / 1024))
    for n, e in bad[:10]: print('  skipped', n, e)
