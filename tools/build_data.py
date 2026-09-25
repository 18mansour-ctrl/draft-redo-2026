#!/usr/bin/env python3
"""Build redo-2026.json from Sleeper.

The back-end spec assumes On Paper's own files (the August FantasyPros board, the
site value chart). None of those are reachable from here, so this builds the same
contract from the one source that is: Sleeper's public API, which holds the real
draft, the real scoring settings, and the real 2026 production.

Two fields are honest approximations and the app says so:
  aug   the real overall pick is what the room actually paid for a drafted player.
        Undrafted players sit after pick 136 in preseason search-rank order.
  now   season value = points already scored + points projected for the rest of
        the year, under this league's own scoring, scaled 0-100 within position.
"""
import json, os, subprocess, sys, statistics as st

LEAGUE = '1392057555869536256'
DRAFT  = '1392057556670631936'
SEASON = 2026
PLAYED = [1, 2]                      # week 3 has not been played
REST   = list(range(3, 19))
CACHE  = '/tmp/redo'
os.makedirs(CACHE, exist_ok=True)

def get(url, name):
    p = os.path.join(CACHE, name)
    if not os.path.exists(p) or os.path.getsize(p) < 3:
        subprocess.run(['curl','-sf','-o',p,url], check=True)
    return json.load(open(p))

league  = get(f'https://api.sleeper.app/v1/league/{LEAGUE}', 'league.json')
picks   = get(f'https://api.sleeper.app/v1/draft/{DRAFT}/picks', 'picks.json')
# the 2026 draft enforced a three-quarterback limit; the league config has since
# been changed to four for 2027, so read the rule off the draft, not the league
draftMeta = get(f'https://api.sleeper.app/v1/draft/{DRAFT}', 'draft.json')
users   = get(f'https://api.sleeper.app/v1/league/{LEAGUE}/users', 'users.json')
rosters = get(f'https://api.sleeper.app/v1/league/{LEAGUE}/rosters', 'rosters.json')
allp    = json.load(open('/tmp/sleeper_players.json')) if os.path.exists('/tmp/sleeper_players.json') \
          else get('https://api.sleeper.app/v1/players/nfl', 'players.json')
SC = league['scoring_settings']

def score(line):
    """Fantasy points for one stat line under this league's settings."""
    return sum(v * line[k] for k, v in SC.items() if k in line and isinstance(line[k], (int, float)))

actual = {w: get(f'https://api.sleeper.app/v1/stats/nfl/regular/{SEASON}/{w}', f'st{w}.json') for w in PLAYED}
proj   = {w: get(f'https://api.sleeper.app/v1/projections/nfl/regular/{SEASON}/{w}', f'pr{w}.json') for w in REST}

# ---- the eight managers, by draft slot ------------------------------------
own = {u['user_id']: (u.get('metadata') or {}).get('team_name') or u['display_name'] for u in users}
r2o = {r['roster_id']: own.get(r['owner_id'], '?') for r in rosters}
SPEC = ['Dane','Abdur','NICK','Max','Olivia','Austin','Tyler','Tommy']
slot2mgr, slot2team = {}, {}
for p in picks:
    if p['round'] == 1:
        slot2mgr[p['draft_slot']] = SPEC[p['draft_slot']-1]
        slot2team[p['draft_slot']] = r2o.get(p['roster_id'], '?')

# ---- the pool: everyone drafted, plus the best undrafted ------------------
drafted = {}
for p in picks:
    drafted[p['player_id']] = p
POS = {'QB','RB','WR','TE','K','DEF'}
pool = set(drafted)
# Sleeper keeps retired players in its list with `active: true` and a legacy
# search_rank, so Tom Brady, Gronkowski and Todd Gurley were all showing up as
# draftable. Requiring a current NFL team is what actually filters them.
extra = sorted((v for k, v in allp.items()
                if k not in drafted and v.get('position') in POS
                and v.get('team') and v.get('active')
                and v.get('search_rank') is not None and v.get('search_rank') < 700),
               key=lambda v: v['search_rank'])
for v in extra[:200]:
    pool.add(v['player_id'])

def nameOf(v):
    if v.get('position') == 'DEF':
        return (v.get('last_name') or v.get('first_name') or v.get('player_id')) + ' DEF'
    return v.get('full_name') or ((v.get('first_name','') + ' ' + v.get('last_name','')).strip())

rows, unpriced = [], []
for pid in pool:
    v = allp.get(pid)
    if not v: unpriced.append(pid); continue
    pos = v.get('position'); pos = 'DEF' if pos in ('DEF','DST') else pos
    if pos not in POS: continue
    pts  = [score(actual[w][pid]) for w in PLAYED if pid in actual[w]]
    prj  = [score(proj[w][pid])   for w in REST   if pid in proj[w]]
    gp   = len(pts)
    ppg  = round(sum(pts)/gp, 2) if gp else 0.0
    ppr  = round(sum(prj)/len(prj), 2) if prj else 0.0
    left = len([x for x in prj if x > 0])
    total = round(sum(pts) + sum(prj), 1)
    d = drafted.get(pid)
    rows.append({
        'sid': pid, 'name': nameOf(v), 'pos': pos, 'nfl': v.get('team') or 'FA',
        'gp': gp, 'ppg': ppg, 'projPpg': ppr, 'gamesLeft': left, 'total': total,
        'drafted': d['pick_no'] if d else None,
        'by': slot2mgr.get(d['draft_slot']) if d else None,
    })

if unpriced:
    sys.exit('FAILED: %d drafted players could not be resolved: %s' % (len(unpriced), unpriced[:8]))

# ---- aug: what the room paid; undrafted sit after the draft ---------------
rank = {v['player_id']: v.get('search_rank', 9999) for v in allp.values() if isinstance(v, dict) and v.get('player_id')}
und = sorted([r for r in rows if r['drafted'] is None], key=lambda r: rank.get(r['sid'], 9999))
for k, r in enumerate(und): r['aug'] = 137 + k
for r in rows:
    if r['drafted'] is not None: r['aug'] = r['drafted']

# ---- now: 0-100 inside position, off season value -------------------------
for pos in POS:
    grp = sorted([r for r in rows if r['pos'] == pos], key=lambda r: -r['total'])
    if not grp: continue
    top = grp[0]['total'] or 1
    for i, r in enumerate(grp):
        r['posRank'] = i + 1
        r['now'] = round(max(0.0, 100.0 * r['total'] / top), 1)
    aug = sorted(grp, key=lambda r: r['aug'])
    for i, r in enumerate(aug): r['augPosRank'] = i + 1

# ---- verdict: 12 positional spots, per the spec ---------------------------
for r in rows:
    d = r['augPosRank'] - r['posRank']
    r['verdict'] = 'hit' if d >= 12 else 'miss' if d <= -12 else 'fine'

rows.sort(key=lambda r: r['aug'])
for i, r in enumerate(rows): r['id'] = i
byid = {r['sid']: r['id'] for r in rows}

out = {
 'meta': {'season': SEASON, 'league': league['name'], 'throughWeek': max(PLAYED),
          'teams': 8, 'rounds': 17, 'qbLimit': draftMeta['settings'].get('position_limit_qb', 3),
          'slots': ['QB','RB','RB','WR','WR','TE','FLEX','FLEX','FLEX','SF','K','DEF'],
          'bench': 5, 'order': [slot2mgr[s] for s in range(1, 9)],
          'teamNames': {slot2mgr[s]: slot2team[s] for s in range(1, 9)},
          'nickSlot': SPEC.index('NICK') + 1,
          'valueNote': 'Season value is every point scored in weeks %s plus every point projected for weeks %d to 18, under this league\'s own scoring.' % (' and '.join(str(w) for w in PLAYED), REST[0])},
 'picks': [{'n': p['pick_no'], 'round': p['round'], 'slot': p['draft_slot'],
            'mgr': slot2mgr[p['draft_slot']], 'playerId': byid[p['player_id']]}
           for p in sorted(picks, key=lambda p: p['pick_no'])],
 'players': rows,
}
dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'redo-2026.json')
json.dump(out, open(dst, 'w'), separators=(',', ':'))
print('wrote %s' % dst)
print('  %d players, %d drafted, %d picks' % (len(rows), sum(1 for r in rows if r['drafted']), len(out['picks'])))
v = {}
for r in rows:
    if r['drafted']: v[r['verdict']] = v.get(r['verdict'], 0) + 1
print('  verdicts among the drafted:', v)
