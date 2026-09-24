#!/bin/sh
# One self-contained file: data, engine, headshots and the house faces all inline.
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
import json, base64, os
src   = open('index.src.html').read()
data  = open('redo-2026.json').read().strip()
heads = open('headshots.json').read().strip() if os.path.exists('headshots.json') else '{}'
avs   = open('avatars.json').read().strip() if os.path.exists('avatars.json') else '{}'
eng   = open('engine.js').read()
d = os.path.expanduser('~/picks/fonts')
want = {'buch':'Sohne-Buch.woff2','kraftig':'Sohne-Kraftig.woff2','halbfett':'Sohne-Halbfett.woff2',
        'dreiviertel':'Sohne-Dreiviertelfett.woff2','schmal':'SohneSchmal-Dreiviertelfett.woff2'}
fonts = {k: base64.b64encode(open(os.path.join(d, v), 'rb').read()).decode() for k, v in want.items()}
face = lambda fam, w, k: "@font-face{font-family:'%s';font-weight:%d;font-display:swap;src:url(data:font/woff2;base64,%s) format('woff2')}" % (fam, w, fonts[k])
css = "\n".join([face('Sohne',400,'buch'), face('Sohne',500,'kraftig'), face('Sohne',600,'halbfett'),
                 face('Sohne',700,'dreiviertel'), face('Sohne Schmal',700,'schmal')])
out = (src.replace('/*__FONTS__*/', css)
          .replace('/*__ENGINE__*/', eng.replace('__DATA__', data))
          .replace('__HEADS__', heads).replace('__AVATARS__', avs))
open('index.html','w').write(out)
print('index.html', len(out), 'bytes')
PY
