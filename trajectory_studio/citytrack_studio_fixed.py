"""Phase 11: map-first UI for the local synthetic CityTrack lab.
Place beside citytrack_app.py, trajectory_osm.py and trajectory_analytics.py.
Run: python citytrack_studio.py | Tests: python citytrack_studio.py --test
"""
import argparse
import sqlite3
import unittest
import citytrack_app as app

CSS = '''
:root{color-scheme:dark;--bg:#0b111c;--panel:#111d2c;--line:#27384b;--muted:#a6b9cf;--accent:#49d9ea}
body{background:var(--bg);font-size:13px}button,select,input{font-size:13px}button:disabled{opacity:.45;cursor:not-allowed}button:focus-visible,select:focus-visible,a:focus-visible,summary:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:3px}a{color:var(--accent)}[hidden]{display:none!important}
.studio-header{height:65px;padding:10px 22px;gap:18px;background:#101927;position:relative} .studio-header h1{font-size:19px;letter-spacing:-.5px}.studio-header small{font-size:11px}.studio-nav{display:flex;align-items:center;gap:8px;margin-left:auto}.studio-nav a{padding:9px 13px;border:1px solid transparent;text-decoration:none;border-radius:7px;color:#b3c3d6}.studio-nav a.active{color:var(--accent);border-color:#315161;background:#132b39}.studio-header .tag{white-space:nowrap;font-size:10px}
main.studio{max-width:none;margin:0;padding:14px 18px 0}.workspace{display:grid;grid-template-columns:280px minmax(0,1fr) 292px;gap:12px;min-height:610px;height:calc(100dvh - 87px);align-items:stretch}.workspace.collapsed{grid-template-columns:minmax(0,1fr) 292px}.workspace.collapsed .sidebar{display:none}.panel{background:var(--panel);border:1px solid var(--line);border-radius:11px;min-width:0}.sidebar,.observations{overflow:auto;padding:15px;scrollbar-width:thin}.eyebrow{color:var(--accent);font-size:10px;letter-spacing:1.7px;font-weight:700;text-transform:uppercase}.panel h2{font-size:15px;margin:7px 0 12px}.panel h3{font-size:13px;margin:0 0 10px}.section-divider{border-top:1px solid var(--line);padding-top:14px;margin-top:15px}.sidebar label{display:block;margin:0 0 6px;color:var(--muted)}.sidebar select{width:100%;min-width:0}.sidebar button{padding:8px 10px}.primary{background:#125364;border-color:#237c89;color:#f0ffff}.primary:hover{background:#176b7b}.sidebar .controls{margin-top:8px;gap:6px}.sidebar p{font-size:12px;margin:8px 0;overflow-wrap:anywhere}.sidebar details summary{cursor:pointer;font-weight:650;color:#dce8f6}.sidebar input[type=file]{width:100%;max-width:100%;font-size:12px;margin:8px 0}.sidebar input[type=file]::file-selector-button{background:#1b3044;border:1px solid #39516a;color:#e5edf9;border-radius:6px;padding:7px;margin-right:5px}.sidebar .checkline{display:flex;align-items:center;gap:8px;color:#dce8f6;margin:0}.checkline input{accent-color:var(--accent)}
.center{display:flex;flex-direction:column;min-width:0;gap:10px;min-height:0}.map-heading{display:flex;align-items:center;gap:8px;justify-content:space-between;flex-wrap:wrap}.map-heading h2{font-size:17px;margin:0}.map-heading button{padding:7px 10px}.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.kpi{border:1px solid var(--line);border-radius:9px;background:var(--panel);padding:9px 10px;min-width:0}.kpi span{display:block;color:var(--muted);font-size:11px}.kpi strong{display:block;font-size:clamp(17px,1.5vw,25px);margin-top:4px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.kpi.route strong{color:#bba6ff}.map-panel{flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden;padding:10px;gap:8px}.map-stage{position:relative;flex:1;min-height:260px;background:#0c1828;border:1px solid var(--line);border-radius:8px;overflow:hidden}.map-stage #map,.map-stage #geo{width:100%;height:100%!important;position:absolute;inset:0;border:0;border-radius:0}.map-panel .controls{margin:0;gap:7px}.map-panel button{padding:7px 10px}.map-panel .muted{font-size:11px}.map-panel .legend{margin:0;font-size:10px;gap:8px 12px}.playback{padding:8px 0 0;border-top:1px solid var(--line)}.playback input{min-width:60px}.playback #position{font-variant-numeric:tabular-nums;white-space:nowrap}.observations .timeline{max-height:none}.observations .event{padding:11px 0}.observations .event small{font-size:11px;line-height:1.6}.observations #review p{font-size:12px;overflow-wrap:anywhere}.observations .muted{font-size:12px}.wide{padding:14px;margin:12px 0 0}.wide summary{cursor:pointer;font-size:14px;font-weight:650}.table-scroll{overflow:auto;margin-top:10px}.wide p{font-size:12px}footer{padding:10px 0 14px;font-size:11px}.note{font-size:11px;color:var(--muted);line-height:1.5;margin:0}.status-line{font-size:11px;overflow-wrap:anywhere}
@media(min-width:1500px){.workspace{grid-template-columns:300px minmax(0,1fr) 320px}.workspace.collapsed{grid-template-columns:minmax(0,1fr) 320px}}
@media(max-width:1100px){.workspace{grid-template-columns:240px minmax(0,1fr);height:auto;min-height:0}.workspace.collapsed{grid-template-columns:minmax(0,1fr)}.observations{grid-column:1/-1;max-height:320px}.center{min-height:660px}.sidebar{max-height:720px}}
@media(max-width:650px){.studio-header{height:auto;flex-wrap:wrap;padding:12px}.studio-nav{margin:0}.studio-header .tag{margin-left:auto}main.studio{padding:10px}.workspace{display:flex;flex-direction:column}.center{order:-1;min-height:580px}.sidebar{max-height:none}.observations{max-height:none}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.map-stage{min-height:290px}.map-heading h2{font-size:15px}.map-panel .controls{flex-wrap:wrap}}
'''

# Reuse the exact existing frontend event handlers and API calls; only layout changes.
BASE = app.routes.HTML
OLD_STYLE = BASE.split('<style>',1)[1].split('</style>',1)[0]
OLD_SCRIPT = BASE.split('<script>',1)[1].split('</script>',1)[0]
BODY = '''<header class="studio-header"><div><h1>CityTrack <span style="color:#49d9ea">/</span> Trajectory Studio</h1><small>Local development · Synthetic observations</small></div><nav class="studio-nav" aria-label="Main navigation"><a href="/" class="active" aria-current="page">Trajectory map</a><a href="/analytics">Analytics dashboard</a></nav><span class="tag">LOCAL · SYNTHETIC DATA</span></header>
<main class="studio"><div class="workspace" id="workspace">
<aside class="panel sidebar" id="sidebar" aria-label="Journey controls"><div class="eyebrow">Workspace</div><h2>Journey controls</h2><label for="vehicle">Synthetic vehicle</label><select id="vehicle"></select><div class="controls"><button id="reload">Refresh journey</button></div><p id="error" class="warn" role="alert"></p>
<div class="section-divider"><h3>Detection simulator</h3><label for="scenario">Scenario</label><select id="scenario"><option value="normal">Normal journey</option><option value="review">Low-confidence observation</option><option value="anomaly">Implausible speed</option></select><div class="controls"><button class="primary" id="newSim">Start new simulation</button><button id="pauseSim" disabled>Pause</button><button id="nextSim" disabled>Next detection</button></div><p id="simStatus" role="status" class="muted">Ready. Select a scenario and start.</p><p class="muted">One synthetic event every 2 seconds; timestamps use accelerated scenario time.</p></div>
<div class="section-divider"><details><summary>Import synthetic observations</summary><p class="muted">CSV / JSON · 256 KiB / 1,000 rows · TEST- IDs and CAM-A to CAM-F only. Invalid batches are rejected.</p><label for="importFile">Dataset</label><input type="file" id="importFile" accept=".csv,.json"><button id="importButton">Import dataset</button><p class="muted">Required: vehicle_id, camera_id, observed_at (ISO 8601 with timezone), confidence (0–1).</p><p id="importStatus" class="muted" role="status">Choose a sample file to begin.</p></details></div>
<div class="section-divider"><h3>Map layers</h3><label class="checkline"><input type="checkbox" id="roadMode" checked> Estimated network route</label><input type="checkbox" id="graphMode" hidden><p class="muted">Dijkstra · cached directed OSM graph. Road-node offsets over 500 m are rejected.</p></div>
<div class="section-divider"><div class="eyebrow">About this lab</div><p class="muted">Fictional camera sites and vehicle IDs only. Routes are possible historical paths, not verified movement or future predictions.</p></div></aside>
<section class="center" aria-label="Journey map workspace"><div class="map-heading"><h2>Vehicle journey reconstruction</h2><button id="toggleSidebar" aria-controls="sidebar" aria-expanded="true">Hide controls</button></div>
<div class="kpis"><div class="kpi"><span>Confirmed sightings</span><strong id="count">–</strong></div><div class="kpi"><span>Direct distance</span><strong id="distance">–</strong></div><div class="kpi route"><span>Estimated road distance</span><strong id="roadDistance">–</strong></div><div class="kpi"><span>Observed duration</span><strong id="duration">–</strong></div><div class="kpi"><span>Direct flags</span><strong id="flags">–</strong></div><div class="kpi"><span>Network flags</span><strong id="roadFlags">–</strong></div><div class="kpi"><span>Routed segments</span><strong id="routed">–</strong></div><div class="kpi"><span>Network / direct ratio</span><strong id="ratio">–</strong></div></div>
<section class="panel map-panel"><div class="controls"><button class="primary" id="enableGeo">Enable street map</button><button id="fitGeo" hidden>Fit observations</button><span id="mapStatus" class="muted" role="status">Offline coordinate view. Internet needed for street map.</span></div><div class="map-stage"><svg id="map" class="map" viewBox="0 0 680 440" aria-label="Synthetic camera coordinate map"></svg><div id="geo" hidden style="background:#d7e0e8"></div></div><div class="controls playback"><button class="primary" id="play">Play</button><button id="reset">Reset</button><input type="range" id="step" min="0" max="0" value="0" aria-label="Timeline position"><span id="position"></span></div><div class="legend"><span><i class="dot" style="background:#41d9ef"></i>Confirmed / direct</span><span><i class="dot" style="background:#a78bfa"></i>Estimated road route</span><span><i class="dot" style="background:#f6a45e"></i>Review / flagged</span><span><i class="dot" style="background:#72859d"></i>Other camera</span></div></section>
<p class="note">Estimated road distance excludes gaps between fictional cameras and snapped road nodes; direct and road endpoints differ. Neither path proves the route travelled.</p></section>
<aside class="panel observations" aria-label="Observation timeline"><div class="eyebrow">Journey evidence · UTC</div><h2>Observation timeline</h2><div id="timeline" class="timeline"></div><div class="section-divider"><h3>Excluded observations</h3><div id="review" class="muted"></div></div></aside></div>
<details class="panel wide"><summary>Segment quality · distances, speeds and road snap offsets</summary><div class="table-scroll"><table><thead><tr><th>From → To</th><th>Direct distance</th><th>Time gap</th><th>Minimum avg. speed</th><th>Direct assessment</th><th>Network distance</th><th>Network avg. speed</th><th>Network assessment</th><th>Road snap offsets (from / to)</th></tr></thead><tbody id="segments"></tbody></table></div><p class="muted">A 120 km/h demo threshold is used for both assessments. Network speeds depend on snapped road nodes and the cached graph; a flag means review is needed, not proof of a violation.</p></details>
<footer>SQLite · Local routing · Optional online street map · Road data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a></footer></main>'''
EXTRA_JS = '''
$('toggleSidebar').onclick=()=>{const collapsed=$('workspace').classList.toggle('collapsed');$('toggleSidebar').setAttribute('aria-expanded',String(!collapsed));$('toggleSidebar').textContent=collapsed?'Show controls':'Hide controls';if(geoMap)requestAnimationFrame(()=>geoMap.invalidateSize())};
if(typeof ResizeObserver!=='undefined'){new ResizeObserver(()=>{if(geoMap)geoMap.invalidateSize({pan:false})}).observe(document.querySelector('.map-stage'))}
'''
app.MAP_PAGE = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CityTrack | Trajectory Studio</title><style>'+OLD_STYLE+CSS+'</style></head><body>'+BODY+'<script>'+OLD_SCRIPT+EXTRA_JS+'</script></body></html>'

class StudioTests(app.IntegrationTests):
    def test_studio_layout_served(self):
        html = self.get('/')
        self.assertIn('<title>CityTrack | Trajectory Studio</title>', html)
        self.assertIn('id="workspace"', html)
        self.assertIn('id="sidebar"', html)
        self.assertIn('id="toggleSidebar"', html)
        self.assertIn('href="/analytics"', html)


def main():
    parser = argparse.ArgumentParser(description='CityTrack Trajectory Studio')
    parser.add_argument('--port', type=int, default=8002)
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    if args.test:
        loader = unittest.defaultTestLoader
        suite = unittest.TestSuite([
            loader.loadTestsFromModule(app.routes),
            loader.loadTestsFromModule(app.quality),
            loader.loadTestsFromTestCase(StudioTests),
        ])
        return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    try:
        app.routes.activate_osm()
        app.routes.initialize()
        app.quality.analytics(app.routes.DB)
        server = app.make_server(app.routes.DB, args.port)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.exit(1, f'Studio startup failed: {exc}\nCheck local graph/database and whether the port is already in use.\n')
    print(f'CityTrack Trajectory Studio: http://127.0.0.1:{args.port}/\nAnalytics: http://127.0.0.1:{args.port}/analytics\nDatabase: {app.routes.DB}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
