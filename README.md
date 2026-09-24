# 2026 Draft Redo

Nick's real August 2026 Sleeper draft, replayed pick by pick, except that when
it is his turn he can take somebody else. The seven rivals take exactly who they
really took and only deviate when the player they really took is already gone.
The result is graded on what those players have actually been worth since.

Phone first. Built to match the Sleeper mobile draft UI.

## Running it

```
./serve.sh          # http://localhost:8172
./build.sh          # rebuild index.html from source
```

`index.html` is the whole app: data, engine, headshots, avatars and the house
faces are all inlined, so it works from a `file://` URL with no network.

## Files

| file | what it is |
|---|---|
| `index.src.html` | the page: markup, tokens, every view |
| `engine.js` | the replay. `redo(nickChoices)` returns board, rosters and ripples |
| `redo-2026.json` | the draft, the player universe, and the hindsight column |
| `headshots.json` | 335 player cut-outs, palette-quantized |
| `avatars.json` | the six managers who have a Sleeper avatar |
| `tools/build_data.py` | rebuilds `redo-2026.json` from Sleeper's public API |
| `tools/heads.py` | rebuilds `headshots.json` |
| `tools/png.py` | a PNG decoder, box-resizer and palette quantizer, zlib only |

## The data

The back-end spec for this app assumes On Paper's own files. None were reachable,
so `tools/build_data.py` builds the same contract from Sleeper's public API: the
real draft by draft id, this league's own scoring settings, and real 2026
production. Re-run it as the season goes on and the hindsight column improves.

Two fields are approximations, and the app says so on its Grade page:

- `aug` uses the real overall pick for a drafted player, since that is what the
  room actually paid. Undrafted players sit after pick 136 in preseason order.
- `now` is season value, every point scored in the played weeks plus every point
  projected for the rest, scaled to 100 inside each position.

Every one of the 136 drafted players prices. The build fails loudly rather than
defaulting anyone to zero.

## The engine's rules

- The anchor is per pick. A rival forced off his round-four pick still takes his
  real round-five pick if that player is available.
- Legality is checked on the anchor too. The 2026 draft allowed three
  quarterbacks.
- The fallback scores off `aug` and never off `now`. A rival who starts taking
  the players who turned out well makes the whole thing a fantasy.
- The seed comes from Nick's own choices, so a given set of choices always
  replays identically.
- An illegal or already-taken choice is rejected and explained, not substituted.
