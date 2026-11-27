"""Phase 20: local launcher and aggregate single-clip reports for CityTrack.
Existing dashboards and saved observations are preserved. No real geolocation.
"""
import argparse
import csv
import html
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / 'video_full_results' / 'video_map.html'
MODULES = ('citytrack_highway.py', 'citytrack_video_geo.py', 'citytrack_video_studio.py',
           'citytrack_video.py', 'citytrack_studio_fixed.py', 'citytrack_app.py',
           'trajectory_osm.py', 'trajectory_analytics.py', 'citytrack_contract_test.py',
           'citytrack_evaluation.py', 'citytrack_reports.py')


def run(module, *args):
    print('CityTrack >', module, *args, flush=True)
    return subprocess.run([sys.executable, str(ROOT / module), *map(str, args)], cwd=ROOT).returncode


def totals(data):
    from citytrack_highway import summary
    counts = summary(data)
    return {'duration': data['duration'], 'fragments': sum(x['fragments'] for x in counts.values()),
            'samples': sum(x['samples'] for x in counts.values()), 'categories': counts}


def export_summary(report, out):
    from citytrack_video_geo import load_data
    a = totals(load_data(report))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    with (out / 'traffic_summary.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['category', 'track_fragments', 'movement_samples', 'recording_duration_seconds'])
        for cat, row in sorted(a['categories'].items()):
            w.writerow([cat, row['fragments'], row['samples'], a['duration']])
        w.writerow(['TOTAL', a['fragments'], a['samples'], a['duration']])
    rows = ''.join(f'<tr><td>{html.escape(cat)}</td><td>{r["fragments"]:,}</td><td>{r["samples"]:,}</td></tr>'
                   for cat, r in sorted(a['categories'].items()))
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CityTrack | Aggregate traffic report</title>
<style>body{{background:#0d1420;color:#e2e8f0;font:16px system-ui,sans-serif;max-width:1000px;margin:auto;padding:32px}}h1{{font-size:32px}}small,p{{color:#adbed1;line-height:1.5}}.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}.kpi,section{{background:#132032;border:1px solid #293c51;border-radius:10px;padding:18px;margin-bottom:12px}}b{{display:block;font-size:28px;color:#52d9eb}}table{{width:100%;border-collapse:collapse;text-align:left}}td,th{{padding:12px;border-bottom:1px solid #293c51}}a,button{{color:#52d9eb;background:transparent;border:1px solid #39536e;border-radius:6px;padding:9px;font:inherit;text-decoration:none;cursor:pointer}}@media print{{body{{color:#111;background:white}}.kpi,section{{background:white;border-color:#aaa}}b,p,small{{color:#111}}a,button{{display:none}}}}</style>
<small>CITYTRACK / PHASE 20</small><h1>Aggregate traffic report</h1><p>Single recording · Anonymous tracking fragments · No geographic inference</p><p><button onclick="window.print()">Print / Save as PDF</button> <a href="traffic_summary.csv" download>Download CSV</a></p><div class="kpis"><div class="kpi">Track fragments<b>{a['fragments']:,}</b></div><div class="kpi">Movement samples<b>{a['samples']:,}</b></div><div class="kpi">Recording duration<b>{a['duration']:.1f} s</b></div></div><section><h2>Vehicle category summary</h2><table><thead><tr><th>Category</th><th>Fragments</th><th>Samples</th></tr></thead><tbody>{rows}</tbody></table></section><p>Fragments are not guaranteed unique vehicles. Category labels are model outputs, not ground truth. No track IDs, coordinates, plate numbers or individual movement histories are exported. This report reads the existing saved video result; it does not modify the source database.</p></html>'''
    (out / 'traffic_summary.html').write_text(page, encoding='utf-8')
    return a


class FinalTests(unittest.TestCase):
    def test_aggregate(self):
        self.assertEqual(totals({'duration': 2, 'tracks': [{'category':'car','samples':3},{'category':'car','samples':5},{'category':'truck','samples':1}]}),
                         {'duration':2,'fragments':3,'samples':9,'categories':{'car':{'fragments':2,'samples':8},'truck':{'fragments':1,'samples':1}}})
    def test_empty(self):
        self.assertEqual(totals({'duration':1,'tracks':[]})['samples'],0)
    def test_export(self):
        import citytrack_video as v
        with tempfile.TemporaryDirectory() as td:
            p = Path(td); source = p / 'source'; out = p / 'output'
            v.export(source, [v.make_row(1,0,30,2,[1,1,20,20],.9,100,100)], 1)
            report = source / 'video_map.html'; before = report.read_bytes()
            self.assertEqual(export_summary(report,out)['fragments'],1)
            self.assertEqual(before,report.read_bytes())
            with (out/'traffic_summary.csv').open(newline='',encoding='utf-8') as f:
                records=list(csv.reader(f))
            self.assertEqual(records[-1],['TOTAL','1','1','1'])
            self.assertIn('not guaranteed unique vehicles',(out/'traffic_summary.html').read_text(encoding='utf-8'))
            with self.assertRaises(FileExistsError): export_summary(report,out)
    def test_bad_report(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); report=p/'bad.html'; report.write_text('invalid',encoding='utf-8')
            with self.assertRaises(ValueError): export_summary(report,p/'out')
            self.assertFalse((p/'out').exists())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group()
    g.add_argument('--check',action='store_true');g.add_argument('--test',action='store_true')
    g.add_argument('--evaluation',action='store_true');g.add_argument('--reports',action='store_true')
    g.add_argument('--traffic-report',action='store_true')
    p.add_argument('--report',type=Path,default=REPORT,help='Existing video_map.html to display or summarize')
    p.add_argument('--out',type=Path,default=ROOT/'traffic_report',help='New folder for aggregate reports')
    p.add_argument('--port',type=int,default=8002)
    a=p.parse_args()
    if not 1<=a.port<=65535:p.error('Port must be between 1 and 65535')
    missing=[m for m in MODULES if not (ROOT/m).is_file()]
    if a.check:
        for m in (*MODULES,'citytrack_osm_network.json','trajectory_import_demo.sqlite3'):
            print(f'[{"OK" if (ROOT/m).is_file() else "MISSING"}] {m}')
        print(f'[{"OK" if a.report.is_file() else "MISSING"}] {a.report}')
        return int(bool(missing or not a.report.is_file() or not (ROOT/'citytrack_osm_network.json').is_file()))
    if missing:p.exit(1,'Missing modules: '+', '.join(missing)+'\n')
    try:
        if a.test:
            statuses=[run('citytrack_highway.py','--test'),run('citytrack_contract_test.py'),run('citytrack_evaluation.py','--test'),run('citytrack_reports.py','--test')]
            statuses.append(int(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FinalTests)).wasSuccessful()))
            print(f'Test suites passed: {statuses.count(0)}/{len(statuses)}')
            return int(any(statuses))
        if a.evaluation:return run('citytrack_evaluation.py')
        if a.reports:return run('citytrack_reports.py','--osm')
        if a.traffic_report:
            result=export_summary(a.report,a.out)
            print(f"{result['fragments']} fragments; {result['samples']} samples. Open {a.out.resolve()/'traffic_summary.html'}")
            return 0
        print(f'Highway studio: http://127.0.0.1:{a.port}/highway',flush=True)
        return run('citytrack_highway.py','--port',a.port,'--report',a.report.resolve())
    except KeyboardInterrupt:return 130
    except (OSError,ValueError,TypeError,KeyError,OverflowError) as exc:p.exit(1,f'CityTrack: {exc}\n')

if __name__=='__main__':raise SystemExit(main())
