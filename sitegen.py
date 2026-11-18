"""Auto-generated public deals website (static HTML, rebuilt every run).

Pages: / (home), /<niche>/ (one per niche), /store/<domain>.html, /about.html,
/privacy.html, /rss.xml, /scripts.html (unlisted), /sitemap.xml, /robots.txt.
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

from affiliate import plain_url_for_extension
from alerts import CATEGORY_STYLE, DISCLOSURE, value_score
from config import settings
from niches import load_niches

log = logging.getLogger("sitegen")
e = html.escape

STORE_COLORS = {
    "homedepot.com": "#ea580c",
    "tractorsupply.com": "#991b1b",
    "ruralking.com": "#b91c1c",
    "harborfreight.com": "#dc2626",
    "northerntool.com": "#1e3a8a",
    "acmetools.com": "#b91c1c",
    "lowes.com": "#1e40af",
    "revzilla.com": "#18181b",
    "cyclegear.com": "#18181b",
    "motosport.com": "#0f172a",
    "amazon.com": "#0f172a",
    "bestbuy.com": "#1d4ed8",
    "walmart.com": "#1d4ed8",
    "target.com": "#dc2626",
    "newegg.com": "#1e3a8a",
    "ebay.com": "#0369a1",
}

CSS = """
:root{--bg:#f6f7fb;--card:#ffffff;--text:#0f172a;--muted:#64748b;--blue:#1d4ed8;
  --blue-soft:#eff6ff;--green:#059669;--green-soft:#ecfdf5;--amber:#d97706;
  --amber-soft:#fffbeb;--red:#dc2626;--border:#e2e8f0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:15px/1.5 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--blue)}
.wrap{max-width:1240px;margin:0 auto;padding:0 16px}
header.site-hdr{position:sticky;top:0;z-index:30;background:rgba(255,255,255,.95);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--border);box-shadow:0 1px 3px rgba(15,23,42,.04)}
.hdr-top{display:flex;align-items:center;gap:12px;padding:10px 0;flex-wrap:wrap}
.logo{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--text);shrink:0}
.logo-mark{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;
  justify-content:center;background:linear-gradient(135deg,#2563eb,#4338ca);color:#fff;
  font-size:18px;box-shadow:0 2px 6px rgba(37,99,235,.25)}
.logo-text{font-size:18px;font-weight:800;letter-spacing:-.02em;line-height:1.1}
.logo-sub{display:block;font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.06em;color:var(--muted)}
.hdr-search{flex:1;min-width:210px;display:flex;align-items:center;background:#f8fafc;
  border:1px solid #cbd5e1;border-radius:12px;overflow:hidden;height:42px}
.hdr-search:focus-within{background:#fff;border-color:var(--blue);box-shadow:0 0 0 3px rgba(29,78,216,.12)}
.hdr-search select{height:100%;border:0;border-right:1px solid var(--border);background:#f1f5f9;
  padding:0 10px;font-size:12px;font-weight:700;color:#334155;cursor:pointer;outline:none}
.hdr-search input{flex:1;height:100%;border:0;background:transparent;padding:0 12px;
  font-size:14px;color:var(--text);outline:none;min-width:0}
.hdr-actions{display:flex;align-items:center;gap:8px}
.btn-dark{display:inline-flex;align-items:center;gap:6px;height:40px;padding:0 14px;
  border-radius:11px;border:0;background:#0f172a;color:#fff;font-size:13px;font-weight:700;
  cursor:pointer;text-decoration:none}
.btn-dark:hover{background:#1e293b}
.badge-count{padding:1px 7px;border-radius:999px;background:#fbbf24;color:#0f172a;
  font-size:11px;font-weight:800}
.btn-emerald{display:inline-flex;align-items:center;gap:6px;height:40px;padding:0 14px;
  border-radius:11px;border:0;background:var(--green);color:#fff;font-size:13px;font-weight:700;
  text-decoration:none;cursor:pointer}
.btn-emerald:hover{background:#047857}
nav.cat-strip{display:flex;align-items:center;gap:8px;padding:9px 0;border-top:1px solid #f1f5f9;
  overflow-x:auto;scrollbar-width:none}
nav.cat-strip::-webkit-scrollbar{display:none}
nav.cat-strip a{display:inline-flex;align-items:center;gap:6px;padding:6px 13px;border-radius:999px;
  border:1px solid var(--border);background:#fff;color:#334155;font-size:12px;font-weight:700;
  text-decoration:none;white-space:nowrap;transition:all .15s}
nav.cat-strip a:hover{border-color:#94a3b8;background:#f8fafc}
nav.cat-strip a.active{background:#0f172a;color:#fff;border-color:#0f172a}
main.wrap{padding-top:20px;padding-bottom:36px}
.hero{background:linear-gradient(135deg,#eff6ff 0%,#eef2ff 55%,#fffbeb 100%);
  border:1px solid #bfdbfe;border-radius:18px;padding:20px 22px;margin-bottom:20px}
.hero-top{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:14px}
.live-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;
  background:#fff;border:1px solid #a7f3d0;color:#047857;font-size:11px;font-weight:800}
.pulse{width:7px;height:7px;border-radius:50%;background:#10b981;display:inline-block}
h1{font-size:24px;line-height:1.25;margin:10px 0 6px;font-weight:800;letter-spacing:-.02em}
h2{font-size:20px;margin:22px 0 12px;font-weight:800;letter-spacing:-.01em;
  display:flex;align-items:center;justify-content:space-between;gap:10px}
h2 a{color:var(--text);text-decoration:none}
h2 a:hover{color:var(--blue)}
.see-all{font-size:13px;font-weight:700;color:var(--blue)}
.lead{color:#475569;font-size:14px;margin:0 0 10px}
.dept-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:14px}
.dept-card{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;
  background:rgba(255,255,255,.92);border:1px solid var(--border);text-decoration:none;
  color:var(--text);transition:transform .15s,border-color .15s}
.dept-card:hover{transform:translateY(-2px);border-color:#93c5fd;background:#fff}
.dept-ico{width:34px;height:34px;border-radius:9px;background:var(--blue-soft);display:flex;
  align-items:center;justify-content:center;font-size:17px;flex-shrink:0}
.dept-name{display:block;font-size:12px;font-weight:800;line-height:1.2}
.dept-cnt{display:block;font-size:11px;font-weight:600;color:var(--muted)}
.layout{display:flex;gap:24px;align-items:flex-start}
.main-col{flex:1;min-width:0}
.side-col{width:310px;flex-shrink:0;display:flex;flex-direction:column;gap:16px;position:sticky;top:128px}
.widget{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:16px;
  box-shadow:0 1px 2px rgba(15,23,42,.03)}
.widget h3{margin:0 0 12px;font-size:12px;font-weight:800;text-transform:uppercase;
  letter-spacing:.05em;color:#0f172a}
.side-code{padding:10px;border-radius:12px;background:#f8fafc;border:1px solid var(--border);
  margin-bottom:8px}
.side-code:last-child{margin-bottom:0}
.side-code-top{display:flex;justify-content:space-between;align-items:center;gap:6px;font-size:12px;font-weight:800}
.side-code-desc{font-size:12px;color:#475569;margin:4px 0 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.side-code-row{display:flex;justify-content:space-between;align-items:center;gap:8px}
.chip-wrap{display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:5px 10px;border-radius:8px;border:1px solid var(--border);background:#f8fafc;
  color:#334155;font-size:12px;font-weight:700;cursor:pointer;text-decoration:none}
.chip:hover{background:#eff6ff;border-color:#93c5fd;color:var(--blue)}
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:#fff;
  border:1px solid var(--border);border-radius:14px;padding:10px 12px;margin:10px 0 16px}
.filter-bar input{flex:1 1 200px;font-size:14px;padding:8px 12px;border-radius:9px;
  border:1px solid #cbd5e1;background:#f8fafc;color:var(--text);outline:none}
.filter-bar input:focus{background:#fff;border-color:var(--blue)}
.filter-bar select{height:36px;padding:0 10px;border-radius:9px;border:1px solid var(--border);
  background:#f8fafc;font-size:12px;font-weight:700;color:#334155;cursor:pointer}
.pill{font-size:12px;font-weight:700;padding:7px 12px;border-radius:999px;cursor:pointer;
  border:1px solid var(--border);background:#fff;color:#475569}
.pill:hover{background:#f8fafc}
.pill.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.filter-count{color:var(--muted);font-size:12px;font-weight:700;margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px}
.grid.list-view{grid-template-columns:1fr}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:15px;
  display:flex;flex-direction:column;justify-content:space-between;gap:10px;
  transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}
.card:hover{transform:translateY(-2px);border-color:#cbd5e1;box-shadow:0 12px 24px -8px rgba(15,23,42,.08)}
.card.verified{border-color:#6ee7b7}
.card-top{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.store-badge{display:inline-block;padding:3px 8px;border-radius:6px;color:#fff;
  font-size:11px;font-weight:800;text-decoration:none}
.cat-tag{padding:3px 8px;border-radius:6px;background:#f1f5f9;color:#334155;font-size:11px;font-weight:800}
.cat-tag.err{background:#fef2f2;color:var(--red)}
.cat-tag.free{background:var(--green-soft);color:var(--green)}
.cat-tag.cash{background:var(--amber-soft);color:var(--amber)}
.badge{padding:3px 8px;border-radius:6px;background:var(--green-soft);color:var(--green);
  font-size:11px;font-weight:800;margin-left:auto}
.what{font-size:15px;font-weight:700;color:var(--text);line-height:1.35;cursor:pointer}
.what:hover{color:var(--blue)}
.value{font-size:21px;font-weight:800;color:#0f172a;letter-spacing:-.02em}
.code{display:flex;gap:8px;align-items:center}
.code code{flex:1;background:#f8fafc;border:1.5px dashed #93c5fd;border-radius:9px;
  padding:6px 10px;text-align:center;font:800 14px ui-monospace,Consolas,monospace;color:var(--blue)}
button.copy{background:var(--blue-soft);color:var(--blue);border:1px solid #bfdbfe;border-radius:9px;
  font-weight:800;padding:7px 12px;font-size:12px;cursor:pointer;white-space:nowrap}
button.copy:hover{background:#dbeafe}
.card-actions{display:flex;align-items:center;gap:8px;padding-top:8px;border-top:1px solid #f1f5f9}
.btn-save{padding:8px 11px;border-radius:9px;border:1px solid var(--border);background:#fff;
  color:#334155;font-size:12px;font-weight:700;cursor:pointer}
.btn-save.saved{background:var(--amber-soft);border-color:#fcd34d;color:#92400e}
.btn{flex:1;display:inline-flex;align-items:center;justify-content:center;font-weight:800;
  padding:9px 12px;border-radius:10px;text-decoration:none;background:var(--blue);color:#fff;
  font-size:13px}
.btn:hover{background:#1e40af}
.meta{color:var(--muted);font-size:12px}
.join-bar{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 4px}
.join-btn{display:inline-flex;align-items:center;gap:6px;background:#0f172a;color:#fff;
  font-weight:700;font-size:12px;padding:8px 13px;border-radius:10px;text-decoration:none}
.join-btn:hover{background:#1e293b}
.premium{display:inline-block;background:#fef3c7;color:#92400e;border:1px solid #fcd34d;
  font-weight:800;font-size:13px;padding:9px 14px;border-radius:10px;text-decoration:none;margin:4px 0 12px}
.empty{color:var(--muted);font-size:15px;background:#fff;border:1px solid var(--border);
  border-radius:14px;padding:24px;text-align:center}
footer.site-ftr{background:#fff;border-top:1px solid var(--border);margin-top:40px;padding:22px 0;
  color:var(--muted);font-size:13px}
.hidden{display:none!important}
.backdrop{position:fixed;inset:0;z-index:50;background:rgba(15,23,42,.55);
  backdrop-filter:blur(2px);display:flex;align-items:center;justify-content:center;padding:16px}
.backdrop.drawer-wrap{justify-content:flex-end;padding:0}
.modal{background:#fff;width:100%;max-width:560px;border-radius:18px;border:1px solid var(--border);
  box-shadow:0 24px 48px rgba(15,23,42,.22);overflow:hidden;max-height:90vh;display:flex;flex-direction:column}
.drawer{background:#fff;width:100%;max-width:410px;height:100%;border-left:1px solid var(--border);
  display:flex;flex-direction:column;box-shadow:-12px 0 36px rgba(15,23,42,.16)}
.m-head{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;
  border-bottom:1px solid var(--border);background:#f8fafc;font-weight:800;font-size:14px}
.m-body{padding:18px;overflow-y:auto;flex:1}
.m-foot{padding:14px 18px;border-top:1px solid var(--border);display:flex;gap:10px;align-items:center}
.x-btn{width:34px;height:34px;border-radius:9px;border:1px solid var(--border);background:#fff;
  cursor:pointer;font-size:16px;font-weight:700;color:#475569}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:60;
  background:#0f172a;color:#fff;padding:10px 16px;border-radius:11px;font-size:13px;font-weight:700;
  box-shadow:0 12px 24px rgba(15,23,42,.28)}
@media(max-width:960px){.layout{flex-direction:column}.side-col{width:100%;position:static}}
"""

COPY_JS = """<script>
(function(){
  var STORE_KEY='dealhunter_watch_v1';
  var saved=[];
  try{saved=JSON.parse(localStorage.getItem(STORE_KEY)||'[]');if(!Array.isArray(saved))saved=[];}catch(e){}
  function saveList(){try{localStorage.setItem(STORE_KEY,JSON.stringify(saved));}catch(e){}}
  function toast(msg){
    var t=document.getElementById('dh-toast');if(!t)return;
    t.textContent=msg;t.classList.remove('hidden');
    clearTimeout(t._tm);t._tm=setTimeout(function(){t.classList.add('hidden')},2200);
  }
  function syncSaveButtons(){
    var b=document.getElementById('wl-badge');
    if(b)b.textContent=String(saved.length);
    document.querySelectorAll('.btn-save').forEach(function(btn){
      var on=saved.some(function(x){return x.h===btn.dataset.hash});
      btn.classList.toggle('saved',on);
      btn.textContent=on?'Saved':'Save';
    });
  }
  function renderDrawer(){
    var box=document.getElementById('wl-items');if(!box)return;
    box.replaceChildren();
    if(!saved.length){
      var p=document.createElement('p');p.className='meta';
      p.textContent='No saved deals yet. Tap Save on any deal card to keep it here.';
      box.appendChild(p);return;
    }
    saved.forEach(function(item){
      var row=document.createElement('div');row.className='side-code';
      var top=document.createElement('div');top.className='side-code-top';
      var st=document.createElement('span');st.textContent=item.store;
      var rm=document.createElement('button');rm.type='button';rm.className='x-btn';
      rm.textContent='×';rm.style.width='26px';rm.style.height='26px';
      rm.addEventListener('click',function(){
        saved=saved.filter(function(x){return x.h!==item.h});
        saveList();syncSaveButtons();renderDrawer();toast('Removed from Watchlist');
      });
      top.append(st,rm);
      var ttl=document.createElement('div');ttl.className='side-code-desc';
      ttl.style.whiteSpace='normal';ttl.textContent=(item.summary||item.val)+' ('+item.val+')';
      var go=document.createElement('a');go.href=item.url;go.textContent='Open deal →';
      go.style.fontSize='12px';go.style.fontWeight='700';go.rel='nofollow sponsored';
      row.append(top,ttl,go);box.appendChild(row);
    });
  }
  function openModal(card){
    var m=document.getElementById('dh-modal');if(!m)return;
    document.getElementById('m-store').textContent=card.dataset.storename+' · '+card.dataset.catlabel;
    document.getElementById('m-title').textContent=card.dataset.summary||card.dataset.storename+' Deal';
    document.getElementById('m-val').textContent=card.dataset.val;
    var cw=document.getElementById('m-code-wrap');
    if(card.dataset.code){
      cw.classList.remove('hidden');
      document.getElementById('m-code').textContent=card.dataset.code;
      document.getElementById('m-copy').dataset.code=card.dataset.code;
    }else{cw.classList.add('hidden');}
    document.getElementById('m-meta').textContent=card.dataset.meta||'';
    document.getElementById('m-go').href=card.dataset.url;
    m.classList.remove('hidden');
  }
  function applyFilters(){
    var bar=document.querySelector('.filter-bar');
    var hdr=document.getElementById('hdr-search');
    var q=((bar&&bar.querySelector('input')?bar.querySelector('input').value:'')||(hdr?hdr.value:'')).trim().toLowerCase();
    var active=bar?bar.querySelector('.pill.active'):null;
    var mode=active?active.dataset.filter:'ALL';
    var stSel=document.getElementById('store-filter');
    var st=stSel?stSel.value:'';
    var n=0;
    document.querySelectorAll('.grid .card').forEach(function(c){
      var okCat=(mode==='ALL'||(mode==='VERIFIED'?c.dataset.verified==='1':(mode==='HAS_CODE'?!!c.dataset.code:c.dataset.cat===mode)));
      var okSt=!st||c.dataset.store===st;
      var okQ=!q||(c.dataset.text||'').indexOf(q)>-1;
      var show=okCat&&okSt&&okQ;
      c.style.display=show?'':'none';
      if(show)n++;
    });
    var cnt=bar?bar.querySelector('.filter-count'):null;
    if(cnt)cnt.textContent=n+' shown';
  }
  document.addEventListener('click',function(ev){
    var b=ev.target.closest('button.copy');
    if(b){
      if(navigator.clipboard)navigator.clipboard.writeText(b.dataset.code||'').catch(function(){});
      var prev=b.textContent;b.textContent='Copied!';toast('Copied "'+(b.dataset.code||'')+'"');
      setTimeout(function(){b.textContent=prev==='Copied!'?'Copy':prev},1500);return;
    }
    var sv=ev.target.closest('.btn-save');
    if(sv){
      var h=sv.dataset.hash;
      var idx=saved.findIndex(function(x){return x.h===h});
      if(idx>-1){saved.splice(idx,1);toast('Removed from Watchlist');}
      else{saved.unshift({h:h,store:sv.dataset.store,summary:sv.dataset.summary,val:sv.dataset.val,url:sv.dataset.url});toast('Saved to Watchlist');}
      saveList();syncSaveButtons();renderDrawer();return;
    }
    var pill=ev.target.closest('.filter-bar .pill');
    if(pill){
      document.querySelectorAll('.filter-bar .pill').forEach(function(x){x.classList.remove('active')});
      pill.classList.add('active');applyFilters();return;
    }
    var stChip=ev.target.closest('[data-pick-store]');
    if(stChip){
      var sel=document.getElementById('store-filter');
      if(sel){sel.value=sel.value===stChip.dataset.pickStore?'':stChip.dataset.pickStore;applyFilters();}
      return;
    }
    var what=ev.target.closest('.card .what');
    if(what){openModal(what.closest('.card'));return;}
    if(ev.target.id==='wl-open'||ev.target.closest('#wl-open')){
      renderDrawer();document.getElementById('dh-drawer').classList.remove('hidden');return;
    }
    if(ev.target.id==='wl-close'||ev.target.id==='dh-drawer'){
      document.getElementById('dh-drawer').classList.add('hidden');return;
    }
    if(ev.target.id==='m-close'||ev.target.id==='dh-modal'){
      document.getElementById('dh-modal').classList.add('hidden');return;
    }
    var vb=ev.target.closest('[data-view]');
    if(vb){
      var g=document.querySelector('.grid');
      if(g)g.classList.toggle('list-view',vb.dataset.view==='list');
    }
  });
  var barInp=document.querySelector('.filter-bar input');
  var hdrInp=document.getElementById('hdr-search');
  if(barInp)barInp.addEventListener('input',function(){if(hdrInp)hdrInp.value=barInp.value;applyFilters();});
  if(hdrInp)hdrInp.addEventListener('input',function(){
    if(barInp){barInp.value=hdrInp.value;applyFilters();}
    else{
      var q=hdrInp.value.trim().toLowerCase();
      document.querySelectorAll('.grid .card').forEach(function(c){
        c.style.display=(!q||(c.dataset.text||'').indexOf(q)>-1)?'':'none';
      });
    }
  });
  var stSel=document.getElementById('store-filter');
  if(stSel)stSel.addEventListener('change',applyFilters);
  document.addEventListener('keydown',function(ev){
    if(ev.key==='/'&&document.activeElement.tagName!=='INPUT'){
      var tgt=barInp||hdrInp;if(tgt){ev.preventDefault();tgt.focus();}
    }else if(ev.key==='Escape'){
      var m=document.getElementById('dh-modal');if(m)m.classList.add('hidden');
      var d=document.getElementById('dh-drawer');if(d)d.classList.add('hidden');
    }
  });
  syncSaveButtons();
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


def go_link(deal: dict) -> str:
    if settings.click_tracking:
        return u(f"/go/{deal['deal_hash'][:12]}?c=web")
    return deal.get("affiliate_url") or f"https://{deal['store_domain']}"


def _store_color(domain: str) -> str:
    d = (domain or "").lower()
    for k, col in STORE_COLORS.items():
        if d == k or d.endswith("." + k):
            return col
    return "#334155"


def card(deal: dict) -> str:
    label, _ = CATEGORY_STYLE.get(deal["category"], ("DEAL", 0))
    cat = str(deal["category"])
    cat_cls = " err" if cat == "PRICE_ERROR" else (" free" if cat == "FREEBIE" else (" cash" if cat == "CASHBACK_BONUS" else ""))
    verified = deal.get("is_verified")
    search_text = " ".join(str(deal.get(k) or "") for k in
                           ("store_name", "store_domain", "summary", "discount_value",
                            "promo_code")).lower()
    link = go_link(deal)
    meta_parts = []
    if deal.get("expiration_date"):
        meta_parts.append(f"Ends {deal['expiration_date']}")
    if deal.get("source"):
        meta_parts.append(f"via {deal['source']}")
    meta_txt = " · ".join(meta_parts)

    parts = [
        f'<div class="card{" verified" if verified else ""}" '
        f'data-cat="{e(cat, quote=True)}" '
        f'data-catlabel="{e(label, quote=True)}" '
        f'data-store="{e(deal["store_domain"], quote=True)}" '
        f'data-storename="{e(deal["store_name"], quote=True)}" '
        f'data-summary="{e(deal.get("summary") or "", quote=True)}" '
        f'data-val="{e(deal["discount_value"], quote=True)}" '
        f'data-code="{e(deal.get("promo_code") or "", quote=True)}" '
        f'data-url="{e(link, quote=True)}" '
        f'data-meta="{e(meta_txt, quote=True)}" '
        f'data-verified="{1 if verified else 0}" data-text="{e(search_text, quote=True)}">',
        '<div class="card-top">'
        f'<a class="store-badge" style="background:{_store_color(deal["store_domain"])}" '
        f'href="{u("/store/" + slug(deal["store_domain"]) + ".html")}">{e(deal["store_name"])}</a>'
        f'<span class="cat-tag{cat_cls}">{e(label)}</span>'
        + ('<span class="badge">✔ VERIFIED</span>' if verified else "")
        + '</div>',
    ]
    if deal.get("summary"):
        parts.append(f'<div class="what" title="Click for deal details">{e(deal["summary"])}</div>')
    parts.append(f'<div class="value">{e(deal["discount_value"])}</div>')
    if deal.get("promo_code"):
        parts.append(
            f'<div class="code"><code>{e(deal["promo_code"])}</code>'
            f'<button type="button" class="copy" data-code="{e(deal["promo_code"], quote=True)}">Copy</button></div>'
        )
    if deal.get("expiration_date"):
        parts.append(f'<div class="meta">Ends {e(str(deal["expiration_date"]))}</div>')
    parts.append(
        '<div class="card-actions">'
        f'<button type="button" class="btn-save" data-hash="{e(deal["deal_hash"], quote=True)}" '
        f'data-store="{e(deal["store_name"], quote=True)}" '
        f'data-summary="{e(deal.get("summary") or "", quote=True)}" '
        f'data-val="{e(deal["discount_value"], quote=True)}" '
        f'data-url="{e(link, quote=True)}">Save</button>'
        f'<a class="btn" href="{e(link, quote=True)}" rel="nofollow sponsored">Get this deal →</a>'
        '</div></div>'
    )
    return "".join(parts)


def page(title: str, body: str, description: str = "", extra_head: str = "",
         active_niche: str = "") -> str:
    niches = load_niches()
    nav = f'<a href="{u("/")}" class="{"active" if not active_niche else ""}">All Deals</a>'
    nav += "".join(
        f'<a href="{u("/" + n.id + "/")}" class="{"active" if active_niche == n.id else ""}">'
        f'{e(n.emoji)} {e(n.name)}</a>'
        for n in niches
    )
    dept_opts = '<option value="">All Categories</option>' + "".join(
        f'<option value="{u("/" + n.id + "/")}">{e(n.name)}</option>' for n in niches
    )
    first_tg = next((n.telegram_chat("free") for n in niches if n.telegram_chat("free").startswith("@")), "")
    alerts_btn = (
        f'<a class="btn-emerald" href="https://t.me/{e(first_tg[1:], quote=True)}" '
        f'target="_blank" rel="noopener">Free Alerts</a>'
        if first_tg else ""
    )
    year = datetime.now().year
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description or title, quote=True)}">{extra_head}
<link rel="alternate" type="application/rss+xml" title="{e(settings.site_name)} RSS" href="{u('/rss.xml')}">
<style>{CSS}</style>{analytics_html()}</head><body>
<header class="site-hdr"><div class="wrap">
  <div class="hdr-top">
    <a class="logo" href="{u("/")}">
      <span class="logo-mark">🏷️</span>
      <span><span class="logo-text">{e(settings.site_name)}</span>
      <span class="logo-sub">Verified Deals &amp; Promo Codes</span></span>
    </a>
    <div class="hdr-search">
      <select aria-label="Jump to category" onchange="if(this.value)location.href=this.value">{dept_opts}</select>
      <input id="hdr-search" type="search" placeholder="Search stores, items, or promo codes (press /)..." aria-label="Search deals">
    </div>
    <div class="hdr-actions">
      {alerts_btn}
      <button type="button" id="wl-open" class="btn-dark">Watchlist <span id="wl-badge" class="badge-count">0</span></button>
    </div>
  </div>
  <nav class="cat-strip" aria-label="Categories">{nav}</nav>
</div></header>
<main class="wrap">{body}</main>
<footer class="site-ftr"><div class="wrap">{e(DISCLOSURE)} ·
<a href="{u("/about.html")}">About &amp; disclosure</a> · <a href="{u("/privacy.html")}">Privacy</a> · <a href="{u("/rss.xml")}">RSS feed</a>
<br>© {year} {e(settings.site_name)}. Deals change fast; check the price before you buy.
</div></footer>
<div id="dh-modal" class="backdrop hidden">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
    <div class="m-head"><span id="m-store">Deal Details</span><button type="button" id="m-close" class="x-btn" aria-label="Close">×</button></div>
    <div class="m-body">
      <h2 id="m-title" style="margin-top:0"></h2>
      <div id="m-val" class="value" style="margin:8px 0 12px"></div>
      <div id="m-code-wrap" class="code hidden" style="margin:12px 0"><code id="m-code"></code><button type="button" id="m-copy" class="copy">Copy Code</button></div>
      <p id="m-meta" class="meta"></p>
    </div>
    <div class="m-foot"><a id="m-go" class="btn" href="#" rel="nofollow sponsored">Go to Store →</a></div>
  </div>
</div>
<div id="dh-drawer" class="backdrop drawer-wrap hidden">
  <div class="drawer" role="dialog" aria-modal="true" aria-label="Saved Watchlist">
    <div class="m-head"><span>Saved Watchlist</span><button type="button" id="wl-close" class="x-btn" aria-label="Close">×</button></div>
    <div id="wl-items" class="m-body"></div>
  </div>
</div>
<div id="dh-toast" class="toast hidden" role="status" aria-live="polite"></div>
{COPY_JS}</body></html>"""


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
    """Join buttons for PUBLIC channels only (@name). Webhook links are never shown."""
    links = []
    for n in niches:
        tg = n.telegram_chat("free")
        if tg.startswith("@"):
            links.append(f'<a class="join-btn" href="https://t.me/{e(tg[1:], quote=True)}" '
                         f'target="_blank" rel="noopener">Join {e(n.emoji)} {e(n.name)} '
                         "on Telegram</a>")
    if settings.discord_invite_url.startswith(("https://discord.gg/", "https://discord.com/invite/")):
        links.append(f'<a class="join-btn" href="{e(settings.discord_invite_url, quote=True)}" '
                     'target="_blank" rel="noopener">Join our Discord</a>')
    return '<div class="join-bar">' + "".join(links) + "</div>" if links else ""


def filter_bar(count: int, stores: list[tuple[str, str]] | None = None) -> str:
    if count < 2:
        return ""
    pills = [("ALL", "All"), ("PRICE_ERROR", "Price errors"), ("COUPON", "Coupons"),
             ("FREEBIE", "Freebies"), ("CASHBACK_BONUS", "Cash bonuses"),
             ("HAS_CODE", "With Code"), ("VERIFIED", "Verified")]
    buttons = "".join(f'<button type="button" class="pill{" active" if k == "ALL" else ""}" '
                      f'data-filter="{k}">{label}</button>' for k, label in pills)
    store_sel = ""
    if stores:
        opts = "".join(f'<option value="{e(dom, quote=True)}">{e(name)}</option>' for dom, name in stores)
        store_sel = f'<select id="store-filter" aria-label="Filter by store"><option value="">All Stores</option>{opts}</select>'
    view_btns = ('<button type="button" class="pill" data-view="grid" title="Grid view">Grid</button>'
                 '<button type="button" class="pill" data-view="list" title="List view">List</button>')
    return ('<div class="filter-bar"><input type="search" placeholder="Filter store, item or code"'
            f' aria-label="Search deals">{buttons}{store_sel}{view_btns}'
            f'<span class="filter-count">{count} shown</span></div>')


def _sidebar(deals: list[dict], niches: list) -> str:
    code_deals = [d for d in deals if d.get("promo_code")][:4]
    code_html = "".join(
        f'<div class="side-code"><div class="side-code-top"><span>{e(d["store_name"])}</span>'
        f'<span style="color:var(--green)">{e(d["discount_value"])}</span></div>'
        f'<div class="side-code-desc">{e(d.get("summary") or d["store_name"])}</div>'
        f'<div class="side-code-row"><code>{e(d["promo_code"])}</code>'
        f'<button type="button" class="copy" data-code="{e(d["promo_code"], quote=True)}">Copy</button>'
        '</div></div>'
        for d in code_deals
    ) or '<p class="meta" style="margin:0">Active promo codes appear here automatically.</p>'

    store_counts: dict[str, tuple[str, int]] = {}
    for d in deals:
        dom = d["store_domain"]
        name, cnt = store_counts.get(dom, (d["store_name"], 0))
        store_counts[dom] = (name, cnt + 1)
    top_stores = sorted(store_counts.items(), key=lambda x: (-x[1][1], x[1][0]))[:14]
    store_chips = "".join(
        f'<a class="chip" href="{u("/store/" + slug(dom) + ".html")}">{e(name)} ({cnt})</a>'
        for dom, (name, cnt) in top_stores
    ) or '<span class="meta">No stores yet.</span>'

    alerts_box = join_banner(niches) + "".join(premium_button(n) for n in niches if n.premium_url)
    alerts_card = (f'<div class="widget"><h3>Free &amp; Instant Alerts</h3>{alerts_box}</div>'
                   if alerts_box else "")

    return (
        '<aside class="side-col">'
        f'<div class="widget"><h3>Top Promo Codes</h3>{code_html}</div>'
        f'<div class="widget"><h3>Browse by Store</h3><div class="chip-wrap">{store_chips}</div></div>'
        f'{alerts_card}'
        '</aside>'
    )


def deal_grid(deals: list[dict]) -> str:
    if not deals:
        return '<p class="empty">No active deals right now. New ones are added every hour.</p>'
    return '<div class="grid">' + "".join(card(d) for d in deals) + "</div>"


def premium_button(niche) -> str:
    if not niche.premium_url:
        return ""
    return (f'<a class="premium" href="{e(niche.premium_url, quote=True)}">'
            f"⭐ Get {e(niche.name)} instantly + price errors</a>")


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
        if link.startswith("/"):
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
        item = d.get("summary") or f"{d['store_name']} deal"
        disc = d["discount_value"]
        code_line = f" Use code {d['promo_code']} at checkout." if d.get("promo_code") else ""
        hook = f"{d['store_name']}: {disc} on {item}"
        spoken = (f"Heads up if you've been eyeing {item} — {d['store_name']} currently has it "
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
        caption = f"{hook} - {d.get('promo_code') or 'Link in bio / Telegram'} {tags}"
        full_copy = f"HOOK (on screen):\n{hook}\n\nSAY THIS:\n{spoken}\n\nCAPTION:\n{caption}"
        cards.append(
            f'<div class="card">'
            f'<div class="meta" style="font-weight:800">{e(d["store_name"])} · {e(disc)}</div>'
            f'<p style="margin:6px 0"><b>On-screen hook:</b> {e(hook)}</p>'
            f'<p style="margin:6px 0"><b>15-sec script:</b> {e(spoken)}</p>'
            f'<p class="meta"><b>Caption:</b> {e(caption)}</p>'
            f'<button type="button" class="copy" style="padding:10px 14px;margin-top:8px" '
            f'data-code="{e(full_copy, quote=True)}">Copy script &amp; caption</button>'
            f'<a class="btn" style="margin-top:8px" href="{e(go_link(d), quote=True)}" rel="nofollow sponsored">Open deal →</a>'
            f'</div>'
        )
    grid = '<div class="grid">' + "".join(cards) + "</div>" if cards else '<p class="empty">No deals yet.</p>'
    body = ("<h1>Short-video deal scripts</h1>"
            "<p class='lead'>Ready-to-record 15-second scripts for TikTok, YouTube Shorts, and Reels.</p>"
            + grid)
    return page(f"Video scripts | {settings.site_name}", body,
                "Short-video deal scripts",
                extra_head='<meta name="robots" content="noindex,nofollow">')


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


async def build_site(db, out_dir: str | None = None) -> int:
    """Regenerate every page. Returns the number of files written."""
    root = Path(out_dir or settings.site_dir)
    root.mkdir(parents=True, exist_ok=True)
    niches = load_niches()
    written = 0
    urls = ["/"]

    # Home
    sections = []
    dept_cards = []
    home_pool: dict[str, dict] = {}
    for n in niches:
        all_niche_deals = _visible(await db.niche_deals(n.id, hours=24 * 3, limit=200))
        for d in all_niche_deals:
            home_pool[d["deal_hash"]] = d
        deals = sorted(all_niche_deals, key=value_score, reverse=True)[:6]
        dept_cards.append(
            f'<a class="dept-card" href="{u("/" + n.id + "/")}">'
            f'<span class="dept-ico">{e(n.emoji)}</span>'
            f'<span><span class="dept-name">{e(n.name)}</span>'
            f'<span class="dept-cnt">{len(all_niche_deals)} active</span></span></a>'
        )
        sections.append(
            f'<h2><span>{e(n.emoji)} <a href="{u("/" + n.id + "/")}">{e(n.name)}</a></span>'
            f'<a class="see-all" href="{u("/" + n.id + "/")}">View all →</a></h2>'
            f"{premium_button(n)}{deal_grid(deals)}"
        )

    hero = (
        '<section class="hero"><div class="hero-top"><div>'
        f'<span class="live-pill"><span class="pulse"></span> Updated Automatically · {len(home_pool)} Active Deals</span>'
        "<h1>Verified deals, promo codes &amp; price drops.</h1>"
        "<p class='lead'>Scanned automatically across Farm, Moto, Tools, Auto, Electronics &amp; Home—click any card to copy codes or save to your Watchlist.</p>"
        f"{join_banner(niches)}"
        "</div></div>"
        f'<div class="dept-grid">{"".join(dept_cards)}</div>'
        "</section>"
    )
    home_layout = (
        f'{hero}<div class="layout"><div class="main-col">{"".join(sections)}</div>'
        f'{_sidebar(list(home_pool.values()), niches)}</div>'
    )
    _write(root, "index.html", page(f"{settings.site_name}: today's best deals", home_layout))
    written += 1

    # Niche pages + collect stores
    stores: dict[str, list[dict]] = {}
    for n in niches:
        deals = _visible(await db.niche_deals(n.id, hours=24 * 30, limit=500))
        for d in deals:
            stores.setdefault(d["store_domain"], []).append(d)
        recent = sorted(deals, key=lambda d: d["created_at"], reverse=True)[:120]
        niche_stores = sorted({d["store_domain"]: d["store_name"] for d in recent}.items(),
                              key=lambda x: x[1].lower())
        body = (
            f"<h1>{e(n.emoji)} {e(n.name)}</h1><p class='lead'>Updated "
            f"{datetime.now().strftime('%B %d, %Y')}.</p>{join_banner([n])}{premium_button(n)}"
            f'<div class="layout"><div class="main-col">'
            f"{filter_bar(len(recent), niche_stores)}{deal_grid(recent)}</div>"
            f"{_sidebar(recent, [n])}</div>"
        )
        _write(root, f"{n.id}/index.html", page(f"{n.name} | {settings.site_name}", body,
                                                f"Latest {n.name.lower()}: coupon codes, "
                                                f"sales and freebies.", active_niche=n.id))
        urls.append(f"/{n.id}/")
        written += 1

    # Store pages
    for domain, deals in stores.items():
        name = deals[0]["store_name"]
        deals = sorted({d["deal_hash"]: d for d in deals}.values(),
                       key=lambda d: (not d.get("is_verified"), d["created_at"]))
        month = datetime.now().strftime("%B %Y")
        body = (f"<h1>{e(name)} coupon codes &amp; deals</h1>"
                f"<p class='lead'>Active {e(name)} promo codes and sales for {month}.</p>"
                f"{filter_bar(len(deals))}{deal_grid(deals)}")
        _write(root, f"store/{slug(domain)}.html",
               page(f"{name} coupon codes & deals ({month}) | {settings.site_name}", body,
                    f"Working {name} promo codes and deals for {month}."))
        urls.append(f"/store/{slug(domain)}.html")
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
        "regularly.</p><p>When you leave for a store through an affiliate link, that store "
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
                   "deals": [{**{k: d.get(k) for k in public_keys},
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
