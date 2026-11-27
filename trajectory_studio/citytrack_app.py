"""Unified local CityTrack synthetic-data demonstration.
Place beside trajectory_osm.py and trajectory_analytics.py.
Run: python citytrack_app.py | Tests: python citytrack_app.py --test
"""
import argparse
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen, Request
from http.server import ThreadingHTTPServer

import trajectory_osm as routes
import trajectory_analytics as quality

NAV = '<nav style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px"><a style="color:#67dce9;padding:10px;border:1px solid #38506d;border-radius:7px;text-decoration:none" href="/">Trajectory map</a><a style="color:#67dce9;padding:10px;border:1px solid #38506d;border-radius:7px;text-decoration:none" href="/analytics">Analytics dashboard</a></nav>'
MAP_PAGE = routes.HTML.replace('<main>', '<main>'+NAV, 1)
ANALYTICS_PAGE = quality.HTML.replace('href="http://127.0.0.1:8000/" target="_blank" rel="noopener"','href="/"').replace('<main>', '<main>'+NAV, 1)

class Handler(routes.Handler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            return self.respond(MAP_PAGE, 'text/html; charset=utf-8')
        if path == '/analytics':
            return self.respond(ANALYTICS_PAGE, 'text/html; charset=utf-8')
        if path == '/api/analytics':
            try:
                return self.respond(quality.analytics(self.server.db_path))
            except (sqlite3.Error, OSError):
                return self.respond({'error':'Unable to read the local analytics database.'}, code=503)
        return super().do_GET()


def make_server(db, port=8000):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path = db
    return server


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name)/'integration.sqlite3'
        routes.initialize(self.db)
        self.server = make_server(self.db, 0)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.shutdown)
        self.url = 'http://127.0.0.1:'+str(self.server.server_port)

    def get(self,path):
        with urlopen(self.url+path,timeout=5) as r:
            return r.read().decode('utf-8')

    def post(self,path,body):
        req=Request(self.url+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urlopen(req,timeout=5) as r:
            return json.load(r)

    def test_navigation(self):
        self.assertIn('href="/analytics"',self.get('/'))
        a=self.get('/analytics')
        self.assertIn('Trajectory analytics',a)
        self.assertIn('href="/"',a)
        self.assertNotIn('http://127.0.0.1:8000/',a)

    def test_shared_database(self):
        before=json.loads(self.get('/api/analytics'))['total']
        records=[dict(vehicle_id='TEST-INTEGRATION',camera_id='CAM-A',observed_at='2026-01-01T09:00:00Z',confidence=.99),dict(vehicle_id='TEST-INTEGRATION',camera_id='CAM-B',observed_at='2026-01-01T09:04:00Z',confidence=.98),dict(vehicle_id='TEST-INTEGRATION',camera_id='CAM-C',observed_at='2026-01-01T09:08:00Z',confidence=.51)]
        body={'format':'json','content':json.dumps(records)}
        result=self.post('/api/import',body)
        self.assertEqual((result['inserted'],result['confirmed'],result['review']),(3,2,1))
        self.assertEqual(self.post('/api/import',body)['duplicates'],3)
        after=json.loads(self.get('/api/analytics'))
        self.assertEqual(after['total'],before+3)
        self.assertIn('TEST-INTEGRATION',self.get('/api/demo'))
        self.assertEqual(json.loads(self.get('/api/trajectory?vehicle=TEST-INTEGRATION')),routes.trajectory(self.db,'TEST-INTEGRATION'))

    def test_analytics_read_only(self):
        before=self.db.read_bytes()
        self.get('/api/analytics')
        self.assertEqual(before,self.db.read_bytes())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test',action='store_true')
    args=parser.parse_args()
    if args.test:
        # Existing tests plus end-to-end HTTP checks, all on temporary databases.
        loader=unittest.defaultTestLoader
        suite=unittest.TestSuite([loader.loadTestsFromModule(routes),loader.loadTestsFromModule(quality),loader.loadTestsFromTestCase(IntegrationTests)])
        return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1
    try:
        routes.activate_osm()
        routes.initialize()
        quality.analytics(routes.DB)
        server=make_server(routes.DB)
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as exc:
        parser.exit(1,f'CityTrack startup failed: {exc}\nCheck the local graph and database; stop any old server on port 8000.\n')
    print('CityTrack local demo: http://127.0.0.1:8000/\nAnalytics: http://127.0.0.1:8000/analytics\nDatabase: '+str(routes.DB),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

if __name__=='__main__':
    raise SystemExit(main())
