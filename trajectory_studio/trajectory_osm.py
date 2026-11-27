"""CityTrack local trajectory prototype. Python 3.9+, no external packages.
Run: python trajectory_osm.py   |   Tests: python trajectory_osm.py --test
Download once: python trajectory_osm.py --download-osm
Synthetic camera locations and vehicle IDs only. Optional online basemap.
Phase 5B: offline shortest paths on downloaded OpenStreetMap drive graph.
The download step requires OSMnx 2.x; runtime uses the standard library.
"""
import argparse
import heapq
from functools import lru_cache
import csv
import io
import re
import datetime as dt
import json
import math
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DB = Path(__file__).resolve().with_name('trajectory_import_demo.sqlite3')
OSM_FILE = Path(__file__).resolve().with_name('citytrack_osm_network.json')
OSM_BBOX = (77.165, 28.58, 77.25, 28.65) # west, south, east, north
OSM_ACTIVE = False
OSM_SNAPS = {}
MAX_SNAP_KM = .5
CAMERAS = [('CAM-A','West Gate', 0.010,0.010), ('CAM-B','Central Junction',0.010,0.025),
           ('CAM-C','North Junction',0.025,0.025), ('CAM-D','East Gate',0.025,0.043),
           ('CAM-E','South Junction',0.002,0.025), ('CAM-F','North West',0.025,0.010)]
# Fictional camera sites placed at illustrative geographic coordinates near Delhi.
# These do not represent real cameras or surveyed road positions.
CAMERAS = [(i,n,round(28.60+y,6),round(77.18+x,6)) for i,n,y,x in CAMERAS]
# IDs are generated test identifiers, not registration numbers.
SAMPLES = [('DEMO-001','Hatchback','CAM-A',0,.99),('DEMO-001','Hatchback','CAM-B',4,.97),
 ('DEMO-001','Hatchback','CAM-C',8,.98),('DEMO-001','Hatchback','CAM-D',13,.96),
 ('DEMO-001','Hatchback','CAM-E',15,.51),
 ('DEMO-002','SUV','CAM-E',1,.97),('DEMO-002','SUV','CAM-B',4,.99),
 ('DEMO-002','SUV','CAM-A',8,.95),('DEMO-002','SUV','CAM-F',12,.96),
 ('DEMO-003','Sedan','CAM-A',0,.99),('DEMO-003','Sedan','CAM-D',0.5,.98),
 ('DEMO-003','Sedan','CAM-C',6,.94)]
# Timings are simulated, not wall-clock travel times. Each run is finite.
SCENARIOS = {
    'normal': [('CAM-A',0,.99),('CAM-B',4,.97),('CAM-C',8,.98),('CAM-D',13,.96)],
    'review': [('CAM-E',0,.97),('CAM-B',4,.98),('CAM-D',6,.51),('CAM-A',8,.95),('CAM-F',12,.96)],
    'anomaly': [('CAM-A',0,.99),('CAM-D',.5,.98),('CAM-C',6,.94)],
}
BASE = dt.datetime(2026,1,1,9,0,tzinfo=dt.timezone.utc)

@contextmanager
def connect(path):
    db = sqlite3.connect(path)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        with db:
            yield db
    finally:
        db.close()

def initialize(path=DB):
    with connect(path) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS cameras(id TEXT PRIMARY KEY,name TEXT,lat REAL,lon REAL);
        CREATE TABLE IF NOT EXISTS detections(id INTEGER PRIMARY KEY, vehicle_id TEXT, model TEXT,
        camera_id TEXT REFERENCES cameras(id), observed_at TEXT, confidence REAL CHECK(confidence BETWEEN 0 AND 1),
        status TEXT CHECK(status IN ('confirmed','review')), UNIQUE(vehicle_id,camera_id,observed_at));
        CREATE INDEX IF NOT EXISTS detection_lookup ON detections(vehicle_id,status,observed_at);
        CREATE TABLE IF NOT EXISTS simulation_runs(vehicle_id TEXT PRIMARY KEY, scenario TEXT NOT NULL,
        base_time TEXT NOT NULL, next_index INTEGER NOT NULL);''')
        db.executemany('INSERT OR IGNORE INTO cameras VALUES(?,?,?,?)',CAMERAS)
        db.executemany('INSERT OR IGNORE INTO detections(vehicle_id,model,camera_id,observed_at,confidence,status) VALUES(?,?,?,?,?,?)',
            [(v,m,c,(BASE+dt.timedelta(minutes=t)).isoformat(),q,'confirmed' if q>=.90 else 'review') for v,m,c,t,q in SAMPLES])

def sim_state(row):
    total=len(SCENARIOS[row['scenario']])
    return {'vehicle_id':row['vehicle_id'],'scenario':row['scenario'],
            'emitted':row['next_index'],'total':total,'complete':row['next_index']==total}

def emit_sim(db,row):
    index=row['next_index']; plan=SCENARIOS[row['scenario']]
    if index>=len(plan): return sim_state(row)
    camera,minutes,confidence=plan[index]
    observed=(dt.datetime.fromisoformat(row['base_time'])+dt.timedelta(minutes=minutes)).isoformat()
    db.execute('INSERT INTO detections(vehicle_id,model,camera_id,observed_at,confidence,status) VALUES(?,?,?,?,?,?)',
        (row['vehicle_id'],'Synthetic test car',camera,observed,confidence,'confirmed' if confidence>=.90 else 'review'))
    db.execute('UPDATE simulation_runs SET next_index=? WHERE vehicle_id=?',(index+1,row['vehicle_id']))
    return sim_state(dict(row,next_index=index+1))

def create_sim(path,scenario):
    if not isinstance(scenario,str) or scenario not in SCENARIOS: raise ValueError('Unknown scenario')
    vehicle='SIM-'+uuid.uuid4().hex[:12].upper()
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row={'vehicle_id':vehicle,'scenario':scenario,'base_time':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),'next_index':0}
        db.execute('INSERT INTO simulation_runs VALUES(?,?,?,?)',tuple(row.values()))
        return emit_sim(db,row)

def advance_sim(path,vehicle,expected):
    if not isinstance(vehicle,str) or type(expected) is not int or expected<0: raise ValueError('Invalid simulation step')
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM simulation_runs WHERE vehicle_id=?',(vehicle,)).fetchone()
        if row is None: raise ValueError('Unknown simulation')
        if expected!=row['next_index']: return sim_state(row)
        return emit_sim(db,row)

IMPORT_FIELDS = {'vehicle_id','camera_id','observed_at','confidence'}
MAX_IMPORT_ROWS = 1000
MAX_IMPORT_BYTES = 256 * 1024

def import_observations(path, fmt, content):
    """Validate the whole synthetic batch before saving it atomically."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError('File is empty or invalid')
    if len(content.encode('utf-8')) > MAX_IMPORT_BYTES:
        raise ValueError('File exceeds 256 KiB')
    content = content.lstrip('\ufeff')
    if fmt == 'csv':
        try:
            reader = csv.DictReader(io.StringIO(content), strict=True)
            if set(reader.fieldnames or []) != IMPORT_FIELDS or len(reader.fieldnames or []) != len(IMPORT_FIELDS):
                raise ValueError('CSV needs exactly: vehicle_id,camera_id,observed_at,confidence')
            rows = list(reader)
        except csv.Error as exc:
            raise ValueError('Invalid CSV: '+str(exc)) from exc
    elif fmt == 'json':
        rows = json.loads(content)
    else:
        raise ValueError('Choose a CSV or JSON file')
    if not isinstance(rows,list) or not 1 <= len(rows) <= MAX_IMPORT_ROWS:
        raise ValueError('Provide 1 to 1000 observation records in a JSON array or CSV')
    validated = []
    known = {c[0] for c in CAMERAS}
    for index,row in enumerate(rows,1):
        try:
            if not isinstance(row,dict) or set(row) != IMPORT_FIELDS:
                raise ValueError('Expected exactly the four required fields')
            vehicle = row['vehicle_id']; camera = row['camera_id']
            if not isinstance(vehicle,str) or not re.fullmatch(r'TEST-[A-Z0-9]{1,24}',vehicle):
                raise ValueError('Use synthetic IDs such as TEST-001')
            if not isinstance(camera,str) or camera not in known:
                raise ValueError('Use a fictional camera ID CAM-A through CAM-F')
            raw_time = row['observed_at']
            if not isinstance(raw_time,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})',raw_time):
                raise ValueError('Use ISO 8601 time with seconds and timezone (Z or +05:30)')
            timestamp = dt.datetime.fromisoformat(raw_time.replace('Z','+00:00')).astimezone(dt.timezone.utc).isoformat()
            if isinstance(row['confidence'],bool): raise ValueError('Confidence must be numeric')
            q = float(row['confidence'])
            if not math.isfinite(q) or not 0 <= q <= 1:
                raise ValueError('Confidence must be between 0 and 1')
            validated.append((vehicle,'Imported synthetic car',camera,timestamp,q,'confirmed' if q>=.90 else 'review'))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f'Record {index}: {exc}') from exc
    inserted = duplicates = confirmed = review = 0
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        for v,m,c,t,q,status in validated:
            existing=db.execute('SELECT confidence FROM detections WHERE vehicle_id=? AND camera_id=? AND observed_at=?',(v,c,t)).fetchone()
            if existing is not None:
                if existing['confidence'] != q:
                    raise ValueError(f'Conflicting duplicate for {v}, {c}, {t}; no records saved')
                duplicates += 1
                continue
            db.execute('INSERT INTO detections(vehicle_id,model,camera_id,observed_at,confidence,status) VALUES(?,?,?,?,?,?)',(v,m,c,t,q,status))
            inserted += 1
            confirmed += status == 'confirmed'
            review += status == 'review'
    return {'inserted':inserted,'duplicates':duplicates,'confirmed':confirmed,'review':review,'vehicles':sorted({r[0] for r in validated})}

def distance(a,b):
    p1,p2=map(math.radians,(a['lat'],b['lat'])); dp=p2-p1; dl=math.radians(b['lon']-a['lon'])
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371*2*math.asin(math.sqrt(min(1,max(0,h))))

# A small fictional, bidirectional road graph. Intermediate nodes create bends.
# Geographic coordinates are for demonstration only, not OSM road geometry.
ROAD_NODES = {i: {'lat':lat,'lon':lon} for i,_,lat,lon in CAMERAS}
ROAD_NODES.update({i:{'lat':lat,'lon':lon} for i,lat,lon in [
    ('J1',28.607,77.197),('J2',28.613,77.205),
    ('J3',28.617,77.211),('J4',28.624,77.211),
    ('J5',28.628,77.215),('J6',28.622,77.222),
    ('J7',28.618,77.188),('J8',28.601,77.200),
    ('J9',28.619,77.198),('J10',28.613,77.223),
]})
ROAD_CHAINS = [('CAM-A','J1','CAM-B'),('CAM-B','J2','J3','J4','CAM-C'),
    ('CAM-C','J5','J6','CAM-D'),('CAM-A','J7','CAM-F'),
    ('CAM-F','J9','CAM-C'),('CAM-E','J8','J1'),('CAM-E','CAM-B'),
    ('J3','J10','J6'),('J9','J2')]
ROAD_EDGES = [(a,b) for chain in ROAD_CHAINS for a,b in zip(chain,chain[1:])]

def make_graph(nodes,edges):
    graph={n:[] for n in nodes}
    for a,b in edges:
        w=distance(nodes[a],nodes[b])
        graph[a].append((b,w)); graph[b].append((a,w))
    return graph

ROAD_GRAPH=make_graph(ROAD_NODES,ROAD_EDGES)

def shortest_path(graph,start,end):
    """Dijkstra with nonnegative edge lengths; None when disconnected."""
    if start not in graph or end not in graph: return None
    best={start:0.0}; prev={}; queue=[(0.0,start)]
    while queue:
        cost,node=heapq.heappop(queue)
        if cost>best[node]: continue
        if node==end:
            route=[end]
            while route[-1]!=start: route.append(prev[route[-1]])
            return list(reversed(route)),cost
        for nxt,weight in graph[node]:
            alt=cost+weight
            if alt<best.get(nxt,math.inf):
                best[nxt]=alt; prev[nxt]=node; heapq.heappush(queue,(alt,nxt))
    return None


def download_osm(path=OSM_FILE):
    """Download only the fixed public demo area, never observations or IDs."""
    import osmnx as ox
    print('Downloading public OpenStreetMap driving network for the fixed demo area...', flush=True)
    graph = ox.graph.graph_from_bbox(OSM_BBOX, network_type='drive', simplify=False, retain_all=True)
    nodes = {str(n): {'lat': float(d['y']), 'lon': float(d['x'])} for n,d in graph.nodes(data=True)}
    # Unsimplified edges retain intermediate OSM shape nodes. Respect direction.
    edges = [[str(a),str(b),float(d['length'])/1000] for a,b,d in graph.edges(data=True)]
    payload = {'source':'OpenStreetMap','bbox':list(OSM_BBOX),'downloaded_at':dt.datetime.now(dt.timezone.utc).isoformat(),'nodes':nodes,'edges':edges}
    build_osm_network(payload) # validate before replacing any prior cache
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8')
    tmp.replace(path)
    print(f'Saved {len(nodes)} road nodes, {len(edges)} directed edges to {path}',flush=True)


def build_osm_network(payload):
    if payload.get('source')!='OpenStreetMap' or payload.get('bbox')!=list(OSM_BBOX):
        raise ValueError('Unexpected road network source or demo bounds')
    nodes=payload['nodes']; edges=payload['edges']
    if not nodes or not edges: raise ValueError('Empty road network')
    graph={n:[] for n in nodes}
    for p in nodes.values():
        if not (-90<=p['lat']<=90 and -180<=p['lon']<=180): raise ValueError('Invalid road coordinate')
    for a,b,w in edges:
        if a not in graph or b not in graph or not math.isfinite(w) or w<0: raise ValueError('Invalid road edge')
        graph[a].append((b,w))
    snaps={}
    for camera,_,lat,lon in CAMERAS:
        point={'lat':lat,'lon':lon}
        n=min(nodes,key=lambda k:distance(point,nodes[k]))
        offset=distance(point,nodes[n])
        snaps[camera]={'node':n,'km':offset,'usable':offset<=MAX_SNAP_KM}
    return nodes,graph,snaps


def activate_osm(path=OSM_FILE):
    global ROAD_NODES,ROAD_GRAPH,OSM_SNAPS,OSM_ACTIVE
    payload=json.loads(path.read_text(encoding='utf-8'))
    ROAD_NODES,ROAD_GRAPH,OSM_SNAPS=build_osm_network(payload)
    OSM_ACTIVE=True
    road_route.cache_clear()
    print(f'Loaded local OSM network: {len(ROAD_NODES)} nodes',flush=True)
    for c,snap in OSM_SNAPS.items():
        print(f'{c}: road node offset {snap["km"]*1000:.0f} m'+(' (too far; unavailable)' if not snap['usable'] else ''),flush=True)

@lru_cache(maxsize=36)
def road_route(start,end):
    if OSM_ACTIVE:
        a,b=OSM_SNAPS.get(start),OSM_SNAPS.get(end)
        if not a or not b or not a['usable'] or not b['usable']: return None
        if start!=end and a['node']==b['node']: return None
        start,end=a['node'],b['node']
    found=shortest_path(ROAD_GRAPH,start,end)
    if found is None: return None
    nodes,km=found
    return {'nodes':nodes,'geometry':[ROAD_NODES[n] for n in nodes],'km':km}

def trajectory(path,vehicle):
    with connect(path) as db:
        rows=[dict(r) for r in db.execute('''SELECT d.*,c.name,c.lat,c.lon FROM detections d JOIN cameras c ON d.camera_id=c.id
        WHERE d.vehicle_id=? ORDER BY d.observed_at,d.id''',(vehicle,))]
    points=[r for r in rows if r['status']=='confirmed']; review=[r for r in rows if r['status']=='review']; segments=[]
    for a,b in zip(points,points[1:]):
        km=distance(a,b); seconds=(dt.datetime.fromisoformat(b['observed_at'])-dt.datetime.fromisoformat(a['observed_at'])).total_seconds()
        speed=km*3600/seconds if seconds>0 else None
        flag=(seconds<=0 and km>.001) or (speed is not None and speed>120)
        route=road_route(a['camera_id'],b['camera_id'])
        road_km=route['km'] if route else None
        road_speed=road_km*3600/seconds if road_km is not None and seconds>0 else None
        segments.append({'from':a['camera_id'],'to':b['camera_id'],'km':round(km,3),'seconds':seconds,
                         'speed_kmh':round(speed,1) if speed is not None else None,'flag':flag,
                         'road_km':round(road_km,3) if road_km is not None else None,
                         'road_speed_kmh':round(road_speed,1) if road_speed is not None else None,
                         'road_geometry':route['geometry'] if route else [],
                         'snap_from_m':round(OSM_SNAPS[a['camera_id']]['km']*1000) if OSM_ACTIVE else None,
                         'snap_to_m':round(OSM_SNAPS[b['camera_id']]['km']*1000) if OSM_ACTIVE else None,
                         'road_flag':bool(road_km is not None and ((seconds<=0 and road_km>.001) or (road_speed is not None and road_speed>120)))})
    elapsed=(dt.datetime.fromisoformat(points[-1]['observed_at'])-dt.datetime.fromisoformat(points[0]['observed_at'])).total_seconds() if len(points)>1 else 0
    return {'vehicle_id':vehicle,'points':points,'review':review,'segments':segments,
            'distance_km':round(sum(s['km'] for s in segments),2),'elapsed_minutes':round(elapsed/60,1),
            'flags':sum(s['flag'] for s in segments),
            'road_distance_km':round(sum(s['road_km'] for s in segments),2) if segments and all(s['road_km'] is not None for s in segments) else None,
            'road_flags':sum(s['road_flag'] for s in segments),
            'road_graph':[] if OSM_ACTIVE else [[ROAD_NODES[a],ROAD_NODES[b]] for a,b in ROAD_EDGES]}

HTML=r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CityTrack | Trajectory Lab</title><style>
*{box-sizing:border-box}body{margin:0;background:#0c1321;color:#e5edf9;font:14px system-ui,sans-serif}header{padding:20px 4vw;border-bottom:1px solid #26354b;display:flex;align-items:center;justify-content:space-between;gap:12px}h1{margin:0;font-size:21px}small,.muted{color:#a4b4cb}main{max-width:1300px;margin:auto;padding:26px 4vw}h2{font-size:17px;margin:0 0 12px}p{line-height:1.5}.tag{border:1px solid #35586b;border-radius:20px;padding:7px 12px;color:#7de4ce;font-size:12px}.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:20px 0}select,button{background:#18283e;color:#e5edf9;border:1px solid #38506d;border-radius:7px;padding:10px;font:inherit}button{cursor:pointer}button:hover{background:#29415a}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.card,.stat{background:#121e30;border:1px solid #28394e;border-radius:12px;padding:16px}.stat strong{display:block;font-size:25px;margin-top:8px}.layout{display:grid;grid-template-columns:1.65fr 1fr;gap:16px}.map{width:100%;display:block;background:#0c1828;border-radius:8px;border:1px solid #263c52;touch-action:none}.controls{display:flex;gap:8px;align-items:center;margin-top:12px;flex-wrap:wrap}.controls input{flex:1;min-width:80px;accent-color:#4ad7f0}.timeline{max-height:420px;overflow:auto}.event{padding:12px 0;border-bottom:1px solid #29394d}.event b{color:#76dff4}.event small{display:block;margin-top:4px}.warn{color:#ffbd7a}.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:12px;font-size:12px;color:#b6c7d9}.dot{display:inline-block;width:10px;height:10px;border-radius:100%;margin-right:5px}.wide{margin-top:16px;overflow:auto}table{width:100%;border-collapse:collapse;text-align:left;white-space:nowrap}td,th{padding:11px 8px;border-bottom:1px solid #29394d}th{color:#9bafc9;font-size:12px}footer{padding:15px 0;color:#99acc4;font-size:12px}@media(max-width:760px){.layout{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}}
.numbered-marker{display:grid;place-items:center;background:#41d9ef;color:#082132;border:2px solid #0b1422;border-radius:50%;font-weight:800;font-size:13px}.leaflet-container{font-family:system-ui,sans-serif}.leaflet-popup-content{color:#172235}.leaflet-popup-content p{margin:5px 0}</style><header><div><h1>CityTrack <span style="color:#66daef">/</span> Trajectory Lab</h1><small>Local development prototype</small></div><span class="tag">LOCAL · SYNTHETIC DATA</span></header>
<main><h2 style="font-size:25px">Vehicle journey reconstruction</h2><p class="muted">Inspect confirmed observations at fictional camera sites near Delhi. Dashed cyan lines show direct connections; purple lines estimate shortest paths on a locally cached OpenStreetMap driving network. Fictional camera points are snapped to nearby road nodes; the gaps are not included in road distance. Neither line proves the route travelled.</p>
<div class="toolbar"><label for="vehicle">Test vehicle</label><select id="vehicle"></select><button id="reload">Refresh</button><span id="error" class="warn" role="alert"></span></div>
<section class="card" style="margin-bottom:18px"><h2>Dynamic detection simulator</h2>
<p class="muted">Generate a new fictional vehicle journey. Each observation is saved locally. One simulated event every 2 seconds; observation timestamps use accelerated scenario time, not real travel time.</p>
<div class="controls"><label for="scenario">Scenario</label><select id="scenario"><option value="normal">Normal journey</option><option value="review">Low-confidence observation</option><option value="anomaly">Implausible speed</option></select><button id="newSim">Start new simulation</button><button id="pauseSim" disabled>Pause</button><button id="nextSim" disabled>Next detection</button></div>
<p id="simStatus" role="status" class="muted">Ready. Select a scenario and start.</p></section>
<section class="card" style="margin-bottom:18px"><h2>Import synthetic observations</h2>
<p class="muted">CSV or JSON array · maximum 256 KiB / 1000 rows · TEST- IDs and CAM-A through CAM-F only. Invalid batches are rejected without saving any rows.</p>
<div class="controls"><label for="importFile">Dataset</label><input type="file" id="importFile" accept=".csv,.json"><button id="importButton">Import dataset</button></div>
<p class="muted">Required fields: vehicle_id, camera_id, observed_at (ISO 8601 with timezone), confidence (0–1).</p><p id="importStatus" role="status" class="muted">Choose a sample file to begin.</p></section>
<div class="stats"><div class="stat">Confirmed sightings<strong id="count">–</strong></div><div class="stat">Point-to-point sum<strong id="distance">–</strong></div><div class="stat">Observed duration<strong id="duration">–</strong></div><div class="stat">Plausibility flags<strong id="flags">–</strong></div></div>
<section class="card" style="margin-bottom:18px"><h2>Phase 5B · Local OpenStreetMap reconstruction</h2><p class="muted">Dijkstra shortest distance · locally cached directed driving graph · no routing API. Road-node offsets over 500 m are rejected. Road distance and direct distance have different endpoints; their ratio is only illustrative. Road data © OpenStreetMap contributors.</p><div class="controls"><label><input type="checkbox" id="roadMode" checked> Show estimated network route</label><input type="checkbox" id="graphMode" hidden></div><div class="stats" style="margin-top:12px;margin-bottom:0"><div class="stat">Estimated network distance<strong id="roadDistance">–</strong></div><div class="stat">Network assessment flags<strong id="roadFlags">–</strong></div><div class="stat">Routed segments<strong id="routed">–</strong></div><div class="stat">Network / direct ratio<strong id="ratio">–</strong></div></div></section>
<div class="layout"><section class="card"><h2>Geographic observation map</h2><svg id="map" class="map" viewBox="0 0 680 440" aria-label="Synthetic camera coordinate map"></svg><div id="geo" hidden style="height:440px;border-radius:8px;background:#d7e0e8"></div><div class="controls"><button id="enableGeo">Enable street map</button><button id="fitGeo" hidden>Fit observations</button><span id="mapStatus" class="muted" role="status">Offline coordinate view. Internet needed for street map.</span></div><div class="controls"><button id="play">Play</button><button id="reset">Reset</button><input type="range" id="step" min="0" max="0" value="0" aria-label="Timeline position"><span id="position"></span></div><div class="legend"><span><i class="dot" style="background:#41d9ef"></i>Confirmed sighting</span><span><i class="dot" style="background:#f6a45e"></i>Flagged segment / excluded sighting</span><span><i class="dot" style="background:#72859d"></i>Other camera</span><span><i class="dot" style="background:#a78bfa"></i>Estimated OSM route (orange if flagged)</span></div></section>
<section class="card"><h2>Observation timeline <small>(UTC)</small></h2><div id="timeline" class="timeline"></div><h2 style="margin-top:18px">Excluded observations</h2><div id="review" class="muted"></div></section></div>
<section class="card wide"><h2>Segment quality</h2><table><thead><tr><th>From → To</th><th>Direct distance</th><th>Time gap</th><th>Minimum avg. speed</th><th>Direct assessment</th><th>Network distance</th><th>Network avg. speed</th><th>Network assessment</th><th>Road snap offsets (from / to)</th></tr></thead><tbody id="segments"></tbody></table><p class="muted">A 120 km/h demo threshold is used for both assessments. Network speeds are conditional on snapped road nodes and the cached graph; a flag means review is needed, not proof of an error or violation.</p></section>
<footer>SQLite database · Local routing · Optional online street map · Fictional camera sites and vehicle IDs only · Road data © <a style="color:#76dff4" href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a></footer></main>
<script>
const $=id=>document.getElementById(id);let cameras=[],data=null,timer=null,request=0;
const fmt=t=>new Date(t).toISOString().slice(0,19).replace('T',' ')+' UTC';
function el(tag,attrs,parent,text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;parent.append(n);return n}
let viewBounds=[77.182,28.598,77.229,28.632];
function updateBounds(){const pts=[...cameras,...(data?data.segments.flatMap(s=>s.road_geometry):[])];if(!pts.length)return;let w=Infinity,e=-Infinity,s=Infinity,n=-Infinity;for(const p of pts){w=Math.min(w,p.lon);e=Math.max(e,p.lon);s=Math.min(s,p.lat);n=Math.max(n,p.lat)}const mid=(s+n)/2,cos=Math.cos(mid*Math.PI/180);let width=Math.max(.005,e-w),height=Math.max(.005,n-s);const ratio=550/320;if(width*cos/height>ratio)height=width*cos/ratio;else width=height*ratio/cos;const x=(w+e)/2;viewBounds=[x-width/2,mid-height/2,x+width/2,mid+height/2]}
function xy(c){const [w,s,e,n]=viewBounds;return [65+(c.lon-w)/(e-w)*550,370-(c.lat-s)/(n-s)*320]}
function activeGeometry(i){const s=data.segments[i];return $('roadMode').checked && s.road_geometry.length?s.road_geometry:[data.points[i],data.points[i+1]]}
function positionAlong(path,f){if(path.length===1)return path[0];const lens=path.slice(1).map((b,i)=>{const a=path[i];return Math.hypot(b.lat-a.lat,(b.lon-a.lon)*Math.cos((a.lat+b.lat)*Math.PI/360))});let left=f*lens.reduce((a,b)=>a+b,0);for(let i=0;i<lens.length;i++){if(left<=lens[i]||i===lens.length-1){const a=path[i],b=path[i+1],t=lens[i]?Math.min(1,left/lens[i]):0;return {lat:a.lat+(b.lat-a.lat)*t,lon:a.lon+(b.lon-a.lon)*t}}left-=lens[i]}return path[path.length-1]}
function draw(){if(!data)return;if(geoMap){drawGeo();return;}const svg=$('map');svg.replaceChildren();for(let x=20;x<680;x+=40)el('line',{x1:x,y1:0,x2:x,y2:440,stroke:'#1a2b3d'},svg);for(let y=20;y<440;y+=40)el('line',{x1:0,y1:y,x2:680,y2:y,stroke:'#1a2b3d'},svg);
if($('graphMode').checked)for(const edge of data.road_graph)el('polyline',{points:edge.map(c=>xy(c).join(',')).join(' '),fill:'none',stroke:'#64748b','stroke-width':3,opacity:.6},svg);
const end=Number($('step').value);const p=data.points.slice(0,end+1);for(let i=1;i<p.length;i++){const [x,y]=xy(p[i-1]),[u,v]=xy(p[i]);el('line',{x1:x,y1:y,x2:u,y2:v,stroke:data.segments[i-1].flag?'#f6a45e':'#41d9ef','stroke-width':4,'stroke-dasharray':'9 5','stroke-linecap':'round'},svg)}
if($('roadMode').checked)for(let i=1;i<p.length;i++){const seg=data.segments[i-1];if(seg.road_geometry.length)el('polyline',{points:seg.road_geometry.map(c=>xy(c).join(',')).join(' '),fill:'none',stroke:seg.road_flag?'#f6a45e':'#a78bfa','stroke-width':5,'stroke-linejoin':'round','stroke-opacity':.9},svg)}
for(const c of cameras){const [x,y]=xy(c);el('circle',{cx:x,cy:y,r:7,fill:'#72859d',stroke:'#0b1422','stroke-width':2},svg);el('text',{x:x+12,y:y-13,fill:'#a9bad0','font-size':11},svg,c.name)}
p.forEach((c,i)=>{const [x,y]=xy(c);el('circle',{cx:x,cy:y,r:i===p.length-1?13:10,fill:'#41d9ef',stroke:'#0b1422','stroke-width':2},svg);el('text',{x:x,y:y+4,'text-anchor':'middle',fill:'#082132','font-size':11,'font-weight':700},svg,String(i+1))});if(moving && p.length && data.points[p.length]){const [x,y]=xy(positionAlong(activeGeometry(p.length-1),progress));el('circle',{cx:x,cy:y,r:6,fill:'#fff',stroke:'#41d9ef','stroke-width':3},svg)}el('text',{x:20,y:24,fill:'#93a8be','font-size':12},svg,'SYNTHETIC COORDINATE VIEW • NORTH ↑');$('position').textContent=p.length+' / '+data.points.length;
}
function stop(){if(timer!==null)cancelAnimationFrame(timer);timer=null;moving=false;progress=0;$('play').textContent='Play'}
function append(parent,tag,text,cls){const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;parent.append(n);return n}
async function get(url){const r=await fetch(url);if(!r.ok)throw Error('Request failed: '+r.status);return r.json()}
async function load(){stop();const id=++request;$('error').textContent='';try{const next=await get('/api/trajectory?vehicle='+encodeURIComponent($('vehicle').value));if(id!==request)return;data=next;updateBounds();$('count').textContent=data.points.length;$('distance').textContent=data.distance_km+' km';$('duration').textContent=data.elapsed_minutes+' min';$('flags').textContent=data.flags;$('roadDistance').textContent=data.road_distance_km===null?'N/A':data.road_distance_km+' km';$('roadFlags').textContent=data.road_flags;$('routed').textContent=data.segments.filter(s=>s.road_geometry.length).length+' / '+data.segments.length;$('ratio').textContent=data.road_distance_km===null||!data.distance_km?'N/A':(data.road_distance_km/data.distance_km).toFixed(2)+'×';$('step').max=Math.max(0,data.points.length-1);$('step').value=$('step').max;
$('timeline').replaceChildren();data.points.forEach((p,i)=>{const n=append($('timeline'),'div','','event');append(n,'b',(i+1)+'. '+p.name+' · '+p.camera_id);append(n,'small',fmt(p.observed_at)+' · '+p.model+' · '+Math.round(p.confidence*100)+'% confidence')});$('review').replaceChildren();if(!data.review.length)append($('review'),'p','None');data.review.forEach(p=>append($('review'),'p',p.name+' · '+fmt(p.observed_at)+' · '+Math.round(p.confidence*100)+'% confidence · pending review','warn'));
$('segments').replaceChildren();data.segments.forEach(s=>{const tr=append($('segments'),'tr','');[s.from+' → '+s.to,s.km+' km',(s.seconds/60).toFixed(1)+' min',s.speed_kmh===null?'N/A':s.speed_kmh+' km/h',s.flag?'Needs review':'Within demo threshold',s.road_km===null?'No route':s.road_km+' km',s.road_speed_kmh===null?'N/A':s.road_speed_kmh+' km/h',s.road_km===null?'Unavailable':s.road_flag?'Needs review':'Within demo threshold',s.snap_from_m===null?'N/A':s.snap_from_m+' m / '+s.snap_to_m+' m'].forEach((v,i)=>append(tr,'td',v,(i===4&&s.flag||i===7&&s.road_flag)?'warn':''))});if(geoMap){lastGeoKey='';fitGeo()}draw()}catch(e){$('error').textContent=e.message}}
let geoMap=null,geoLayer=null,mover=null,moving=false,progress=0,lastGeoKey='',loadingGeo=false,geoGeneration=0;
const ll=p=>[p.lat,p.lon];
function popup(p,index){const n=document.createElement('div');append(n,'strong',(index==null?'':(index+1)+'. ')+p.name+' · '+(p.camera_id||p.id));append(n,'p','Synthetic camera site');append(n,'div',p.lat.toFixed(6)+', '+p.lon.toFixed(6));if(p.observed_at){append(n,'div',fmt(p.observed_at));append(n,'div',Math.round(p.confidence*100)+'% confidence · '+p.status)}return n}
function fitGeo(){if(!geoMap)return;const points=data&&data.points.length?[...data.points,...data.segments.flatMap(s=>s.road_geometry)]:cameras;if(points.length)geoMap.fitBounds(points.map(ll),{padding:[35,35],maxZoom:15})}
function drawGeo(){const end=Number($('step').value),p=data.points.slice(0,end+1),key=data.vehicle_id+':'+end+':'+data.points.length+':'+$('roadMode').checked+':'+$('graphMode').checked;
if(key!==lastGeoKey){lastGeoKey=key;geoLayer.clearLayers();mover=null;if($('graphMode').checked)for(const edge of data.road_graph)L.polyline(edge.map(ll),{color:'#64748b',weight:3,opacity:.55,interactive:false}).addTo(geoLayer);for(const c of cameras)L.circleMarker(ll(c),{radius:6,color:'#475569',fillColor:'#64748b',fillOpacity:1}).bindPopup(popup(c)).addTo(geoLayer);
for(let i=1;i<p.length;i++)L.polyline([ll(p[i-1]),ll(p[i])],{color:data.segments[i-1].flag?'#e87919':'#0891b2',weight:4,dashArray:'8 7'}).addTo(geoLayer);
if($('roadMode').checked)for(let i=1;i<p.length;i++){const seg=data.segments[i-1];if(seg.road_geometry.length)L.polyline(seg.road_geometry.map(ll),{color:seg.road_flag?'#e87919':'#7c3aed',weight:5,opacity:.9}).addTo(geoLayer)}
p.forEach((point,i)=>{const icon=L.divIcon({className:'numbered-marker',html:String(i+1),iconSize:[28,28],iconAnchor:[14,14]});L.marker(ll(point),{icon}).bindPopup(popup(point,i)).addTo(geoLayer)});
for(const point of data.review)L.circleMarker(ll(point),{radius:7,color:'#b45309',fillColor:'#fb923c',fillOpacity:.8}).bindPopup(popup(point)).addTo(geoLayer)}
if(moving && p.length && data.points[p.length]){const pos=ll(positionAlong(activeGeometry(p.length-1),progress));if(!mover)mover=L.circleMarker(pos,{radius:7,color:'#0e7490',fillColor:'white',fillOpacity:1,interactive:false}).addTo(geoLayer);else mover.setLatLng(pos)}else if(mover){geoLayer.removeLayer(mover);mover=null}
$('position').textContent=p.length+' / '+data.points.length;}
function offline(){geoGeneration++;if(geoMap)geoMap.remove();geoMap=null;geoLayer=null;lastGeoKey='';mover=null;$('geo').hidden=true;$('map').style.display='block';$('fitGeo').hidden=true;$('enableGeo').textContent='Enable street map';$('mapStatus').textContent='Offline coordinate view. Internet needed for street map.';draw()}
function asset(tag,attributes){return new Promise((resolve,reject)=>{const node=document.createElement(tag);Object.assign(node,attributes);const timeout=setTimeout(()=>{node.remove();reject(Error('Map library download timed out'))},12000);node.onload=()=>{clearTimeout(timeout);resolve()};node.onerror=()=>{clearTimeout(timeout);node.remove();reject(Error('Map library could not load'))};document.head.append(node)})}
let leafletReady=false;
$('enableGeo').onclick=async()=>{if(geoMap){offline();return}if(loadingGeo)return;loadingGeo=true;$('enableGeo').disabled=true;$('mapStatus').textContent='Loading online map…';try{if(!leafletReady){await Promise.all([asset('link',{rel:'stylesheet',href:'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',integrity:'sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=',crossOrigin:'anonymous'}),asset('script',{src:'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',integrity:'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=',crossOrigin:'anonymous'})]);leafletReady=true}if(!data)throw Error('Observations have not loaded yet');$('map').style.display='none';$('geo').hidden=false;geoMap=L.map('geo').setView([28.62,77.20],13);const generation=++geoGeneration;const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'});tiles.on('tileerror',()=>{if(generation===geoGeneration)$('mapStatus').textContent='Some map tiles failed; you can switch back to offline view.'});tiles.addTo(geoMap);geoLayer=L.layerGroup().addTo(geoMap);lastGeoKey='';fitGeo();drawGeo();$('fitGeo').hidden=false;$('enableGeo').textContent='Switch to offline view';$('mapStatus').textContent='Online basemap · local OSM shortest path estimate';}catch(e){offline();$('mapStatus').textContent=e.message+'; offline view remains available.'}finally{loadingGeo=false;$('enableGeo').disabled=false}};
$('fitGeo').onclick=fitGeo;$('roadMode').onchange=()=>{stop();draw()};$('graphMode').onchange=()=>{lastGeoKey='';draw()};
$('step').oninput=()=>{stop();draw()};$('reset').onclick=()=>{stop();$('step').value=0;draw()};$('play').onclick=()=>{if(!data||data.points.length<2)return;if(timer!==null){stop();draw();return}if(+$('step').value>=+$('step').max)$('step').value=0;moving=true;progress=0;draw();$('play').textContent='Pause';let start=performance.now();function frame(now){progress=Math.min(1,(now-start)/850);if(progress===1){$('step').value=+$('step').value+1;start=now;progress=0;if(+$('step').value>=+$('step').max){stop();draw();return}}draw();timer=requestAnimationFrame(frame)}timer=requestAnimationFrame(frame)};$('vehicle').onchange=()=>{pauseSimulation();load()};$('reload').onclick=load;
let sim=null, simRunning=false, simBusy=false, simTimer=null;
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await r.json();if(!r.ok)throw Error(result.error||'Simulation request failed');return result}
function simUI(message){$('newSim').disabled=simBusy;$('pauseSim').disabled=simBusy||!sim||sim.complete;$('nextSim').disabled=simBusy||simRunning||!sim||sim.complete;$('pauseSim').textContent=simRunning?'Pause':'Resume';$('simStatus').textContent=message||(!sim?'Ready.':sim.vehicle_id+' · '+sim.emitted+' / '+sim.total+' observations generated · '+(sim.complete?'Completed':simRunning?'Running':'Paused'));}
function pauseSimulation(){simRunning=false;clearTimeout(simTimer);simTimer=null;simUI()}
function scheduleSim(){clearTimeout(simTimer);if(simRunning&&sim&&!sim.complete)simTimer=setTimeout(tickSim,2000)}
async function showSimulation(){const select=$('vehicle');if(!Array.from(select.options).some(o=>o.value===sim.vehicle_id)){const o=append(select,'option',sim.vehicle_id+' — Synthetic test car');o.value=sim.vehicle_id}select.value=sim.vehicle_id;await load()}
async function tickSim(){if(simBusy||!sim||sim.complete)return;simBusy=true;simUI();try{sim=await post('/api/sim/step',{vehicle_id:sim.vehicle_id,expected:sim.emitted});if($('vehicle').value===sim.vehicle_id||simRunning)await showSimulation();if(sim.complete)pauseSimulation()}catch(e){pauseSimulation();simBusy=false;simUI(e.message+' — Resume to retry.');return}finally{simBusy=false}simUI();scheduleSim()}
$('newSim').onclick=async()=>{pauseSimulation();simBusy=true;simUI();try{sim=await post('/api/sim/start',{scenario:$('scenario').value});simRunning=true;await showSimulation()}catch(e){pauseSimulation();simBusy=false;simUI(e.message);return}finally{simBusy=false}simUI();scheduleSim()};
$('pauseSim').onclick=()=>{if(simRunning)pauseSimulation();else if(sim&&!sim.complete){simRunning=true;showSimulation().then(()=>{simUI();scheduleSim()})}};
$('nextSim').onclick=async()=>{if(sim&&!sim.complete){await showSimulation();await tickSim()}};
$('importButton').onclick=async()=>{const file=$('importFile').files[0];if(!file){$('importStatus').textContent='Choose a CSV or JSON file first.';return}if(file.size>262144){$('importStatus').textContent='File exceeds 256 KiB.';return}if(simBusy){$('importStatus').textContent='Wait for the current simulation step to finish.';return}pauseSimulation();simBusy=true;simUI();$('importButton').disabled=true;$('importStatus').textContent='Validating dataset…';try{const format=file.name.split('.').pop().toLowerCase();const result=await post('/api/import',{format,content:await file.text()});const init=await get('/api/demo');const select=$('vehicle');select.replaceChildren();for(const v of init.vehicles){const o=append(select,'option',v.vehicle_id+' — '+v.model);o.value=v.vehicle_id}select.value=result.vehicles[0];await load();$('importStatus').textContent=`Saved ${result.inserted} new observations (${result.confirmed} confirmed, ${result.review} for review); skipped ${result.duplicates} duplicates. Select a vehicle to explore.`}catch(e){$('importStatus').textContent=e.message}finally{simBusy=false;$('importButton').disabled=false;simUI()}};
(async()=>{try{const init=await get('/api/demo');cameras=init.cameras;for(const v of init.vehicles){const o=append($('vehicle'),'option',v.vehicle_id+' — '+v.model);o.value=v.vehicle_id}await load()}catch(e){$('error').textContent=e.message}})();
</script></html>'''

class Handler(BaseHTTPRequestHandler):
    def respond(self, body, content_type='application/json; charset=utf-8', code=200):
        payload=body.encode('utf-8') if isinstance(body,str) else json.dumps(body).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=='/': return self.respond(HTML,'text/html; charset=utf-8')
        if parsed.path=='/api/demo':
            with connect(self.server.db_path) as db:
                cameras=[dict(r) for r in db.execute('SELECT * FROM cameras ORDER BY id')]
                vehicles=[dict(r) for r in db.execute('SELECT DISTINCT vehicle_id,model FROM detections ORDER BY vehicle_id')]
            return self.respond({'cameras':cameras,'vehicles':vehicles})
        if parsed.path=='/api/trajectory':
            vehicle=parse_qs(parsed.query).get('vehicle',[''])[0]
            with connect(self.server.db_path) as db:
                exists=db.execute('SELECT 1 FROM detections WHERE vehicle_id=? LIMIT 1',(vehicle,)).fetchone()
            if not exists:return self.respond({'error':'Unknown synthetic vehicle'},code=404)
            return self.respond(trajectory(self.server.db_path,vehicle))
        return self.respond({'error':'Not found'},code=404)

    def do_POST(self):
        # Only accept same-origin browser mutations with a JSON body.
        if self.headers.get('Origin') not in (None, 'http://127.0.0.1:'+str(self.server.server_port), 'http://localhost:'+str(self.server.server_port)):
            return self.respond({'error':'Origin not allowed'},code=403)
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
            return self.respond({'error':'Expected JSON'},code=415)
        try:
            size=int(self.headers.get('Content-Length','0'))
            limit= 2*1024*1024 if self.path=='/api/import' else 4096
            if not 0<size<=limit: raise ValueError('Invalid body size')
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict): raise ValueError('Expected JSON object')
            if self.path=='/api/import': return self.respond(import_observations(self.server.db_path,body.get('format'),body.get('content')),code=200)
            if self.path=='/api/sim/start': return self.respond(create_sim(self.server.db_path,body.get('scenario')),code=201)
            if self.path=='/api/sim/step': return self.respond(advance_sim(self.server.db_path,body.get('vehicle_id'),body.get('expected')))
            return self.respond({'error':'Not found'},code=404)
        except (ValueError,UnicodeError) as exc:
            return self.respond({'error':str(exc)},code=400)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)/'test.db'; initialize(self.path)
    def tearDown(self):self.temp.cleanup()
    def test_confirmed_order_and_review(self):
        t=trajectory(self.path,'DEMO-001'); self.assertEqual([p['camera_id'] for p in t['points']],['CAM-A','CAM-B','CAM-C','CAM-D']); self.assertEqual(len(t['review']),1); self.assertEqual(t['flags'],0); self.assertEqual(t['elapsed_minutes'],13)
    def test_anomaly(self):self.assertGreater(trajectory(self.path,'DEMO-003')['flags'],0)
    def test_idempotent_seed(self):
        initialize(self.path); self.assertEqual(len(trajectory(self.path,'DEMO-001')['points']),4)
    def test_distance(self):self.assertAlmostEqual(distance({'lat':0,'lon':0},{'lat':0,'lon':1}),111.195,places=2)
    def test_geographic_coordinates(self):
        t=trajectory(self.path,'DEMO-001'); self.assertTrue(all(28.60<=p['lat']<=28.65 and 77.18<=p['lon']<=77.24 for p in t['points']))
    def test_sim_normal(self):
        run=create_sim(self.path,'normal'); v=run['vehicle_id']; self.assertEqual(len(trajectory(self.path,v)['points']),1)
        while not run['complete']: run=advance_sim(self.path,v,run['emitted'])
        t=trajectory(self.path,v); self.assertEqual(len(t['points']),4); self.assertEqual(t['flags'],0); self.assertEqual(t['elapsed_minutes'],13)
        self.assertEqual(advance_sim(self.path,v,run['emitted']),run)
    def test_sim_review(self):
        run=create_sim(self.path,'review'); v=run['vehicle_id']
        while not run['complete']: run=advance_sim(self.path,v,run['emitted'])
        t=trajectory(self.path,v); self.assertEqual(len(t['points']),4); self.assertEqual(len(t['review']),1)
    def test_sim_anomaly(self):
        run=create_sim(self.path,'anomaly'); v=run['vehicle_id']
        run=advance_sim(self.path,v,1); self.assertGreater(trajectory(self.path,v)['flags'],0)
    def test_sim_retry(self):
        run=create_sim(self.path,'normal'); v=run['vehicle_id']; next_run=advance_sim(self.path,v,1)
        self.assertEqual(advance_sim(self.path,v,1),next_run); self.assertEqual(len(trajectory(self.path,v)['points']),2)
    def test_sim_persistence(self):
        run=create_sim(self.path,'normal'); initialize(self.path); self.assertEqual(advance_sim(self.path,run['vehicle_id'],1)['emitted'],2)
        self.assertNotEqual(create_sim(self.path,'normal')['vehicle_id'],run['vehicle_id'])
    def test_sim_invalid(self):
        with self.assertRaises(ValueError):create_sim(self.path,'bad')
        with self.assertRaises(ValueError):advance_sim(self.path,'missing',1)
        with self.assertRaises(ValueError):advance_sim(self.path,'missing',True)
    def test_empty(self):self.assertEqual(trajectory(self.path,'NONE')['points'],[])

    def records(self):
        return [dict(vehicle_id='TEST-001',camera_id=c,observed_at=t,confidence=q) for c,t,q in [('CAM-C','2026-01-01T09:08:00Z',.98),('CAM-A','2026-01-01T14:30:00+05:30',.99),('CAM-B','2026-01-01T09:04:00Z',.51)]]
    def test_import_json_order(self):
        r=import_observations(self.path,'json',json.dumps(self.records()));self.assertEqual((r['inserted'],r['confirmed'],r['review']),(3,2,1))
        t=trajectory(self.path,'TEST-001');self.assertEqual([p['camera_id'] for p in t['points']],['CAM-A','CAM-C']);self.assertEqual(t['elapsed_minutes'],8)
    def test_import_csv(self):
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=sorted(IMPORT_FIELDS));writer.writeheader();writer.writerows(self.records());self.assertEqual(import_observations(self.path,'csv',stream.getvalue())['inserted'],3)
    def test_import_duplicates(self):
        rows=self.records();import_observations(self.path,'json',json.dumps(rows));rows[1]['observed_at']='2026-01-01T09:00:00Z';r=import_observations(self.path,'json',json.dumps(rows));self.assertEqual((r['inserted'],r['duplicates']),(0,3))
    def test_import_atomic_invalid(self):
        rows=self.records();rows[-1]['camera_id']='UNKNOWN'
        with self.assertRaises(ValueError):import_observations(self.path,'json',json.dumps(rows))
        self.assertEqual(trajectory(self.path,'TEST-001')['points'],[])
    def test_import_conflict_rolls_back(self):
        rows=self.records();import_observations(self.path,'json',json.dumps(rows));extra=dict(rows[0],vehicle_id='TEST-002');rows[0]['confidence']=.2
        with self.assertRaises(ValueError):import_observations(self.path,'json',json.dumps([extra]+rows))
        self.assertEqual(trajectory(self.path,'TEST-002')['points'],[])
    def test_import_invalid_values(self):
        for key,value in [('confidence','NaN'),('confidence',1.5),('observed_at','2026-01-01T09:00:00'),('vehicle_id','OTHER'),('confidence',True)]:
            with self.assertRaises(ValueError):import_observations(self.path,'json',json.dumps([dict(self.records()[0],**{key:value})]))
    def test_import_invalid_shape(self):
        for fmt,body in [('json','{}'),('csv','bad,header\n1,2'),('json','[]'),('txt','stuff')]:
            with self.assertRaises(ValueError):import_observations(self.path,fmt,body)

    def test_route_shortest(self):
        g={'A':[('B',2),('C',8)],'B':[('C',2)],'C':[]}
        self.assertEqual(shortest_path(g,'A','C'),(['A','B','C'],4))
    def test_route_disconnected(self):
        self.assertIsNone(shortest_path({'A':[],'B':[]},'A','B'))
        self.assertIsNone(shortest_path(ROAD_GRAPH,'missing','CAM-A'))
    def test_route_same_camera(self):
        self.assertEqual(road_route('CAM-A','CAM-A')['km'],0)
    def test_route_endpoints_and_distances(self):
        t=trajectory(self.path,'DEMO-001')
        self.assertGreater(t['road_distance_km'],t['distance_km'])
        for a,b,seg in zip(t['points'],t['points'][1:],t['segments']):
            self.assertEqual(seg['road_geometry'][0],ROAD_NODES[a['camera_id']])
            self.assertEqual(seg['road_geometry'][-1],ROAD_NODES[b['camera_id']])
            self.assertGreaterEqual(seg['road_km'],seg['km'])
    def test_route_flags(self):
        self.assertGreater(trajectory(self.path,'DEMO-003')['road_flags'],0)
        self.assertEqual(trajectory(self.path,'DEMO-001')['road_flags'],0)
    def test_route_single_observation(self):
        run=create_sim(self.path,'normal');t=trajectory(self.path,run['vehicle_id'])
        self.assertIsNone(t['road_distance_km']);self.assertEqual(t['segments'],[])
    def test_route_all_pairs(self):
        for a in CAMERAS:
            for b in CAMERAS:
                route=road_route(a[0],b[0]);self.assertIsNotNone(route)
                self.assertAlmostEqual(route['km'],road_route(b[0],a[0])['km'])

class OSMTests(unittest.TestCase):
    def test_directed_network_and_snap(self):
        nodes={str(i):{'lat':lat,'lon':lon} for i,(_,_,lat,lon) in enumerate(CAMERAS)}
        payload={'source':'OpenStreetMap','bbox':list(OSM_BBOX),'nodes':nodes,'edges':[['0','1',1.5],['1','2',2.0]]}
        n,g,s=build_osm_network(payload)
        self.assertEqual(s['CAM-A']['node'],'0')
        self.assertEqual(s['CAM-A']['km'],0)
        self.assertEqual(shortest_path(g,'0','2'),(['0','1','2'],3.5))
        self.assertIsNone(shortest_path(g,'2','0'))
    def test_far_snap_rejected(self):
        nodes={'x':{'lat':28.58,'lon':77.165}}
        _,_,snaps=build_osm_network({'source':'OpenStreetMap','bbox':list(OSM_BBOX),'nodes':nodes,'edges':[['x','x',0]]})
        self.assertFalse(snaps['CAM-A']['usable'])
    def test_invalid_edges(self):
        with self.assertRaises(ValueError):
            build_osm_network({'source':'OpenStreetMap','bbox':list(OSM_BBOX),'nodes':{'a':{'lat':0,'lon':0}},'edges':[['a','b',1]]})
    def test_real_mode_routes_from_fixture(self):
        global OSM_ACTIVE,ROAD_NODES,ROAD_GRAPH,OSM_SNAPS
        old=(OSM_ACTIVE,ROAD_NODES,ROAD_GRAPH,OSM_SNAPS)
        try:
            nodes={str(i):{'lat':lat,'lon':lon} for i,(_,_,lat,lon) in enumerate(CAMERAS)}
            payload={'source':'OpenStreetMap','bbox':list(OSM_BBOX),'nodes':nodes,'edges':[['0','1',1.5],['1','2',2.0]]}
            ROAD_NODES,ROAD_GRAPH,OSM_SNAPS=build_osm_network(payload);OSM_ACTIVE=True;road_route.cache_clear()
            self.assertEqual(road_route('CAM-A','CAM-C')['km'],3.5)
            self.assertIsNone(road_route('CAM-C','CAM-A'))
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'test.db';initialize(path);t=trajectory(path,'DEMO-001')
                self.assertEqual(t['segments'][0]['snap_from_m'],0)
                self.assertIsNone(t['road_distance_km']);self.assertEqual(t['road_graph'],[])
        finally:
            OSM_ACTIVE,ROAD_NODES,ROAD_GRAPH,OSM_SNAPS=old;road_route.cache_clear()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8000);parser.add_argument('--test',action='store_true');parser.add_argument('--download-osm',action='store_true');args=parser.parse_args()
    if args.test:unittest.main(argv=['trajectory_osm.py']);raise SystemExit
    if args.download_osm:
        try: download_osm()
        except Exception as exc: parser.exit(1,f'OSM download failed: {exc}\nInstall osmnx 2.x and check internet access.\n')
        raise SystemExit
    try: activate_osm()
    except (OSError,ValueError,KeyError,TypeError) as exc: parser.exit(1,f'Could not load local OSM graph: {exc}\nRun python trajectory_osm.py --download-osm first.\n')
    initialize();server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.db_path=DB
    print(f'CityTrack demo: http://127.0.0.1:{args.port}',flush=True);print(f'Database: {DB}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
