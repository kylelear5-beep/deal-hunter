"""Auto-generated public deals website (static HTML, rebuilt every hour).

Pages: / (home), /<niche>/ (one per niche), /store/<domain>.html, /about.html,
/privacy.html, /sitemap.xml, /robots.txt. Served by api.py from SITE_DIR.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

from affiliate import best_link, has_product_link, plain_url_for_extension, store_search
from alerts import CATEGORY_STYLE, DISCLOSURE, deal_label, price_safe, value_score
from config import settings
from niches import load_niches

log = logging.getLogger("sitegen")
e = html.escape

CSS = """
:root{--bg:#f4f6fa;--card:#fff;--text:#111827;--muted:#4b5563;--line:#d1d5db;--blue:#1d4ed8;
  --blue-d:#1e40af;--green:#047857;--green-bg:#dcfce7;--amber:#b45309;--amber-bg:#fef3c7}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
a{color:var(--blue)}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
header.top{position:sticky;top:0;z-index:20;background:#fff;border-bottom:1px solid var(--line);
  box-shadow:0 1px 3px rgba(15,23,42,.06)}
.row1{display:flex;align-items:center;gap:12px;padding:10px 0}
.logo{display:flex;align-items:center;gap:8px;font-size:22px;font-weight:800;color:var(--text);
  text-decoration:none;white-space:nowrap}
.logo .mark{width:36px;height:36px;border-radius:10px;background:var(--blue);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:19px}
.logo b{color:var(--blue)}
.search{flex:1;display:flex;align-items:center;gap:8px;min-width:0;height:46px;padding:0 12px;
  border:2px solid var(--line);border-radius:12px;background:#f9fafb}
.search:focus-within{border-color:var(--blue);background:#fff}
.search input{flex:1;min-width:0;border:0;background:transparent;font-size:17px;color:var(--text);
  outline:none}
.hbtn{display:inline-flex;align-items:center;gap:6px;min-height:46px;padding:0 14px;border-radius:12px;
  font-weight:800;font-size:15px;text-decoration:none;cursor:pointer;border:0;white-space:nowrap}
.hbtn.dark{background:#111827;color:#fff}
.hbtn.green{background:var(--green);color:#fff}
.hbtn .n{background:#fbbf24;color:#111;border-radius:999px;padding:1px 8px;font-size:13px}
nav.cats{display:flex;gap:8px;overflow-x:auto;padding:8px 0 12px;scrollbar-width:none}
nav.cats a{flex:none;padding:8px 14px;border-radius:999px;border:1px solid var(--line);background:#fff;
  color:var(--text);font-weight:700;font-size:15px;text-decoration:none;white-space:nowrap}
nav.cats a.on{background:#111827;color:#fff;border-color:#111827}
main{padding:18px 16px 10px}
h1{font-size:30px;line-height:1.2;margin:0 0 6px} h2{font-size:24px;margin:28px 0 12px}
.lead{color:var(--muted);font-size:18px;margin:0 0 14px}
.hero{background:linear-gradient(135deg,#eff6ff,#eef2ff 55%,#fffbeb);border:1px solid #bfdbfe;
  border-radius:18px;padding:20px;margin-bottom:16px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px}
.stat{background:#fff;border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-weight:700;
  font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-top:12px}
.tile{display:flex;align-items:center;gap:10px;padding:10px 12px;background:#fff;border:1px solid var(--line);
  border-radius:12px;text-decoration:none;color:var(--text);font-weight:800;font-size:15px}
.tile:hover{border-color:var(--blue)}
.tile .em{font-size:24px} .tile small{display:block;color:var(--muted);font-weight:600;font-size:13px}
.premium{display:inline-block;background:#fbbf24;color:#000;font-weight:800;padding:10px 16px;
  border-radius:10px;text-decoration:none;margin:4px 6px 10px 0}
.join-bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:10px 0 0}\n.join-label{font-weight:800;font-size:14px;margin-right:2px}
.join-btn{background:#0369a1;color:#fff;font-weight:800;font-size:14px;padding:6px 12px;border-radius:999px;
  text-decoration:none}
.filter-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#fff;border:1px solid var(--line);
  border-radius:14px;padding:10px 12px;margin:0 0 14px}
.pill{font-size:15px;font-weight:800;padding:8px 13px;border-radius:999px;cursor:pointer;
  border:1px solid var(--line);background:#fff;color:var(--text)}
.pill.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.filter-bar select{font-size:15px;font-weight:700;padding:8px 10px;border-radius:10px;border:1px solid var(--line);
  background:#f9fafb;color:var(--text)}
.filter-count{margin-left:auto;color:var(--muted);font-weight:700;font-size:15px}
.signup{background:#fff;border:2px solid var(--blue);border-radius:16px;padding:18px 20px;margin:18px 0}
.signup h2{margin:0 0 4px;font-size:24px}.signup .q{font-weight:800;font-size:17px;margin:14px 0 6px}
.signup label{display:inline-flex;align-items:center;gap:8px;font-size:17px;min-height:40px;margin-right:16px}
.signup input[type=checkbox],.signup input[type=radio]{width:22px;height:22px}
.signup input[type=email]{width:100%;font-size:18px;padding:10px 12px;border:2px solid var(--line);border-radius:10px}
.signup .go{width:100%;min-height:50px;margin-top:16px;border:0;border-radius:12px;background:var(--blue);
  color:#fff;font-size:19px;font-weight:800;cursor:pointer}
.signup .done{border:3px solid #047857;border-radius:12px;padding:14px 16px;font-size:18px}
.signup .err{color:#b91c1c;font-weight:800}.signup .hp{position:absolute;left:-9999px}
.mine{margin:18px 0}.mine h2{margin:0 0 6px}.mine .mine-top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.mine .perks{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}
.mine .perk{background:#fff;border:2px solid #f59e0b;border-radius:12px;padding:10px 14px;font-weight:800;
  text-decoration:none;color:var(--text)}
.mygrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.grid.list{grid-template-columns:1fr}
.card{display:flex;flex-direction:column;gap:8px;background:var(--card);border:1px solid var(--line);
  border-radius:16px;padding:14px;transition:box-shadow .15s,transform .15s}
.card:hover{box-shadow:0 10px 24px -10px rgba(15,23,42,.25);transform:translateY(-1px)}
.card.verified{border:2px solid var(--green)}
.card-top{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-size:13px}
.chip{display:inline-block;padding:2px 9px;border-radius:7px;font-weight:800;font-size:13px;text-decoration:none}
.chip.store{background:#111827;color:#fff}
.chip.type{background:#f3f4f6;color:#111827;border:1px solid var(--line)}
.chip.ok{background:var(--green-bg);color:var(--green)}
.ago{margin-left:auto;color:var(--muted);font-weight:600}
.title{font-size:17px;font-weight:800;line-height:1.3;margin:0}
.value{font-size:22px;font-weight:900;color:var(--green)}
.meta{color:var(--muted);font-size:14px}
.actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:auto;padding-top:8px;
  border-top:1px solid #eef0f3}
button.copy{min-height:40px;padding:0 12px;border-radius:10px;border:2px dashed var(--blue);background:#eff6ff;
  color:var(--blue-d);font:800 15px ui-monospace,Consolas,"Courier New",monospace;cursor:pointer}
button.share{min-height:40px;padding:0 12px;border-radius:10px;border:1px solid var(--line);background:#fff;font-weight:700;cursor:pointer}
.card.flash{outline:4px solid #f59e0b;outline-offset:2px}
button.save{min-height:40px;padding:0 12px;border-radius:10px;border:1px solid var(--line);background:#fff;
  font-weight:800;font-size:14px;cursor:pointer;color:var(--text)}
button.save.on{background:var(--amber-bg);border-color:#f59e0b;color:var(--amber)}
.btn{margin-left:auto;display:inline-flex;align-items:center;min-height:40px;padding:0 16px;border-radius:10px;
  background:var(--blue);color:#fff;font-weight:800;font-size:15px;text-decoration:none}
.btn:hover{background:var(--blue-d)}
.empty{color:var(--muted);font-size:18px;background:#fff;border:1px solid var(--line);border-radius:14px;
  padding:24px;text-align:center}
.drawer{position:fixed;inset:0;z-index:40;background:rgba(17,24,39,.55);display:flex;justify-content:flex-end}
.drawer[hidden]{display:none}
.drawer .panel{background:#fff;width:min(420px,100%);height:100%;overflow:auto;padding:18px}
.drawer .item{border:1px solid var(--line);border-radius:12px;padding:10px;margin:10px 0}
footer{background:#fff;border-top:1px solid var(--line);margin-top:30px;padding:18px 0;color:var(--muted);
  font-size:15px}
@media (max-width:640px){.row1{flex-wrap:wrap}.tile{padding:8px;font-size:14px}.tile .em{font-size:20px}.search{order:3;flex-basis:100%}.hbtn .t{display:none}
  h1{font-size:25px}.filter-count{margin-left:0}}
"""

SITE_JS = """<script>
(function(){
var LS='dh_watch_v1',watch={};
try{watch=JSON.parse(localStorage.getItem(LS)||'{}')||{}}catch(e){watch={}}
function keep(){try{localStorage.setItem(LS,JSON.stringify(watch))}catch(e){}}
var grid=document.querySelector('.grid'),cards=grid?[].slice.call(grid.querySelectorAll('.card')):[];
var q=document.getElementById('q'),bar=document.querySelector('.filter-bar'),mode='ALL';
var storeSel=bar&&bar.querySelector('[data-role=store]'),nicheSel=bar&&bar.querySelector('[data-role=niche]');
var sortSel=bar&&bar.querySelector('[data-role=sort]'),count=bar&&bar.querySelector('.filter-count');
if(storeSel){var st={};cards.forEach(function(c){st[c.dataset.store]=(st[c.dataset.store]||0)+1});
 Object.keys(st).sort(function(a,b){return a.localeCompare(b)}).forEach(function(s){
 var o=document.createElement('option');o.value=s;o.textContent=s+' ('+st[s]+')';storeSel.appendChild(o)})}
function run(){var t=(q&&q.value||'').trim().toLowerCase(),n=0,s=storeSel&&storeSel.value,
 ni=nicheSel&&nicheSel.value;
 cards.forEach(function(c){var d=c.dataset,ok=
  (mode==='ALL'||(mode==='VERIFIED'?d.verified==='1':mode==='CODES'?d.code!=='':
   mode==='OPENBOX'?!!d.cond:
   mode==='SAVED'?!!watch[d.hash]:d.cat===mode))&&(!s||d.store===s)&&
  (!ni||(','+d.niches+',').indexOf(','+ni+',')>-1)&&(!t||(d.text||'').indexOf(t)>-1);
  c.style.display=ok?'':'none';if(ok)n++});
 if(count)count.textContent=n+' shown'}
function sort(){if(!grid||!sortSel)return;var v=sortSel.value;cards.sort(function(a,b){
 if(v==='store')return a.dataset.store.localeCompare(b.dataset.store);
 if(v==='codes')return (b.dataset.code?1:0)-(a.dataset.code?1:0)||(b.dataset.new>a.dataset.new?1:-1);
 return b.dataset.new>a.dataset.new?1:-1});cards.forEach(function(c){grid.appendChild(c)})}
if(bar){bar.addEventListener('click',function(ev){var p=ev.target.closest('.pill');if(p){
 bar.querySelectorAll('.pill').forEach(function(x){x.classList.remove('active')});p.classList.add('active');
 mode=p.dataset.filter;run()}var v=ev.target.closest('[data-view]');if(v&&grid){
 grid.classList.toggle('list',v.dataset.view==='list')}});
 [storeSel,nicheSel].forEach(function(x){x&&x.addEventListener('change',run)});
 sortSel&&sortSel.addEventListener('change',sort)}
if(q){var p=new URLSearchParams(location.search).get('q');if(p){q.value=p}
 q.addEventListener('input',run);q.addEventListener('keydown',function(ev){
 if(ev.key==='Enter'&&!grid){location.href=q.dataset.home+'?q='+encodeURIComponent(q.value)}})}
document.addEventListener('keydown',function(ev){var a=document.activeElement.tagName;
 if(ev.key==='/'&&q&&a!=='INPUT'&&a!=='SELECT'){ev.preventDefault();q.focus()}
 if(ev.key==='Escape')closeW()});
var wl=document.getElementById('wl'),wlList=document.getElementById('wl-list'),wlN=document.getElementById('wl-n');
function esc(s){var d=document.createElement('div');d.textContent=s||'';return d.innerHTML}
function paint(){var k=Object.keys(watch);if(wlN)wlN.textContent=k.length;
 cards.forEach(function(c){var b=c.querySelector('button.save'),on=!!watch[c.dataset.hash];
  if(b){b.classList.toggle('on',on);b.textContent=on?'\\u2605 Saved':'\\u2606 Save'}});
 if(wlList)wlList.innerHTML=k.length?k.map(function(h){var w=watch[h];return '<div class="item"><b>'+
  esc(w.s)+'</b> \\u2013 '+esc(w.v)+'<br>'+esc(w.t)+(w.c?'<br>Code: <b>'+esc(w.c)+'</b>':'')+
  '<br><a href="'+esc(w.l)+'" rel="nofollow sponsored" target="_blank">Get deal</a> \\u00b7 '+
  '<a href="#" data-unsave="'+esc(h)+'">Remove</a></div>'}).join(''):
  '<p class="meta">Nothing saved yet. Tap \\u2606 Save on any deal to keep it here (only on this device).</p>'}
function closeW(){if(wl)wl.hidden=true}
document.addEventListener('click',function(ev){
 var c=ev.target.closest('button.copy');if(c){var lab=c.dataset.label||c.textContent;c.dataset.label=lab;
  navigator.clipboard.writeText(c.dataset.code).then(function(){c.textContent='Copied \\u2713';
  setTimeout(function(){c.textContent=lab},1500)});return}
 var sh=ev.target.closest('button.share');if(sh){var url=new URL(sh.dataset.url,location.href).href,
  txt=sh.dataset.share+' - found on Deal Hunter';
  if(navigator.share){navigator.share({title:'Deal Hunter',text:txt,url:url}).catch(function(){});return}
  navigator.clipboard.writeText(txt+' '+url).then(function(){sh.textContent='Link copied \\u2713';
  setTimeout(function(){sh.textContent='\\u2197 Share'},1800)});return}
 var s=ev.target.closest('button.save');if(s){var cd=s.closest('.card').dataset;
  if(watch[cd.hash])delete watch[cd.hash];else watch[cd.hash]={t:cd.title,s:cd.store,v:cd.value,c:cd.code,l:cd.link};
  keep();paint();run();return}
 var u=ev.target.closest('[data-unsave]');if(u){ev.preventDefault();delete watch[u.dataset.unsave];keep();paint();run();return}
 if(ev.target.closest('#wl-open')){if(wl){paint();wl.hidden=false}return}
 if(ev.target.closest('#wl-close')||ev.target===wl)closeW()});
paint();run();
if(location.hash.indexOf('#d-')===0){var t=document.getElementById(location.hash.slice(1));
 if(t){t.classList.add('flash');t.scrollIntoView({block:'center'})}}
})();
</script>"""


def slug(domain: str) -> str:
    return re.sub(r"[^a-z0-9.-]", "-", domain.lower())


def base_path() -> str:
    """'' for a site at the root of its domain, '/deal-hunter' on GitHub project Pages."""
    return urlparse(settings.public_base_url).path.rstrip("/") if settings.public_base_url else ""


def u(path: str) -> str:
    """Site-internal link that also works when the site lives in a sub-folder."""
    return base_path() + path


CATS_JS = {"farm": "Farm and ranch", "tools": "Tools", "moto": "Motorcycle", "auto": "Auto and truck",
           "electronics": "Tech", "astro": "Telescope and space", "other": "Home"}

PICKS_JS = """<script>
(function(){
var K='dh_picks_v1',p=null;
try{p=JSON.parse(localStorage.getItem(K)||'null')}catch(e){}
var qs=new URLSearchParams(location.search);
if(qs.get('for')){p=p||{};var add=qs.get('for').split(',');p.cats=(p.cats||[]).concat(add)
 .filter(function(x,i,a){return x&&a.indexOf(x)===i});
 if(qs.get('prime'))p.prime=qs.get('prime');if(qs.get('audio'))p.audio=qs.get('audio');
 try{localStorage.setItem(K,JSON.stringify(p))}catch(e){}}
var src=qs.get('src');try{if(src)sessionStorage.setItem('dh_src',src);src=sessionStorage.getItem('dh_src')}catch(e){}
var TW=document.body.dataset.tagWeb,TE=document.body.dataset.tagEmail;
if(src==='email'&&TW&&TE){[].slice.call(document.querySelectorAll('a[href*="tag='+TW+'"]')).forEach(function(a){
 a.href=a.href.replace('tag='+TW,'tag='+TE)});[].slice.call(document.querySelectorAll('[data-link*="tag='+TW+'"]'))
 .forEach(function(c){c.dataset.link=c.dataset.link.replace('tag='+TW,'tag='+TE)})}
var box=document.getElementById('signup'),mine=document.getElementById('mine');
function showMine(){if(!mine||!p||!p.cats||!p.cats.length)return;
 var all=p.cats.indexOf('all')>-1,g=document.querySelector('.grid'),mg=mine.querySelector('.mygrid');
 if(!g||!mg)return;mg.innerHTML='';
 var cs=[].slice.call(g.querySelectorAll('.card')).filter(function(c){return all||
  c.dataset.niches.split(',').some(function(n){return p.cats.indexOf(n)>-1})});
 cs.sort(function(a,b){return parseFloat(b.dataset.pay||0)-parseFloat(a.dataset.pay||0)});
 cs.slice(0,9).forEach(function(c){var x=c.cloneNode(true);x.removeAttribute('id');mg.appendChild(x)});
 mine.querySelectorAll('[data-show]').forEach(function(a){var w=a.dataset.show;
  a.hidden=!((w==='noprime'&&p.prime==='no')||(w==='prime'&&p.prime==='yes')||(w==='audio'&&p.audio==='yes'))});
 mine.hidden=!cs.length;if(box&&cs.length)box.hidden=true}
showMine();
document.addEventListener('click',function(ev){if(ev.target.closest('[data-repick]')&&box){
 ev.preventDefault();box.hidden=false;box.scrollIntoView({block:'start'})}});
if(!box)return;var f=box.querySelector('form');
f&&f.addEventListener('submit',function(ev){ev.preventDefault();
 var err=box.querySelector('.err'),em=f.email.value.trim();
 if(!/^[^@\\s]+@[^@\\s]+\\.[a-z]{2,}$/i.test(em)){err.textContent='Enter your email first.';f.email.focus();return}
 err.textContent='';
 var cats=[].slice.call(f.querySelectorAll('[name=cat]:checked')).map(function(x){return x.value});
 var d={email:em,cats:cats.join(','),prime:(f.querySelector('[name=prime]:checked')||{}).value||'',
  audio:(f.querySelector('[name=audio]:checked')||{}).value||'',
  freq:(f.querySelector('[name=freq]:checked')||{}).value||'daily',website:f.website.value};
 p={cats:cats.length?cats:['all'],prime:d.prime,audio:d.audio};
 try{localStorage.setItem(K,JSON.stringify(p))}catch(e){}
 var url=box.dataset.url,btn=f.querySelector('.go');btn.disabled=true;btn.textContent='Signing you up\\u2026';
 function done(){f.hidden=true;box.querySelector('.done').hidden=false;showMine();if(mine&&!mine.hidden)box.hidden=false}
 if(!url){done();return}
 fetch(url,{method:'POST',mode:'no-cors',headers:{'Content-Type':'text/plain'},body:JSON.stringify(d)})
  .then(done,function(){btn.disabled=false;btn.textContent='Send me deals';
   err.textContent='That did not go through. Check your connection and try again.'})});
})();
</script>"""


def signup_box() -> str:
    """Email sign-up: 5 quick questions. Sent to the Sheet web app, which adds the person to Brevo."""
    cats = "".join(f'<label><input type="checkbox" name="cat" value="{k}"> {e(v)}</label>'
                   for k, v in CATS_JS.items())
    def yn(name):
        return (f'<label><input type="radio" name="{name}" value="yes"> Yes</label>'
                f'<label><input type="radio" name="{name}" value="no"> No</label>')
    return (f'<section class="signup" id="signup" data-url="{e(settings.signup_url, quote=True)}">'
            '<h2>📬 Get deals in your inbox</h2>'
            '<p class="meta" style="font-size:17px">Free. Only the deals you care about. 5 quick taps.</p>'
            '<form novalidate><div class="q">1. Your email</div>'
            '<input type="email" name="email" autocomplete="email" placeholder="you@email.com" '
            'aria-label="Your email">'
            '<input class="hp" type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">'
            f'<div class="q">2. What deals do you want?</div><div>{cats}'
            '<label><input type="checkbox" name="cat" value="all"> Everything</label></div>'
            f'<div class="q">3. Do you have Amazon Prime?</div><div>{yn("prime")}</div>'
            f'<div class="q">4. Do you listen to audiobooks?</div><div>{yn("audio")}</div>'
            '<div class="q">5. How often?</div><div>'
            '<label><input type="radio" name="freq" value="daily" checked> Every day</label>'
            '<label><input type="radio" name="freq" value="weekly"> Once a week</label></div>'
            '<p class="err" role="alert"></p>'
            '<button class="go" type="submit">Send me deals</button>'
            '<p class="meta" style="text-align:center">No spam from us. Unsubscribe with one tap.</p></form>'
            '<div class="done" hidden><p style="margin:0 0 8px;font-size:22px;font-weight:800">✅ You\'re in!</p>'
            f'<p style="margin:0 0 8px">Your first deals arrive at {settings.email_hour} AM.</p>'
            '<p style="margin:0">🔍 Don\'t see us? Check your spam folder. Our deals are so good, '
            'your inbox thinks they\'re too good to be true. Tap "Not spam" and we\'ll behave.</p></div>'
            '</section>')


def my_deals_section() -> str:
    """'Your deals': filled in the browser from the visitor's saved picks. Best-paying first."""
    from amazon_perks import perk_links
    want = {"Try Amazon Prime free": "noprime", "Prime Exclusive deals": "prime",
            "Try Audible free": "audio"}
    perks = "".join(f'<a class="perk" data-show="{want[t]}" hidden href="{e(link, quote=True)}" '
                    f'rel="sponsored nofollow" target="_blank">{e(em)} {e(t)} ↗</a>'
                    for em, t, _, link in perk_links() if t in want)
    return ('<section class="mine" id="mine" hidden><div class="mine-top"><h2>⭐ Your deals</h2>'
            '<a href="#signup" data-repick class="meta">Change my picks</a></div>'
            f'<div class="perks">{perks}</div><div class="mygrid"></div></section>')


def go_link(deal: dict) -> str:
    if settings.click_tracking:
        return u(f"/go/{deal['deal_hash'][:12]}?c=web")
    return best_link(deal)


def _found(iso: str | None) -> str:
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt.strftime("%b %d").replace(" 0", " ")
    except (ValueError, TypeError):
        return ""


def _pay(deal: dict) -> float:
    """How good the deal is, weighted by how much the click pays (Amazon first, then eBay)."""
    from emailer import payout_score
    try:
        return payout_score(deal)
    except Exception:  # never let ranking break the page
        return 0.0


def card(deal: dict) -> str:
    """One deal card. Only real data: store, what, the discount, code, dates, link."""
    deal = price_safe(deal)
    label, _ = deal_label(deal)
    verified = bool(deal.get("is_verified"))
    code = deal.get("promo_code") or ""
    title = deal.get("summary") or f"{deal['store_name']} deal"
    search_text = " ".join(str(deal.get(k) or "") for k in
                           ("store_name", "store_domain", "summary", "discount_value",
                            "promo_code")).lower()
    link = go_link(deal)
    attrs = {"data-cat": str(deal["category"]), "data-verified": "1" if verified else "0",
             "data-text": search_text, "data-store": deal["store_name"],
             "data-niches": ",".join(deal.get("niches") or []), "data-code": code,
             "data-cond": deal.get("condition") or "",
             "data-hash": deal["deal_hash"][:16], "data-new": str(deal.get("created_at") or ""),
             "data-title": title, "data-value": deal["discount_value"], "data-link": link,
             "data-pay": f"{_pay(deal):.2f}"}
    attr = " ".join(f'{k}="{e(v, quote=True)}"' for k, v in attrs.items())
    store_url = u("/store/" + slug(deal["store_domain"]) + ".html")
    anchor = "d-" + deal["deal_hash"][:12]
    share_rel = "/store/" + slug(deal["store_domain"]) + ".html#" + anchor
    share_url = (settings.public_base_url.rstrip("/") + share_rel) if settings.public_base_url \
        else u(share_rel)
    share_text = f"{deal['store_name']}: {title} ({deal['discount_value']})"
    parts = [f'<article id="{anchor}" class="card{" verified" if verified else ""}" {attr}>',
             '<div class="card-top">',
             f'<a class="chip store" href="{store_url}">{e(deal["store_name"])}</a>',
             f'<span class="chip type">{e(label.title())}</span>',
             '<span class="chip ok">✔ Verified at checkout</span>' if verified else "",
             f'<span class="ago">Found {e(_found(deal.get("created_at")))}</span></div>',
             f'<h3 class="title">{e(title)}</h3>',
             f'<div class="value">{e(deal["discount_value"])}</div>']
    if deal.get("expiration_date"):
        parts.append(f'<div class="meta">Ends {e(str(deal["expiration_date"]))}</div>')
    search = None if has_product_link(deal) else store_search(deal)
    if search:
        parts.append(f'<div class="meta">Search {e(search[0])} for this item</div>')
    elif not has_product_link(deal) and not settings.click_tracking:
        host = urlparse(link).netloc.removeprefix("www.")
        if host and host != deal["store_domain"]:
            parts.append(f'<div class="meta">Opens the deal post on {e(host)}</div>')
    parts.append('<div class="actions">')
    if code:
        parts.append(f'<button class="copy" data-code="{e(code, quote=True)}" '
                     f'title="Copy code">{e(code)} ⧉</button>')
    parts.append(f'<button class="share" type="button" data-url="{e(share_url, quote=True)}" '
                 f'data-share="{e(share_text, quote=True)}" title="Share this deal">↗ Share</button>')
    parts.append('<button class="save" type="button">☆ Save</button>'
                 f'<a class="btn" href="{e(link, quote=True)}" rel="nofollow sponsored" '
                 f'target="_blank">{"Search " + e(search[0]) if search else "Get deal"} ↗</a>'
                 '</div></article>')
    return "".join(parts)


def page(title: str, body: str, description: str = "", extra_head: str = "",
         active: str = "", search: bool = True) -> str:
    niches = load_niches()
    nav = "".join(f'<a href="{u("/" + n.id + "/")}"{" class=on" if n.id == active else ""}>'
                  f'{e(n.emoji)} {e(n.name.replace(" Deals", ""))}</a>' for n in niches)
    nav += (f'<a href="{u("/open-box/")}"{" class=on" if active == "open-box" else ""}>'
            '📦 Open Box</a>')
    nav += (f'<a href="{u("/free-trials/")}"{" class=on" if active == "free-trials" else ""}>'
            '🎁 Free trials</a>')
    from amazon_perks import shortcut_links
    nav += "".join(f'<a href="{e(link, quote=True)}" rel="sponsored nofollow" target="_blank">'
                   f'{e(t.replace("Amazon ", ""))}</a>' for t, link in shortcut_links())
    home_on = ' class=on' if active == "home" else ""
    pick = ""
    if settings.sovrn_pick_url.startswith("https://sovrn.co/"):
        pick = (f' · <a href="{e(settings.sovrn_pick_url, quote=True)}" rel="sponsored nofollow" '
                'target="_blank">Today\'s pick: DeWalt drills at Walmart</a>')
    share = ""
    if False:  # no Discord links on the website (Kyle's rule)
        share = (f'<a class="hbtn green" href="{e(settings.discord_invite_url, quote=True)}" '
                 'target="_blank" rel="noopener">＋<span class="t"> Share a deal</span></a>')
    search_box = (f'<label class="search">🔍<input id="q" type="search" data-home="{u("/")}" '
                  'placeholder="Search stores, items or codes (press /)" '
                  'aria-label="Search deals"></label>') if search else '<div style="flex:1"></div>'
    year = datetime.now().year
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description or title, quote=True)}">{extra_head}
<link rel="alternate" type="application/rss+xml" title="{e(settings.site_name)} RSS" href="{u('/rss.xml')}">
<style>{CSS}</style>{analytics_html()}</head><body data-tag-web="{e(settings.amazon_tag_web, quote=True)}" data-tag-email="{e(settings.amazon_tag_email, quote=True)}">
<header class="top"><div class="wrap"><div class="row1">
<a class="logo" href="{u("/")}"><span class="mark">🏷️</span><span>{e(settings.site_name)}</span></a>
{search_box}{share}
<button class="hbtn dark" id="wl-open" type="button">☆<span class="t"> Watchlist</span> <span class="n" id="wl-n">0</span></button>
</div><nav class="cats" aria-label="Categories"><a href="{u("/")}"{home_on}>🏠 All deals</a>{nav}</nav></div></header>
<main class="wrap">{event_banner()}{body}</main>
<div class="drawer" id="wl" hidden><div class="panel"><div style="display:flex;justify-content:space-between;align-items:center">
<h2 style="margin:0">☆ Watchlist</h2><button class="save" id="wl-close" type="button">Close ✕</button></div>
<p class="meta">Saved on this device only. Prices and codes can change, so check before you buy.</p>
<div id="wl-list"></div></div></div>
<footer><div class="wrap">{e(DISCLOSURE)} ·
<a href="{u("/guides/")}">Buying guides</a> · <a href="{u("/stores/")}">All stores</a> · <a href="{u("/about.html")}">About &amp; disclosure</a> · <a href="{u("/privacy.html")}">Privacy</a> · <a href="{u("/rss.xml")}">RSS feed</a>{pick}
<br>© {year} {e(settings.site_name)}. Deals change fast; check the price before you buy.
</div></footer>{SITE_JS}{PICKS_JS}</body></html>"""


def event_banner() -> str:
    """Amazon sale banner (e.g. Black Friday) while the event is on; nothing otherwise."""
    from amazon_perks import active_events
    return "".join(
        f'<a class="btn" style="display:block;text-align:center;margin:12px 0;font-size:1.1em" '
        f'href="{e(link, quote=True)}" rel="sponsored nofollow" target="_blank">{e(t)} →</a>'
        for t, link in active_events())


def verification_meta() -> str:
    """Ownership tags (Impact, Pinterest, ...) from site_meta/verification.txt. Only <meta> tags."""
    f = Path(__file__).resolve().parent / "site_meta" / "verification.txt"
    if not f.is_file():
        return ""
    tags = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
            if re.fullmatch(r"<meta\s[^<>]*>", ln.strip())]
    return "".join(tags)


def analytics_html() -> str:
    """Optional free, cookie-less visitor counts (Cloudflare Web Analytics or GoatCounter)."""
    parts = []
    if settings.cloudflare_analytics_token:
        tok = json.dumps({"token": settings.cloudflare_analytics_token})
        parts.append("<script defer src='https://static.cloudflareinsights.com/beacon.min.js' "
                     f"data-cf-beacon='{e(tok, quote=True)}'></script>")
    site = re.sub(r"[^a-zA-Z0-9-]", "", settings.goatcounter_site)
    if site:
        parts.append(f'<script data-goatcounter="https://{site}.goatcounter.com/count" '
                     'async src="https://gc.zgo.at/count.js"></script>')
    return "".join(parts)


def join_banner(niches: list) -> str:
    """Telegram join buttons (free channels). Never Discord (Kyle's rule)."""
    if not settings.site_telegram_links:
        return ""
    from tginvite import LINKS
    links = []
    single = len(niches) == 1
    for n in niches:
        link = LINKS.get(n.id, "")
        if not link:
            tg = n.telegram_chat("free")
            link = f"https://t.me/{tg[1:]}" if tg.startswith("@") else ""
        if link:
            text = (f"Join {e(n.emoji)} {e(n.name)} on Telegram" if single
                    else f"{e(n.emoji)} {e(n.name.replace(' Deals', ''))}")
            links.append(f'<a class="join-btn" href="{e(link, quote=True)}" '
                         f'target="_blank" rel="noopener">{text}</a>')
    if not links:
        return ""
    label = "" if single else '<span class="join-label">Free alerts on Telegram:</span>'
    return '<div class="join-bar">' + label + "".join(links) + "</div>"


def filter_bar(count: int, niches: list | None = None) -> str:
    """Type tabs, store/category pickers, sort and list/grid switch. Works on the cards below."""
    if count < 2:
        return ""
    pills = [("ALL", "All"), ("CODES", "Promo codes"), ("FREEBIE", "Freebies"),
             ("PRICE_ERROR", "Price errors"), ("CASHBACK_BONUS", "Cash bonuses"),
             ("OPENBOX", "📦 Open box"), ("VERIFIED", "Verified"), ("SAVED", "☆ Saved")]
    buttons = "".join(f'<button type="button" class="pill{" active" if k == "ALL" else ""}" '
                      f'data-filter="{k}">{label}</button>' for k, label in pills)
    niche_sel = ""
    if niches:
        niche_sel = ('<select data-role="niche" aria-label="Category"><option value="">All categories</option>'
                     + "".join(f'<option value="{e(n.id, quote=True)}">{e(n.emoji)} {e(n.name)}</option>'
                               for n in niches) + "</select>")
    return ('<div class="filter-bar">' + buttons + niche_sel
            + '<select data-role="store" aria-label="Store"><option value="">All stores</option></select>'
            '<select data-role="sort" aria-label="Sort"><option value="new">Newest first</option>'
            '<option value="codes">Promo codes first</option><option value="store">Store A–Z</option></select>'
            '<button type="button" class="pill" data-view="grid" title="Grid view">▦</button>'
            '<button type="button" class="pill" data-view="list" title="List view">☰</button>'
            f'<span class="filter-count">{count} shown</span></div>')


def deal_grid(deals: list[dict]) -> str:
    if not deals:
        return '<p class="empty">No active deals right now. New ones are added every 30 minutes.</p>'
    return '<div class="grid">' + "".join(card(d) for d in deals) + "</div>"


def premium_button(niche) -> str:
    if not settings.site_channel_links or not niche.premium_url:
        return ""
    return (f'<a class="premium" href="{e(niche.premium_url, quote=True)}">'
            f"⭐ Get {e(niche.name)} instantly + price errors</a>")


def _ts(iso) -> float:
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _visible(deals: list[dict]) -> list[dict]:
    if settings.paid_exclusive_price_errors:
        deals = [d for d in deals if d["category"] != "PRICE_ERROR"]
    return deals


def _rfc2822(iso_str: str | None) -> str:
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return format_datetime(dt)
    except (ValueError, TypeError):
        return format_datetime(datetime.now(timezone.utc))


def rss_xml(deals: list[dict]) -> str:
    base = settings.public_base_url or ""
    site_url = base + "/" if base else "/"
    items = []
    for d in deals[:50]:
        d = price_safe(d)
        title = f"{d['store_name']}: {d['discount_value']}"
        if d.get("summary"):
            title += f" - {d['summary']}"
        desc_parts = [d.get("summary") or "", f"Discount: {d['discount_value']}"]
        if d.get("promo_code"):
            desc_parts.append(f"Code: {d['promo_code']}")
        if d.get("is_verified"):
            desc_parts.append("Verified at checkout")
        desc = " | ".join(p for p in desc_parts if p)
        link = go_link(d)
        if link.startswith("/"):   # click-tracking links are site-relative; feeds need full URLs
            link = urlparse(base)._replace(path="", query="", fragment="").geturl() + link \
                if base else link
        items.append(
            f"<item><title>{e(title)}</title><link>{e(link)}</link>"
            f'<guid isPermaLink="false">{e(d["deal_hash"])}</guid>'
            f"<pubDate>{e(_rfc2822(d.get('created_at')))}</pubDate>"
            f"<description>{e(desc)}</description></item>"
        )
    now_rfc = format_datetime(datetime.now(timezone.utc))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f'<title>{e(settings.site_name)}</title>'
        f'<link>{e(site_url)}</link>'
        f'<description>Latest deals, promo codes, and freebies from {e(settings.site_name)}.</description>'
        f'<lastBuildDate>{e(now_rfc)}</lastBuildDate>'
        + "".join(items)
        + '</channel></rss>'
    )


def tiktok_scripts_html(deals: list[dict]) -> str:
    """Mobile-friendly short-video scripts (TikTok / Shorts / Reels) for today's top deals."""
    cards = []
    for d in deals[:6]:
        d = price_safe(d)
        item = d.get("summary") or f"{d['store_name']} deal"
        disc = d["discount_value"]
        code_line = f" Use code {d['promo_code']} at checkout." if d.get("promo_code") else ""
        hook = f"{d['store_name']}: {disc} on {item}"
        spoken = (f"Heads up if you've been eyeing {item}: {d['store_name']} currently has it "
                  f"for {disc}.{code_line} I put the direct link on {settings.site_name}.")
        tags = "#deals #pricealert #clearance #savingmoney"
        niches = set(d.get("niches") or [])
        if "farm" in niches:
            tags += " #homestead #tractorsupply"
        if "moto" in niches:
            tags += " #motorcycle #motorcyclegear"
        if "tools" in niches:
            tags += " #tools #tooldeals"
        if "auto" in niches:
            tags += " #truck #carmods"
        if "electronics" in niches:
            tags += " #techdeals #electronics"
        if "astro" in niches:
            tags += " #astrophotography #telescope"
        caption = f"{hook} - {d.get('promo_code') or 'Link in bio'} {tags}"
        full_copy = f"HOOK (on screen):\n{hook}\n\nSAY THIS:\n{spoken}\n\nCAPTION:\n{caption}"
        cards.append(
            f'<div class="card">'
            f'<div class="store">{e(d["store_name"])} · {e(disc)}</div>'
            f'<p><b>On-screen hook:</b> {e(hook)}</p>'
            f'<p><b>15-sec script:</b> {e(spoken)}</p>'
            f'<p class="meta"><b>Caption:</b> {e(caption)}</p>'
            f'<button type="button" class="copy" style="padding:10px 14px;margin-top:8px" '
            f'data-code="{e(full_copy, quote=True)}">Copy script &amp; caption</button>'
            f'<a class="btn" href="{e(go_link(d), quote=True)}" rel="nofollow sponsored">Open deal →</a>'
            f'</div>'
        )
    grid = '<div class="grid">' + "".join(cards) + "</div>" if cards else '<p class="empty">No deals yet.</p>'
    body = ("<h1>Short-video deal scripts</h1>"
            "<p class='lead'>Ready-to-record 15-second scripts for TikTok, YouTube Shorts, and Reels.</p>"
            + grid)
    return page(f"Video scripts | {settings.site_name}", body,
                "Short-video deal scripts",
                extra_head='<meta name="robots" content="noindex,nofollow">')


# ---------------------------------------------------------------- buying guides
# Evergreen tips per category; the deal list under them refreshes every run.
GUIDE_TIPS = {
    "farm": ("Farm, ranch & outdoor gear", [
        "Tractor Supply and Rural King run their biggest sales around spring planting and "
        "Black Friday. Feed, fencing and chicken supplies drop most in late winter.",
        "Buy chainsaws, log splitters and generators in spring or summer, not right before a "
        "storm when prices and demand jump.",
        "Check the store's own brand (like Tractor Supply's in-house lines). It's often the same "
        "quality for less.",
        "Sign up for store reward programs. Many give a coupon on your birthday or after a few "
        "purchases."]),
    "moto": ("Motorcycle gear & parts", [
        "Helmets, jackets and gloves go on sale at the end of riding season (fall) and when new "
        "colors come out in early spring.",
        "RevZilla, Cycle Gear and Motorcycle Superstore often price-match each other, so check "
        "all three.",
        "Never buy a used helmet. A helmet that has been dropped may not protect you.",
        "Closeout colors are the same gear for less. If you don't care about the color, save."]),
    "tools": ("Power tools & hand tools", [
        "The best tool deals come around Father's Day, Black Friday and the holidays, when "
        "brands add a free battery or tool.",
        "Stay with one battery brand (DeWalt, Milwaukee, Ryobi...). Bare tools without a "
        "battery are much cheaper once you own batteries.",
        "Kits with 2 batteries are often cheaper than buying the batteries alone.",
        "Factory-reconditioned tools usually have a warranty and cost far less than new."]),
    "auto": ("Auto & truck parts", [
        "Auto parts stores have online-only codes, often 20% off or more. Order online and pick "
        "up in store the same day.",
        "Check your vehicle's exact year, engine and trim before buying. Returns on wrong "
        "parts are a hassle.",
        "Oil, filters and wipers are cheapest during holiday weekend sales. Stock up then.",
        "Many stores test batteries, alternators and check-engine codes for free."]),
    "electronics": ("Electronics & tech", [
        "Compare the exact model number. Black Friday TVs are sometimes cheaper 'special' models "
        "with fewer features.",
        "Open-box and refurbished items from Best Buy, Amazon and Apple often have the same "
        "warranty as new. See our Open Box page.",
        "Prices on last year's phones, laptops and headphones drop when new models come out.",
        "Price-tracking helps: if an item was cheaper last month, it will probably drop again."]),
    "astro": ("Telescopes, binoculars & astro gear", [
        "Telescope sales come around Black Friday, the holidays and big sky events like "
        "eclipses and meteor showers.",
        "For beginners, a smart telescope or a simple Dobsonian gives the most views per dollar.",
        "Check the mount, not just the telescope. A shaky mount ruins the view.",
        "Astro shops like High Point Scientific and Agena often bundle free eyepieces or "
        "filters, which adds real value."]),
    "other": ("Everyday & home", [
        "Walmart, Target and Amazon match each other on big sale days. Check all three.",
        "Target Circle and Walmart+ deals can stack with sale prices.",
        "Household basics are cheapest with subscribe-and-save or bulk club packs.",
        "Kitchen gadgets like air fryers drop most around Prime Day and Black Friday."]),
}


def guide_html(niche, deals: list[dict]) -> str:
    """'Best <category> deals this week' guide: tips + the top 10 live deals."""
    topic, tips = GUIDE_TIPS.get(niche.id, (niche.name, []))
    month = datetime.now().strftime("%B %Y")
    tip_html = "".join(f"<li>{e(t)}</li>" for t in tips)
    body = (f"<h1>{e(niche.emoji)} Best {e(topic.lower())} deals: {month} buying guide</h1>"
            f"<p class='lead'>How to save on {e(topic.lower())}, plus the top {len(deals)} live "
            f"deals right now. Updated {datetime.now().strftime('%B %d, %Y')}.</p>"
            f"<h2>Money-saving tips</h2><ul>{tip_html}</ul>"
            f"<h2>Top deals this week</h2>{deal_grid(deals)}"
            f'<p><a class="btn" href="{u("/" + niche.id + "/")}">See all {e(niche.name.lower())} →</a></p>')
    return page(f"Best {topic.lower()} deals ({month}): buying guide | {settings.site_name}", body,
                f"How to save on {topic.lower()} in {month}, with the best live deals and "
                "coupon codes, updated every 30 minutes.", active=niche.id)


def guides_index_html(niches) -> str:
    items = "".join(
        f'<a class="tile" href="{u("/guides/" + n.id + ".html")}"><span class="em">{e(n.emoji)}</span>'
        f'<span>{e(GUIDE_TIPS.get(n.id, (n.name,))[0])}<small>Buying guide</small></span></a>'
        for n in niches)
    return page(f"Buying guides | {settings.site_name}",
                "<h1>📚 Buying guides</h1><p class='lead'>When to buy, what to look for, and "
                f"the best live deals in each category.</p><div class='tiles'>{items}</div>",
                "Buying guides with money-saving tips and the best live deals by category.")


def free_trials_html() -> str:
    from amazon_perks import NOTE, perk_links
    cards = "".join(
        f'<div class="card"><div class="store">{e(em)} {e(t)}</div><p>{e(b)}</p>'
        f'<a class="btn" href="{e(link, quote=True)}" rel="sponsored nofollow" '
        f'target="_blank">See it on Amazon →</a></div>' for em, t, b, link in perk_links())
    body = ("<h1>🎁 Free trials &amp; Amazon perks</h1><p class='lead'>Free trials and "
            "money-saving Amazon programs worth knowing about.</p>"
            f"<div class='grid'>{cards}</div><p class='meta'>{e(NOTE)}</p>")
    return page(f"Free trials & Amazon perks | {settings.site_name}", body,
                "Free Amazon trials and money-saving programs: Prime, Audible, Kindle "
                "Unlimited, Prime Access, Amazon Business and more.", active="free-trials")


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if rel.endswith((".html", ".xml")):
        from affiliate import retag_amazon
        content = retag_amazon(content, "web")       # website sales show as the web tracking ID
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


async def build_site(db, out_dir: str | None = None) -> int:
    """Regenerate every page. Returns the number of files written."""
    root = Path(out_dir or settings.site_dir)
    root.mkdir(parents=True, exist_ok=True)
    niches = load_niches()
    if settings.site_telegram_links:
        try:
            import tginvite
            await tginvite.ensure(db, niches)
        except Exception as exc:  # noqa: BLE001 - join buttons must never stop the site
            log.warning("Telegram invite links skipped: %s", exc)
    written = 0
    urls = ["/"]

    # Niche deals (also feed the homepage and store pages)
    stores: dict[str, list[dict]] = {}
    by_niche: dict[str, list[dict]] = {}
    for n in niches:
        deals = _visible(await db.niche_deals(n.id, hours=24 * 30, limit=500))
        by_niche[n.id] = deals
        for d in deals:
            stores.setdefault(d["store_domain"], []).append(d)

    # Home: every live deal from the last week, newest first, filterable in the browser
    recent_all: dict[str, dict] = {}
    for deals in by_niche.values():
        for d in deals:
            recent_all.setdefault(d["deal_hash"], d)
    week_ago = (datetime.now(timezone.utc).timestamp() - 7 * 86400)
    home_deals = sorted((d for d in recent_all.values()
                         if _ts(d.get("created_at")) >= week_ago),
                        key=lambda d: str(d.get("created_at") or ""), reverse=True)[:240]
    n_codes = sum(1 for d in home_deals if d.get("promo_code"))
    n_stores = len({d["store_domain"] for d in home_deals})
    tiles = "".join(
        f'<a class="tile" href="{u("/" + n.id + "/")}"><span class="em">{e(n.emoji)}</span>'
        f'<span>{e(n.name.replace(" Deals", ""))}<small>{len(by_niche.get(n.id, []))} deals</small>'
        "</span></a>" for n in niches)
    premiums = "".join(premium_button(n) for n in niches)
    body = (f'<section class="hero"><h1>Today\'s best deals</h1>'
            f"<p class='lead'>Coupon codes, freebies and price drops, found automatically and "
            f"updated every 30 minutes.</p>"
            f'<div class="stats"><span class="stat">{len(home_deals)} live deals</span>'
            f'<span class="stat">{n_codes} promo codes</span><span class="stat">{n_stores} stores</span></div>'
            f'{join_banner(niches)}<div class="tiles">{tiles}</div></section>{premiums}'
            f"{my_deals_section()}{signup_box()}"
            f"{filter_bar(len(home_deals), niches)}{deal_grid(home_deals)}")
    _write(root, "index.html", page(f"{settings.site_name}: today's best deals, coupon codes & freebies",
                                    body, "Live coupon codes, freebies and price drops for farm, "
                                    "motorcycle, tools, auto, electronics and more. Updated every "
                                    "30 minutes.", extra_head=verification_meta(), active="home"))
    written += 1

    # Niche pages
    for n in niches:
        recent = sorted(by_niche[n.id], key=lambda d: d["created_at"], reverse=True)[:120]
        body = (f"<h1>{e(n.emoji)} {e(n.name)}</h1><p class='lead'>Updated "
                f"{datetime.now().strftime('%B %d, %Y')}. {len(recent)} live deals.</p>"
                f"{join_banner([n])}{premium_button(n)}{filter_bar(len(recent))}{deal_grid(recent)}")
        _write(root, f"{n.id}/index.html", page(f"{n.name} | {settings.site_name}", body,
                                                f"Latest {n.name.lower()}: coupon codes, "
                                                f"sales and freebies.", active=n.id))
        urls.append(f"/{n.id}/")
        written += 1

    # Open box & refurbished page (across every category)
    open_box = sorted((d for d in recent_all.values() if d.get("condition")),
                      key=lambda d: str(d.get("created_at") or ""), reverse=True)[:240]
    body = ("<h1>📦 Open Box &amp; Refurbished Deals</h1><p class='lead'>Open-box, refurbished "
            "and renewed items, often much cheaper than new. Check the condition and warranty "
            f"before you buy. {len(open_box)} live deals.</p>"
            f"{filter_bar(len(open_box), niches)}{deal_grid(open_box)}")
    _write(root, "open-box/index.html",
           page(f"Open box & refurbished deals | {settings.site_name}", body,
                "Open-box, refurbished and renewed deals from Amazon, Best Buy, Walmart and "
                "more, updated every 30 minutes.", active="open-box"))
    urls.append("/open-box/")
    written += 1

    # Buying guides: tips + the top 10 deals of the last week in each category
    for n in niches:
        week = [d for d in by_niche[n.id] if _ts(d.get("created_at")) >= week_ago]
        top = sorted(week, key=value_score, reverse=True)[:10]
        _write(root, f"guides/{n.id}.html", guide_html(n, top))
        urls.append(f"/guides/{n.id}.html")
        written += 1
    _write(root, "guides/index.html", guides_index_html(niches))
    urls.append("/guides/")
    written += 1

    _write(root, "free-trials/index.html", free_trials_html())
    urls.append("/free-trials/")
    written += 1

    # Store pages: every store with deals, plus every store in our categories (so Google
    # always finds a page for "<store> coupon"), with intro text, Q&A and structured data.
    import seo
    from alerts import price_safe as _ps
    all_domains = set(stores)
    for n in niches:
        all_domains |= set(n.stores)
    base_url = (settings.public_base_url or "").rstrip("/")
    now_local = datetime.now()
    month = now_local.strftime("%B %Y")
    store_index = []
    for domain in sorted(all_domains):
        deals = stores.get(domain, [])
        name = seo.store_name(domain, deals[0]["store_name"] if deals else "")
        deals = sorted({d["deal_hash"]: d for d in deals}.values(),
                       key=lambda d: str(d["created_at"]), reverse=True)
        deals.sort(key=lambda d: not d.get("is_verified"))      # verified codes first
        safe = [_ps(d) for d in deals]
        s = seo.summary(domain, safe)
        qa = seo.faq(name, s)
        rel = f"/store/{slug(domain)}.html"
        page_url = base_url + rel if base_url else rel
        related = ""
        if not deals:
            niche_ids = [n.id for n in niches if domain in n.stores]
            pool = [d for nid in niche_ids for d in by_niche.get(nid, [])][:12]
            if pool:
                related = "<h2>Similar deals right now</h2>" + deal_grid(pool)
        body = (f"<h1>{e(name)} coupon codes &amp; promo codes</h1>"
                f"<p class='lead'>{e(seo.intro(name, s, now_local))}</p>"
                f"{filter_bar(len(deals)) if deals else ''}{deal_grid(deals) if deals else ''}"
                f"{related}{seo.faq_html(qa)}")
        head = (f'<link rel="canonical" href="{e(page_url, quote=True)}">'
                + seo.jsonld(name, page_url, (base_url + "/") if base_url else "/", safe, qa,
                             [go_link(d) for d in deals]))
        count = f"{s['codes']} codes" if s["codes"] else f"{s['deals']} deals"
        _write(root, f"store/{slug(domain)}.html",
               page(f"{name} Coupon Codes & Promo Codes ({month}) | {settings.site_name}", body,
                    f"{name} coupon codes and deals for {month}: {count}, updated every 30 "
                    f"minutes. Copy a working {name} promo code and save.", extra_head=head))
        urls.append(rel)
        store_index.append((name, rel, s["deals"]))
        written += 1
    links = "".join(f'<li><a href="{u(rel)}">{e(nm)} coupons</a>'
                    f'{f" <small>({cnt} live)</small>" if cnt else ""}</li>'
                    for nm, rel, cnt in sorted(store_index, key=lambda x: x[0].lower()))
    _write(root, "stores/index.html",
           page(f"All stores: coupon codes A to Z | {settings.site_name}",
                f"<h1>All stores A to Z</h1><p class='lead'>Coupon codes and deals for "
                f"{len(store_index)} stores, updated every 30 minutes.</p><ul class='stores'>{links}</ul>",
                "Coupon codes and promo codes for farm, tool, motorcycle, auto, electronics and "
                "telescope stores, A to Z."))
    urls.append("/stores/")
    written += 1

    # About / disclosure + privacy
    contact = (f'<p>Contact: <a href="mailto:{e(settings.site_contact_email)}">'
               f"{e(settings.site_contact_email)}</a></p>" if settings.site_contact_email else "")
    _write(root, "about.html", page(f"About & affiliate disclosure | {settings.site_name}",
        f"<h1>About &amp; affiliate disclosure</h1><p>{e(settings.site_name)} automatically "
        "collects public deals, coupon codes and freebies, and tests some codes at a real "
        "checkout before marking them verified.</p><p><b>Affiliate disclosure:</b> some links "
        "on this site and in our channels are affiliate links. If you buy through them we may "
        "earn a commission at no extra cost to you. This never changes which deals we list."
        f"</p><p>Prices and codes change fast. Always check the final price at checkout.</p>"
        f"{contact}"))
    _write(root, "privacy.html", page(f"Privacy policy | {settings.site_name}",
        "<h1>Privacy policy</h1><p>We don't use accounts, ads trackers or analytics cookies. "
        + ("We count visits with a privacy-friendly, cookie-free counter (no personal data). "
           if settings.cloudflare_analytics_token or settings.goatcounter_site else "")
        + "When you click a deal we count the click (which deal, which page or channel, and the "
        "time) to know which deals are popular. We don't store your IP address with that "
        "count.</p><p>Our server keeps standard technical logs for security, deleted "
        "regularly.</p><p>Your Watchlist is saved only in your own browser on your own "
        "device. We never see it.</p><h2>Deals by email</h2><p>If you sign up for deal emails we "
        "keep your email address and the answers you picked (deal types, Prime, audiobooks, how "
        "often) so we only send what you asked for. Our email service, Brevo, stores and sends "
        "them. Every email has a one-tap unsubscribe link. We never sell or share your email. "
        "Your picks are also saved in your own browser so the site can show your deals first.</p>"
        "<p>When you leave for a store through an affiliate link, that store "
        "and its affiliate network may set their own cookies under their own privacy "
        "policies.</p>"
        "<h2>Browser extension</h2><p>Our Deal Hunter browser extension looks at the web "
        "address of the tab you're on only to find that store's name (for example "
        "tractorsupply.com). It then downloads the public deal list for that store from this "
        "website. It never reads page content, passwords or forms, and it doesn't keep a "
        "history of the sites you visit. Your extension settings are saved in your own "
        "browser. We don't sell or share any data.</p>" + contact))
    written += 2
    urls += ["/about.html", "/privacy.html"]

    # Static deal files for the Chrome extension: api/deals/<domain>.json
    public_keys = ("deal_hash", "store_name", "store_domain", "promo_code", "discount_value",
                   "category", "expiration_date", "source_url", "affiliate_url", "is_verified",
                   "created_at")
    all_active = await db.niche_deals(None, hours=24 * 60, limit=5000)
    extra, _ = await db.query_deals(verified_only=False, limit=5000)
    by_domain: dict[str, dict[str, dict]] = {}
    for d in all_active + extra:
        by_domain.setdefault(d["store_domain"], {})[d["deal_hash"]] = d
    for domain, deals in by_domain.items():
        rows = sorted(deals.values(), key=lambda d: (not d.get("is_verified"), d["created_at"]))
        payload = {"domain": domain, "count": len(rows),
                   "deals": [{**{k: price_safe(d).get(k) for k in public_keys},
                             "extension_url": plain_url_for_extension(d)} for d in rows]}
        _write(root, f"api/deals/{slug(domain)}.json", json.dumps(payload))
        written += 1
    _write(root, "api/index.json", json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "domains": sorted(by_domain)}))
    written += 1

    unique_deals = {d["deal_hash"]: d for domain_deals in by_domain.values()
                    for d in domain_deals.values()}
    rss_deals = sorted(_visible(list(unique_deals.values())),
                       key=lambda d: d.get("created_at") or "", reverse=True)
    _write(root, "rss.xml", rss_xml(rss_deals))
    written += 1

    top_video_deals = sorted(rss_deals, key=value_score, reverse=True)
    _write(root, "scripts.html", tiktok_scripts_html(top_video_deals))
    written += 1

    base = settings.public_base_url
    bp = base_path()
    robots = f"User-agent: *\nAllow: /\nDisallow: {bp}/go/\nDisallow: {bp}/api/\nDisallow: {bp}/scripts.html\n"
    if base:
        robots += f"Sitemap: {base}/sitemap.xml\n"
        today = datetime.now(timezone.utc).date().isoformat()
        sm = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sm += [f"<url><loc>{e(base + url)}</loc><lastmod>{today}</lastmod></url>" for url in urls]
        sm.append("</urlset>")
        _write(root, "sitemap.xml", "\n".join(sm))
        written += 1
    _write(root, "robots.txt", robots)
    written += 1

    # Files to publish as-is, e.g. Google/Bing site-ownership files: static/<name> -> /<name>
    static = Path(__file__).resolve().parent / "static"
    if static.is_dir():
        for f in static.iterdir():
            if f.is_file() and not f.name.startswith("."):
                (root / f.name).write_bytes(f.read_bytes())
                written += 1
    log.info("Website rebuilt: %d files", written)
    return written
