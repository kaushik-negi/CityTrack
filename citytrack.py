"""One local entry point for the CityTrack synthetic trajectory prototype.
Run: python citytrack.py --help
"""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MODULES = ('citytrack_studio_fixed.py', 'citytrack_app.py', 'trajectory_osm.py',
           'trajectory_analytics.py', 'citytrack_contract_test.py',
           'citytrack_evaluation.py', 'citytrack_reports.py')
GRAPH = 'citytrack_osm_network.json'
DATABASE = 'trajectory_import_demo.sqlite3'


def run(module, *args):
    print(f'\nCityTrack > {module} {" ".join(args)}', flush=True)
    return subprocess.run([sys.executable, str(ROOT / module), *args],
                          cwd=ROOT).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--test', action='store_true', help='Run all four test suites')
    action.add_argument('--evaluation', action='store_true', help='Generate offline benchmark HTML')
    action.add_argument('--reports', action='store_true', help='Generate synthetic HTML and CSV reports')
    action.add_argument('--check', action='store_true', help='Check required files without modifying them')
    parser.add_argument('--port', type=int, default=8002, help='Studio port (default 8002)')
    parser.add_argument('--demo-graph', action='store_true', help='Use the fictional graph for reports only')
    args = parser.parse_args()
    if args.demo_graph and not args.reports:
        parser.error('--demo-graph requires --reports')
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    missing = [name for name in MODULES if not (ROOT / name).is_file()]
    if args.check:
        print('Project folder:', ROOT)
        for name in (*MODULES, GRAPH, DATABASE):
            print(f'[{"OK" if (ROOT / name).is_file() else "MISSING"}] {name}')
        return int(bool(missing or not (ROOT / GRAPH).is_file()))
    if missing:
        print('Missing Python modules: ' + ', '.join(missing), file=sys.stderr)
        return 1
    try:
        if args.test:
            results = [run('citytrack_studio_fixed.py', '--test'),
                       run('citytrack_contract_test.py'),
                       run('citytrack_evaluation.py', '--test'),
                       run('citytrack_reports.py', '--test')]
            print(f'\nTest suites passed: {results.count(0)}/{len(results)}')
            return int(any(results))
        if args.evaluation:
            return run('citytrack_evaluation.py')
        if args.reports:
            if args.demo_graph:
                return run('citytrack_reports.py')
            if not (ROOT / GRAPH).is_file():
                print('Cached OSM graph missing. Restore it, or use --reports --demo-graph.', file=sys.stderr)
                return 1
            return run('citytrack_reports.py', '--osm')
        if not (ROOT / GRAPH).is_file():
            print('Cached OSM graph missing. Copy citytrack_osm_network.json into this folder.', file=sys.stderr)
            return 1
        return run('citytrack_studio_fixed.py', '--port', str(args.port))
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
