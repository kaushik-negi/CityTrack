"""Synthetic-only contract smoke test for CityTrack. No camera, OCR or Firebase access.
Run beside trajectory_osm.py: python citytrack_contract_test.py
All records are built in and the database is temporary.
"""
import json
import tempfile
import unittest
from pathlib import Path
import trajectory_osm as engine

# Mock original history shape: camera, local track ID, plate text, time,
# image path, status, color. All values below are invented for this test.
# The matching synthetic confidence and normalized event time are fixture
# metadata, NOT values measured or returned by original OCR.
FIXTURE = (
    (('CAM-C', 7, 'TEST-CONTRACT', '2026-01-01 09:08:00Frame: 30', '', 'At line: 1', 'Blue'), '2026-01-01T09:08:00Z', .51),
    (('CAM-A', 1, 'TEST-CONTRACT', '2026-01-01 09:00:00Frame: 10', '', 'At line: 1', 'Blue'), '2026-01-01T09:00:00Z', .99),
    (('CAM-B', 5, 'TEST-CONTRACT', '2026-01-01 09:04:00Frame: 20', '', 'At line: 1', 'Blue'), '2026-01-01T09:04:00Z', .97),
)

def fixture_records():
    # Translate only the immutable mock records, never external camera data.
    return [dict(vehicle_id='TEST-CONTRACT', camera_id=entry[0],
                 observed_at=stamp, confidence=confidence)
            for entry, stamp, confidence in FIXTURE]

class ContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / 'contract.sqlite3'
        engine.initialize(self.db)

    def import_fixture(self):
        return engine.import_observations(self.db, 'json', json.dumps(fixture_records()))

    def test_import_and_review(self):
        result = self.import_fixture()
        self.assertEqual((result['inserted'], result['confirmed'], result['review']), (3, 2, 1))

    def test_order_and_filter(self):
        self.import_fixture()
        route = engine.trajectory(self.db, 'TEST-CONTRACT')
        self.assertEqual([p['camera_id'] for p in route['points']], ['CAM-A', 'CAM-B'])
        self.assertEqual([p['camera_id'] for p in route['review']], ['CAM-C'])
        self.assertEqual(route['elapsed_minutes'], 4)

    def test_repeat_import(self):
        self.import_fixture()
        result = self.import_fixture()
        self.assertEqual((result['inserted'], result['duplicates']), (0, 3))

    def test_missing_confidence_rejected(self):
        records = fixture_records()
        del records[0]['confidence']
        with self.assertRaises(ValueError):
            engine.import_observations(self.db, 'json', json.dumps(records))
        self.assertEqual(engine.trajectory(self.db, 'TEST-CONTRACT')['points'], [])

if __name__ == '__main__':
    unittest.main(verbosity=2)
