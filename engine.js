/* ===== data ===== */
const DATA = __DATA__;
const META = DATA.meta, PLAYERS = DATA.players, REAL = DATA.picks;
const TEAMS = META.teams, ROUNDS = META.rounds, PICKS = REAL.length;
const SLOTS = META.slots, BENCH = META.bench, QBLIMIT = META.qbLimit;
const ORDER = META.order, NICK = 'NICK';
const CAP = {QB: QBLIMIT, K: 1, DEF: 1};
const BY_ID = {}; PLAYERS.forEach(p => BY_ID[p.id] = p);
const NICK_PICKS = REAL.filter(p => p.mgr === NICK).map(p => p.n);

/* Each rival's willingness to stray, used only when his real pick is gone.
   Measured the same way the 2027 room was: how far off the board he actually
   drafted in August. Low numbers take the best man left. */
const TAU = {Dane:0.20, Abdur:0.45, Max:0.32, Olivia:0.18, Austin:0.15, Tyler:0.28, Tommy:0.12, NICK:0.10};

/* ===== rng: deterministic for a given set of Nick's choices ===== */
function seedFrom(choices){
 let h = 2166136261;
 Object.keys(choices).sort((a,b)=>a-b).forEach(k=>{
  const s = k + ':' + choices[k];
  for(let i=0;i<s.length;i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }});
 return h >>> 0;
}
function rngFrom(seed){ let s = seed || 1; return () => { s = (Math.imul(s,1664525) + 1013904223) >>> 0; return s/4294967296; }; }

/* ===== roster rules ===== */
function counts(roster){ const c={QB:0,RB:0,WR:0,TE:0,K:0,DEF:0}; roster.forEach(p=>c[p.pos]++); return c; }
function legal(roster, p){
 if(CAP[p.pos] && counts(roster)[p.pos] >= CAP[p.pos]) return false;
 return roster.length < SLOTS.length + BENCH;
}
/* what a roster still needs, for the fallback only */
function needs(roster){
 const c = counts(roster);
 const n = {QB:Math.max(0,1-c.QB), RB:Math.max(0,2-c.RB), WR:Math.max(0,2-c.WR),
            TE:Math.max(0,1-c.TE), K:Math.max(0,1-c.K), DEF:Math.max(0,1-c.DEF)};
 const flexUsed = Math.max(0,c.RB-2) + Math.max(0,c.WR-2) + Math.max(0,c.TE-1);
 n.FLEX = Math.max(0, 3-flexUsed); n.SF = c.QB >= 2 ? 0 : 1;
 return n;
}

/* ===== the fallback =====
   Scores off `aug`, the August board, and never off `now`. This is the line the
   spec calls the most important in it: if a rival who was forced off his real
   pick starts taking the players who turned out well, the whole exercise is a
   fantasy. `now` is not read anywhere in this function. */
function choose(mgr, avail, roster, round, rnd){
 const need = needs(roster), c = counts(roster);
 const scored = [];
 for(const id of avail){
  const p = BY_ID[id];
  if(!legal(roster, p)) continue;
  let e = p.aug;
  if((p.pos==='K'||p.pos==='DEF') && round < ROUNDS-1) continue;      /* nobody takes them early */
  if(round >= ROUNDS-1 && need[p.pos] > 0 && (p.pos==='K'||p.pos==='DEF')) e *= 0.05;
  const starter = need[p.pos] > 0
   || (['RB','WR','TE'].includes(p.pos) && need.FLEX > 0)
   || (p.pos==='QB' && need.SF > 0);
  if(!starter && round <= 10) e *= 1.25;
  if(p.pos==='QB' && c.QB >= 2 && round < 12) e *= 2.2;
  scored.push([e, id]);
 }
 if(!scored.length) return null;
 scored.sort((a,b)=>a[0]-b[0]);
 const tau = TAU[mgr] || 0.2;
 const top = scored.slice(0,6), best = Math.log(top[0][0]);
 const w = top.map(([s]) => Math.exp(-(Math.log(s)-best)/tau));
 const tot = w.reduce((a,b)=>a+b,0);
 let r = rnd()*tot, k = 0;
 for(; k < w.length; k++){ r -= w[k]; if(r <= 0) break; }
 return top[Math.min(k, top.length-1)][1];
}

/* ===== the replay =====
   redo(nickChoices) -> {board, rosters, ripples}
   nickChoices maps one of Nick's pick numbers to a player id, or to "keep".
   Rivals take exactly who they really took whenever that player is still on the
   board and still legal for them. The anchor is per pick, not per manager: a
   rival forced off his real fourth-round pick still takes his real fifth. */
function redo(nickChoices){
 const choices = nickChoices || {};
 const rnd = rngFrom(seedFrom(choices));
 const taken = new Set(), avail = new Set(PLAYERS.map(p=>p.id));
 const rosters = {}; ORDER.forEach(m => rosters[m] = []);
 const board = [], ripples = []; let blocked = null;
 const chainOf = {};                       /* playerId -> chain id of the change that displaced him */
 let chainSeq = 0;

 for(const real of REAL){
  const mgr = real.mgr;
  let id = null, why = null, changed = false;

  if(mgr === NICK){
   const want = choices[real.n];
   if(want === undefined){ blocked = {n: real.n, reason: 'open'}; break; }
   id = want === 'keep' ? real.playerId : want;
   /* The spec rejects an illegal choice rather than quietly substituting. An
      earlier change can make a later "keep" illegal: take a fourth quarterback
      and the real one you meant to keep no longer fits. Say so and stop. */
   if(!avail.has(id)){
    blocked = {n: real.n, id, reason: 'gone', tookBy: (board.find(b => b.id === id)||{}).mgr};
    break;
   }
   if(!legal(rosters[mgr], BY_ID[id])){
    blocked = {n: real.n, id, reason: 'limit', pos: BY_ID[id].pos};
    break;
   }
   changed = id !== real.playerId; why = changed ? 'your change' : 'kept';
  } else {
   const wanted = real.playerId;
   if(avail.has(wanted) && legal(rosters[mgr], BY_ID[wanted])){
    id = wanted; why = 'his real pick';
   } else {
    id = choose(mgr, avail, rosters[mgr], real.round, rnd);
    why = 'forced off his pick';
    if(id !== null){
     const chain = chainOf[wanted] !== undefined ? chainOf[wanted] : ++chainSeq;
     chainOf[id] = chain;
     ripples.push({n: real.n, round: real.round, mgr,
       wanted: wanted, wantedBy: null, took: id, chain,
       delta: Math.round(BY_ID[id].aug - BY_ID[wanted].aug)});
    }
   }
  }
  if(id === null) break;
  avail.delete(id); taken.add(id);
  rosters[mgr].push(BY_ID[id]);
  board.push({n: real.n, round: real.round, slot: real.slot, mgr, id,
              realId: real.playerId, changed, why});
 }
 /* name who ended up with the player each displaced rival wanted */
 const tookBy = {}; board.forEach(b => tookBy[b.id] = b.mgr);
 ripples.forEach(r => r.wantedBy = tookBy[r.wanted] || null);
 return {board, rosters, ripples, blocked};
}

/* ===== grading: draft against draft, never against today's roster ===== */
const REAL_ROSTERS = (() => {
 const r = {}; ORDER.forEach(m => r[m] = []);
 REAL.forEach(p => r[p.mgr].push(BY_ID[p.playerId]));
 return r;
})();
const value = roster => Math.round(roster.reduce((a,p) => a + p.total, 0));
function grade(rosters){
 const swings = [];
 const mine = new Set(rosters[NICK].map(p=>p.id));
 const was  = new Set(REAL_ROSTERS[NICK].map(p=>p.id));
 rosters[NICK].forEach(p => { if(!was.has(p.id)) swings.push({p, dir:'in'}); });
 REAL_ROSTERS[NICK].forEach(p => { if(!mine.has(p.id)) swings.push({p, dir:'out'}); });
 swings.sort((a,b) => (b.dir==='in'?b.p.total:-b.p.total) - (a.dir==='in'?a.p.total:-a.p.total));
 const byPos = {};
 ['QB','RB','WR','TE','K','DEF'].forEach(pos => {
  byPos[pos] = {now: value(rosters[NICK].filter(p=>p.pos===pos)),
                was: value(REAL_ROSTERS[NICK].filter(p=>p.pos===pos))};
 });
 const rivals = ORDER.filter(m=>m!==NICK).map(m =>
   ({mgr:m, now:value(rosters[m]), was:value(REAL_ROSTERS[m])}))
   .sort((a,b) => (b.now-b.was) - (a.now-a.was));
 return {now: value(rosters[NICK]), was: value(REAL_ROSTERS[NICK]), swings, byPos, rivals};
}

/* ===== the starting lineup, the way the roster page shows it ===== */
const ELIG = {QB:['QB'], RB:['RB'], WR:['WR'], TE:['TE'],
              FLEX:['RB','WR','TE'], SF:['QB','RB','WR','TE'], K:['K'], DEF:['DEF']};
function lineup(roster){
 /* fill each slot with the best remaining eligible player by season value */
 const pool = roster.slice().sort((a,b) => b.total - a.total);
 const used = new Set(), out = [];
 SLOTS.forEach(sl => {
  const i = pool.findIndex((p,j) => !used.has(j) && ELIG[sl].includes(p.pos));
  if(i >= 0){ used.add(i); out.push({slot: sl, p: pool[i]}); }
  else out.push({slot: sl, p: null});
 });
 const bench = pool.filter((p,j) => !used.has(j));
 return {starters: out, bench};
}
