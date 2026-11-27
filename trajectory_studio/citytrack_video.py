"""CityTrack Phase 16: anonymous, single-clip camera-coordinate trajectories.
No plate recognition, geographic inference, cross-camera linking or real-time feeds.
Python 3.10+; pip install ultralytics imageio-ffmpeg (first use downloads weights).
"""
import argparse
import csv
import json
import math
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / 'video_results'
CLASSES = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
SCHEMA = '''CREATE TABLE observations (
    track_id INTEGER NOT NULL, frame INTEGER NOT NULL, time_s REAL NOT NULL,
    category TEXT NOT NULL, x REAL NOT NULL CHECK(x BETWEEN 0 AND 1),
    y REAL NOT NULL CHECK(y BETWEEN 0 AND 1), confidence REAL NOT NULL,
    PRIMARY KEY(track_id, frame));'''
FIELDS = ('track_id','frame','time_s','category','x','y','confidence')


def make_row(track_id, frame, fps, cls, box, confidence, width, height):
    """Normalized bottom-center of a detected bounding box, not a GPS fix."""
    if cls not in CLASSES or width <= 0 or height <= 0 or fps <= 0:
        raise ValueError('Invalid detection metadata')
    x1,y1,x2,y2 = map(float, box)
    if not all(math.isfinite(v) for v in (x1,y1,x2,y2,confidence,fps)) or x2 < x1 or y2 < y1 or not 0 <= confidence <= 1:
        raise ValueError('Invalid detection geometry or confidence')
    return (int(track_id), int(frame), round(frame/fps, 4), CLASSES[cls],
            round(max(0,min(1,(x1+x2)/2/width)),6),
            round(max(0,min(1,y2/height)),6),round(float(confidence),4))


def summarize(rows):
    groups = {}
    for tid, frame, t, cat, x, y, conf in rows:
        groups.setdefault(tid, []).append([frame,t,cat,x,y,conf])
    tracks = []
    for tid, pts in sorted(groups.items()):
        pts.sort(key=lambda p:p[0])
        # Tracks can fragment or switch under occlusion; no attempt at cross-clip association.
        cat = max(sorted({p[2] for p in pts}), key=lambda c: sum(p[2]==c for p in pts))
        tracks.append(dict(id=tid, category=cat, points=[[p[1],p[3],p[4]] for p in pts],
                           samples=len(pts), start=pts[0][1], end=pts[-1][1],
                           confidence=round(sum(p[5] for p in pts)/len(pts),4)))
    return tracks


PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CityTrack | Video trajectories</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b111c;color:#e2e8f0;font:14px system-ui,sans-serif}header{padding:18px 24px;border-bottom:1px solid #283a4c;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}h1{font-size:21px;margin:0}h2{font-size:16px;margin:0 0 12px}small,p{color:#a6b9cf;line-height:1.5}a{color:#49d9ea}main{max-width:1450px;margin:auto;padding:20px} .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:15px}.card,section{background:#111d2c;border:1px solid #27384b;border-radius:10px;padding:14px;min-width:0}.kpi{display:block;font-size:25px;color:#49d9ea;margin-top:5px}.layout{display:grid;grid-template-columns:minmax(0,2fr) minmax(230px,1fr);gap:12px}canvas{width:100%;height:auto;display:block;background:#0c1828;border-radius:8px;border:1px solid #27384b}button,select{background:#172b40;color:#e2e8f0;border:1px solid #39516a;border-radius:6px;padding:9px;font:inherit}label{display:block;color:#a6b9cf;margin-bottom:5px}.controls{display:flex;gap:10px;align-items:center;margin:12px 0;flex-wrap:wrap}input[type=range]{flex:1;min-width:100px;accent-color:#49d9ea}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:9px 5px;text-align:left;border-bottom:1px solid #27384b}th{color:#a6b9cf} .scroll{max-height:430px;overflow:auto} #details{line-height:1.7} .tag{color:#49d9ea;font-size:11px;letter-spacing:1px}@media(max-width:750px){.layout{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr}}
</style><header><div><h1>CityTrack / Video trajectories</h1><small>Single recording · anonymous temporary track IDs</small></div><a href="http://127.0.0.1:8002/">Open existing Trajectory Studio</a></header><main><p><strong>Camera-coordinate map — not a geographic map.</strong> Points show detected bottom-center positions in the recording, normalized to the image. No latitude, longitude, road distance, plate number or vehicle identity is inferred. Paths end at the limits of the clip; gaps and tracker ID switches are possible.</p><div class="kpis"><div class="card">Track fragments<strong class="kpi" id="n"></strong></div><div class="card">Recorded samples<strong class="kpi" id="samples"></strong></div><div class="card">Analyzed video time<strong class="kpi" id="duration"></strong></div><div class="card">Coordinate system<strong class="kpi">Image</strong></div></div><div class="layout"><section><h2>Movement map</h2><canvas id="map" width="960" height="540" aria-label="Normalized camera-coordinate trajectories"></canvas><div class="controls"><button id="play">Play</button><button id="reset">Reset</button><input id="time" type="range" min="0" step="any" aria-label="Video time"><span id="clock"></span></div><small>Colored lines connect nearby-in-time detections; gaps longer than 0.5 seconds remain disconnected. The grid is an image plane, not a map of roads.</small></section><section><h2>Track selection</h2><label for="track">Temporary ID within this clip</label><select id="track"><option value="all">All track fragments</option></select><p id="details"></p><h2>Recorded track fragments</h2><div class="scroll"><table><thead><tr><th>ID</th><th>Class</th><th>Samples</th></tr></thead><tbody id="rows"></tbody></table></div></section></div><p>Data is saved locally in video_observations.sqlite3 and video_observations.csv. Confidence is a detector score, not identification accuracy. Track fragment counts are not guaranteed unique vehicle counts.</p></main><script>
const data=__DATA__; const tracks=data.tracks;const $=id=>document.getElementById(id);const c=$('map'),ctx=c.getContext('2d');const W=c.width,H=c.height;let playing=false,last=0;
$('n').textContent=tracks.length;$('samples').textContent=tracks.reduce((s,t)=>s+t.samples,0);$('duration').textContent=data.duration.toFixed(1)+' s';$('time').max=data.duration;$('time').value=data.duration;
for(const tr of tracks){const opt=document.createElement('option');opt.value=tr.id;opt.textContent='Track '+tr.id+' · '+tr.category;$('track').append(opt);const row=document.createElement('tr');for(const value of [tr.id,tr.category,tr.samples]){const td=document.createElement('td');td.textContent=value;row.append(td)}$('rows').append(row)}
function draw(){const time=Number($('time').value);$('clock').textContent=time.toFixed(1)+' / '+data.duration.toFixed(1)+' s';ctx.fillStyle='#0c1828';ctx.fillRect(0,0,W,H);ctx.strokeStyle='#213448';ctx.lineWidth=1;for(let x=0;x<=W;x+=48){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke()}for(let y=0;y<=H;y+=54){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke()}ctx.fillStyle='#9db0c6';ctx.font='12px system-ui';ctx.fillText('IMAGE COORDINATES · x → / y ↓',14,22);const selected=$('track').value;for(const tr of tracks){if(selected!=='all'&&Number(selected)!==tr.id)continue;const color='hsl('+((tr.id*137.508)%360)+' 80% 65%)';ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=selected==='all'?2:4;let prev=null;for(const p of tr.points){if(p[0]>time)break;if(prev&&p[0]-prev[0]<=0.5){ctx.beginPath();ctx.moveTo(prev[1]*W,prev[2]*H);ctx.lineTo(p[1]*W,p[2]*H);ctx.stroke()}prev=p}if(prev&&time-prev[0]<=0.5){ctx.beginPath();ctx.arc(prev[1]*W,prev[2]*H,5,0,Math.PI*2);ctx.fill();ctx.font='12px system-ui';ctx.fillText('#'+tr.id,Math.min(W-42,prev[1]*W+8),Math.max(15,prev[2]*H-8))}}const tr=tracks.find(t=>String(t.id)===selected);$('details').textContent=tr?`${tr.category} · ${tr.samples} samples · ${tr.start.toFixed(2)}–${tr.end.toFixed(2)} s · Mean detection score ${(tr.confidence*100).toFixed(1)}%`:'Choose a temporary track or view all paths.'}
function tick(ts){if(!playing)return;if(!last)last=ts;let next=Math.min(data.duration,Number($('time').value)+(ts-last)/1000);last=ts;$('time').value=next;draw();if(next>=data.duration){playing=false;$('play').textContent='Play';return}requestAnimationFrame(tick)}$('play').onclick=()=>{if(playing){playing=false;$('play').textContent='Play';return}if(Number($('time').value)>=data.duration)$('time').value=0;playing=true;last=0;$('play').textContent='Pause';requestAnimationFrame(tick)};$('reset').onclick=()=>{playing=false;$('play').textContent='Play';$('time').value=0;draw()};$('time').oninput=draw;$('track').onchange=draw;draw();</script></html>'''


def export(out, rows, duration):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    rows = sorted(rows, key=lambda r:(r[1],r[0]))
    with closing(sqlite3.connect(out/'video_observations.sqlite3')) as db, db:
        db.execute(SCHEMA)
        db.executemany('INSERT INTO observations VALUES (?,?,?,?,?,?,?)',rows)
    with (out/'video_observations.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(FIELDS);w.writerows(rows)
    payload=json.dumps({'duration':duration,'tracks':summarize(rows)},allow_nan=False,separators=(',',':')).replace('<','\\u003c')
    (out/'video_map.html').write_text(PAGE.replace('__DATA__',payload),encoding='utf-8')


def reader(path, seconds):
    import imageio_ffmpeg
    return imageio_ffmpeg.read_frames(str(path),pix_fmt='bgr24',output_params=['-vf','scale=960:-2','-t',str(seconds)])


def process(path, out, seconds, stride):
    import numpy as np
    from ultralytics import YOLO
    if out.exists():
        raise FileExistsError(f'Output folder already exists: {out}. Use --out with a new folder.')
    model=YOLO('yolo11n.pt')
    rows=[]; remap={}; frames=0
    with closing(reader(path,seconds)) as gen:
        meta=next(gen); width,height=meta['size'];fps=float(meta['fps'])
        if not math.isfinite(fps) or fps<=0: raise ValueError('Video FPS unavailable')
        print(f'Decoded {width}x{height} at {fps:g} FPS; analyzing every {stride} frame(s).',flush=True)
        for i,raw in enumerate(gen):
            if i/fps >= seconds: break
            frames=i+1
            if i%stride: continue
            frame=np.frombuffer(raw,dtype=np.uint8).reshape(height,width,3).copy()
            result=model.track(frame,persist=True,tracker='bytetrack.yaml',classes=list(CLASSES),conf=0.25,imgsz=640,verbose=False)[0]
            b=result.boxes
            if b is not None and b.id is not None:
                for tid,cls,xyxy,conf in zip(b.id.int().cpu().tolist(),b.cls.int().cpu().tolist(),b.xyxy.cpu().tolist(),b.conf.cpu().tolist()):
                    anon=remap.setdefault(tid,len(remap)+1)
                    rows.append(make_row(anon,i,fps,cls,xyxy,conf,width,height))
            if i%max(stride,int(fps)*stride)==0: print(f'{i/fps:.1f}s processed; {len(rows)} samples',flush=True)
    if frames==0: raise RuntimeError('No frames decoded')
    export(out,rows,round(frames/fps,3))
    print(f'Saved {len(rows)} observations in {out}\nOpen: {out / "video_map.html"}',flush=True)
    if not rows: print('No tracks detected. No trajectories were fabricated.')


class Tests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(make_row(1,30,30,2,[100,100,300,200],.9,400,400),(1,30,1.,'car',.5,.5,.9))
    def test_bounds(self):
        self.assertEqual(make_row(1,0,30,7,[-40,0,0,500],.5,400,400)[4:6],(0,1))
    def test_bad_class(self):
        with self.assertRaises(ValueError): make_row(1,0,30,0,[0,0,10,10],.9,400,400)
    def test_order(self):
        a=make_row(1,60,30,2,[10,10,20,20],.9,100,100);b=make_row(1,0,30,2,[10,10,20,20],.9,100,100)
        self.assertEqual(summarize([a,b])[0]['start'],0)
        self.assertEqual(summarize([a,b])[0]['end'],2)
    def test_export(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'results';r=make_row(1,0,30,2,[10,10,20,20],.9,100,100);export(out,[r],1)
            with closing(sqlite3.connect(out/'video_observations.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT * FROM observations').fetchone(),r)
            self.assertIn('Camera-coordinate map', (out/'video_map.html').read_text(encoding='utf-8'))
            self.assertEqual(len((out/'video_observations.csv').read_text().splitlines()),2)
            with self.assertRaises(FileExistsError): export(out,[],1)
    def test_empty(self):
        self.assertEqual(summarize([]),[])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video',nargs='?',type=Path);p.add_argument('--seconds',type=float,default=30);p.add_argument('--stride',type=int,default=2);p.add_argument('--out',type=Path,default=DEFAULT_OUTPUT);p.add_argument('--test',action='store_true');p.add_argument('--probe',action='store_true');a=p.parse_args()
    if a.test: return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    if not a.video or not a.video.is_file(): p.error('Provide a local video file.')
    if not math.isfinite(a.seconds) or not 0<a.seconds<=120 or not 1<=a.stride<=5:p.error('Use 0 < seconds <= 120 and stride 1–5.')
    try:
        if a.probe:
            with closing(reader(a.video,1)) as gen:
                print(next(gen));print(f'First decoded frame: {len(next(gen))} bytes')
        else: process(a.video,a.out,a.seconds,a.stride)
    except ImportError as exc: p.exit(1,f'Missing dependency: {exc}\nRun python -m pip install ultralytics imageio-ffmpeg\n')
    except (OSError,ValueError,RuntimeError,StopIteration) as exc:p.exit(1,f'Video processing failed: {exc}\n')
    return 0

if __name__=='__main__': raise SystemExit(main())
