"""Phase 19: anonymous single-recording highway schematic; no geolocation.
Run beside citytrack_video_geo.py and previous modules. Existing reports read-only.
"""
import argparse
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import urlopen
from urllib.error import HTTPError
import citytrack_video_geo as geo

base = geo.base
LINK = '<a href="/highway">Highway studio</a>'
NAV = geo.NAV.replace('</nav>', LINK + '</nav>')

def summary(data):
    counts = {}
    for t in data['tracks']:
        cat = t['category']
        row = counts.setdefault(cat, {'fragments': 0, 'samples': 0})
        row['fragments'] += 1
        row['samples'] += t['samples']
    return counts

PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CityTrack | Highway studio</title><style>
*{box-sizing:border-box}body{margin:0;background:#0d1420;color:#e2e8f0;font:14px system-ui,sans-serif}header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;padding:16px 24px;border-bottom:1px solid #29394e}h1{font-size:22px;margin:0}h2{font-size:16px;margin:0 0 10px}a{color:#52d9eb}small,p{color:#adbed1;line-height:1.5}main{max-width:1800px;margin:auto;padding:16px}.notice{background:#29251c;border:1px solid #8b6a37;border-radius:9px;color:#ffe2ad;padding:12px;margin-bottom:12px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}.panel,.stat{background:#132032;border:1px solid #293c51;border-radius:10px;padding:13px;min-width:0}.stat b{display:block;color:#52d9eb;font-size:25px;margin-top:4px}.layout{display:grid;grid-template-columns:minmax(220px,1fr) minmax(0,3.6fr);gap:12px}label{display:block;color:#b7c8da;margin:10px 0 5px}select,button,input::file-selector-button{font:inherit;background:#1a3045;color:#e2e8f0;border:1px solid #38546e;border-radius:6px;padding:8px}select{width:100%}button{cursor:pointer}button:disabled{opacity:.5}.controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:10px 0}input[type=range]{flex:1;min-width:90px;accent-color:#52d9eb}canvas{width:100%;height:auto;display:block;border-radius:7px;background:#0b1724}video{width:100%;max-height:420px;background:#06090e;border-radius:7px}video[hidden]{display:none}.count{display:flex;justify-content:space-between;border-bottom:1px solid #2c4055;padding:8px 0}.muted{color:#adbed1}.clock{font-variant-numeric:tabular-nums}hr{border:0;border-top:1px solid #293c51;margin:16px 0}input[type=file]{max-width:100%}@media(max-width:800px){.layout{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}
</style></head><body><header><div><h1>CityTrack / Highway studio</h1><small>Phase 19 · single recording · anonymous tracks</small></div>__NAV__</header><main>
<div class="notice"><b>FICTIONAL HIGHWAY SCHEMATIC — NOT A GEOGRAPHIC MAP.</b> Trails use original normalized image positions. The background is decorative, not measured road or lane geometry. No actual location, speed, lane assignment, plate number or identity is inferred.</div>
<div class="stats"><div class="stat">Recorded fragments<b id="total"></b></div><div class="stat">Recorded samples<b id="samples"></b></div><div class="stat">Matching filters<b id="matching"></b></div><div class="stat">Displayed now<b id="visible"></b></div></div>
<div class="layout"><aside class="panel"><h2>Display controls</h2><label for="category">Vehicle category</label><select id="category"><option value="all">All categories</option></select><label for="minimum">Minimum samples per fragment</label><select id="minimum"><option value="1">1 (all)</option><option value="10" selected>10</option><option value="20">20</option><option value="40">40</option></select><label for="track">Temporary track fragment</label><select id="track"><option value="all">All matching fragments</option></select><label for="trail">Trail history</label><select id="trail"><option value="2" selected>Last 2 seconds</option><option value="5">Last 5 seconds</option><option value="10">Last 10 seconds</option><option value="all">All elapsed samples</option></select><label for="background">Background</label><select id="background"><option value="road">Illustrative road schematic</option><option value="grid">Image coordinate grid</option></select><p id="details"></p><hr><h2>Category summary</h2><div id="counts"></div><small>Counts are track fragments, not unique vehicles.</small><hr><h2>Optional video preview</h2><small>Select the original local clip. Nothing is uploaded. Verify it is the same recording.</small><p><input type="file" id="file" accept="video/*,.webm,.mp4"></p><p id="vstatus" role="status"></p></aside>
<section class="panel"><h2>Highway movement · image coordinates</h2><canvas id="canvas" width="960" height="540" aria-label="Anonymous movement trails over an illustrative highway schematic"></canvas><div class="controls"><button id="play">Play</button><button id="reset">Reset</button><input id="time" type="range" min="0" step="0.01" aria-label="Elapsed recording time"><span class="clock" id="clock"></span></div><small>Trails break at gaps greater than 0.5 seconds. Recent trails reduce clutter; no missing positions are fabricated.</small><hr><h2>Original recording preview</h2><video id="clip" hidden controls preload="metadata" playsinline></video><p id="hint">Choose the local video to preview it alongside the schematic.</p></section></div><p>Read-only reuse of the saved Phase 16 report. Original database and earlier dashboard tabs remain available.</p></main>
<script>
const data=__DATA__, tracks=data.tracks, $=id=>document.getElementById(id), c=$('canvas'), ctx=c.getContext('2d'), W=c.width,H=c.height, clip=$('clip');
let chosen=[],playing=false,raf=0,last=null,ready=false,blob=null;
const color=t=>`hsl(${(t.id*137.508)%360} 85% 64%)`;
const total=tracks.reduce((a,t)=>a+t.samples,0);$('total').textContent=tracks.length.toLocaleString();$('samples').textContent=total.toLocaleString();$('time').max=data.duration;$('time').value=0;
for(const [cat,count] of Object.entries(data.counts).sort()){const o=new Option(cat,cat);$('category').add(o);const r=document.createElement('div');r.className='count';const a=document.createElement('span'),b=document.createElement('b');a.textContent=cat;b.textContent=count.fragments.toLocaleString();r.append(a,b);$('counts').append(r)}
function filters(){const cat=$('category').value,min=Number($('minimum').value),old=$('track').value;chosen=tracks.filter(t=>(cat==='all'||cat===t.category)&&t.samples>=min);$('track').replaceChildren(new Option('All matching fragments','all'));for(const t of chosen)$('track').add(new Option(`#${t.id} · ${t.category} · ${t.samples} samples`,String(t.id)));if(chosen.some(t=>String(t.id)===old))$('track').value=old;$('matching').textContent=chosen.length.toLocaleString();draw()}
function line(points,col,width,dash=[]){ctx.beginPath();for(let i=0;i<points.length;i++){let [x,y]=points[i];i?ctx.lineTo(x*W,y*H):ctx.moveTo(x*W,y*H)}ctx.strokeStyle=col;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.stroke();ctx.setLineDash([])}
function poly(points,col){ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x*W,y*H):ctx.moveTo(x*W,y*H));ctx.closePath();ctx.fillStyle=col;ctx.fill()}
function background(){ctx.fillStyle='#0b1724';ctx.fillRect(0,0,W,H);if($('background').value==='road'){poly([[0,.13],[1,.40],[1,.67],[0,.37]],'#334151');poly([[0,.34],[1,.68],[1,1],[.29,1],[0,.52]],'#334151');line([[0,.24],[1,.53]],'#9ca3af',2,[12,10]);line([[0,.43],[.65,.92],[.85,1]],'#9ca3af',2,[12,10]);line([[0,.36],[1,.68]],'#64748b',5);line([[0,.13],[1,.40]],'#aab6c4',2);line([[0,.52],[.29,1]],'#aab6c4',2)}else{for(let i=0;i<=10;i++){line([[i/10,0],[i/10,1]],'#26394d',1);line([[0,i/10],[1,i/10]],'#26394d',1)}}ctx.fillStyle='#d2dfec';ctx.font='15px system-ui';ctx.fillText($('background').value==='road'?'ILLUSTRATIVE ROAD BACKGROUND · IMAGE COORDINATES':'IMAGE COORDINATES · x → / y ↓',14,24)}
function draw(){const time=Number($('time').value),sel=$('track').value,windowSec=$('trail').value==='all'?Infinity:Number($('trail').value),start=time-windowSec;const list=sel==='all'?chosen:chosen.filter(t=>String(t.id)===sel);$('clock').textContent=time.toFixed(2)+' / '+data.duration.toFixed(1)+' s';background();let count=0;for(const t of list){let part=[],prev=null,lastPoint=null;const col=color(t);function flush(){if(part.length>1)line(part,col,sel==='all'?2:4);if(part.length===1){ctx.fillStyle=col;ctx.beginPath();ctx.arc(part[0][0]*W,part[0][1]*H,2,0,Math.PI*2);ctx.fill()}part=[]}for(const p of t.points){if(p[0]>time)break;if(p[0]<start)continue;if(prev!==null&&p[0]-prev>.5)flush();part.push([p[1],p[2]]);prev=p[0];lastPoint=p}flush();if(lastPoint){count++;if(time-lastPoint[0]<=.5){ctx.beginPath();ctx.fillStyle=col;ctx.arc(lastPoint[1]*W,lastPoint[2]*H,sel==='all'?4:6,0,Math.PI*2);ctx.fill();if(sel!=='all'){ctx.font='15px system-ui';ctx.fillText('#'+t.id,lastPoint[1]*W+8,lastPoint[2]*H-8)}}}}$('visible').textContent=count.toLocaleString();$('details').textContent=sel==='all'?'Showing '+list.length+' matching fragments.':list.length?`Fragment #${list[0].id} · ${list[0].start.toFixed(2)}–${list[0].end.toFixed(2)} s · ${list[0].samples} samples`:'No matching fragment'}
function stop(){playing=false;cancelAnimationFrame(raf);$('play').textContent='Play';if(ready&&!clip.paused)clip.pause()}
function tick(ts){if(!playing)return;if(last===null)last=ts;const t=ready?clip.currentTime:Number($('time').value)+(ts-last)/1000;last=ts;$('time').value=Math.min(data.duration,t);draw();if(t>=data.duration||ready&&clip.ended){stop();return}raf=requestAnimationFrame(tick)}
function start(){if(playing||!data.duration)return;if(Number($('time').value)>=data.duration)$('time').value=0;playing=true;last=null;$('play').textContent='Pause';if(ready){clip.currentTime=Number($('time').value);clip.play().catch(()=>{stop();$('vstatus').textContent='Video playback failed. Clear the file to use map-only playback.'})}raf=requestAnimationFrame(tick)}
$('play').onclick=()=>playing?stop():start();$('reset').onclick=()=>{stop();$('time').value=0;if(ready)clip.currentTime=0;draw()};$('time').oninput=()=>{if(ready)clip.currentTime=Math.min(clip.duration,Number($('time').value));draw()};$('category').onchange=filters;$('minimum').onchange=filters;$('trail').onchange=draw;$('background').onchange=draw;$('track').onchange=()=>{const t=chosen.find(t=>String(t.id)===$('track').value);if(t){stop();$('time').value=t.start;if(ready)clip.currentTime=t.start}draw()};
$('file').onchange=()=>{stop();ready=false;if(blob)URL.revokeObjectURL(blob);blob=null;clip.removeAttribute('src');clip.load();clip.hidden=true;$('hint').hidden=false;$('vstatus').textContent='';const f=$('file').files[0];if(!f)return;blob=URL.createObjectURL(f);clip.src=blob;clip.hidden=false;$('hint').hidden=true;$('vstatus').textContent='Loading local preview…'};
clip.onloadedmetadata=()=>{ready=Number.isFinite(clip.duration)&&Math.abs(clip.duration-data.duration)<=1;$('vstatus').textContent=ready?'Synchronized by elapsed time. Verify this is the original clip.':'Duration mismatch. Playback is independent.';if(ready)clip.currentTime=Math.min(clip.duration,Number($('time').value))};clip.onplay=()=>{if(ready&&!playing){playing=true;last=null;$('play').textContent='Pause';raf=requestAnimationFrame(tick)}};clip.onpause=()=>{if(ready&&playing)stop()};clip.onseeked=()=>{if(ready){$('time').value=Math.min(data.duration,clip.currentTime);draw()}};clip.onerror=()=>{if(!blob)return;ready=false;stop();$('vstatus').textContent='Browser cannot decode the file. Schematic playback remains available.'};filters();
</script></body></html>'''

def page(report):
    data = geo.load_data(report)
    data['counts'] = summary(data)
    data.pop('bounds', None)
    payload = json.dumps(data, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    return PAGE.replace('__NAV__', NAV, 1).replace('__DATA__', payload, 1)

class Handler(geo.Handler):
    def do_GET(self):
        if urlsplit(self.path).path == '/highway':
            try:
                body = page(self.server.video_report)
            except FileNotFoundError:
                return self.respond(base.unavailable('Saved report missing.'), base.HTML, 404)
            except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
                return self.respond(base.unavailable('Saved report invalid or unreadable.'), base.HTML, 422)
            return self.respond(body, base.HTML)
        return super().do_GET()

    def respond(self, body, content_type='application/json; charset=utf-8', code=200):
        if isinstance(body, str) and content_type.startswith('text/html') and 'href="/highway"' not in body:
            body = body.replace('</nav>', LINK + '</nav>', 1)
        return super().respond(body, content_type, code)

def make_server(db, port=8002, report=geo.REPORT):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path = db
    server.video_report = report
    return server

class HighwayTests(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(summary({'tracks':[{'category':'car','samples':3},{'category':'car','samples':4},{'category':'truck','samples':2}]}), {'car':{'fragments':2,'samples':7},'truck':{'fragments':1,'samples':2}})
    def test_empty(self):
        self.assertEqual(summary({'tracks':[]}), {})
    def test_page(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'report';base.video.export(out,[base.video.make_row(1,0,30,2,[1,2,20,30],.9,100,100)],1)
            report=out/'video_map.html';before=report.read_bytes();html=page(report)
            self.assertIn('FICTIONAL HIGHWAY SCHEMATIC',html);self.assertIn('"car":{"fragments":1,"samples":1}',html);self.assertNotIn('__DATA__',html);self.assertEqual(before,report.read_bytes())
    def test_http(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=root/'test.db';base.app.routes.initialize(db);out=root/'report';base.video.export(out,[],1);report=out/'video_map.html';before=report.read_bytes()
            with make_server(db,0,report) as server:
                th=threading.Thread(target=server.serve_forever,daemon=True);th.start();url='http://127.0.0.1:'+str(server.server_port)
                try:
                    for path in ('/','/analytics','/video','/video-map','/highway'):
                        with urlopen(url+path,timeout=5) as r:self.assertIn('href="/highway"',r.read().decode())
                    self.assertEqual(before,report.read_bytes());report.unlink()
                    with self.assertRaises(HTTPError) as err:urlopen(url+'/highway',timeout=5)
                    self.assertEqual(err.exception.code,404)
                finally:server.shutdown();th.join(5)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--test',action='store_true');p.add_argument('--port',type=int,default=8002);p.add_argument('--report',type=Path,default=geo.REPORT);a=p.parse_args()
    if a.test:
        l=unittest.defaultTestLoader;suite=unittest.TestSuite([l.loadTestsFromModule(base.app.routes),l.loadTestsFromModule(base.app.quality),l.loadTestsFromTestCase(base.studio.StudioTests),l.loadTestsFromTestCase(base.video.Tests),l.loadTestsFromTestCase(base.VideoTabTests),l.loadTestsFromTestCase(geo.GeoTests),l.loadTestsFromTestCase(HighwayTests)])
        return int(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())
    if not 1<=a.port<=65535:p.error('Invalid port')
    try:
        base.app.routes.activate_osm();base.app.routes.initialize();base.app.quality.analytics(base.app.routes.DB);server=make_server(base.app.routes.DB,a.port,a.report)
    except (OSError,ValueError,KeyError,TypeError) as exc:p.exit(1,f'Startup failed: {exc}\nCheck existing graph and stop any old server.\n')
    print(f'CityTrack Phase 19: http://127.0.0.1:{a.port}/highway\nVideo report: {a.report}\nIllustrative highway schematic; not GPS.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0
if __name__=='__main__':raise SystemExit(main())
