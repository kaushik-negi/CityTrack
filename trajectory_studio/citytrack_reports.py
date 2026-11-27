"""CityTrack Phase 13: export reports for built-in fictional scenarios only.
Run: python citytrack_reports.py | Test: python citytrack_reports.py --test
No live database access, identifiers, camera locations or event timestamps are exported.
"""
import argparse
import csv
import html
import tempfile
import unittest
from pathlib import Path
import trajectory_osm as routes

LABELS = {'normal': 'Normal journey', 'review': 'Low-confidence observation', 'anomaly': 'Implausible speed'}
FIELDS = ['scenario', 'observations', 'confirmed', 'review', 'mean_confidence_pct', 'duration_min', 'direct_km', 'network_km', 'routed_segments', 'segments', 'direct_flags', 'network_flags']
HEADERS = ['Scenario', 'Observations', 'Confirmed', 'Review', 'Mean confidence (%)', 'Duration (min)', 'Direct (km)', 'Network (km)', 'Routed segments', 'Total segments', 'Direct flags', 'Network flags']

def build_reports():
    results = []
    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / 'fixture.sqlite3'
        routes.initialize(db)
        for key, label in LABELS.items():
            state = routes.create_sim(db, key)
            while not state['complete']:
                state = routes.advance_sim(db, state['vehicle_id'], state['emitted'])
            data = routes.trajectory(db, state['vehicle_id'])
            observations = data['points'] + data['review']
            results.append(dict(scenario=label, observations=len(observations), confirmed=len(data['points']), review=len(data['review']), mean_confidence_pct=round(100*sum(x['confidence'] for x in observations)/len(observations), 2), duration_min=data['elapsed_minutes'], direct_km=data['distance_km'], network_km=data['road_distance_km'], routed_segments=sum(s['road_km'] is not None for s in data['segments']), segments=len(data['segments']), direct_flags=data['flags'], network_flags=data['road_flags']))
    return results

def display(value):
    return 'Unavailable' if value is None else str(value)

def render(rows, network):
    esc = lambda v: html.escape(display(v))
    cards = ''.join(f'<article><h2>{esc(r["scenario"])}</h2><strong>{r["confirmed"]}/{r["observations"]}</strong><p>Confirmed observations</p><dl><dt>Review observations</dt><dd>{r["review"]}</dd><dt>Estimated network distance</dt><dd>{esc(r["network_km"])} km</dd><dt>Network flags</dt><dd>{r["network_flags"]}</dd></dl></article>' for r in rows)
    table = '<thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in HEADERS)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k in FIELDS)+'</tr>' for r in rows)+'</tbody>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CityTrack | Scenario reports</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#0d1522;color:#e5edf8;font:15px system-ui,sans-serif}}main{{max-width:1250px;margin:auto;padding:32px}}header{{border-bottom:1px solid #30435b;padding-bottom:20px;margin-bottom:24px}}.eyebrow{{color:#51d8e8;letter-spacing:2px;font-size:12px;font-weight:bold}}h1{{font-size:32px;margin:12px 0}}p{{color:#afbed1;line-height:1.6}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}article,section{{background:#142032;border:1px solid #2a3c54;border-radius:12px;padding:20px}}h2{{font-size:17px;margin-top:0}}article strong{{font-size:36px;color:#51d8e8}}article p{{margin-top:0}}dl{{display:grid;grid-template-columns:1fr auto;gap:10px}}dt{{color:#afbed1}}dd{{margin:0;font-weight:600}}section{{margin-top:20px;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:12px 8px;border-bottom:1px solid #30435b;text-align:left}}th{{color:#afbed1}}button,a{{display:inline-block;background:#18384a;color:#e5edf8;border:1px solid #39637a;border-radius:7px;padding:10px 15px;text-decoration:none;font:inherit;cursor:pointer}}@media print{{body{{background:white;color:#182434}}main{{padding:0}}article,section{{background:white;border-color:#ccc;break-inside:avoid}}p,dt,th,.eyebrow{{color:#43536a}}article strong{{color:#116477}}.actions{{display:none}}table{{font-size:9px}}th,td{{padding:5px 3px}}}}
</style><main><header><div class="eyebrow">CITYTRACK / PHASE 13</div><h1>Synthetic journey reports</h1><p>Built-in fictional scenarios · {esc(network)} · Independent temporary database</p><div class="actions"><button onclick="window.print()">Print / Save as PDF</button> <a href="citytrack_scenario_reports.csv" download>Download CSV</a></div></header><div class="grid">{cards}</div><section><h2>Scenario comparison</h2><table>{table}</table></section><section><h2>Interpretation and limitations</h2><p>Confidence values are fabricated inputs. Network distances are shortest-path estimates and exclude road snap gaps. Flags use the demonstration speed threshold, not a legal speed limit or proof of a violation. Duration is measured between confirmed synthetic observations. A missing network distance means a complete network route was unavailable.</p><p>Only built-in fixtures are processed. The working database, imported records, identifiers, camera locations and observation timestamps are not included in these reports.</p></section></main></html>'''

def export(rows, folder, network):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / 'citytrack_scenario_reports.csv'
    html_path = folder / 'citytrack_scenario_reports.html'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)
    html_path.write_text(render(rows, network), encoding='utf-8')
    return html_path, csv_path

class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = build_reports()
    def test_scenarios(self):
        self.assertEqual([r['observations'] for r in self.rows], [4,5,3])
    def test_review(self):
        self.assertEqual([r['review'] for r in self.rows], [0,1,0])
    def test_flags(self):
        self.assertGreaterEqual(self.rows[2]['direct_flags'],1)
    def test_fields(self):
        for r in self.rows: self.assertEqual(set(r),set(FIELDS))
    def test_duration(self):
        self.assertEqual([r['duration_min'] for r in self.rows],[13,12,6])
    def test_export(self):
        with tempfile.TemporaryDirectory() as d:
            h,c = export(self.rows,d,'Fictional demonstration graph')
            self.assertIn('Print / Save as PDF', h.read_text(encoding='utf-8'))
            with c.open(encoding='utf-8-sig',newline='') as f: self.assertEqual(len(list(csv.DictReader(f))),3)
    def test_escape(self):
        self.assertIn('&lt;script&gt;', render(self.rows,'<script>'))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--test',action='store_true')
    p.add_argument('--osm',action='store_true',help='Use the existing local OSM graph instead of the fictional graph; no download.')
    p.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'reports')
    a=p.parse_args()
    if a.test: return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReportTests)).wasSuccessful() else 1
    try:
        if a.osm: routes.activate_osm()
        network='Cached OpenStreetMap graph (© OpenStreetMap contributors)' if a.osm else 'Fictional demonstration graph'
        h,c=export(build_reports(),a.output,network)
    except (OSError,ValueError,KeyError,TypeError) as e: p.exit(1,f'Report generation failed: {e}\n')
    print(f'HTML: {h}\nCSV: {c}\nExisting application database was not opened.')
    return 0
if __name__=='__main__': raise SystemExit(main())
