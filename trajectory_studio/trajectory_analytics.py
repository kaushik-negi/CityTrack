"""CityTrack Phase 6: read-only aggregate analytics for synthetic test data.
Run beside trajectory_osm.py: python trajectory_analytics.py
Tests: python trajectory_analytics.py --test
Standard library only. No external requests or changes to the database.
"""
import argparse
import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DB = Path(__file__).resolve().with_name('trajectory_import_demo.sqlite3')
SCENARIOS = {'normal': 4, 'review': 5, 'anomaly': 3}
SYNTHETIC = re.compile(r'(?:DEMO-00[123]|SIM-[A-F0-9]{12}|TEST-[A-Z0-9]{1,24})\Z')


def analytics(path):
    # URI mode=ro prevents writes and accidental creation of a new database.
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.execute('BEGIN')  # consistent snapshot across the two reads
        counts = dict(total=0, confirmed=0, review=0)
        buckets = [0, 0, 0, 0]
        confidence_sum = 0.0
        vehicles = set()
        for vid, status, confidence in db.execute('SELECT vehicle_id,status,confidence FROM detections'):
            if not isinstance(vid, str) or not SYNTHETIC.fullmatch(vid):
                continue
            if status not in ('confirmed', 'review') or not isinstance(confidence, (int,float)) or not 0 <= confidence <= 1:
                continue
            vehicles.add(vid)
            counts['total'] += 1
            counts[status] += 1
            confidence_sum += confidence
            buckets[0 if confidence < .5 else 1 if confidence < .9 else 2 if confidence < .95 else 3] += 1
        scenarios = {k: {'started': 0, 'completed': 0} for k in SCENARIOS}
        for vid, scenario, step in db.execute('SELECT vehicle_id,scenario,next_index FROM simulation_runs'):
            if not isinstance(vid,str) or not vid.startswith('SIM-') or not SYNTHETIC.fullmatch(vid) or scenario not in SCENARIOS:
                continue
            if not isinstance(step,int) or not 0 <= step <= SCENARIOS[scenario]:
                continue
            scenarios[scenario]['started'] += 1
            scenarios[scenario]['completed'] += int(step == SCENARIOS[scenario])
    n = counts['total']
    started = sum(x['started'] for x in scenarios.values())
    completed = sum(x['completed'] for x in scenarios.values())
    return {**counts, 'synthetic_journeys':len(vehicles),
            'confirmation_pct':round(100*counts['confirmed']/n,1) if n else None,
            'review_pct':round(100*counts['review']/n,1) if n else None,
            'mean_confidence_pct':round(100*confidence_sum/n,1) if n else None,
            'confidence_buckets':buckets, 'scenarios':scenarios,
            'runs_started':started, 'runs_completed':completed,
            'completion_pct':round(100*completed/started,1) if started else None}

HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CityTrack | Analytics</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0e1521;color:#e2e8f0;font:16px system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:28px}h1{font-size:30px;margin:10px 0}h2{font-size:18px;margin:0 0 20px}p{color:#a8b7ca;line-height:1.5}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.tag{color:#67dce9;font-size:12px;font-weight:bold;letter-spacing:2px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:14px;margin:20px 0}.panel,.metric{background:#121e2e;border:1px solid #26384e;border-radius:14px;padding:20px}.metric span{color:#a8b7ca;font-size:14px}.metric strong{display:block;font-size:30px;margin-top:9px}.split{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,370px),1fr));gap:16px}.bar{height:12px;background:#26384e;border-radius:8px;overflow:hidden;margin:7px 0 17px}.fill{height:100%;background:#41d9ef;border-radius:8px}.label{display:flex;justify-content:space-between;gap:10px;font-size:14px}.muted{font-size:13px;color:#a8b7ca}button,a{display:inline-block;border:1px solid #38516c;border-radius:8px;background:#18283c;color:#e2e8f0;padding:10px 14px;text-decoration:none;font:inherit;cursor:pointer}button:disabled{opacity:.5}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:13px 5px;border-bottom:1px solid #26384e}th{color:#a8b7ca;font-weight:500}#status{min-height:24px}.error{color:#ffae88}</style></head><body><main><div class="top"><div><div class="tag">CITYTRACK / PHASE 6</div><h1>Trajectory analytics</h1><p>Aggregate quality metrics for synthetic test observations only.</p></div><div><a href="http://127.0.0.1:8000/" target="_blank" rel="noopener">Open trajectory map</a> <button id="refresh">Refresh</button></div></div><p id="status" role="status">Loading...</p><section class="grid" id="metrics"></section><section class="split"><div class="panel"><h2>Detection quality</h2><div id="quality"></div><p class="muted">Confirmation and review are stored statuses; confidence is a synthetic input, not measured OCR accuracy.</p></div><div class="panel"><h2>Confidence distribution</h2><div id="confidence"></div><p class="muted">Counts by supplied confidence score.</p></div><div class="panel"><h2>Simulation scenarios</h2><table><thead><tr><th>Scenario</th><th>Started</th><th>Completed</th></tr></thead><tbody id="scenarios"></tbody></table><p class="muted">Includes unfinished runs. No individual journey identifiers are returned.</p></div><div class="panel"><h2>Simulation completion</h2><div id="completion"></div><p class="muted">Completed means all predefined detections were generated, not that a real journey was observed.</p></div></section><p class="muted">Local read-only SQLite connection · No Firebase · No external requests · Refresh manually after generating or importing test data.</p></main><script>
const $=id=>document.getElementById(id);function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}const pct=x=>x===null?'—':x.toFixed(1)+'%';function metric(label,value){const d=node('div',undefined,'metric');d.append(node('span',label),node('strong',value));$('metrics').append(d)}function bar(parent,label,value,total,color){const row=node('div',undefined,'label');row.append(node('span',label),node('strong',String(value)));const track=node('div',undefined,'bar');const fill=node('div',undefined,'fill');fill.style.width=(total?Math.min(100,100*value/total):0)+'%';fill.style.background=color;track.append(fill);parent.append(row,track)}async function load(){const b=$('refresh');b.disabled=true;$('status').className='';$('status').textContent='Loading local metrics…';try{const r=await fetch('/api/analytics',{cache:'no-store'});const a=await r.json();if(!r.ok)throw Error(a.error||'Request failed');for(const id of ['metrics','quality','confidence','scenarios','completion'])$(id).replaceChildren();metric('Synthetic journey IDs',a.synthetic_journeys);metric('Total observations',a.total);metric('Confirmed observations',a.confirmed);metric('Review observations',a.review);metric('Confirmation rate',pct(a.confirmation_pct));metric('Mean input confidence',pct(a.mean_confidence_pct));metric('Review rate',pct(a.review_pct));metric('Simulation completion',pct(a.completion_pct));bar($('quality'),'Confirmed',a.confirmed,a.total,'#41d9ef');bar($('quality'),'Needs review',a.review,a.total,'#f6a45e');const labels=['Below 50%','50% to below 90%','90% to below 95%','95% to 100%'];a.confidence_buckets.forEach((v,i)=>bar($('confidence'),labels[i],v,a.total,'#a78bfa'));for(const [name,s] of Object.entries(a.scenarios)){const tr=node('tr');tr.append(node('td',({normal:'Normal',review:'Low confidence',anomaly:'Implausible speed'})[name]||name),node('td',s.started),node('td',s.completed));$('scenarios').append(tr)}bar($('completion'),'Completed runs',a.runs_completed,a.runs_started,'#41d9ef');bar($('completion'),'Unfinished runs',a.runs_started-a.runs_completed,a.runs_started,'#64748b');$('status').textContent='Updated at '+new Date().toLocaleTimeString();}catch(e){$('status').className='error';$('status').textContent=e.message+' — displayed metrics, if any, may be stale.'}finally{b.disabled=false}}$('refresh').onclick=load;load();</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def send_data(self, data, status=200, kind='application/json; charset=utf-8'):
        body = (data if isinstance(data,str) else json.dumps(data,allow_nan=False)).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/': return self.send_data(HTML,kind='text/html; charset=utf-8')
        if path=='/api/analytics':
            try: return self.send_data(analytics(self.server.db_path))
            except (sqlite3.Error,OSError): return self.send_data({'error':'Cannot read the Phase 4/5 SQLite database. Check that it exists and has the expected schema.'},503)
        return self.send_data({'error':'Not found'},404)

class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.db'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript('CREATE TABLE detections(vehicle_id TEXT,status TEXT,confidence REAL);CREATE TABLE simulation_runs(vehicle_id TEXT,scenario TEXT,next_index INTEGER);')
    def put(self,observations=(),runs=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany('INSERT INTO detections VALUES(?,?,?)',observations)
            db.executemany('INSERT INTO simulation_runs VALUES(?,?,?)',runs)
    def test_empty(self):
        a=analytics(self.path); self.assertEqual(a['total'],0); self.assertIsNone(a['confirmation_pct']); self.assertIsNone(a['completion_pct'])
    def test_counts(self):
        self.put([('TEST-001','confirmed',.99),('TEST-001','review',.51),('DEMO-001','confirmed',.95)])
        a=analytics(self.path); self.assertEqual((a['total'],a['confirmed'],a['review'],a['synthetic_journeys']),(3,2,1,2)); self.assertEqual(a['confirmation_pct'],66.7)
    def test_buckets(self):
        self.put([('TEST-X','review',x) for x in (0,.499,.5,.899,.9,.949,.95,1)])
        self.assertEqual(analytics(self.path)['confidence_buckets'],[2,2,2,2])
    def test_completion(self):
        self.put(runs=[('SIM-AAAAAAAAAAAA','normal',4),('SIM-BBBBBBBBBBBB','normal',2),('SIM-CCCCCCCCCCCC','review',5),('SIM-DDDDDDDDDDDD','anomaly',3)])
        a=analytics(self.path); self.assertEqual(a['runs_completed'],3); self.assertEqual(a['completion_pct'],75.0)
    def test_nonsynthetic_excluded(self):
        self.put([('PRIVATE-123','confirmed',.99),('TEST-001','confirmed',.9)], [('PRIVATE-123','normal',4)])
        a=analytics(self.path); self.assertEqual(a['total'],1);self.assertEqual(a['runs_started'],0); self.assertNotIn('TEST-001',json.dumps(a))
    def test_read_only(self):
        before=self.path.read_bytes(); analytics(self.path); self.assertEqual(self.path.read_bytes(),before)
    def test_missing_not_created(self):
        p=self.path.with_name('absent.db')
        with self.assertRaises(sqlite3.Error): analytics(p)
        self.assertFalse(p.exists())

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--test',action='store_true'); parser.add_argument('--port',type=int,default=8001); parser.add_argument('--db',type=Path,default=DB); args=parser.parse_args()
    if args.test: unittest.main(argv=['trajectory_analytics.py'])
    try: analytics(args.db)
    except (sqlite3.Error,OSError) as exc: parser.exit(1,f'Cannot read database {args.db}: {exc}\nRun the Phase 5 application first.\n')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler); server.db_path=args.db
    print(f'CityTrack analytics: http://127.0.0.1:{args.port}\nRead-only database: {args.db}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
