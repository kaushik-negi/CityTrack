"""CityTrack Studio with a read-only tab for an existing anonymous video report.
Run beside the existing CityTrack Python modules; no new packages required.
No geographic inference, plate recognition, or cross-camera identity matching.
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

import citytrack_studio_fixed as studio
import citytrack_app as app
import citytrack_video as video

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / 'video_full_results' / 'video_map.html'
LINK = '<a href="/video" style="color:#49d9ea;padding:9px 13px;border:1px solid #315161;border-radius:7px;text-decoration:none">Video trajectories</a>'
MAP = app.MAP_PAGE.replace('</nav>', LINK + '</nav>', 1)
ANALYTICS = app.ANALYTICS_PAGE.replace('</nav>', LINK + '</nav>', 1)
VIDEO_NAV = '<nav style="display:flex;gap:16px;flex-wrap:wrap"><a href="/">Trajectory map</a><a href="/analytics">Analytics dashboard</a><a href="/video" aria-current="page">Video trajectories</a></nav>'
HTML = 'text/html; charset=utf-8'


def load_page(report):
    # Read only the known report, extract JSON, never execute its HTML or script.
    with Path(report).open(encoding='utf-8') as f:
        raw = f.read(32_000_001)
    if len(raw) > 32_000_000:
        raise ValueError('Report too large')
    _, marker, rest = raw.partition('const data=')
    if not marker:
        raise ValueError('Missing video data')
    data, _ = json.JSONDecoder().raw_decode(rest.lstrip())
    if not isinstance(data, dict) or not isinstance(data.get('tracks'), list):
        raise ValueError('Invalid video data')
    duration = data.get('duration')
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
        raise ValueError('Invalid duration')
    # Rebuild only the original anonymous report template, with JSON escaped for script context.
    payload = json.dumps(data, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    return video.PAGE.replace('__DATA__', payload).replace(
        '<a href="http://127.0.0.1:8002/">Open existing Trajectory Studio</a>', VIDEO_NAV, 1)


def unavailable(message):
    return ('<!doctype html><html><meta charset="utf-8"><title>CityTrack | Video trajectories</title>'
            '<body style="background:#0b111c;color:#e2e8f0;font:16px system-ui;padding:32px">'
            + VIDEO_NAV + '<h1>Video trajectories</h1><p>' + message + '</p>'
            '<p>Expected file: <code>video_full_results/video_map.html</code> inside CityTrack.</p>'
            '<p>Your existing geographic dashboard and database remain available.</p></body></html>')


class Handler(app.Handler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            return self.respond(MAP, HTML)
        if path == '/analytics':
            return self.respond(ANALYTICS, HTML)
        if path == '/video':
            try:
                page = load_page(self.server.video_report)
            except FileNotFoundError:
                return self.respond(unavailable('The saved video report is missing. Copy your existing results folder here.'), HTML, 404)
            except (OSError, ValueError, TypeError, OverflowError, RecursionError):
                return self.respond(unavailable('The saved report could not be read. Check that it is the original generated video_map.html.'), HTML, 422)
            return self.respond(page, HTML)
        return super().do_GET()


def make_server(db, port=8002, report=REPORT):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path = db
    server.video_report = report
    return server


class VideoTabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.db = root / 'test.sqlite3'
        app.routes.initialize(self.db)
        self.out = root / 'video_full_results'
        video.export(self.out, [video.make_row(1, 0, 30, 2, [1,2,20,30], .9, 100, 100)], 1.0)
        self.report = self.out / 'video_map.html'
        self.server = make_server(self.db, 0, self.report)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.shutdown)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def get(self, path):
        with urlopen(self.url + path, timeout=5) as r:
            return r.read().decode('utf-8')

    def test_navigation(self):
        for path in ('/', '/analytics'):
            self.assertIn('href="/video"', self.get(path))
        page = self.get('/video')
        self.assertIn('href="/analytics"', page)
        self.assertIn('Camera-coordinate map', page)
        self.assertIn('"samples":1', page)

    def test_read_only(self):
        before = [p.read_bytes() for p in (self.db, self.report, self.out/'video_observations.sqlite3')]
        self.get('/video')
        self.assertEqual(before, [p.read_bytes() for p in (self.db, self.report, self.out/'video_observations.sqlite3')])

    def test_missing(self):
        self.report.unlink()
        with self.assertRaises(HTTPError) as e:
            self.get('/video')
        self.assertEqual(e.exception.code, 404)
        self.assertIn('saved video report is missing', e.exception.read().decode())

    def test_malformed(self):
        self.report.write_text('invalid report', encoding='utf-8')
        with self.assertRaises(HTTPError) as e:
            self.get('/video')
        self.assertEqual(e.exception.code, 422)

    def test_existing_api(self):
        self.assertIn('DEMO-001', self.get('/api/demo'))
        self.assertIn('total', json.loads(self.get('/api/analytics')))

    def test_does_not_serve_arbitrary_files(self):
        with self.assertRaises(HTTPError) as e:
            self.get('/video_full_results/video_observations.sqlite3')
        self.assertEqual(e.exception.code, 404)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--test', action='store_true')
    p.add_argument('--port', type=int, default=8002)
    a = p.parse_args()
    if a.test:
        loader = unittest.defaultTestLoader
        suite = unittest.TestSuite([loader.loadTestsFromModule(app.routes), loader.loadTestsFromModule(app.quality), loader.loadTestsFromTestCase(studio.StudioTests), loader.loadTestsFromTestCase(video.Tests), loader.loadTestsFromTestCase(VideoTabTests)])
        return int(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())
    if not 1 <= a.port <= 65535:
        p.error('Invalid port')
    try:
        app.routes.activate_osm()
        app.routes.initialize()
        app.quality.analytics(app.routes.DB)
        server = make_server(app.routes.DB, a.port)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.exit(1, f'Startup failed: {exc}\nCheck the cached OSM graph and stop any old server on this port.\n')
    print(f'CityTrack Studio: http://127.0.0.1:{a.port}/\nVideo trajectories: http://127.0.0.1:{a.port}/video\nAnalytics: http://127.0.0.1:{a.port}/analytics', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
