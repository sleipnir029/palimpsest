"""HTML/CSS/JS template for the T72 report. Tokens (%%NAME%%) filled by build_t72_report.py."""

TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>T72 &mdash; Parser-conditional extraction accuracy</title>
<meta name="description" content="A benchmark of LLMs against PDF parsers for structured extraction from electrocatalysis papers, and the claim that accuracy is conditional on the parser.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#EEF1EE; --paper-2:#F6F8F6; --ink:#14181A; --ink-2:#3A4044;
  --muted:#6B7280; --rule:#D7DBD6; --rule-2:#C3CAC4;
  --teal:#0F6E63; --teal-2:#0B544B; --teal-tint:#DCECE8;
  --correction:#B23A2E; --amber:#C68A2E;
  --serif:"Newsreader",Georgia,"Times New Roman",serif;
  --grotesk:"Archivo",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --maxw:42rem; --margin-col:14rem; --gap:2.6rem;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--paper);color:var(--ink);
  font-family:var(--serif);font-size:19px;line-height:1.62;
  font-variant-numeric:oldstyle-nums;
  text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased;
}
::selection{background:var(--teal-tint)}
a{color:var(--teal-2);text-decoration:none;border-bottom:1px solid var(--rule-2)}
a:hover{border-bottom-color:var(--teal)}
a:focus-visible,button:focus-visible,select:focus-visible,.nav a:focus-visible{
  outline:2px solid var(--teal);outline-offset:2px;border-radius:2px}
.skip{position:absolute;left:-999px;top:0;background:var(--ink);color:#fff;padding:.5rem .8rem;z-index:50}
.skip:focus{left:.5rem;top:.5rem}

/* ---------- structural typography ---------- */
.grotesk{font-family:var(--grotesk)}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:.86em}
.muted{color:var(--muted)}
.eyebrow{font-family:var(--grotesk);text-transform:uppercase;letter-spacing:.16em;
  font-size:.72rem;font-weight:600;color:var(--teal-2)}
h1,h2,h3{font-weight:500;line-height:1.12;letter-spacing:-.01em;margin:0}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}

/* ---------- top nav ---------- */
.nav{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--paper) 86%,transparent);
  backdrop-filter:saturate(140%) blur(6px);border-bottom:1px solid var(--rule)}
.nav-in{max-width:74rem;margin:0 auto;display:flex;gap:.2rem;align-items:center;
  padding:.55rem 1.3rem;flex-wrap:wrap}
.nav .brand{font-family:var(--grotesk);font-weight:700;letter-spacing:.02em;margin-right:auto;font-size:.92rem}
.nav .brand span{color:var(--teal-2)}
.nav a{font-family:var(--grotesk);font-size:.78rem;color:var(--ink-2);border:0;
  padding:.28rem .5rem;border-radius:4px}
.nav a .n{color:var(--muted);font-variant-numeric:tabular-nums}
.nav a:hover{background:var(--paper-2);color:var(--ink)}
.nav a.active{color:var(--teal-2);background:var(--teal-tint)}
@media(max-width:820px){.nav a .lbl{display:none}.nav a{padding:.28rem .42rem}}

/* ---------- layout ---------- */
.wrap{max-width:74rem;margin:0 auto;padding:0 1.3rem}
.essay{max-width:calc(var(--maxw) + var(--margin-col) + var(--gap));margin:0 auto}
.passage{display:grid;grid-template-columns:minmax(0,var(--maxw)) var(--margin-col);
  column-gap:var(--gap);align-items:start}
.passage>*{grid-column:1}
.passage>.mnote{grid-column:2;grid-row:auto}
@media(max-width:900px){
  .passage{display:block;max-width:var(--maxw);margin-inline:auto}
  .mnote{margin:.4rem 0 1.2rem}
}
section{padding:3.4rem 0 1rem;border-top:1px solid var(--rule)}
section:first-of-type{border-top:0}
.section-head{margin-bottom:1.4rem}
.section-head h2{font-size:2rem;margin-top:.35rem}
.section-head .kicker{display:flex;align-items:baseline;gap:.7rem}
.section-head .secno{font-family:var(--mono);font-size:.8rem;color:var(--correction);
  border:1px solid var(--rule-2);padding:.05rem .4rem;border-radius:3px}
p{margin:0 0 1.05rem}
.lead{font-size:1.16rem;line-height:1.5;color:var(--ink-2)}
.passage h3{font-family:var(--grotesk);font-weight:600;font-size:1rem;letter-spacing:-.01em;
  margin:1.8rem 0 .5rem}
em{font-style:italic}
strong{font-weight:600}
hr.rule{border:0;border-top:1px solid var(--rule);margin:2rem 0}

/* ---------- marginalia (the signature) ---------- */
.mnote{font-family:var(--grotesk);font-size:.8rem;line-height:1.5;color:var(--ink-2);
  border-left:2px solid var(--teal);padding-left:.8rem}
.mnote .mlabel{display:block;text-transform:uppercase;letter-spacing:.12em;font-size:.64rem;
  font-weight:700;color:var(--teal-2);margin-bottom:.25rem}
.mnote.warn{border-left-color:var(--correction)}
.mnote.warn .mlabel{color:var(--correction)}

/* ---------- correction motif ---------- */
.was{color:var(--correction);text-decoration:line-through;text-decoration-thickness:1.5px;
  text-decoration-color:color-mix(in srgb,var(--correction) 70%,transparent);opacity:.85}
.now{color:var(--ink);font-weight:600}
.now::before{content:"\2192";color:var(--correction);margin:0 .28em 0 .18em;font-weight:400}
.flag{font-family:var(--grotesk);font-size:.62rem;text-transform:uppercase;letter-spacing:.08em;
  color:var(--correction);border:1px solid color-mix(in srgb,var(--correction) 40%,var(--rule));
  border-radius:3px;padding:.02rem .3rem;vertical-align:middle;white-space:nowrap}

/* ---------- masthead ---------- */
.mast{padding:3.2rem 0 2.6rem;border-top:0}
.mast h1{font-size:clamp(2.5rem,6vw,4.1rem);line-height:1.02;letter-spacing:-.022em;margin:.7rem 0 0}
.mast h1 em{font-style:italic;color:var(--teal-2)}
.mast .standfirst{font-size:1.22rem;line-height:1.5;color:var(--ink-2);max-width:38rem;margin:1.1rem 0 0}
.chips{display:flex;flex-wrap:wrap;gap:.45rem;margin:1.5rem 0 0}
.chip{font-family:var(--grotesk);font-size:.74rem;color:var(--ink-2);background:var(--paper-2);
  border:1px solid var(--rule);border-radius:100px;padding:.28rem .7rem}
.chip b{color:var(--ink);font-weight:600}
.chip .dot{color:var(--teal)}

/* hero stat panel */
.hero{display:grid;grid-template-columns:1.05fr .95fr;gap:2rem;align-items:center;
  margin:2.4rem 0 .5rem;padding:1.6rem 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
@media(max-width:760px){.hero{grid-template-columns:1fr;gap:1.2rem}}
.hero .big{font-family:var(--grotesk);font-weight:700;font-size:clamp(2.2rem,5vw,3rem);
  letter-spacing:-.02em;line-height:1}
.hero .big .arrow{color:var(--correction);margin:0 .12em}
.hero .cap{font-size:1.02rem;color:var(--ink-2);margin:.7rem 0 0;max-width:24rem}
.hero .firstread{font-family:var(--grotesk);font-size:.76rem;color:var(--muted);margin-top:.7rem}

/* ---------- tables ---------- */
.tbl{width:100%;border-collapse:collapse;font-size:.92rem;margin:.4rem 0 1.4rem}
.tbl th{font-family:var(--grotesk);font-weight:600;font-size:.72rem;text-transform:uppercase;
  letter-spacing:.08em;color:var(--muted);text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--rule-2)}
.tbl th.num{text-align:right}
.tbl td{padding:.42rem .6rem;border-bottom:1px solid var(--rule)}
.tbl tbody tr:hover{background:var(--paper-2)}
.swatch{display:inline-block;width:.66rem;height:.66rem;border-radius:2px;margin-right:.5rem;vertical-align:baseline}
.tag{font-family:var(--grotesk);font-size:.66rem;text-transform:uppercase;letter-spacing:.06em;
  padding:.04rem .35rem;border-radius:3px;border:1px solid var(--rule-2)}
.tag-open{color:var(--teal-2);background:var(--teal-tint);border-color:transparent}
.tag-closed{color:var(--ink-2);background:var(--paper-2)}

/* ---------- metric glossary ---------- */
.gloss{margin:1rem 0}
.gloss .row{display:grid;grid-template-columns:11rem 1fr;gap:1rem;padding:.85rem 0;border-top:1px solid var(--rule)}
.gloss .row:last-child{border-bottom:1px solid var(--rule)}
@media(max-width:680px){.gloss .row{grid-template-columns:1fr;gap:.2rem}}
.gloss .term{font-family:var(--grotesk);font-weight:600;font-size:.92rem}
.gloss .term .def{display:block;font-family:var(--mono);font-size:.74rem;color:var(--muted);
  font-weight:400;margin-top:.2rem}
.gloss .why{font-size:.98rem;color:var(--ink-2)}
.gloss .why b{color:var(--ink);font-weight:600}

/* ---------- timeline ---------- */
.timeline{margin:1rem 0 1.5rem;border-left:2px solid var(--rule-2);padding-left:1.4rem}
.stage{position:relative;padding:0 0 1.5rem}
.stage::before{content:"";position:absolute;left:-1.4rem;top:.35rem;width:.7rem;height:.7rem;
  border-radius:50%;background:var(--paper);border:2px solid var(--teal);transform:translateX(-50%)}
.stage.fix::before{border-color:var(--correction)}
.stage .when{font-family:var(--mono);font-size:.74rem;color:var(--muted)}
.stage h3{font-family:var(--grotesk);font-weight:600;font-size:1.05rem;margin:.1rem 0 .3rem}
.stage p{font-size:.98rem;margin:0;color:var(--ink-2)}

/* ---------- figures / charts ---------- */
figure{margin:1.6rem 0 1.8rem}
.figfull{max-width:calc(var(--maxw) + var(--margin-col) + var(--gap))}
figure figcaption{font-family:var(--grotesk);font-size:.78rem;color:var(--muted);margin-top:.7rem;
  line-height:1.5;border-top:1px solid var(--rule);padding-top:.5rem}
figure figcaption b{color:var(--ink-2);font-weight:600}
.chart{width:100%}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.controls{display:flex;flex-wrap:wrap;gap:1rem;align-items:flex-end;margin:.2rem 0 1.1rem}
.ctl{display:flex;flex-direction:column;gap:.3rem}
.ctl label{font-family:var(--grotesk);font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.ctl select{font-family:var(--grotesk);font-size:.86rem;color:var(--ink);background:var(--paper-2);
  border:1px solid var(--rule-2);border-radius:5px;padding:.34rem .6rem}
.seg{display:inline-flex;border:1px solid var(--rule-2);border-radius:6px;overflow:hidden;background:var(--paper-2)}
.seg button{font-family:var(--grotesk);font-size:.8rem;color:var(--ink-2);background:transparent;
  border:0;padding:.34rem .8rem;cursor:pointer}
.seg button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
.legend{display:flex;flex-wrap:wrap;gap:.4rem 1rem;margin:.7rem 0 0;font-family:var(--grotesk);font-size:.76rem;color:var(--ink-2)}
.legend span{display:inline-flex;align-items:center;gap:.4rem}
.legend i{width:.7rem;height:.7rem;border-radius:2px;display:inline-block}
text{font-family:var(--grotesk)}

/* ---------- why / mechanisms ---------- */
.mech{padding:1.5rem 0;border-top:1px solid var(--rule)}
.mech:first-of-type{border-top:0}
.mech .head{display:flex;align-items:baseline;gap:.7rem;flex-wrap:wrap;margin-bottom:.5rem}
.mech .mn{font-family:var(--mono);color:var(--teal-2);font-size:.95rem}
.mech h3{font-family:var(--serif);font-weight:600;font-size:1.3rem;letter-spacing:-.01em}
.badge{font-family:var(--grotesk);font-size:.64rem;text-transform:uppercase;letter-spacing:.08em;
  padding:.1rem .45rem;border-radius:3px;font-weight:600}
.badge.cited{color:var(--teal-2);background:var(--teal-tint)}
.badge.hyp{color:var(--amber);background:color-mix(in srgb,var(--amber) 16%,var(--paper-2));
  border:1px solid color-mix(in srgb,var(--amber) 35%,transparent)}
.mech .evidence{font-family:var(--grotesk);font-size:.86rem;color:var(--ink-2);
  background:var(--paper-2);border-left:2px solid var(--teal);padding:.6rem .9rem;margin:.6rem 0 0;border-radius:0 4px 4px 0}
.mech .evidence b{color:var(--ink)}
.mech .src{font-family:var(--grotesk);font-size:.78rem;color:var(--muted);margin-top:.5rem}

/* ---------- objections ---------- */
.obj{padding:1.15rem 0;border-top:1px solid var(--rule)}
.obj-q{font-size:1.12rem;color:var(--ink);display:flex;gap:.7rem;align-items:baseline}
.obj-n{font-family:var(--mono);font-size:.8rem;color:var(--muted)}
.obj-a{margin-top:.35rem;padding-left:1.9rem;color:var(--ink-2);font-size:1rem}
.obj-v{font-family:var(--grotesk);font-weight:700;color:var(--teal-2);margin-right:.3rem}
@media(max-width:680px){.obj-a{padding-left:0}}

/* ---------- ledger ---------- */
.ledger{font-family:var(--grotesk);margin:1rem 0 1.4rem;font-size:.92rem}
.ledger .lrow{display:grid;grid-template-columns:13rem 1fr;gap:1rem;padding:.7rem 0;border-top:1px dashed var(--rule-2)}
.ledger .lrow:last-child{border-bottom:1px dashed var(--rule-2)}
@media(max-width:680px){.ledger .lrow{grid-template-columns:1fr;gap:.15rem}}
.ledger .lk{font-weight:600;color:var(--ink)}
.ledger .lv{color:var(--ink-2)}
.ledger .lv .mono{color:var(--teal-2)}
.caveat{background:color-mix(in srgb,var(--correction) 7%,var(--paper-2));
  border:1px solid color-mix(in srgb,var(--correction) 22%,var(--rule));border-radius:6px;
  padding:1rem 1.1rem;margin:1.2rem 0;font-size:.96rem}
.caveat .ct{font-family:var(--grotesk);font-weight:700;color:var(--correction);font-size:.78rem;
  text-transform:uppercase;letter-spacing:.08em;display:block;margin-bottom:.4rem}

/* ---------- decision ---------- */
.choice{display:grid;grid-template-columns:1fr 1fr;gap:1.1rem;margin:1.3rem 0}
@media(max-width:680px){.choice{grid-template-columns:1fr}}
.opt{border:1px solid var(--rule-2);border-radius:8px;padding:1.1rem 1.2rem;background:var(--paper-2)}
.opt h3{font-family:var(--mono);font-size:1rem;color:var(--teal-2);margin-bottom:.4rem}
.opt .pro,.opt .con{font-family:var(--grotesk);font-size:.86rem;margin:.3rem 0;padding-left:1.2rem;position:relative}
.opt .pro::before{content:"+";position:absolute;left:0;color:var(--teal);font-weight:700}
.opt .con::before{content:"\2212";position:absolute;left:0;color:var(--correction);font-weight:700}

/* ---------- sources / colophon ---------- */
.sources{list-style:none;padding:0;margin:1rem 0}
.sources li{padding:.7rem 0;border-top:1px solid var(--rule)}
.src-who{font-family:var(--grotesk);font-weight:600;color:var(--ink);margin-right:.4rem}
.src-gloss{font-family:var(--grotesk);font-size:.82rem;color:var(--muted);margin-top:.2rem}
.colophon{padding:2.4rem 0 4rem;border-top:1px solid var(--rule);color:var(--muted);
  font-family:var(--grotesk);font-size:.82rem;line-height:1.6}
.colophon b{color:var(--ink-2)}

/* ---------- orientation: key findings + glossary ---------- */
.findings{border:1px solid var(--rule-2);border-radius:8px;background:var(--paper-2);padding:1.3rem 1.5rem;margin:1.6rem 0}
.findings h2{font-family:var(--grotesk);font-weight:700;font-size:.8rem;text-transform:uppercase;
  letter-spacing:.12em;color:var(--teal-2);margin-bottom:.9rem}
.findings ol{margin:0;padding:0;list-style:none;counter-reset:kf}
.findings li{counter-increment:kf;position:relative;padding:.5rem 0 .5rem 2.4rem;
  border-top:1px solid var(--rule);font-size:1.02rem;color:var(--ink)}
.findings li:first-child{border-top:0}
.findings li::before{content:counter(kf,decimal-leading-zero);position:absolute;left:0;top:.62rem;
  font-family:var(--mono);font-size:.78rem;color:var(--correction)}
.findings li b{font-weight:600}
.findings li .mono{color:var(--teal-2)}
details.disc{border-top:1px solid var(--rule);margin:0}
details.disc>summary{cursor:pointer;list-style:none;padding:.9rem 0;font-family:var(--grotesk);
  font-weight:600;font-size:.95rem;color:var(--ink);display:flex;align-items:center;gap:.6rem}
details.disc>summary::-webkit-details-marker{display:none}
details.disc>summary::before{content:"+";font-family:var(--mono);color:var(--teal-2);font-size:1.1rem;width:1rem}
details.disc[open]>summary::before{content:"\2212"}
details.disc>summary .hint{font-family:var(--grotesk);font-weight:400;font-size:.82rem;color:var(--muted);margin-left:auto}
details.disc>.disc-body{padding:.2rem 0 1.2rem}
.glossary{display:grid;grid-template-columns:1fr 1fr;gap:1.4rem 2.2rem}
@media(max-width:760px){.glossary{grid-template-columns:1fr}}
.glossary h3{font-family:var(--grotesk);font-weight:700;font-size:.72rem;text-transform:uppercase;
  letter-spacing:.1em;color:var(--muted);margin:0 0 .3rem;padding-bottom:.3rem;border-bottom:1px solid var(--rule-2)}
.glossary dl{margin:0}
.glossary dt{font-family:var(--grotesk);font-weight:600;font-size:.9rem;color:var(--ink);margin-top:.65rem}
.glossary dd{margin:.1rem 0 0;font-size:.92rem;line-height:1.45;color:var(--ink-2)}
.glossary dd .mono{color:var(--teal-2)}

/* ---------- raising the ceiling: flow + menu ---------- */
.split{display:grid;grid-template-columns:1fr 1fr;gap:1.1rem;margin:1.4rem 0}
@media(max-width:680px){.split{grid-template-columns:1fr}}
.gapcard{border:1px solid var(--rule-2);border-radius:8px;padding:1.1rem 1.2rem;background:var(--paper-2)}
.gapcard .gh{font-family:var(--grotesk);font-weight:700;font-size:.95rem;display:flex;justify-content:space-between;align-items:baseline}
.gapcard .gh .pctn{font-family:var(--mono);color:var(--correction);font-size:1.1rem}
.gapcard .who{font-family:var(--grotesk);font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:.2rem 0 .6rem}
.gapcard p{font-size:.92rem;margin:.5rem 0 0;color:var(--ink-2)}
.gapcard .fix{font-family:var(--grotesk);font-size:.84rem;color:var(--ink);margin-top:.7rem;padding-top:.6rem;border-top:1px solid var(--rule)}
.gapcard .fix b{color:var(--teal-2)}
.passlist{counter-reset:pl;margin:1.2rem 0}
.passlist .p{counter-increment:pl;position:relative;padding:.9rem 0 .9rem 3rem;border-top:1px solid var(--rule)}
.passlist .p::before{content:counter(pl);position:absolute;left:0;top:.85rem;width:1.7rem;height:1.7rem;
  border:1.5px solid var(--teal);border-radius:50%;color:var(--teal-2);font-family:var(--mono);
  font-size:.82rem;display:flex;align-items:center;justify-content:center}
.passlist .p h3{font-family:var(--grotesk);font-weight:600;font-size:1rem;margin:0 0 .2rem}
.passlist .p .cost{font-family:var(--mono);font-size:.74rem;color:var(--muted);float:right}
.passlist .p p{font-size:.95rem;margin:.2rem 0 0;color:var(--ink-2)}
.future{font-family:var(--grotesk);font-size:.64rem;text-transform:uppercase;letter-spacing:.09em;font-weight:700;
  color:var(--amber);border:1px solid color-mix(in srgb,var(--amber) 40%,transparent);
  background:color-mix(in srgb,var(--amber) 12%,var(--paper-2));border-radius:3px;padding:.1rem .45rem;vertical-align:middle}

@media(prefers-reduced-motion:no-preference){
  .reveal{opacity:0;transform:translateY(8px);transition:opacity .6s ease,transform .6s ease}
  .reveal.in{opacity:1;transform:none}
}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<nav class="nav" aria-label="Sections">
  <div class="nav-in">
    <div class="brand">palimpsest<span>/</span>T72</div>
    <a href="#start"><span class="n">&#9656;</span> <span class="lbl">Start</span></a>
    <a href="#corpus"><span class="n">1</span> <span class="lbl">Question</span></a>
    <a href="#method"><span class="n">2</span> <span class="lbl">Method</span></a>
    <a href="#story"><span class="n">3</span> <span class="lbl">The turn</span></a>
    <a href="#results"><span class="n">4</span> <span class="lbl">Results</span></a>
    <a href="#why"><span class="n">5</span> <span class="lbl">Why</span></a>
    <a href="#ceiling"><span class="n">6</span> <span class="lbl">Ceiling</span></a>
    <a href="#objections"><span class="n">7</span> <span class="lbl">Objections</span></a>
    <a href="#repro"><span class="n">8</span> <span class="lbl">Reproducibility</span></a>
    <a href="#decision"><span class="n">9</span> <span class="lbl">Decision</span></a>
  </div>
</nav>

<main id="main" class="wrap"><div class="essay">

<!-- ======================= MASTHEAD ======================= -->
<header class="mast">
  <div class="eyebrow">Palimpsest &middot; Experiment&nbsp;T72 &middot; %%DATE%%</div>
  <h1>How much of &lsquo;accuracy&rsquo;<br>is the <em>model</em> at all?</h1>
  <p class="standfirst">A benchmark of %%N_MODELS%% language models against %%N_PARSERS%% PDF
  parsers, extracting %%N_GOLD%% hand-verified measurements from %%N_PAPERS%% oxygen-evolution
  catalysis papers &mdash; and the case that extraction accuracy is <em>conditional on the parser</em>,
  not a fixed property of the model.</p>

  <div class="hero">
    <div>
      <div class="big">0.46<span class="arrow">&rarr;</span>0.78</div>
      <p class="cap">The model the first pass flagged as <em>worst</em> &mdash; deepseek-flash &mdash;
      recovers from &micro;F1&nbsp;%%DSFLASH_MINERU%% on MinerU to %%DSFLASH_DOCLING%% on Docling.
      Same weights, same prompt; only the parser changed.</p>
      <p class="firstread">First reading (06-20, before the gold audit):
      <span class="was">0.27 &rarr; 0.63</span>. Re-scored after correction, the gap only widened.</p>
    </div>
    <figure class="chart" id="hero-chart" aria-label="deepseek-flash micro-F1 across the four parsers"></figure>
  </div>

  <div class="chips">
    <span class="chip"><span class="dot">&#9679;</span> grid <b>%%N_MODELS%%&times;%%N_PARSERS%%&times;%%N_PAPERS%%</b></span>
    <span class="chip">gold <b>%%N_GOLD%% tuples</b> &middot; hand-audited</span>
    <span class="chip">prompt&nbsp;hash <b class="mono">%%PROMPT_HASH%%</b></span>
    <span class="chip">spend <b>&asymp;&euro;24 / &euro;50</b> &middot; re-score &euro;0</span>
    <span class="chip">scorer <b>deterministic &plusmn;1%</b></span>
  </div>
</header>

<!-- ======================= START HERE ======================= -->
<section id="start" style="border-top:0;padding-top:1.4rem">
  <div class="findings">
    <h2>What this page shows &mdash; in five lines</h2>
    <ol>
      <li><b>You don&rsquo;t need an expensive model.</b> The highest average on the corrected grid is a
        cheap one (%%TOP_MODEL%%, &micro;F1 %%TOP_F1%%); cost per correct extraction spans about
        <span class="mono">%%COST_SPREAD%%&times;</span>.</li>
      <li><b>Accuracy is conditional on the parser.</b> The same weights (deepseek-flash) score
        &micro;F1 <span class="mono">%%DSFLASH_MINERU%%</span> on one parser and
        <span class="mono">%%DSFLASH_DOCLING%%</span> on another.</li>
      <li><b>Most of the remaining gap is the parser, not the model.</b> Of %%TAX_MISS%% misses,
        %%TAX_COVGAP%% (%%TAX_COVGAP_PCT%%%) are values absent from the parser&rsquo;s text; once that
        ceiling is divided out, grid recall rises %%GRID_RECALL%%% &rarr; %%GRID_REACHABLE%%%.</li>
      <li><b>The way to capture more is passes, not a different input.</b> Sending the PDF straight to a
        vision model fixes only the %%TAX_COVGAP_PCT%%% ceiling (and breaks provenance); the
        %%TAX_MODELGAP_PCT%%% model gap needs a second pass / ensemble / loop &mdash; see &sect;6.</li>
      <li><b>One decision is still open:</b> the locked runtime default is the weakest overall model.
        Candidates and trade-offs in &sect;9.</li>
    </ol>
  </div>

  <details class="disc">
    <summary>Definitions &amp; glossary<span class="hint">domain + method terms &mdash; click to expand</span></summary>
    <div class="disc-body">
      <div class="glossary">
        <div>
          <h3>The science</h3>
          <dl>
            <dt>OER</dt><dd>Oxygen-evolution reaction &mdash; the slow half-reaction in water electrolysis these catalysts accelerate.</dd>
            <dt>Overpotential</dt><dd>Extra voltage (mV) above thermodynamic minimum needed to drive a target current; <em>lower is better</em>. Usually quoted at 10&nbsp;mA/cm&sup2;.</dd>
            <dt>Tafel slope</dt><dd>mV per decade of current &mdash; how much more voltage each 10&times; in rate costs; lower means better kinetics. Often printed only inside a figure.</dd>
            <dt>Mass / specific activity</dt><dd>Current normalized per gram of catalyst (mass) or per real surface area (specific).</dd>
            <dt>Turnover frequency (TOF)</dt><dd>Reactions per active site per second &mdash; intrinsic site activity.</dd>
            <dt>Stability</dt><dd>How long performance holds (hours) under load &mdash; the durability test.</dd>
            <dt>RHE &middot; iR-correction</dt><dd>Reference electrode potentials are quoted vs RHE; <span class="mono">iR</span>-correction removes the solution&rsquo;s resistive voltage drop.</dd>
          </dl>
        </div>
        <div>
          <h3>The method</h3>
          <dl>
            <dt>Parser</dt><dd>The tool that turns a PDF into text + layout the model reads. <em>Figure-aware</em> parsers also emit text rendered inside figures.</dd>
            <dt>Gold tuple</dt><dd>A hand-verified (measurement type, value) the model is expected to find.</dd>
            <dt>Recall &middot; precision &middot; F1</dt><dd>Found / total; correct / reported; their harmonic mean.</dd>
            <dt>micro vs &micro; (macro)</dt><dd>Micro pools all papers (weights big papers more); &micro; averages per-paper scores equally.</dd>
            <dt>Coverage ceiling</dt><dd>The best recall <em>any</em> model could reach on a parser &mdash; the share of gold values whose text the parser actually emitted.</dd>
            <dt>Reachable-recall</dt><dd>Recall with the ceiling divided out (<span class="mono">hits / reachable</span>) &mdash; isolates pure model skill from parser limits.</dd>
            <dt>Coverage gap vs model gap</dt><dd>A miss the parser caused (value not in text) vs one the model caused (value was there, not taken).</dd>
            <dt>raw vs strict</dt><dd>Free-form JSON vs decoding locked to a JSON schema.</dd>
            <dt>prompt_hash &middot; tolerance</dt><dd><span class="mono">%%PROMPT_HASH%%</span> fingerprints the inputs; a value counts as correct within <span class="mono">&plusmn;1%</span>.</dd>
          </dl>
        </div>
      </div>
    </div>
  </details>
</section>

<!-- ======================= 1 · QUESTION & CORPUS ======================= -->
<section id="corpus">
  <div class="section-head">
    <div class="kicker"><span class="secno">01</span><span class="eyebrow">The question &amp; the corpus</span></div>
    <h2>Two questions, one experiment</h2>
  </div>

  <div class="passage">
    <p class="lead">palimpsest is an autonomous agent that turns research PDFs into a provenance-tracked
    knowledge graph. Before trusting any model to do that unattended, two questions had to be answered
    with numbers.</p>
    <aside class="mnote"><span class="mlabel">Why it matters</span>The thesis contribution is the
    constrained-autonomy agent. Parser-conditional accuracy is the section that tells the agent
    <em>which</em> model and parser it may rely on.</aside>

    <p><strong>One &mdash; does extracting measurements from a paper require an expensive model?</strong>
    If a &euro;0.0007-per-paper model matches a frontier one, the whole economics of running the agent
    change. <strong>Two &mdash; and the sharper question &mdash; how much of what we call &lsquo;accuracy&rsquo;
    is the model at all, versus the PDF parser that fed it?</strong> That second question is the
    <em>parser-conditional accuracy</em> claim, and it is what T72 puts numbers on.</p>

    <p>The design is a full grid: every model reads every paper as rendered by every parser, and its
    structured output is scored against a hand-built gold standard with a deterministic tolerance check.
    The corpus is five oxygen-evolution-reaction (OER) catalyst papers from <span class="mono">Nature</span>
    journals, chosen because their key results &mdash; overpotentials, Tafel slopes, stabilities &mdash;
    live in a mix of tables, prose, and figures.</p>
  </div>

  <p style="font-size:.98rem;color:var(--ink-2)">The corpus is %%N_PAPERS%% papers (%%N_GOLD%% gold tuples),
  the roster %%N_MODELS%% models across four providers, each read through four parsers. The split that matters among
  parsers is <em>figure-aware</em> (Docling, PaddleOCR, dots.ocr) versus <em>text-block</em> (MinerU).</p>

  <details class="disc">
    <summary>The %%N_PAPERS%% papers and %%N_MODELS%% models<span class="hint">full tables &mdash; click to expand</span></summary>
    <div class="disc-body">
      <h3 class="grotesk" style="font-family:var(--grotesk);font-weight:600;font-size:.85rem;margin:.4rem 0 .4rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)">Corpus &mdash; %%N_PAPERS%% papers, %%N_GOLD%% gold tuples</h3>
      <table class="tbl">
        <thead><tr><th class="num">#</th><th>SHA-8</th><th>DOI</th><th class="num">Pages</th><th class="num">Gold</th></tr></thead>
        <tbody>%%CORPUS_ROWS%%</tbody>
      </table>
      <h3 class="grotesk" style="font-family:var(--grotesk);font-weight:600;font-size:.85rem;margin:1.4rem 0 .4rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)">Roster &mdash; %%N_MODELS%% models, four providers</h3>
      <table class="tbl">
        <thead><tr><th>Label</th><th>Model</th><th>Provider</th><th>Family</th><th>Access</th><th>Tier</th></tr></thead>
        <tbody>%%ROSTER_ROWS%%</tbody>
      </table>
      <p class="muted" style="font-size:.84rem;font-family:var(--grotesk)">A free-tier Gemini ran on a subset
      and is excluded from the comparable grid.</p>
    </div>
  </details>
</section>

<!-- ======================= 2 · METHOD ======================= -->
<section id="method">
  <div class="section-head">
    <div class="kicker"><span class="secno">02</span><span class="eyebrow">Method, and why each metric exists</span></div>
    <h2>Every number on this page is auditable</h2>
  </div>

  <div class="passage">
    <p class="lead">Each metric was added to answer a specific doubt. None is decorative.</p>
    <aside class="mnote"><span class="mlabel">Design choice</span>Costs are re-derived from token counts
    &times; each provider&rsquo;s verified rate, <em>not</em> read from the in-app meter, which falls back to
    Sonnet pricing for unknown providers and would silently mis-price every non-Claude row.</aside>
  </div>

  <div class="gloss">
    <div class="row"><div class="term">recall<span class="def">tp / gold</span></div>
      <div class="why"><b>Completeness.</b> Did the model miss anything? A 90%-precise model that skips a
      tenth of every paper is useless to an agent that must capture all of a paper&rsquo;s data.</div></div>
    <div class="row"><div class="term">precision<span class="def">tp / predicted</span></div>
      <div class="why"><b>Trust.</b> Of what it reported, how much was real? This is the guard against
      hallucinated measurements entering the graph.</div></div>
    <div class="row"><div class="term">F1<span class="def">2PR / (P+R)</span></div>
      <div class="why"><b>One honest number.</b> High only when precision <em>and</em> recall are both high,
      so a lopsided model can&rsquo;t look good.</div></div>
    <div class="row"><div class="term">micro-recall<span class="def">&Sigma;tp / &Sigma;gold</span></div>
      <div class="why"><b>Weighting by size.</b> Aggregates across papers so a 19-tuple paper counts for more
      than a 2-tuple one, instead of letting small papers swing the average.</div></div>
    <div class="row"><div class="term">&euro; / correct<span class="def">&Sigma;&euro; / &Sigma;tp</span></div>
      <div class="why"><b>Production economics.</b> Cheap-but-wrong is expensive per <em>useful</em> result.
      Cost per paper is meaningless; cost per correct extraction is the real ROI the agent pays.</div></div>
    <div class="row"><div class="term">raw vs strict<span class="def">free JSON vs schema-locked</span></div>
      <div class="why"><b>A probe.</b> Does forcing a JSON schema help? Run both and see. Raw is what
      production actually does; strict is the controlled contrast.</div></div>
    <div class="row"><div class="term">coverage gap<br>&middot; model gap<span class="def">error taxonomy</span></div>
      <div class="why"><b>Separating blame.</b> A miss is a <em>coverage gap</em> if the value isn&rsquo;t in
      the parser&rsquo;s text at all (no model could get it) or a <em>model gap</em> if it was there and the
      model didn&rsquo;t take it. Only the second is a model&rsquo;s fault.</div></div>
  </div>

  <div class="passage">
    <p><strong>Why not grade with an LLM judge?</strong> Because grading LLM output with an LLM is circular,
    costs money, and folds the judge&rsquo;s own variance into the measurement. The scorer here is a numeric
    tolerance check &mdash; <span class="mono">&plusmn;1%</span>, with a <span class="mono">&plusmn;0.5</span>
    floor for integers and <span class="mono">&plusmn;1e-4</span> for sub-unit values &mdash; which is free,
    deterministic, and re-runnable to the same answer forever.</p>
    <aside class="mnote"><span class="mlabel">Why not</span>An LLM judge would also have made the &euro;0
    re-score impossible: you can replay a tolerance check over cached output for free; you cannot replay a
    paid judge for free.</aside>
  </div>
</section>

<!-- ======================= 3 · THE STORY AS IT CHANGED ======================= -->
<section id="story">
  <div class="section-head">
    <div class="kicker"><span class="secno">03</span><span class="eyebrow">The story as it changed</span></div>
    <h2>The experiment corrected itself &mdash; twice</h2>
  </div>

  <div class="passage">
    <p class="lead">A palimpsest is a manuscript scraped clean and written over, the earlier text still
    faintly visible. This experiment earned the name: its first conclusions were overwritten, and the
    corrections are left showing on purpose.</p>
    <aside class="mnote warn"><span class="mlabel">The signature</span>Where a number on this page was
    <span class="was">struck</span> and replaced, that is a real revision from the gold audit or the
    re-score &mdash; not decoration. The method <em>is</em> the self-correction.</aside>
  </div>

  <div class="timeline">
    <div class="stage">
      <div class="when">Stage 0 &middot; 06-19</div>
      <h3>Proof of concept</h3>
      <p>One paper, eight models. DeepSeek-pro and a free Gemini both hit 0.97 F1 at &euro;0.01 and &euro;0.
      Encouraging, but one paper proves nothing.</p>
    </div>
    <div class="stage">
      <div class="when">Stage 1 &middot; 06-20 &middot; MinerU only</div>
      <h3>The shock</h3>
      <p>Five papers, the locked production default &mdash; deepseek-flash &mdash; came <em>last</em>,
      at <span class="was">0.27</span> &micro;F1, scoring zero on three papers. The instinct was to call it
      a bad model and move on. Instead: hold the verdict until a second parser is tried.</p>
    </div>
    <div class="stage fix">
      <div class="when">Stage 2 &middot; 06-20 &middot; + Docling, dots, Paddle</div>
      <h3>The rescue &mdash; and the real finding</h3>
      <p>On Docling, deepseek-flash jumped to <strong>0.63</strong> &micro;F1.
      The &ldquo;worst model&rdquo; was a <em>parser artifact</em>. That is the thesis: the same weights,
      read through a different parser, change rank entirely.</p>
    </div>
    <div class="stage fix">
      <div class="when">Stage 3 &middot; 06-21 &middot; correction pass (&euro;0)</div>
      <h3>Audit, decompose, re-score</h3>
      <p>Every gold number was re-read against its PDF: all 41 were real, but one paper-5 &ldquo;stability&rdquo;
      tuple was a <span class="was">mislabel</span> and was dropped, taking 24 spurious model-gaps with it.
      Coverage and error-taxonomy tools then split every miss into parser-fault vs model-fault. Because every
      paid call had been cached, this entire pass cost nothing.</p>
    </div>
  </div>

  <div class="passage">
    <aside class="mnote"><span class="mlabel">What we did <em>not</em> do</span>We did not re-run the paid
    grid to &ldquo;clean up&rdquo; numbers, did not switch to an LLM judge, and did not drop deepseek-flash
    after Stage 1. Each restraint is what kept the comparison honest and the budget at &euro;0 for Stage 3.</aside>
    <p>Everything below uses the <strong>06-21 corrected snapshots</strong> &mdash; %%N_GOLD%% gold tuples,
    re-scored from cache. The earlier 06-20 figures survive only in the struck text, as the record of what
    changed.</p>
  </div>
</section>

<!-- ======================= 4 · RESULTS ======================= -->
<section id="results">
  <div class="section-head">
    <div class="kicker"><span class="secno">04</span><span class="eyebrow">Results</span></div>
    <h2>The cheap end is competitive</h2>
  </div>

  <div class="passage">
    <p class="lead">On the corrected grid, the highest average belongs to a cheap model, and the spread in
    cost per correct extraction is about <strong>%%COST_SPREAD%%&times;</strong> &mdash; which is the whole point.</p>
  </div>

  <figure class="figfull">
    <div class="controls" role="group" aria-label="Leaderboard controls">
      <div class="ctl"><label for="lb-metric">Metric</label>
        <select id="lb-metric">
          <option value="muF1">&micro;-F1</option>
          <option value="microRecall">micro-recall</option>
          <option value="muPrecision">&micro;-precision</option>
          <option value="eurPerTp">&euro; / correct</option>
          <option value="latency">latency (s)</option>
        </select></div>
      <div class="ctl"><label for="lb-parser">Parser</label>
        <select id="lb-parser">
          <option value="avg">average of 4</option>
          <option value="mineru">MinerU</option>
          <option value="docling">Docling</option>
          <option value="dots">dots.ocr</option>
          <option value="paddle">PaddleOCR</option>
        </select></div>
      <div class="ctl"><label>Decoding</label>
        <div class="seg" id="lb-mode" role="group" aria-label="Decoding mode">
          <button data-mode="raw" aria-pressed="true">raw</button>
          <button data-mode="strict" aria-pressed="false">strict</button>
        </div></div>
    </div>
    <div class="chart" id="leaderboard"></div>
    <figcaption id="lb-cap"></figcaption>
  </figure>

  <div class="passage">
    <p>Read the leaderboard against the matrix below. The leaderboard ranks models; the matrix shows
    <em>why a ranking is fragile</em> &mdash; each cell is one model&rsquo;s micro-recall on one parser, and
    the row-to-row swing inside a single model is often larger than the gap between models.</p>
    <aside class="mnote"><span class="mlabel">How to read it</span>Darker = higher recall. The bottom row is
    the <em>coverage ceiling</em>: the best recall any model could reach on that parser, set by what the
    parser&rsquo;s text actually contains.</aside>
  </div>

  <figure class="figfull">
    <div class="chart" id="heatmap"></div>
    <figcaption><b>Parser-conditional accuracy.</b> Micro-recall, raw mode, 06-21. The cheap models swing
    most across parsers; the robust models (deepseek-pro, sonnet) hold a high floor everywhere &mdash; which
    is the property an agent needs, because it does not get to pick the parser per paper.</figcaption>
  </figure>

  <figure class="figfull">
    <div class="controls" role="group" aria-label="Cost chart controls">
      <div class="ctl"><label>Cost axis</label>
        <div class="seg" id="sc-axis" role="group" aria-label="Cost axis">
          <button data-axis="eurPerTp" aria-pressed="true">&euro; / correct</button>
          <button data-axis="eurPerPaper" aria-pressed="false">&euro; / paper</button>
        </div></div>
    </div>
    <div class="chart" id="scatter"></div>
    <figcaption><b>Accuracy buys little after the cheap tier.</b> Average over the four parsers, raw mode,
    log cost axis. Points to the upper-left are the prize: high accuracy, near-zero cost. Sonnet sits far to
    the right for a fraction of a point of F1.</figcaption>
  </figure>

  <div class="passage">
    <h3>Skill vs ceiling &mdash; what the model actually missed</h3>
    <p>Raw recall blames the model for values the parser never produced. <em>Reachable-recall</em> divides the
    coverage ceiling out &mdash; <span class="mono">hits / (gold the parser surfaced)</span> &mdash; so what
    remains is pure model skill. The lift from one to the other is the parser&rsquo;s share of the blame.</p>
    <aside class="mnote"><span class="mlabel">Reading</span>The dot is raw recall; the tick is reachable.
    A wide gap means that model was held back by the parser, not its own ability. Grid-wide it is
    %%GRID_RECALL%%% &rarr; %%GRID_REACHABLE%%%.</aside>
  </div>

  <figure class="figfull">
    <div class="chart" id="reachable"></div>
    <figcaption><b>Most models are better than their recall suggests.</b> Average over the four parsers, raw.
    Once figure-only values are excluded, deepseek-pro and sonnet clear 95%; even deepseek-flash reaches
    %%DSFLASH_REACHABLE%%% from a raw %%DSFLASH_MICRO%%%.</figcaption>
  </figure>
</section>

<!-- ======================= 5 · WHY ======================= -->
<section id="why">
  <div class="section-head">
    <div class="kicker"><span class="secno">05</span><span class="eyebrow">Why models differ across parsers</span></div>
    <h2>Five mechanisms, one effect</h2>
  </div>

  <div class="passage">
    <p class="lead">Why does the <em>same</em> model rise and fall with the parser? The closed models
    (GPT, Gemini, Claude) keep their internals private, so part of this is necessarily inference. Each claim
    below is tagged <span class="badge cited">cited</span> for a published mechanism or
    <span class="badge hyp">hypothesis</span> for our reading of the T72 evidence.</p>
    <aside class="mnote"><span class="mlabel">Honesty</span>We do not claim to know GPT-5.4&rsquo;s
    architecture. We claim that <em>known, general</em> mechanisms predict exactly the pattern T72 shows.</aside>
  </div>

  <div class="mech">
    <div class="head"><span class="mn">i</span><h3>Where the number sits in the span</h3>
      <span class="badge cited">cited</span></div>
    <p>MinerU emits coarse text blocks; a target value lands deep inside a long span. Docling emits fine,
    figure-aware spans; the same value sits near a boundary. Language models recall information at the
    <em>edges</em> of a context far better than in its middle &mdash; the &ldquo;lost in the middle&rdquo;
    effect &mdash; and the rotary positional encoding most models use has a long-term decay that biases
    attention toward span edges.</p>
    <div class="evidence"><b>T72 evidence:</b> deepseek-flash &micro;F1 MinerU %%DSFLASH_MINERU%% &rarr;
    Docling %%DSFLASH_DOCLING%%; the gain is largest exactly for the small models most sensitive to span length.</div>
    <div class="src">Liu et&nbsp;al. 2023, <a href="https://arxiv.org/abs/2307.03172">Lost in the Middle</a>
    &middot; Su et&nbsp;al. 2021, <a href="https://arxiv.org/abs/2104.09864">RoFormer / RoPE</a></div>
  </div>

  <div class="mech">
    <div class="head"><span class="mn">ii</span><h3>The value isn&rsquo;t in the text at all</h3>
      <span class="badge cited">cited</span></div>
    <p>Some numbers exist only as typeset labels inside a figure. A text-only parser never emits them, so no
    model &mdash; however capable &mdash; can extract them. This is not a model property; it is a hard ceiling
    set by the parser&rsquo;s modality. It alone explains most of the parser ranking.</p>
    <div class="evidence"><b>T72 evidence:</b> %%N_FIGONLY%% Tafel slopes live only inside one paper&rsquo;s
    Fig.&nbsp;3b. Coverage ceiling: Docling %%CEIL_DOCLING%%%, PaddleOCR %%CEIL_PADDLE%%% vs MinerU %%CEIL_MINERU%%%,
    dots.ocr %%CEIL_DOTS%%%. Those four values are the entire difference.</div>
    <div class="src">Measured directly &mdash; see the coverage chart below.</div>
  </div>

  <div class="mech">
    <div class="head"><span class="mn">iii</span><h3>Sparse experts, thin activation</h3>
      <span class="badge hyp">hypothesis</span></div>
    <p>The DeepSeek models are Mixture-of-Experts: a huge parameter pool with only a small slice
    (&asymp;37B of 671B in the published V3) active per token. On dense, well-formatted spans this is plenty;
    on noisy, low-signal coarse blocks, a cheap MoE may route to too little capacity to recover a buried
    number &mdash; consistent with deepseek-flash collapsing on MinerU yet topping cells on Docling.</p>
    <div class="evidence"><b>T72 evidence:</b> deepseek-flash is the most parser-sensitive model in the grid;
    deepseek-pro &mdash; same provider, more capacity &mdash; holds a high floor on every parser.</div>
    <div class="src">DeepSeek-AI 2024, <a href="https://arxiv.org/abs/2412.19437">DeepSeek-V3 Technical Report</a>
    (architecture reference; T72 models are closed V4 variants).</div>
  </div>

  <div class="mech">
    <div class="head"><span class="mn">iv</span><h3>How the tokenizer splits a number</h3>
      <span class="badge hyp">hypothesis</span></div>
    <p>Whether &ldquo;45.16&rdquo; becomes one token or several changes how reliably a model reproduces it.
    Tokenization is known to move arithmetic and numeric fidelity measurably. When a parser reformats a value
    (spacing, unit placement, OCR artifacts), it can shift the tokenization and nudge a model into dropping or
    mangling the digits.</p>
    <div class="evidence"><b>T72 evidence:</b> errors cluster on multi-digit, unit-bearing values
    (Tafel slopes, mass activities) rather than on small integers &mdash; the pattern numeric-tokenization
    effects predict.</div>
    <div class="src">Singh &amp; Strouse 2024, <a href="https://arxiv.org/abs/2402.14903">Tokenization counts</a></div>
  </div>

  <div class="mech">
    <div class="head"><span class="mn">v</span><h3>Forcing a schema costs the cheap models</h3>
      <span class="badge cited">cited</span></div>
    <p>Constrained (&lsquo;strict&rsquo;) decoding to a JSON schema narrows the model&rsquo;s output
    distribution. Tighter format restrictions measurably <em>degrade</em> reasoning, and weaker models pay
    more. That is why raw &mdash; not schema-locked &mdash; is the production-faithful headline here.</p>
    <div class="evidence"><b>T72 evidence:</b> switch the leaderboard to <em>strict</em>: the cheap models
    lose ground (Gemini Flash-Lite drops sharply on several cells) while the GPTs barely move.</div>
    <div class="src">Tam et&nbsp;al. 2024, <a href="https://arxiv.org/abs/2408.02442">Let Me Speak Freely?</a></div>
  </div>

  <div class="passage" style="margin-top:2rem">
    <p>The first two mechanisms are measured directly in T72; the charts below are the evidence. The error
    taxonomy splits every miss into parser-fault and model-fault; the coverage strip shows the ceiling each
    parser imposes.</p>
  </div>

  <figure class="figfull">
    <div class="chart" id="taxonomy"></div>
    <figcaption><b>Where the misses come from.</b> Every gold slot across the raw grid, by outcome. Coverage
    gaps (parser-fault) are concentrated entirely in the text-only parsers; on Docling and PaddleOCR they
    vanish. Of %%TAX_MISS%% total misses, %%TAX_COVGAP%% (%%TAX_COVGAP_PCT%%%) are coverage, %%TAX_MODELGAP%%
    are genuine model gaps, %%TAX_WRONGTYPE%% is a type confusion.</figcaption>
  </figure>

  <figure class="figfull">
    <div class="chart" id="coverage"></div>
    <figcaption><b>The ceiling each parser imposes.</b> Share of gold values whose literal text the parser
    actually emitted. The %%N_FIGONLY%%-point gap on MinerU and dots.ocr is the four figure-only Tafel slopes:</figcaption>
    <ul class="muted" style="font-family:var(--mono);font-size:.82rem;line-height:1.7;margin:.6rem 0 0;padding-left:1.1rem">%%FIGUREONLY%%</ul>
  </figure>

  <div class="passage">
    <p>The same split sorts the <em>measurement types</em>. %%TYPE_HARDEST%% looks like the hardest quantity
    (recall %%TYPE_HARDEST_R%%%) &mdash; but its whole shortfall is the figure-only ceiling: divide that out and
    it is among the easiest. <strong>Stability</strong> is the genuinely hard one for the models: no coverage
    gap, yet recall stays low, because a bare value can&rsquo;t tell a hero catalyst&rsquo;s lifetime from a
    reference&rsquo;s.</p>
    <aside class="mnote"><span class="mlabel">Reading</span>Solid bar = recall; the hollow extension = the
    reachable-recall a figure-aware parser unlocks. Only %%TYPE_HARDEST%% has a meaningful extension.</aside>
  </div>

  <figure class="figfull">
    <div class="chart" id="bytype"></div>
    <figcaption><b>Which quantities are hard &mdash; and why.</b> Recall by measurement type across the raw grid.
    The gap between solid and hollow is the parser ceiling; everything to the left of it is the model.</figcaption>
  </figure>
</section>

<!-- ======================= 6 · RAISING THE CEILING ======================= -->
<section id="ceiling">
  <div class="section-head">
    <div class="kicker"><span class="secno">06</span><span class="eyebrow">Raising the ceiling</span>
      <span class="future">proposed &middot; T73</span></div>
    <h2>What would actually capture everything?</h2>
  </div>

  <div class="passage">
    <p class="lead">The obvious idea is to stop parsing and send the PDF straight to a vision model. It helps
    less than it looks, and it costs something palimpsest cannot give up. The fix the data points to is
    <em>passes</em>, not a different input.</p>
    <aside class="mnote warn"><span class="mlabel">Caveat</span>T72 measured <em>single-shot</em> extraction.
    Everything in this section is a proposed method with a predicted mechanism &mdash; the next experiment
    (T73) would measure it.</aside>
  </div>

  <div class="passage">
    <p>Start from the taxonomy, because the two kinds of miss have two different cures. Sending the page as an
    image attacks only the first; it does nothing for the second &mdash; which is the larger.</p>
  </div>

  <div class="split">
    <div class="gapcard">
      <div class="gh">Coverage gap <span class="pctn">%%TAX_COVGAP_PCT%%%</span></div>
      <div class="who">parser&rsquo;s fault &middot; value not in the text</div>
      <p>The %%N_FIGONLY%% Tafel slopes printed only inside a figure. A text-only parser can never emit them.</p>
      <div class="fix"><b>Fix:</b> a figure-aware parser already closes this (Docling, PaddleOCR hit a 100%
      ceiling). Belt-and-suspenders: send only parser-flagged <em>figure crops</em> to a vision model, inheriting
      the parser&rsquo;s bbox so provenance survives.</div>
    </div>
    <div class="gapcard">
      <div class="gh">Model gap <span class="pctn">%%TAX_MODELGAP_PCT%%%</span></div>
      <div class="who">model&rsquo;s fault &middot; value was there, not taken</div>
      <p>The value sat in the parser&rsquo;s output and the model simply didn&rsquo;t return it. Changing the
      input format does not fix this.</p>
      <div class="fix"><b>Fix:</b> a second pass &mdash; re-query for what&rsquo;s missing, union across parsers,
      or loop with a verifier. This is the real headroom.</div>
    </div>
  </div>

  <div class="passage">
    <h3>Why not just send the PDF to the API?</h3>
    <p>Three reasons it is an auxiliary tool, not a replacement. <strong>One</strong>, it targets only the
    %%TAX_COVGAP_PCT%%% coverage gap &mdash; already solved more cheaply by a figure-aware parser.
    <strong>Two</strong>, it breaks the provenance invariant: every triple palimpsest stores must carry
    <span class="mono">(paper_hash, parser, page, bbox)</span>. A parser hands you the bbox; a raw vision call
    does not &mdash; the model would have to self-report pixel coordinates, unreliably. <strong>Three</strong>,
    a rendered page is thousands of image tokens, so the cheap-model economics that make this study interesting
    collapse, and vision OCR of dense numeric tables is often <em>worse</em> than a good text parser.</p>
    <aside class="mnote"><span class="mlabel">The principle</span>The parser is not in the way of accuracy &mdash;
    it is what makes a provenance-clean, auditable triple possible. Vision is a patch for figures, not the road.</aside>
  </div>

  <div class="passage">
    <h3>The passes, cheapest first</h3>
    <p>All of these keep parse-then-extract, so provenance is intact, and all are affordable precisely because
    the strong models here are cheap &mdash; the thesis turned into a method.</p>
  </div>

  <div class="passlist">
    <div class="p"><span class="cost">~free</span><h3>Parser ensemble (union)</h3>
      <p>Run two figure-aware parsers and union the extractions. Different parsers surface different values;
      near-free recall, provenance preserved. The first move.</p></div>
    <div class="p"><span class="cost">+1 call</span><h3>Coverage-driven second pass</h3>
      <p>Tell the model what it already found and ask specifically for the types usually present but missing:
      &ldquo;you reported overpotential and stability; OER papers normally also report a Tafel slope and mass
      activity &mdash; extract them or state &lsquo;absent&rsquo;.&rdquo; Aimed straight at the model gap.</p></div>
    <div class="p"><span class="cost">&times;N calls</span><h3>Self-consistency</h3>
      <p>Sample N times at non-zero temperature, then union or vote. Recall rises with the union; the vote
      cleans precision. Cost scales with N &mdash; cheap models make it viable.</p></div>
    <div class="p"><span class="cost">loop</span><h3>Verify-and-loop (the critic)</h3>
      <p>A pass that checks each extracted value against its cited span &mdash; killing false positives and bad
      bboxes &mdash; then re-reads for misses. Repeat until a pass adds nothing new: <em>loop-until-dry</em>.</p></div>
  </div>

  <div class="passage">
    <p><strong>The recommendation:</strong> keep parse-then-extract; default to a figure-aware parser (ceiling
    solved); add a two-pass loop (extract &rarr; coverage-driven re-query &rarr; stop when dry), unioned across
    two parsers; reserve targeted vision for parser-flagged figure crops only. Predicted effect: most of the
    %%TAX_MODELGAP%% model gaps convert to hits for the price of about one extra cheap call per paper.</p>
  </div>
</section>

<!-- ======================= 7 · OBJECTIONS ======================= -->
<section id="objections">
  <div class="section-head">
    <div class="kicker"><span class="secno">07</span><span class="eyebrow">Objections &amp; answers</span></div>
    <h2>What a skeptical examiner asks</h2>
  </div>
  <div class="passage">
    <p class="lead">The claim is only as strong as its weakest objection. Here are the nine that matter, each
    with the answer the data already supports.</p>
  </div>
  %%OBJECTIONS%%
</section>

<!-- ======================= 7 · REPRODUCIBILITY ======================= -->
<section id="repro">
  <div class="section-head">
    <div class="kicker"><span class="secno">08</span><span class="eyebrow">Reproducibility ledger</span></div>
    <h2>What makes this re-runnable &mdash; and where it stops</h2>
  </div>
  <div class="passage">
    <p class="lead">Reproducibility is a feature of the harness, not a hope. The honest version also names its
    own limits.</p>
  </div>

  <div class="ledger">
    <div class="lrow"><div class="lk">Prompt hash</div><div class="lv"><span class="mono">%%PROMPT_HASH%%</span>
      &mdash; SHA over skill body + schema + normalization + class names. Any change invalidates the cache,
      so stale outputs can never be scored against a new prompt.</div></div>
    <div class="lrow"><div class="lk">Deterministic scorer</div><div class="lv">&plusmn;1% tolerance,
      <span class="mono">&plusmn;0.5</span> integer floor, <span class="mono">&plusmn;1e-4</span> sub-unit.
      Free and identical on every replay.</div></div>
    <div class="lrow"><div class="lk">Parse-once cache</div><div class="lv">Parsers keyed by SHA-256 of the PDF
      bytes; a paper is never parsed twice.</div></div>
    <div class="lrow"><div class="lk">Every paid call cached</div><div class="lv">205 extraction cells persisted to
      disk &rarr; the entire 06-21 re-score cost <span class="mono">&euro;0</span>.</div></div>
    <div class="lrow"><div class="lk">Stamped snapshots</div><div class="lv">Per-parser CSVs are never overwritten;
      each carries a <span class="mono">.meta.json</span> with git commit, budget before/after, prompt hash,
      timestamp.</div></div>
    <div class="lrow"><div class="lk">Cost re-derived</div><div class="lv">From token counts &times; each
      provider&rsquo;s verified rate &mdash; not the in-app meter, which mis-prices non-Claude providers.</div></div>
    <div class="lrow"><div class="lk">This page</div><div class="lv">Generated by
      <span class="mono">reports/build_t72_report.py</span> straight from the snapshots; regenerating it is
      a single command with no network and no API calls.</div></div>
  </div>

  <div class="caveat">
    <span class="ct">Limits of reproducibility</span>
    Closed models can drift server-side &mdash; only the model id is pinned, not the weights behind it.
    Anthropic temperature is left at the API default (DeepSeek and the OpenAI-compatible models are pinned to 0),
    so non-DeepSeek cells carry single-run variance of a few points. The structural findings are stable across
    re-runs; individual cells are not. This is why the page reports worst-case-across-parsers, not peak cells.
  </div>
</section>

<!-- ======================= 8 · DECISION ======================= -->
<section id="decision">
  <div class="section-head">
    <div class="kicker"><span class="secno">09</span><span class="eyebrow">The open decision</span></div>
    <h2>The locked default is still the weakest model</h2>
  </div>
  <div class="passage">
    <p class="lead">The runtime default is deepseek-flash &mdash; the cheapest by a wide margin and the lowest
    average in the grid (&micro;F1 %%DSFLASH_AVG_F1%%). Whether to change it is a config-locked decision, and
    the evidence points two ways.</p>
    <aside class="mnote"><span class="mlabel">Recommendation</span>For an agent that cannot choose its parser
    per paper, robustness beats peak. deepseek-pro is the conservative answer; gemini-3.1-flash-lite is the
    bolder one.</aside>
  </div>

  <div class="choice">
    <div class="opt">
      <h3>deepseek-pro</h3>
      <div class="pro">Same provider, same wire &mdash; a one-line drop-in (<span class="mono">model=deepseek-v4-pro</span>)</div>
      <div class="pro">Never collapses: a high recall floor on all four parsers</div>
      <div class="pro">Still cheap &mdash; &micro;F1 %%DSPRO_F1%% at a fraction of a cent per correct</div>
      <div class="con">Not the single best average (%%DSPRO_F1%% vs %%TOP_F1%%)</div>
    </div>
    <div class="opt">
      <h3>%%TOP_KEY%%</h3>
      <div class="pro">Best average in the grid (&micro;F1 %%TOP_F1%%) and the cheapest non-zero cost</div>
      <div class="pro">Fastest of the roster by latency</div>
      <div class="con">Points the runtime at a new provider &mdash; a larger operational change</div>
      <div class="con">Loses ground under strict decoding (mechanism v)</div>
    </div>
  </div>
  <p class="muted" style="font-family:var(--grotesk);font-size:.88rem">Either way, the headline holds: you do
  not need an expensive model. The decision is which cheap model, and how much robustness you buy.</p>
</section>

<!-- ======================= COLOPHON ======================= -->
<section id="sources" style="border-top:2px solid var(--ink)">
  <div class="section-head"><div class="kicker"><span class="eyebrow">Research resources</span></div></div>
  <ul class="sources">%%SOURCES%%</ul>
  <div class="colophon">
    <p><b>Colophon.</b> Built for experiment T72 of <b>palimpsest</b> &mdash; an autonomous research agent
    (MSc mini-thesis, RWTH). Data: the 06-21 corrected snapshots in
    <span class="mono">experiments/results/</span>; charts are hand-built inline SVG, no charting library.
    Regenerate with <span class="mono">pixi run python reports/build_t72_report.py</span>. Type: Newsreader,
    Archivo, IBM&nbsp;Plex&nbsp;Mono. Every figure traces to a cached extraction; struck numbers are real
    revisions, kept visible.</p>
  </div>
</section>

</div></main>

<script>
const DATA = %%DATA_JSON%%;
const PC = {mineru:"#B07D2B", dots:"#9A6A8C", docling:"#0F6E63", paddle:"#38618C"};
const MC = {}; DATA.models.forEach(m=>MC[m.key]=m.color);
const MNAME = {}; DATA.models.forEach(m=>MNAME[m.key]=m.name);
const ORDER = DATA.models.map(m=>m.key);
const NS = "http://www.w3.org/2000/svg";
const PLABEL = k=>DATA.parserMeta[k].label;

function E(tag, attrs, kids){
  const e=document.createElementNS(NS,tag);
  for(const k in (attrs||{})) e.setAttribute(k, attrs[k]);
  (kids||[]).forEach(c=>e.appendChild(typeof c==="string"?document.createTextNode(c):c));
  return e;
}
function svg(w,h){ return E("svg",{viewBox:`0 0 ${w} ${h}`,role:"img"}); }
function txt(x,y,s,o){ return E("text",Object.assign({x,y},o||{}),[String(s)]); }
const pct = v=>Math.round(v*100)+"%";
const f2 = v=>v.toFixed(2);
const eur = v=> v<0.001 ? "€"+v.toFixed(5) : "€"+v.toFixed(4);

/* ---------------- hero slope ---------------- */
function heroChart(){
  const host=document.getElementById("hero-chart"); if(!host) return;
  const W=440,H=210, L=18,R=18,T=24,B=34;
  const s=svg(W,H); const ps=DATA.parsers;
  const vals=ps.map(p=>DATA.hero.muF1[p]);
  const x=i=> L + i*( (W-L-R)/(ps.length-1) );
  const y=v=> T + (1-v)*(H-T-B);
  for(let g=0;g<=4;g++){const yy=T+g/4*(H-T-B);
    s.appendChild(E("line",{x1:L,y1:yy,x2:W-R,y2:yy,stroke:"#D7DBD6","stroke-width":1}));
    s.appendChild(txt(W-R+2,yy+3,(1-g/4).toFixed(2),{fill:"#9aa0a6","font-size":9}));}
  const d=ps.map((p,i)=>`${i?"L":"M"}${x(i)},${y(vals[i])}`).join(" ");
  s.appendChild(E("path",{d,fill:"none",stroke:"#B23A2E","stroke-width":2.5,"stroke-linejoin":"round"}));
  ps.forEach((p,i)=>{
    s.appendChild(E("circle",{cx:x(i),cy:y(vals[i]),r:4.5,fill:"#EEF1EE",stroke:PC[p],"stroke-width":2.5}));
    s.appendChild(txt(x(i),y(vals[i])-10,vals[i].toFixed(2),{"text-anchor":"middle","font-size":11,"font-weight":600,fill:"#14181A"}));
    s.appendChild(txt(x(i),H-12,PLABEL(p),{"text-anchor":"middle","font-size":10,fill:"#6B7280"}));
  });
  host.innerHTML=""; host.appendChild(s);
}

/* ---------------- leaderboard ---------------- */
const METRICS={
  muF1:{label:"µ-F1",low:false,fmt:f2,max:1},
  microRecall:{label:"micro-recall",low:false,fmt:pct,max:1},
  muPrecision:{label:"µ-precision",low:false,fmt:f2,max:1},
  eurPerTp:{label:"€ / correct",low:true,fmt:eur,max:null},
  latency:{label:"latency",low:true,fmt:v=>v.toFixed(1)+"s",max:null},
};
const LB={metric:"muF1",parser:"avg",mode:"raw"};
function lbSource(mode,parser){
  return parser==="avg"?DATA.avgByModel[mode]:(DATA.grid[mode][parser]||{});
}
function leaderboard(){
  const host=document.getElementById("leaderboard");
  const M=METRICS[LB.metric];
  const src=lbSource(LB.mode,LB.parser), raw=lbSource("raw",LB.parser);
  const rows=ORDER.map(k=>{
    const has=src[k]&&src[k][LB.metric]!=null;
    const v = has?src[k][LB.metric]:(raw[k]?raw[k][LB.metric]:null);
    return {k,v,rawOnly:LB.mode==="strict"&&!has,missing:v==null};
  }).filter(r=>!r.missing);
  rows.sort((a,b)=> M.low ? a.v-b.v : b.v-a.v);
  const maxv=Math.max.apply(null,rows.map(r=>r.v));
  const W=720, rowH=34, padL=148, padR=70, T=10, B=8;
  const H=T+B+rows.length*rowH;
  const s=svg(W,H);
  rows.forEach((r,i)=>{
    const y=T+i*rowH;
    const bw=(W-padL-padR)*(r.v/ (maxv||1));
    s.appendChild(txt(padL-10,y+rowH/2+4,MNAME[r.k],{"text-anchor":"end","font-size":12,fill:"#14181A","font-weight":500}));
    s.appendChild(E("rect",{x:padL,y:y+7,width:Math.max(bw,1),height:rowH-15,rx:2,
      fill: M.low?"#9A6A8C":MC[r.k], opacity:r.rawOnly?0.4:0.92}));
    s.appendChild(txt(padL+Math.max(bw,1)+7,y+rowH/2+4,M.fmt(r.v)+(r.rawOnly?"  (raw)":""),
      {"font-size":11,fill:"#3A4044","font-family":"IBM Plex Mono"}));
  });
  host.innerHTML=""; host.appendChild(s);
  const cap=document.getElementById("lb-cap");
  const pl = LB.parser==="avg"?"averaged over the four parsers":"on "+PLABEL(LB.parser);
  cap.innerHTML="<b>"+M.label+"</b>, "+LB.mode+" decoding, "+pl+". "+
    (M.low?"Shorter is better — lower cost/latency.":"Longer is better.")+
    (LB.mode==="strict"?" Anthropic and DeepSeek have no strict run; shown faded at their raw value.":"");
}

/* ---------------- heatmap ---------------- */
function heatmap(){
  const host=document.getElementById("heatmap");
  const ps=DATA.parsers, W=720, cellH=34, padL=150, padT=30, padB=44, gap=4;
  const cw=(W-padL-14)/ps.length;
  const H=padT+padB+(ORDER.length+1)*cellH;
  const s=svg(W,H);
  ps.forEach((p,j)=> s.appendChild(txt(padL+j*cw+cw/2,padT-10,PLABEL(p),
    {"text-anchor":"middle","font-size":11,fill:"#14181A","font-weight":600})) );
  ORDER.forEach((k,i)=>{
    const y=padT+i*cellH;
    s.appendChild(txt(padL-10,y+cellH/2+4,MNAME[k],{"text-anchor":"end","font-size":12,fill:"#14181A"}));
    ps.forEach((p,j)=>{
      const c=DATA.grid.raw[p][k], v=c?c.microRecall:null, x=padL+j*cw;
      const a=v==null?0:0.12+0.82*v;
      s.appendChild(E("rect",{x:x+gap/2,y:y+gap/2,width:cw-gap,height:cellH-gap,rx:3,
        fill:`rgba(15,110,99,${a})`, stroke: v!=null&&v<0.4?"#B23A2E":"none","stroke-width":1.5}));
      if(v!=null) s.appendChild(txt(x+cw/2,y+cellH/2+4,f2(v),
        {"text-anchor":"middle","font-size":11,"font-family":"IBM Plex Mono",
         fill: a>0.55?"#EEF1EE":"#14181A"}));
    });
  });
  const y=padT+ORDER.length*cellH;
  s.appendChild(txt(padL-10,y+cellH/2+4,"coverage ceiling",{"text-anchor":"end","font-size":11,fill:"#6B7280","font-style":"italic"}));
  ps.forEach((p,j)=>{
    const v=DATA.coverage[p].ceiling, x=padL+j*cw;
    s.appendChild(E("rect",{x:x+gap/2,y:y+gap/2,width:cw-gap,height:cellH-gap,rx:3,
      fill:"none",stroke:"#C3CAC4","stroke-width":1,"stroke-dasharray":"3 3"}));
    s.appendChild(txt(x+cw/2,y+cellH/2+4,pct(v),{"text-anchor":"middle","font-size":11,
      "font-family":"IBM Plex Mono",fill: v<1?"#B23A2E":"#6B7280"}));
  });
  host.innerHTML=""; host.appendChild(s);
}

/* ---------------- scatter ---------------- */
const SC={axis:"eurPerTp"};
function scatter(){
  const host=document.getElementById("scatter");
  const W=720,H=380,L=64,R=20,T=20,Bm=52;
  const pts=ORDER.map(k=>({k,x:DATA.avgByModel.raw[k][SC.axis],y:DATA.avgByModel.raw[k].muF1}));
  const xs=pts.map(p=>p.x);
  const lo=Math.log10(Math.min.apply(null,xs)*0.8), hi=Math.log10(Math.max.apply(null,xs)*1.25);
  const X=v=> L + (Math.log10(v)-lo)/(hi-lo)*(W-L-R);
  const Y=v=> T + (1-v)*(H-T-Bm);
  const s=svg(W,H);
  for(let g=0;g<=5;g++){const yy=T+g/5*(H-T-Bm),val=(1-g/5);
    s.appendChild(E("line",{x1:L,y1:yy,x2:W-R,y2:yy,stroke:"#E0E4E0","stroke-width":1}));
    s.appendChild(txt(L-8,yy+3,val.toFixed(1),{"text-anchor":"end","font-size":10,fill:"#9aa0a6"}));}
  for(let e=Math.ceil(lo);e<=Math.floor(hi);e++){const xx=X(Math.pow(10,e));
    s.appendChild(E("line",{x1:xx,y1:T,x2:xx,y2:H-Bm,stroke:"#E0E4E0","stroke-width":1}));
    s.appendChild(txt(xx,H-Bm+16,"€"+(Math.pow(10,e)>=0.01?Math.pow(10,e).toFixed(2):Math.pow(10,e).toExponential(0)),
      {"text-anchor":"middle","font-size":10,fill:"#9aa0a6","font-family":"IBM Plex Mono"}));}
  s.appendChild(txt((L+W-R)/2,H-10,(SC.axis==="eurPerTp"?"cost per correct extraction":"cost per paper")+"  (log)",
    {"text-anchor":"middle","font-size":11,fill:"#6B7280"}));
  s.appendChild(txt(16,T+6,"µ-F1",{"font-size":11,fill:"#6B7280"}));
  s.appendChild(txt(L+6,T+4,"← cheaper · better →",{"font-size":10,fill:"#9aa0a6"}));
  pts.forEach(p=>{
    s.appendChild(E("circle",{cx:X(p.x),cy:Y(p.y),r:6,fill:MC[p.k],opacity:0.92}));
    const left=X(p.x)>W-150;
    s.appendChild(txt(X(p.x)+(left?-10:10),Y(p.y)+(p.k==="haiku-4.5"?14:4),MNAME[p.k],
      {"font-size":10.5,fill:"#14181A","text-anchor":left?"end":"start"}));
  });
  host.innerHTML=""; host.appendChild(s);
}

/* ---------------- taxonomy ---------------- */
function taxonomy(){
  const host=document.getElementById("taxonomy");
  const cats=[["hit","#0F6E63","hits"],["model_gap","#C68A2E","model gap"],
    ["coverage_gap","#9aa0a6","coverage gap"],["wrong_type","#B23A2E","wrong type"]];
  const W=720,rowH=46,padL=86,padR=14,T=8;
  const ps=DATA.parsers, H=T+ps.length*rowH+8;
  const s=svg(W,H);
  ps.forEach((p,i)=>{
    const t=DATA.taxonomy[p], slots=t.slots, y=T+i*rowH;
    s.appendChild(txt(padL-10,y+rowH/2,PLABEL(p),{"text-anchor":"end","font-size":12,fill:"#14181A","font-weight":600}));
    let x=padL; const bw=W-padL-padR;
    cats.forEach(([key,col])=>{
      const w=bw*(t[key]/slots);
      if(w>0){ s.appendChild(E("rect",{x,y:y+8,width:w,height:rowH-22,fill:col,opacity:0.9}));
        if(w>26) s.appendChild(txt(x+w/2,y+rowH/2+2,t[key],{"text-anchor":"middle","font-size":10,
          fill: key==="hit"||key==="wrong_type"?"#EEF1EE":"#14181A","font-family":"IBM Plex Mono"})); }
      x+=w;
    });
    s.appendChild(txt(W-padR,y+rowH-4,"ceiling "+pct(DATA.coverage[p].ceiling),
      {"text-anchor":"end","font-size":9,fill:"#9aa0a6","font-family":"IBM Plex Mono"}));
  });
  host.innerHTML=""; host.appendChild(s);
  host.insertAdjacentHTML("afterend","");
  let leg=document.getElementById("tax-legend");
  if(!leg){leg=document.createElement("div"); leg.id="tax-legend"; leg.className="legend";
    leg.innerHTML=cats.map(([k,c,l])=>`<span><i style="background:${c}"></i>${l}</span>`).join("");
    host.parentNode.insertBefore(leg,host.nextSibling);}
}

/* ---------------- coverage ---------------- */
function coverage(){
  const host=document.getElementById("coverage");
  const ps=DATA.parsers,W=720,rowH=40,padL=92,padR=54,T=8;
  const H=T+ps.length*rowH+6, s=svg(W,H);
  ps.forEach((p,i)=>{
    const v=DATA.coverage[p].ceiling,y=T+i*rowH,bw=W-padL-padR;
    s.appendChild(txt(padL-10,y+rowH/2,PLABEL(p),{"text-anchor":"end","font-size":12,fill:"#14181A","font-weight":600}));
    s.appendChild(E("rect",{x:padL,y:y+9,width:bw,height:rowH-22,rx:2,fill:"#E0E4E0"}));
    s.appendChild(E("rect",{x:padL,y:y+9,width:bw*v,height:rowH-22,rx:2,fill:DATA.parserMeta[p].figureAware?"#0F6E63":"#B07D2B"}));
    if(v<1) s.appendChild(E("rect",{x:padL+bw*v,y:y+9,width:bw*(1-v),height:rowH-22,rx:2,
      fill:"none",stroke:"#B23A2E","stroke-width":1.5,"stroke-dasharray":"3 2"}));
    s.appendChild(txt(W-padR+8,y+rowH/2+1,pct(v),{"font-size":12,fill:v<1?"#B23A2E":"#14181A",
      "font-family":"IBM Plex Mono","font-weight":600}));
  });
  host.innerHTML=""; host.appendChild(s);
}

/* ---------------- controls + boot ---------------- */
/* ---------------- reachable-recall dumbbell ---------------- */
function reachableChart(){
  const host=document.getElementById("reachable"); if(!host) return;
  const W=720,rowH=34,padL=150,padR=60,T=10;
  const rows=ORDER.map(k=>({k,a:DATA.reachable[k].microRecall,b:DATA.reachable[k].reachableRecall}))
    .sort((x,y)=>y.b-x.b);
  const H=T+rows.length*rowH+24;
  const lo=0.5, hi=1.0, X=v=>padL+(v-lo)/(hi-lo)*(W-padL-padR);
  const s=svg(W,H);
  for(let g=5;g<=10;g++){const xx=X(g/10);
    s.appendChild(E("line",{x1:xx,y1:T,x2:xx,y2:T+rows.length*rowH,stroke:"#E0E4E0","stroke-width":1}));
    s.appendChild(txt(xx,H-8,(g/10).toFixed(1),{"text-anchor":"middle","font-size":9,fill:"#9aa0a6","font-family":"IBM Plex Mono"}));}
  rows.forEach((r,i)=>{
    const y=T+i*rowH+rowH/2;
    s.appendChild(txt(padL-12,y+4,MNAME[r.k],{"text-anchor":"end","font-size":12,fill:"#14181A"}));
    s.appendChild(E("line",{x1:X(r.a),y1:y,x2:X(r.b),y2:y,stroke:MC[r.k],"stroke-width":2,opacity:.55}));
    s.appendChild(E("circle",{cx:X(r.a),cy:y,r:5,fill:MC[r.k]}));
    s.appendChild(E("line",{x1:X(r.b),y1:y-6,x2:X(r.b),y2:y+6,stroke:MC[r.k],"stroke-width":2.5}));
    s.appendChild(txt(X(r.b)+10,y+4,pct(r.b),{"font-size":10.5,fill:"#3A4044","font-family":"IBM Plex Mono"}));
  });
  host.innerHTML=""; host.appendChild(s);
  legendOnce(host,"reach-legend",[["#14181A","● recall (raw)","dot"],["#14181A","│ reachable-recall","tick"]]);
}

/* ---------------- recall by measurement type ---------------- */
function typeChart(){
  const host=document.getElementById("bytype"); if(!host) return;
  const W=720,rowH=40,padL=140,padR=60,T=8;
  const rows=DATA.byType;
  const H=T+rows.length*rowH+8, X=v=>padL+v*(W-padL-padR);
  const s=svg(W,H);
  for(let g=0;g<=10;g+=2){const xx=X(g/10);
    s.appendChild(E("line",{x1:xx,y1:T,x2:xx,y2:T+rows.length*rowH,stroke:"#E0E4E0","stroke-width":1}));}
  rows.forEach((r,i)=>{
    const y=T+i*rowH;
    s.appendChild(txt(padL-12,y+rowH/2,r.type,{"text-anchor":"end","font-size":12,fill:"#14181A","font-weight":600}));
    s.appendChild(txt(padL-12,y+rowH/2+14,"n="+r.total,{"text-anchor":"end","font-size":9,fill:"#9aa0a6","font-family":"IBM Plex Mono"}));
    if(r.reachableRecall>r.recall)
      s.appendChild(E("rect",{x:X(r.recall),y:y+9,width:X(r.reachableRecall)-X(r.recall),height:rowH-22,
        fill:"none",stroke:"#B23A2E","stroke-width":1.2,"stroke-dasharray":"3 2"}));
    s.appendChild(E("rect",{x:padL,y:y+9,width:Math.max(X(r.recall)-padL,1),height:rowH-22,rx:2,fill:"#0F6E63",opacity:.9}));
    s.appendChild(txt(X(Math.max(r.recall,r.reachableRecall))+8,y+rowH/2+4,
      pct(r.recall)+(r.reachableRecall>r.recall?" → "+pct(r.reachableRecall):""),
      {"font-size":10.5,fill:"#3A4044","font-family":"IBM Plex Mono"}));
  });
  host.innerHTML=""; host.appendChild(s);
  legendOnce(host,"type-legend",[["#0F6E63","recall","sq"],["#B23A2E","reachable (ceiling lifted)","dash"]]);
}

function legendOnce(host,id,items){
  if(document.getElementById(id)) return;
  const leg=document.createElement("div"); leg.id=id; leg.className="legend";
  leg.innerHTML=items.map(([c,l])=>`<span><i style="background:${c}"></i>${l}</span>`).join("");
  host.parentNode.insertBefore(leg,host.nextSibling);
}

function wire(){
  document.getElementById("lb-metric").addEventListener("change",e=>{LB.metric=e.target.value;leaderboard();});
  document.getElementById("lb-parser").addEventListener("change",e=>{LB.parser=e.target.value;leaderboard();});
  document.querySelectorAll("#lb-mode button").forEach(b=>b.addEventListener("click",()=>{
    LB.mode=b.dataset.mode;
    document.querySelectorAll("#lb-mode button").forEach(x=>x.setAttribute("aria-pressed",x===b));
    leaderboard();
  }));
  document.querySelectorAll("#sc-axis button").forEach(b=>b.addEventListener("click",()=>{
    SC.axis=b.dataset.axis;
    document.querySelectorAll("#sc-axis button").forEach(x=>x.setAttribute("aria-pressed",x===b));
    scatter();
  }));
}
function drawAll(){ heroChart(); leaderboard(); heatmap(); scatter(); reachableChart(); taxonomy(); coverage(); typeChart(); }
function boot(){
  drawAll(); wire();
  // scrollspy
  const links=[...document.querySelectorAll(".nav a")];
  const map={}; links.forEach(a=>map[a.getAttribute("href").slice(1)]=a);
  const so=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){
    links.forEach(l=>l.classList.remove("active")); const a=map[e.target.id]; if(a)a.classList.add("active");}});},
    {rootMargin:"-45% 0px -50% 0px"});
  document.querySelectorAll("section[id]").forEach(s=>so.observe(s));
  // reveal
  if(matchMedia("(prefers-reduced-motion: no-preference)").matches){
    document.querySelectorAll(".passage,figure,.mech,.obj,.stage").forEach(el=>{
      el.classList.add("reveal");
      new IntersectionObserver((es,o)=>es.forEach(en=>{if(en.isIntersecting){en.target.classList.add("in");o.unobserve(en.target);}}),
        {rootMargin:"0px 0px -8% 0px"}).observe(el);
    });
  }
}
let rt; addEventListener("resize",()=>{clearTimeout(rt);rt=setTimeout(drawAll,180);});
if(document.readyState!=="loading") boot(); else addEventListener("DOMContentLoaded",boot);
</script>
</body>
</html>
'''
