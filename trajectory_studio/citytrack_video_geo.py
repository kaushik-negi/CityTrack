"""Phase 18: illustrative geographic display of anonymous single-clip trajectories.
No geographic inference or vehicle identification. Uses saved Phase 16 report read-only.
"""
import argparse
import json
import math
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import citytrack_video_studio as base

ROOT = Path(__file__).resolve().parent
REPORT = base.REPORT
LINK = '<a href="/video-map" style="color:#49d9ea;padding:9px 13px;border:1px solid #315161;border-radius:7px;text-decoration:none">Video map (demo)</a>'
NAV = base.VIDEO_NAV.replace('</nav>', LINK + '</nav>')

# Fixed arbitrary display rectangle, not derived from footage or camera location.
BOUNDS = (28.615, 77.190, 28.625, 77.210)  # south, west, north, east

def project(x, y):
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in (x,y)):
        raise ValueError('Invalid normalized point')
    s,w,n,e = BOUNDS
    return [n-y*(n-s), w+x*(e-w)]


def load_data(report):
    with Path(report).open(encoding='utf-8') as f:
        raw = f.read(32_000_001)
    if len(raw)>32_000_000: raise ValueError('Report too large')
    _, marker, rest = raw.partition('const data=')
    if not marker: raise ValueError('Missing video data')
    data, _ = json.JSONDecoder().raw_decode(rest.lstrip())
    if not isinstance(data,dict) or not isinstance(data.get('tracks'),list): raise ValueError('Invalid report')
    d=data.get('duration')
    if not isinstance(d,(int,float)) or not math.isfinite(d) or not 0<=d<=120: raise ValueError('Invalid duration')
    tracks=[]; seen=set(); count=0
    for t in data['tracks']:
        tid=t['id']; cat=t['category']; pts=t['points']
        if type(tid) is not int or tid<1 or tid in seen or cat not in base.video.CLASSES.values() or not isinstance(pts,list) or not pts: raise ValueError('Invalid track')
        seen.add(tid); count+=len(pts)
        if count>200000: raise ValueError('Too many samples')
        last=-1; clean=[]
        for p in pts:
            ts,x,y=p
            if not isinstance(ts,(int,float)) or not math.isfinite(ts) or not 0<=ts<=d or ts<last: raise ValueError('Invalid timestamp')
            project(x,y); clean.append([ts,x,y]); last=ts
        tracks.append({'id':tid,'category':cat,'points':clean,'samples':len(clean),'start':clean[0][0],'end':clean[-1][0]})
    return {'duration':d,'tracks':tracks,'bounds':BOUNDS}

PAGE=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CityTrack | Video map demo</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0d1420;color:#e2e8f0;font:14px system-ui,sans-serif}header{padding:16px 24px;border-bottom:1px solid #26394d;display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 12px}a{color:#49d9ea}main{max-width:1550px;margin:auto;padding:20px}.notice{border:1px solid #9e7840;background:#29251c;color:#ffe0a9;border-radius:8px;padding:12px;margin-bottom:14px;line-height:1.5}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}.card,section{background:#132032;border:1px solid #26394d;border-radius:10px;padding:13px}.card strong{display:block;color:#49d9ea;font-size:22px;margin-top:4px}.layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(245px,1fr);gap:12px}.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}button,select,input::file-selector-button{background:#1d3248;color:#e2e8f0;border:1px solid #39536e;border-radius:6px;padding:9px;font:inherit}button{cursor:pointer}button:disabled{opacity:.5}select{max-width:100%}input[type=range]{flex:1;min-width:80px;accent-color:#49d9ea}small,p{color:#b3c3d5;line-height:1.5}#canvas{display:block;width:100%;height:auto;background:#0b1929;border-radius:7px}#geo{height:clamp(350px,58vh,650px);background:#162437;border-radius:7px}#geo[hidden],#canvas[hidden]{display:none}.tag{font-size:12px;font-weight:700;color:#ffe0a9}.list{max-height:260px;overflow:auto}table{border-collapse:collapse;width:100%;text-align:left}td,th{padding:8px;border-bottom:1px solid #293c52}video{width:100%;max-height:220px;background:#060a10;margin-top:10px}#clock{font-variant-numeric:tabular-nums}.leaflet-container{font-family:system-ui,sans-serif}.leaflet-tooltip{font-size:12px}@media(max-width:850px){.layout{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr}}
</style></head><body><header><div><h1>CityTrack / Video map</h1><small>Single recording · simulated placement only</small></div>__NAV__</header><main>
<div class="notice"><b>SIMULATED GEOGRAPHIC PLACEMENT — NOT GPS.</b> The video location is unknown. An arbitrary fixed rectangle near Delhi is used only to illustrate map display. The trails are derived from image coordinates, not calibrated positions, and may cross buildings or roads. Do not use them for geographic distance, speed, navigation or identification.</div>
<div class="kpis"><div class="card">Track fragments<strong id="n"></strong></div><div class="card">Movement samples<strong id="samples"></strong></div><div class="card">Video duration<strong id="duration"></strong></div><div class="card">Placement<strong>Simulated</strong></div></div>
<div class="layout"><section><h2>Movement visualization</h2><div class="controls"><button id="enable">Enable OpenStreetMap</button><button id="fit" hidden>Fit demo area</button><span id="status" role="status">Offline image-coordinate view</span></div><canvas id="canvas" width="960" height="540" aria-label="Camera-coordinate movement trails"></canvas><div id="geo" hidden aria-label="Illustrative map placement"></div><div class="controls"><button id="play">Play</button><button id="reset">Reset</button><input type="range" id="time" min="0" step="0.01" aria-label="Recording time"><span id="clock"></span></div><small>Paths are not connected across gaps longer than 0.5 seconds. The timeline uses elapsed recording time, not capture date or real GPS time.</small></section>
<section><h2>Track selection</h2><label for="track">Anonymous track fragment</label><div class="controls"><select id="track"><option value="all">All fragments</option></select></div><p id="details"></p><h2>Recorded fragments</h2><div class="list"><table><thead><tr><th>ID</th><th>Category</th><th>Samples</th></tr></thead><tbody id="rows"></tbody></table></div><h2 style="margin-top:18px">Optional video preview</h2><small>Choose the same local recording to synchronize playback. File stays in your browser; no upload.</small><p><input id="file" type="file" accept="video/*,.webm,.mp4" aria-label="Select original local video"></p><video id="clip" controls hidden preload="metadata"></video><p id="vstatus" role="status"></p></section></div><p>Map data © OpenStreetMap contributors. Original video report and SQLite files are not modified. No plate recognition, cross-camera linkage or geographic inference.</p></main>
<script>
const data=__DATA__, tracks=data.tracks, $=id=>document.getElementById(id);const c=$('canvas'),ctx=c.getContext('2d'), W=c.width,H=c.height;let map=null, layer=null, loading=false, playing=false,last=0,raf=0,blob=null,videoReady=false;const clip=$('clip');
const [s,w,n,e]=data.bounds;const ll=p=>[n-p[2]*(n-s),w+p[1]*(e-w)];const color=t=>'hsl('+((t.id*137.508)%360)+' 80% 54%)';
$('n').textContent=tracks.length;$('samples').textContent=tracks.reduce((a,t)=>a+t.samples,0).toLocaleString();$('duration').textContent=data.duration.toFixed(1)+' s';$('time').max=data.duration;$('time').value=data.duration;
for(const t of tracks){let o=document.createElement('option');o.value=t.id;o.textContent='Track '+t.id+' · '+t.category;$('track').append(o);let row=document.createElement('tr');for(const v of [t.id,t.category,t.samples]){let td=document.createElement('td');td.textContent=v;row.append(td)}$('rows').append(row)}
function portions(t,time){let parts=[],part=[],prev=null;for(const p of t.points){if(p[0]>time)break;if(prev&&p[0]-prev[0]>.5){parts.push(part);part=[]}part.push(p);prev=p}if(part.length)parts.push(part);return parts}
function draw(){const time=Number($('time').value),sel=$('track').value; $('clock').textContent=time.toFixed(2)+' / '+data.duration.toFixed(1)+' s';const chosen=sel==='all'?tracks:tracks.filter(t=>String(t.id)===sel);$('details').textContent=sel==='all'?'All fragments. Choose one to reduce clutter.':chosen.length?`${chosen[0].category} · ${chosen[0].samples} samples · ${chosen[0].start.toFixed(2)}–${chosen[0].end.toFixed(2)} s`:'No track';
if(map){layer.clearLayers();for(const t of chosen){for(const part of portions(t,time)){if(part.length>1)L.polyline(part.map(ll),{color:color(t),weight:sel==='all'?2:5,opacity:.85,interactive:false}).addTo(layer);else L.circleMarker(ll(part[0]),{radius:2,color:color(t),interactive:false}).addTo(layer)}const p=t.points.findLast(p=>p[0]<=time);if(p&&time-p[0]<=.5)L.circleMarker(ll(p),{radius:sel==='all'?4:7,color:color(t),fillOpacity:1}).bindTooltip('Anonymous #'+t.id+' · simulated').addTo(layer)}return}
ctx.fillStyle='#0b1929';ctx.fillRect(0,0,W,H);ctx.strokeStyle='#26394d';ctx.lineWidth=1;for(let x=0;x<=W;x+=48){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke()}for(let y=0;y<=H;y+=54){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke()}ctx.fillStyle='#b3c3d5';ctx.font='14px system-ui';ctx.fillText('IMAGE COORDINATES · x → / y ↓',15,23);for(const t of chosen){ctx.strokeStyle=color(t);ctx.fillStyle=color(t);ctx.lineWidth=sel==='all'?2:4;for(const part of portions(t,time)){ctx.beginPath();part.forEach((p,i)=>i?ctx.lineTo(p[1]*W,p[2]*H):ctx.moveTo(p[1]*W,p[2]*H));ctx.stroke();if(part.length===1){ctx.beginPath();ctx.arc(part[0][1]*W,part[0][2]*H,2,0,Math.PI*2);ctx.fill()}}const p=t.points.findLast(p=>p[0]<=time);if(p&&time-p[0]<=.5){ctx.beginPath();ctx.arc(p[1]*W,p[2]*H,5,0,Math.PI*2);ctx.fill()}}}
function asset(tag,attrs){return new Promise((resolve,reject)=>{const el=document.createElement(tag);Object.assign(el,attrs);el.onload=resolve;el.onerror=()=>{el.remove();reject(Error('Map library unavailable'))};document.head.append(el)})}
function fit(){if(map)map.fitBounds([[s,w],[n,e]],{padding:[20,20]})}
$('fit').onclick=fit;$('enable').onclick=async()=>{if(loading)return;if(map){map.remove();map=null;layer=null;$('geo').hidden=true;c.hidden=false;$('fit').hidden=true;$('enable').textContent='Enable OpenStreetMap';$('status').textContent='Offline image-coordinate view';draw();return}loading=true;$('enable').disabled=true;try{if(!window.L){await Promise.all([asset('link',{rel:'stylesheet',href:'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',integrity:'sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=',crossOrigin:'anonymous'}),asset('script',{src:'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',integrity:'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=',crossOrigin:'anonymous'})])}c.hidden=true;$('geo').hidden=false;map=L.map('geo',{preferCanvas:true});const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'});tiles.on('tileerror',()=>{if(map)$('status').textContent='Some tiles unavailable · simulated placement only'});tiles.addTo(map);L.rectangle([[s,w],[n,e]],{color:'#f59e0b',dashArray:'5 5',fill:false,interactive:false}).addTo(map);layer=L.layerGroup().addTo(map);fit();$('fit').hidden=false;$('enable').textContent='Switch to image view';$('status').textContent='Simulated placement · not GPS';draw()}catch(err){if(map)map.remove();map=null;layer=null;c.hidden=false;$('geo').hidden=true;$('fit').hidden=true;$('status').textContent='Map unavailable; offline view is available.';draw()}finally{loading=false;$('enable').disabled=false}};
function stop(){playing=false;cancelAnimationFrame(raf);$('play').textContent='Play';if(videoReady&&!clip.paused)clip.pause()}
function tick(ts){if(!playing)return;if(!last)last=ts;const v=videoReady?clip.currentTime:Number($('time').value)+(ts-last)/1000;last=ts;$('time').value=Math.min(data.duration,v);draw();if(v>=data.duration||videoReady&&clip.ended){stop();return}raf=requestAnimationFrame(tick)}
function start(){if(playing)return;if(Number($('time').value)>=data.duration)$('time').value=0;if(videoReady){clip.currentTime=Number($('time').value);clip.play().catch(()=>{stop();$('vstatus').textContent='Video playback unavailable; remove the selected file to use map-only playback.'})}playing=true;last=0;$('play').textContent='Pause';raf=requestAnimationFrame(tick)}
$('play').onclick=()=>playing?stop():start();$('reset').onclick=()=>{stop();$('time').value=0;if(videoReady)clip.currentTime=0;draw()};$('time').oninput=()=>{if(videoReady)clip.currentTime=Math.min(clip.duration,Number($('time').value));draw()};$('track').onchange=draw;
$('file').onchange=()=>{stop();videoReady=false;if(blob)URL.revokeObjectURL(blob);blob=null;clip.removeAttribute('src');clip.load();clip.hidden=true;const f=$('file').files[0];if(!f)return;blob=URL.createObjectURL(f);clip.src=blob;clip.hidden=false;$('vstatus').textContent='Loading local preview…'};clip.onloadedmetadata=()=>{if(Math.abs(clip.duration-data.duration)>1){$('vstatus').textContent='Duration differs from analyzed clip; map playback stays independent.';videoReady=false;return}videoReady=true;clip.currentTime=Math.min(clip.duration,Number($('time').value));$('vstatus').textContent='Synchronized to recording time (verify this is the same clip).'};clip.onplay=()=>{if(videoReady&&!playing){playing=true;last=0;$('play').textContent='Pause';raf=requestAnimationFrame(tick)}};clip.onpause=()=>{if(videoReady&&playing)stop()};clip.onseeked=()=>{if(videoReady){$('time').value=Math.min(data.duration,clip.currentTime);draw()}};clip.onerror=()=>{videoReady=false;stop();$('vstatus').textContent='Browser cannot decode this video. Map playback remains available.'};draw();
</script></body></html>'''


def page(report):
    data=load_data(report)
    payload=json.dumps(data,allow_nan=False,separators=(',',':')).replace('<','\\u003c')
    return PAGE.replace('__NAV__',NAV,1).replace('__DATA__',payload,1)


class Handler(base.Handler):
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/': return self.respond(base.MAP.replace('</nav>',LINK+'</nav>',1),base.HTML)
        if path=='/analytics': return self.respond(base.ANALYTICS.replace('</nav>',LINK+'</nav>',1),base.HTML)
        if path=='/video':
            try: body=base.load_page(self.server.video_report).replace('</nav>',LINK+'</nav>',1)
            except (OSError,ValueError,TypeError,KeyError): return super().do_GET()
            return self.respond(body,base.HTML)
        if path=='/video-map':
            try: body=page(self.server.video_report)
            except FileNotFoundError: return self.respond(base.unavailable('Saved report missing. Keep video_full_results/video_map.html in the project.'),base.HTML,404)
            except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError): return self.respond(base.unavailable('Saved report invalid or unreadable.'),base.HTML,422)
            return self.respond(body,base.HTML)
        return super().do_GET()


def make_server(db,port=8002,report=REPORT):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.db_path=db;server.video_report=report;return server


class GeoTests(unittest.TestCase):
    def test_projection(self):
        self.assertEqual(project(0,0),[BOUNDS[2],BOUNDS[1]])
        self.assertAlmostEqual(project(1,1)[0],BOUNDS[0]);self.assertAlmostEqual(project(1,1)[1],BOUNDS[3])
        with self.assertRaises(ValueError): project(float('nan'),0)
    def test_report(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'report';base.video.export(out,[base.video.make_row(1,0,30,2,[1,2,20,30],.9,100,100)],1)
            p=out/'video_map.html';before=p.read_bytes();data=load_data(p);self.assertEqual(data['tracks'][0]['samples'],1);self.assertIn('SIMULATED GEOGRAPHIC PLACEMENT',page(p));self.assertEqual(before,p.read_bytes())
    def test_empty(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'report';base.video.export(out,[],1);self.assertEqual(load_data(out/'video_map.html')['tracks'],[])
    def test_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'report.html';p.write_text('const data={"duration":1,"tracks":[{"id":1,"category":"car","points":[[0,2,0]]}]}',encoding='utf-8')
            with self.assertRaises(ValueError):load_data(p)
    def test_http(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=root/'test.db';base.app.routes.initialize(db);out=root/'report';base.video.export(out,[base.video.make_row(1,0,30,2,[1,2,20,30],.9,100,100)],1);report=out/'video_map.html';before=report.read_bytes()
            with make_server(db,0,report) as server:
                th=threading.Thread(target=server.serve_forever,daemon=True);th.start();url='http://127.0.0.1:'+str(server.server_port)
                try:
                    for path in ('/','/analytics','/video','/video-map'):
                        with urlopen(url+path,timeout=5) as r: self.assertIn('href="/video-map"',r.read().decode())
                    self.assertEqual(before,report.read_bytes());report.unlink()
                    with self.assertRaises(HTTPError) as err:urlopen(url+'/video-map',timeout=5)
                    self.assertEqual(err.exception.code,404)
                finally: server.shutdown();th.join(5)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--test',action='store_true');p.add_argument('--port',type=int,default=8002);p.add_argument('--report',type=Path,default=REPORT);a=p.parse_args()
    if a.test:
        l=unittest.defaultTestLoader;suite=unittest.TestSuite([l.loadTestsFromModule(base.app.routes),l.loadTestsFromModule(base.app.quality),l.loadTestsFromTestCase(base.studio.StudioTests),l.loadTestsFromTestCase(base.video.Tests),l.loadTestsFromTestCase(base.VideoTabTests),l.loadTestsFromTestCase(GeoTests)])
        return int(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())
    if not 1<=a.port<=65535:p.error('Invalid port')
    try:
        base.app.routes.activate_osm();base.app.routes.initialize();base.app.quality.analytics(base.app.routes.DB);server=make_server(base.app.routes.DB,a.port,a.report)
    except (OSError,ValueError,KeyError,TypeError) as exc:p.exit(1,f'Startup failed: {exc}\nCheck existing graph and stop any old server.\n')
    print(f'CityTrack Phase 18: http://127.0.0.1:{a.port}/video-map\nVideo report: {a.report}\nSimulated placement only; not GPS.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0

if __name__=='__main__':raise SystemExit(main())
