"""Decode, box-downscale and palette-quantize a PNG using nothing but zlib.

Sleeper's headshots are 350x254 cut-outs with a transparent background. sips
re-encodes them as RGBA and triples the size, so this does the work instead:
median-cut to 256 colours, which for a photo on a transparent ground is
visually lossless at the sizes these are drawn, and writes a palette PNG with
tRNS. The point is one self-contained file with no build dependencies.
"""
import zlib, struct
from collections import Counter

def _chunks(d):
    assert d[:8] == b'\x89PNG\r\n\x1a\n', 'not a png'
    i, out = 8, []
    while i < len(d):
        ln = struct.unpack('>I', d[i:i+4])[0]
        typ = d[i+4:i+8]
        out.append((typ, d[i+8:i+8+ln]))
        i += 12 + ln
    return out

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
    return a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)

def decode(data):
    """-> (w, h, [RGBA bytes]) as a flat bytearray."""
    ihdr = plte = trns = None; idat = b''
    for typ, body in _chunks(data):
        if typ == b'IHDR': ihdr = body
        elif typ == b'PLTE': plte = body
        elif typ == b'tRNS': trns = body
        elif typ == b'IDAT': idat += body
    w, h, bd, ct, _, _, il = struct.unpack('>IIBBBBB', ihdr)
    if il: raise ValueError('interlaced png unsupported')
    if bd not in (8, 16): raise ValueError('bit depth %d unsupported' % bd)
    ch = {0:1, 2:3, 3:1, 4:2, 6:4}[ct] * (2 if bd == 16 else 1)
    raw = zlib.decompress(idat)
    stride = w * ch
    out = bytearray(stride * h)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        f = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos+stride]); pos += stride
        if f == 1:
            for i in range(ch, stride): line[i] = (line[i] + line[i-ch]) & 255
        elif f == 2:
            for i in range(stride): line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i-ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i-ch] if i >= ch else 0
                c = prev[i-ch] if i >= ch else 0
                line[i] = (line[i] + _paeth(a, prev[i], c)) & 255
        out[y*stride:(y+1)*stride] = line
        prev = line
    if bd == 16:                      # keep the high byte of each sample
        out = bytearray(out[i] for i in range(0, len(out), 2))
        ch //= 2; stride = w * ch
    # widen to RGBA
    rgba = bytearray(w*h*4)
    if ct == 6:
        rgba[:] = out
    elif ct == 2:
        for i in range(w*h):
            rgba[i*4:i*4+3] = out[i*3:i*3+3]; rgba[i*4+3] = 255
    elif ct == 3:
        al = list(trns) if trns else []
        for i in range(w*h):
            p = out[i]
            rgba[i*4:i*4+3] = plte[p*3:p*3+3]
            rgba[i*4+3] = al[p] if p < len(al) else 255
    elif ct in (0, 4):
        st = 1 if ct == 0 else 2
        for i in range(w*h):
            g = out[i*st]
            rgba[i*4] = rgba[i*4+1] = rgba[i*4+2] = g
            rgba[i*4+3] = out[i*st+1] if ct == 4 else 255
    return w, h, rgba

def resize(w, h, rgba, tw, th):
    """Box filter on premultiplied alpha, so the cut-out edge keeps no halo."""
    out = bytearray(tw*th*4)
    for oy in range(th):
        y0, y1 = oy*h//th, max(oy*h//th + 1, (oy+1)*h//th)
        for ox in range(tw):
            x0, x1 = ox*w//tw, max(ox*w//tw + 1, (ox+1)*w//tw)
            r = g = b = a = n = 0
            for yy in range(y0, y1):
                base = (yy*w + x0)*4
                for xx in range(x1-x0):
                    i = base + xx*4
                    al = rgba[i+3]
                    r += rgba[i]*al; g += rgba[i+1]*al; b += rgba[i+2]*al
                    a += al; n += 1
            o = (oy*tw + ox)*4
            if a:
                out[o] = min(255, r//a); out[o+1] = min(255, g//a); out[o+2] = min(255, b//a)
            out[o+3] = a//n if n else 0
    return out

def quantize(tw, th, rgba, maxc=256):
    """Median cut. The boxes partition the colour set, so the pixel->index map
    falls out of the split and no nearest-neighbour search is needed."""
    px = [tuple(rgba[i*4:i*4+4]) for i in range(tw*th)]
    cnt = Counter(px)
    clear = [c for c in cnt if c[3] < 8]
    solid = [c for c in cnt if c[3] >= 8]
    boxes = [solid] if solid else []
    budget = maxc - (1 if clear else 0)
    while len(boxes) < budget:
        best, bi = -1, -1
        for i, bx in enumerate(boxes):
            if len(bx) < 2: continue
            vol = 0
            for ax in range(4):
                vs = [c[ax] for c in bx]
                vol = max(vol, max(vs) - min(vs))
            score = vol * sum(cnt[c] for c in bx)
            if score > best: best, bi = score, i
        if bi < 0: break
        bx = boxes.pop(bi)
        ax = max(range(4), key=lambda a: max(c[a] for c in bx) - min(c[a] for c in bx))
        bx.sort(key=lambda c: c[ax])
        tot = sum(cnt[c] for c in bx); run = 0; cut = 1
        for j, c in enumerate(bx):
            run += cnt[c]
            if run >= tot/2: cut = max(1, min(j+1, len(bx)-1)); break
        boxes.append(bx[:cut]); boxes.append(bx[cut:])
    pal, cmap = [], {}
    if clear:
        for c in clear: cmap[c] = 0
        pal.append((0, 0, 0, 0))
    for bx in boxes:
        idx = len(pal)
        tw_ = sum(cnt[c] for c in bx)
        rep = tuple(sum(c[a]*cnt[c] for c in bx)//tw_ for a in range(4))
        pal.append(rep)
        for c in bx: cmap[c] = idx
    return bytearray(cmap[p] for p in px), pal

def encode(tw, th, idx, pal):
    def chunk(t, b):
        return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t+b) & 0xffffffff)
    raw = bytearray()
    for y in range(th):
        raw.append(0)                      # PNG spec: do not filter palette images
        raw += idx[y*tw:(y+1)*tw]
    out = b'\x89PNG\r\n\x1a\n'
    out += chunk(b'IHDR', struct.pack('>IIBBBBB', tw, th, 8, 3, 0, 0, 0))
    out += chunk(b'PLTE', bytes(b for c in pal for b in c[:3]))
    al = [c[3] for c in pal]
    while al and al[-1] == 255: al.pop()
    if al: out += chunk(b'tRNS', bytes(al))
    out += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    out += chunk(b'IEND', b'')
    return out

def shrink(data, target_h):
    w, h, rgba = decode(data)
    th = target_h
    tw = max(1, round(w * th / h))
    small = resize(w, h, rgba, tw, th)
    idx, pal = quantize(tw, th, small)
    return encode(tw, th, idx, pal)
