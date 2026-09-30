"""One self-contained HTML file: inline CSS and JavaScript, the data embedded as JSON, no external resource of any kind
(no CDN, no font, no image, no link that leaves the file), so it opens offline and can be attached to an audit.

The summary card is static HTML (readable with JavaScript off); the timeline is drawn by the inline script from the
embedded data, always through textContent (log text is never interpreted as HTML). In the embedded JSON every "/",
"<", ">" and "&" is escaped, and in the static part "://" is written as an entity, so the file contains no literal
URL even when the log does.
"""
from __future__ import annotations

import html
import json
import re

from . import __version__


def embed_json(obj) -> str:
    s = json.dumps(obj, ensure_ascii=True, separators=(",", ":"), default=str)
    return s.replace("/", "\\/").replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def esc(s) -> str:
    return html.escape("" if s is None else str(s)).replace("://", ":&#47;&#47;")


def _fmt_int(v) -> str:
    return "-" if v is None else f"{v:,}" if isinstance(v, int) else f"{v:,.2f}" if isinstance(v, float) else esc(v)


def _dur(sec) -> str:
    if sec is None:
        return "-"
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def _card(label, value, note=None, warn=False) -> str:
    return (f'<div class="card{" warn" if warn else ""}"><div class="lbl">{esc(label)}</div>'
            f'<div class="val">{value}</div>' + (f'<div class="note">{esc(note)}</div>' if note else "") + "</div>")


def static_summary(s: dict) -> str:
    tok = s["tokens"]
    models = ", ".join(m["model"] for m in s["models"]) or "unknown"
    cards = [
        _card("Framework", esc(s["framework_label"]) + (f" {esc(s['cli_version'])}" if s["cli_version"] else ""),
              "CLI version " + ("as recorded in the log" if s["cli_version"] else "not in the log")),
        _card("Model string(s)", esc(models), "more than one model string" if s["multiple_models"] else None,
              warn=s["multiple_models"] or not s["models"]),
        _card("Turns", _fmt_int(s["turns"]), s["turns_basis"]),
        _card("Tool calls", _fmt_int(s["tool_calls"]), f"{s['tool_errors']} failed"),
        _card("Tokens in / out", f"{_fmt_int(tok['input'])} / {_fmt_int(tok['output'])}", s["tokens_basis"]),
        _card("Cache read / write", f"{_fmt_int(tok['cache_read'])} / {_fmt_int(tok['cache_write'])}",
              f"reasoning {_fmt_int(tok['reasoning'])}"),
        _card("Wall time", _dur(s["wall_time"]["seconds"]), s["wall_time"]["basis"]),
        _card("Files written / edited", f"{len(s['files_written'])} / {len(s['files_edited'])}",
              f"{s['files_read']} files read"),
        _card("Network-shaped commands", _fmt_int(len(s["network_flags"])), "guard.py patterns",
              warn=bool(s["network_flags"])),
        _card("Secret scan", "clean" if s["secret_scan"]["clean"] else "HITS - redacted here",
              f"{sum(s['secret_scan']['redactions'].values())} redaction(s) in this report",
              warn=not s["secret_scan"]["clean"]),
    ]
    if s.get("cost_usd") is not None:
        cards.append(_card("Cost (as the framework reports it)", f"{s['cost_usd']:.4f}" if isinstance(
            s["cost_usd"], (int, float)) else esc(s["cost_usd"])))
    out = ['<section class="cards">' + "".join(cards) + "</section>"]
    if s["warnings"]:
        out.append('<section class="box warnbox"><h2>Read this first</h2><ul>' +
                   "".join(f"<li>{esc(w)}</li>" for w in s["warnings"]) + "</ul></section>")
    rows = "".join(f'<tr><td>{esc(t)}</td><td class="num">{n}</td><td><span class="bar" style="width:'
                   f'{max(2, int(200 * n / max(1, max(s["tool_calls_by_tool"].values()))))}px"></span></td></tr>'
                   for t, n in s["tool_calls_by_tool"].items())
    out.append('<section class="grid2"><div class="box"><h2>Tool calls by tool</h2><table>' +
               (rows or '<tr><td colspan="3">none</td></tr>') + "</table></div>")
    mrows = "".join(f'<tr><td>{esc(m["model"])}</td><td class="num">{m["events"]}</td></tr>' for m in s["models"])
    krows = "".join(f'<tr><td>{esc(k)}</td><td class="num">{v}</td></tr>' for k, v in s["events_by_kind"].items())
    out.append('<div class="box"><h2>Models</h2><table><tr><th>model string</th><th>events naming it</th></tr>' +
               (mrows or '<tr><td colspan="2">none in the log</td></tr>') + "</table><h2>Events by kind</h2><table>" +
               krows + "</table></div></section>")
    net = "".join(f'<li><a class="evlink" href="#e{r["event"]}">#{r["event"]}</a> <b>{esc(r["tool"])}</b> '
                  f'<span class="muted">{esc(r["reason"])}</span><pre>{esc((r["command"] or "")[:600])}</pre></li>'
                  for r in s["network_flags"][:500])
    out.append('<section class="box"><h2>Network-shaped commands</h2>' +
               (f"<ul class=\"flat\">{net}</ul>" if net else "<p>none flagged</p>") +
               f'<p class="muted">Patterns: {esc(s["network_patterns"])}. A flag means the command looks like network '
               "access, not that it happened.</p></section>")
    files = "".join(f"<li>{esc(f)}</li>" for f in s["files_written"][:1000])
    edits = "".join(f"<li>{esc(f)}</li>" for f in s["files_edited"][:1000])
    out.append('<section class="grid2"><details class="box"><summary>Files written (' + str(len(s["files_written"])) +
               ")</summary><ul>" + files + '</ul></details><details class="box"><summary>Files edited (' +
               str(len(s["files_edited"])) + ")</summary><ul>" + edits + "</ul></details></section>")
    sc = s["secret_scan"]
    hits = "".join(f"<li>{esc(h['file'])}: {esc(', '.join(h['patterns']))}</li>" for h in sc["hits"])
    red = ", ".join(f"{esc(k)} x{v}" for k, v in sc["redactions"].items()) or "none"
    out.append('<section class="box"><h2>Secret scan (vec_agent_evidence/common.py patterns)</h2><p>Input files: ' +
               ("clean" if sc["clean"] else "credential-shaped content found") + "</p>" +
               (f"<ul>{hits}</ul>" if hits else "") + f"<p>Redacted in this report: {red}</p></section>")
    src_rows = "".join(f'<tr><td>{esc(x["file"])}</td><td class="num">{x["bytes"]:,}</td><td class="mono">'
                       f'{esc(x["sha256"])}</td></tr>' for x in s["sources"])
    out.append('<details class="box"><summary>Input files (' + str(len(s["sources"])) + ")</summary><table><tr><th>file"
               "</th><th>bytes</th><th>sha256</th></tr>" + src_rows + "</table></details>")
    out.append('<section class="box"><h2>What this report does not show</h2><ul>' +
               "".join(f"<li>{esc(x)}</li>" for x in s["not_shown"]) + "</ul></section>")
    return "\n".join(out)


CSS = """
:root{--bg:#fbfbfa;--fg:#1d1d1b;--mut:#6b6b66;--line:#e2e1dc;--card:#fff;--warn:#b54708;--warnbg:#fff4e5;
--user:#1f6feb;--assistant:#2da44e;--tool_call:#8250df;--tool_result:#6e7781;--system:#9a6700;--err:#cf222e}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#e8e6e1;--mut:#9b998f;--line:#34332f;--card:#1f1e1b;
--warnbg:#3a2a12;--warn:#f0b35c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,
"Segoe UI",Roboto,sans-serif}header,main{max-width:1200px;margin:0 auto;padding:12px 20px}
h1{font-size:20px;margin:8px 0 2px}h2{font-size:15px;margin:4px 0 8px}.muted{color:var(--mut)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin:10px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.card.warn{border-color:var(--warn);background:var(--warnbg)}.lbl{font-size:12px;color:var(--mut)}
.val{font-size:18px;font-weight:600;margin:2px 0;word-break:break-word}.note{font-size:11px;color:var(--mut)}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0}
.warnbox{border-color:var(--warn);background:var(--warnbg)}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media (max-width:800px){.grid2{grid-template-columns:1fr}}table{border-collapse:collapse;width:100%}
td,th{padding:3px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.num{text-align:right}
.bar{display:inline-block;height:9px;background:var(--tool_call);border-radius:2px}.mono,pre{font-family:ui-monospace,
SFMono-Regular,Consolas,monospace;font-size:12px}pre{white-space:pre-wrap;word-break:break-word;margin:4px 0;
background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;max-height:480px;overflow:auto}
ul.flat{list-style:none;padding:0}summary{cursor:pointer;font-weight:600}
#controls{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:2;
display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center}#controls label{white-space:nowrap}
#controls input[type=search]{min-width:220px;padding:4px 6px}.ev{border-left:4px solid var(--line);
background:var(--card);margin:4px 0;border-radius:4px}.ev .hd{display:flex;gap:8px;padding:4px 8px;cursor:pointer;
align-items:baseline}.ev .hd span{white-space:nowrap}.ev .pv{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
color:var(--mut);flex:1;min-width:0}.ev .bd{padding:0 10px 8px 10px}.b{font-size:11px;padding:0 6px;border-radius:9px;
color:#fff}.k-user{border-left-color:var(--user)}.k-assistant{border-left-color:var(--assistant)}
.k-tool_call{border-left-color:var(--tool_call)}.k-tool_result{border-left-color:var(--tool_result)}
.k-system{border-left-color:var(--system)}.b.user{background:var(--user)}.b.assistant{background:var(--assistant)}
.b.tool_call{background:var(--tool_call)}.b.tool_result{background:var(--tool_result)}.b.system{background:var(--system)}
.ev.err .hd{background:rgba(207,34,46,.08)}.fl{font-size:11px;color:var(--err);font-weight:600}
.ev.target{outline:2px solid var(--warn)}.meta{font-size:12px;color:var(--mut)}button{padding:4px 10px}
"""

JS = r"""
(function(){
var D=JSON.parse(document.getElementById('lens-data').textContent);
var E=D.events,KINDS=['user','assistant','tool_call','tool_result','system'];
var st={kinds:{},tool:'',actor:'',q:'',flagged:false,errors:false,limit:400,open:false};
KINDS.forEach(function(k){st.kinds[k]=true;});
function el(t,c,txt){var e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e;}
var C=document.getElementById('controls'),L=document.getElementById('list'),N=document.getElementById('count');
var counts={};E.forEach(function(e){counts[e.kind]=(counts[e.kind]||0)+1;});
KINDS.forEach(function(k){var l=el('label');var c=el('input');c.type='checkbox';c.checked=true;
c.onchange=function(){st.kinds[k]=c.checked;st.limit=400;draw();};l.appendChild(c);
l.appendChild(document.createTextNode(' '+k+' ('+(counts[k]||0)+')'));C.appendChild(l);});
function sel(label,vals,key){var l=el('label',null,label+' ');var s=el('select');s.appendChild(el('option',null,'all'));
s.options[0].value='';vals.forEach(function(v){var o=el('option',null,v);o.value=v;s.appendChild(o);});
s.onchange=function(){st[key]=s.value;st.limit=400;draw();};l.appendChild(s);C.appendChild(l);}
var tools={},actors={};E.forEach(function(e){if(e.tool)tools[e.tool]=1;if(e.actor)actors[e.actor]=1;});
sel('tool',Object.keys(tools).sort(),'tool');sel('actor',Object.keys(actors).sort(),'actor');
var q=el('input');q.type='search';q.placeholder='search text, command, files';
q.oninput=function(){st.q=q.value.toLowerCase();st.limit=400;draw();};C.appendChild(q);
function tog(label,key){var l=el('label');var c=el('input');c.type='checkbox';
c.onchange=function(){st[key]=c.checked;st.limit=400;draw();};l.appendChild(c);
l.appendChild(document.createTextNode(' '+label));C.appendChild(l);}
tog('flagged only','flagged');tog('errors only','errors');tog('expand all','open');
function ok(e){if(!st.kinds[e.kind])return false;if(st.tool&&e.tool!==st.tool)return false;
if(st.actor&&e.actor!==st.actor)return false;if(st.flagged&&!(e.flags&&e.flags.length))return false;
if(st.errors&&!e.is_error)return false;if(st.q){var h=((e.text||'')+' '+(e.command||'')+' '+(e.files||[]).join(' ')+
' '+(e.tool||'')).toLowerCase();if(h.indexOf(st.q)<0)return false;}return true;}
var t0=null;for(var i=0;i<E.length;i++){if(E[i].ts){t0=Date.parse(E[i].ts);break;}}
function rel(ts){if(!ts||t0==null)return '';var d=Math.round((Date.parse(ts)-t0)/1000);if(isNaN(d))return '';
var s=d<0?'-':'+';d=Math.abs(d);var h=Math.floor(d/3600),m=Math.floor(d%3600/60),x=d%60;
return s+(h?h+':':'')+(m<10&&h?'0':'')+m+':'+(x<10?'0':'')+x;}
function row(e){var d=el('div','ev k-'+e.kind+(e.is_error?' err':''));d.id='e'+e.i;var hd=el('div','hd');
hd.appendChild(el('span','muted','#'+e.i));hd.appendChild(el('span','muted mono',e.ts?e.ts.slice(11,19):''));
hd.appendChild(el('span','muted mono',rel(e.ts)));hd.appendChild(el('span','b '+e.kind,e.kind+(e.subkind?':'+e.subkind:'')));
hd.appendChild(el('span','muted',e.actor||''));if(e.tool)hd.appendChild(el('b',null,e.tool));
(e.flags||[]).forEach(function(f){hd.appendChild(el('span','fl',f));});
var pv=(e.command||e.text||'').replace(/\s+/g,' ');hd.appendChild(el('span','pv',pv.slice(0,240)));d.appendChild(hd);
var bd=el('div','bd');bd.hidden=!st.open;var pre=el('pre',null,(e.command&&e.text!==e.command?'$ '+e.command+'\n\n':'')+
(e.text||''));bd.appendChild(pre);if(e.text_len)bd.appendChild(el('div','meta','text shortened for this report: '+
e.text_len+' characters in the log'));var m=[];if(e.files&&e.files.length)m.push((e.file_op||'files')+': '+e.files.join(', '));
if(e.model)m.push('model: '+e.model);if(e.usage)m.push('usage: '+JSON.stringify(e.usage));if(e.call_id)m.push('call: '+e.call_id);
if(e.session)m.push('session: '+e.session);if(e.source)m.push('source: '+e.source);
if(m.length)bd.appendChild(el('div','meta',m.join('  |  ')));d.appendChild(bd);
hd.onclick=function(){bd.hidden=!bd.hidden;};return d;}
function draw(){L.textContent='';var shown=0,match=0;var frag=document.createDocumentFragment();
for(var i=0;i<E.length;i++){var e=E[i];if(!ok(e))continue;match++;if(shown<st.limit){frag.appendChild(row(e));shown++;}}
L.appendChild(frag);N.textContent='showing '+shown+' of '+match+' matching events ('+E.length+' in total)';
var more=document.getElementById('more');more.hidden=shown>=match;}
document.getElementById('more').onclick=function(){st.limit+=400;draw();};
function reveal(i){var e=E[i];if(!e)return;if(!ok(e)){KINDS.forEach(function(k){st.kinds[k]=true;});
Array.prototype.forEach.call(C.querySelectorAll('input[type=checkbox]'),function(c,j){if(j<KINDS.length)c.checked=true;
else c.checked=false;});st.tool='';st.actor='';st.q='';st.flagged=false;st.errors=false;st.open=false;q.value='';
Array.prototype.forEach.call(C.querySelectorAll('select'),function(s){s.value='';});}
var pos=0;for(var j=0;j<E.length&&j<=i;j++){if(ok(E[j]))pos++;}if(pos>st.limit)st.limit=pos+50;draw();
var d=document.getElementById('e'+i);if(d){d.classList.add('target');d.querySelector('.bd').hidden=false;
d.scrollIntoView({block:'center'});}}
document.addEventListener('click',function(ev){var a=ev.target.closest?ev.target.closest('a.evlink'):null;
if(a){ev.preventDefault();reveal(parseInt(a.getAttribute('href').slice(2),10));}});
function fromHash(){if(location.hash&&location.hash.indexOf('#e')===0)reveal(parseInt(location.hash.slice(2),10));}
window.addEventListener('hashchange',fromHash);draw();fromHash();
})();
"""

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer">
<title>@@TITLE@@</title><style>@@CSS@@</style></head>
<body><header><h1>@@TITLE@@</h1>
<div class="muted">@@SUBTITLE@@</div></header>
<main>
@@SUMMARY@@
<section class="box"><h2>Timeline</h2>
<noscript><p>The timeline needs JavaScript (inline, offline). The summary above is plain HTML; the events are also in
the JSON written with --events.</p></noscript>
<div id="controls"></div><div id="count" class="muted"></div><div id="list"></div>
<p><button id="more" hidden>show 400 more</button></p></section>
</main>
<script type="application/json" id="lens-data">@@DATA@@</script>
<script>@@JS@@</script>
</body></html>
"""


def render(summary: dict, events: list, title: str, generated: str, max_text: int = 3000) -> str:
    rows = []
    for i, e in enumerate(events):
        d = e.to_dict()
        d["i"] = i
        if len(d.get("text", "")) > max_text:
            d["text_len"] = len(d["text"])
            d["text"] = d["text"][:max_text] + "\n[... shortened]"
        if len(d.get("command") or "") > max_text:
            d["command"] = d["command"][:max_text] + " [... shortened]"
        if len(d.get("files") or []) > 50:
            d["files"] = d["files"][:50] + [f"... {len(e.files) - 50} more"]
        rows.append(d)
    subtitle = (f"{summary['framework_label']} {summary['cli_version'] or ''} | sessions: "
                f"{', '.join(summary['session_ids'][:3]) or 'unknown'} | {summary['events']} events | generated "
                f"{generated} by vec_trajectory_lens {__version__} (offline report: this file loads nothing)")
    parts = {"TITLE": esc(title), "SUBTITLE": esc(subtitle), "CSS": CSS, "JS": JS, "SUMMARY": static_summary(summary),
             "DATA": embed_json({"events": rows})}
    # one pass over the template: text that came from a log is inserted as is and never scanned for placeholders
    return re.sub(r"@@(TITLE|SUBTITLE|CSS|JS|SUMMARY|DATA)@@", lambda m: parts[m.group(1)], PAGE)
