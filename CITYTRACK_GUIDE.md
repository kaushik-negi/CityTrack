# CityTrack Trajectory Studio

## Local prototype | Setup, technical reference and demonstration

**Scope:** A local educational prototype that reconstructs possible historical routes from fictional vehicle observations. It uses real OpenStreetMap road geometry for the demonstration area but does not ingest real camera feeds, identify real vehicles, integrate the original ANPR pipeline, or predict future vehicle locations.

Original reference repository: https://github.com/kaushik-negi/CityTrack

## 1. Quick start (Windows / VS Code)

Use the existing CityTrack directory. Python 3.12 was used in the Windows demonstration. Keep the original repository and a backup of the local database. Stop old servers using Ctrl+C before starting another server on the same port.

```powershell
cd "D:\City-Track-chatgpt\CityTrack"
python citytrack.py --check
python citytrack.py --test
python citytrack.py
```

Open http://127.0.0.1:8002/ in Chrome. Analytics is at http://127.0.0.1:8002/analytics. The initial coordinate view works offline. Enable street map to load Leaflet and online map tiles. The routing computation uses the local graph independently of the online tiles. To use a different port, for example: `python citytrack.py --port 8003`.

If extracting the final source bundle into a new directory, copy `citytrack_osm_network.json` and (optionally, for saved synthetic history) `trajectory_import_demo.sqlite3` from the existing project into that directory. The database is initialized automatically if absent. The bundle does not include those two local files, the original ANPR directory, or any Firebase credentials. No additional Python packages are needed with a valid cached graph. If the graph is missing and you cannot restore a backup, the existing download utility can recreate it with an internet connection:

```powershell
python -m pip install "osmnx>=2,<3"
python trajectory_osm.py --download-osm
```

OSM data changes over time, so a freshly downloaded graph may produce different estimates. Retain OpenStreetMap attribution when displaying or redistributing OSM-derived data; see https://www.openstreetmap.org/copyright.

## 2. Architecture and files

```text
Simulator / synthetic CSV / synthetic JSON
                 |
       Validation and filtering
                 |
        Local SQLite database
                 |
      Chronological observations
                 |
      Historical reconstruction ---- Cached OSM graph
                 |
     Studio map + aggregate analytics
```

| File | Role |
|---|---|
| citytrack.py | Central command-line launcher |
| citytrack_studio_fixed.py | Three-panel Studio interface and server entry point |
| citytrack_app.py | Shared HTTP application and integration |
| trajectory_osm.py | Validation, SQLite, simulation and directed shortest-path routing |
| trajectory_analytics.py | Aggregate synthetic data quality metrics |
| citytrack_contract_test.py | Mock-format compatibility tests, not live ANPR integration |
| citytrack_evaluation.py | Controlled fictional graph benchmark and HTML output |
| citytrack_reports.py | Built-in synthetic scenario summary exports |
| sample_observations.csv / .json | Matching synthetic import fixtures |
| citytrack_osm_network.json | Local road graph (user supplies or downloads) |
| trajectory_import_demo.sqlite3 | Local synthetic observation database (created or restored) |

The backend is Python's local HTTP server and SQLite. The application binds to loopback. The map is an offline SVG coordinate view with optional Leaflet/OpenStreetMap visualization. No cloud service is required for the trajectory module.

## 3. Reconstruction and assessment

Confirmed observations are sorted by normalized UTC timestamp. The direct distance uses great-circle distance between adjacent observations. For the road estimate, fictional camera points are matched to nearby road nodes (offsets above 500 m are rejected); Dijkstra's algorithm selects a shortest-distance path through the cached directed graph between consecutive confirmed observations. Road distance excludes the gaps from the fictional camera coordinates to snapped nodes. The road/direct ratio is illustrative because endpoints differ. Segment average speed is distance divided by elapsed observation time. A 120 km/h demo threshold flags inconsistent movement for review, not proof of wrongdoing or a legal speed violation.

Cyan markers represent confirmed synthetic sightings; dashed cyan lines represent direct connections; purple lines represent estimated network paths; orange denotes excluded sightings or flagged segments. A shortest path is only one possible historical route. Turn restrictions and real traffic conditions are not fully modeled.

## 4. Synthetic import contract

CSV requires exactly these columns; JSON requires an array of objects with the same four fields:

- `vehicle_id`: fictional `TEST-` ID followed by 1–24 uppercase letters or digits.
- `camera_id`: CAM-A through CAM-F only (fictional sites).
- `observed_at`: ISO 8601 date-time with seconds and an explicit timezone.
- `confidence`: numeric input score from 0 to 1; scores >=0.90 are confirmed, otherwise review.

Import is limited to 1,000 records and 256 KiB per file. Invalid batches are rejected atomically; duplicates use the vehicle/camera/timestamp key. Sample CSV and JSON contain the same five records, so importing both into a fresh database should save five then skip five. Select `TEST-001` after importing. These are synthetic test inputs, not measured OCR accuracy.

## 5. Demonstration script (approximately 4–5 minutes)

1. Start `python citytrack.py` and open the map. Explain that all observations and camera positions are fictional.
2. Select Normal journey and start the simulation. Show the four confirmed observations, timeline, map playback and zero flags. Events arrive every two seconds in accelerated simulation time.
3. Select Low-confidence observation and start a new simulation. Show four confirmed observations and one excluded observation with 51% input confidence.
4. Select Implausible speed and start a new simulation. Show three confirmed observations and the orange flagged route; explain that the flag is for review.
5. Open Analytics dashboard to show aggregate counts and confidence distributions. Refresh after a simulation if needed.
6. In a separate terminal generate the evaluation and scenario reports:

```powershell
python citytrack.py --evaluation
start citytrack_evaluation.html
python citytrack.py --reports
start reports\citytrack_scenario_reports.html
```

Show the directed-edge overlap results and the detour failure case. The scenario report has CSV download and browser Print / Save as PDF controls. If the graph is unavailable, `python citytrack.py --reports --demo-graph` generates reports using an illustrative graph instead. Reports use a temporary database and do not export saved vehicle histories.

## 6. Verified results

The user's Windows screenshots show successful rendering and these results using a cached OSM network of 23,650 nodes. Distances depend on that graph snapshot.

| Scenario | Confirmed / total | Estimated network distance | Network flags |
|---|---:|---:|---:|
| Normal | 4/4 | 7.68 km | 0 |
| Low-confidence | 4/5 | 6.39 km | 0 |
| Implausible speed | 3/3 | 7.17 km | 1 |

Controlled evaluation: 5 of 6 fixtures routed, 4 exact matches out of 6, mean absolute distance error 4.21% and mean directed-edge overlap 84% across routed fixtures. A detour with missing observations achieved only 20% overlap. The user observed a median per-case runtime of 7.55 microseconds on small benchmark graphs, not end-to-end application latency. These figures are not population-level or real-world accuracy estimates.

Automated regression suites rerun successfully in the authoring environment: Studio/backend 41, synthetic contract 4, evaluation 9, reports 7, total 61. Tests use controlled fixtures and do not prove live ANPR integration or production reliability. Windows full-suite output after launching via citytrack.py was not independently supplied with the final screenshot.

## 7. Troubleshooting

- `Errno 2`: confirm the working directory and filename with `Get-Location` and `Test-Path .\citytrack.py`.
- Old interface: open port 8002, not 8000. Restart the server and refresh with Ctrl+F5.
- Address in use: stop the old server or choose another port with `--port`.
- Graph missing: restore the cached graph or use the download step above.
- Online tiles unavailable: use the offline view. The cached graph still enables local route reconstruction.
- Database locked: stop other programs holding the database before copying it. Keep the existing file as a backup.

## 8. Scope and limitations for presentation

The completed work is a local synthetic historical trajectory reconstruction and evaluation prototype, not a deployed vehicle monitoring product. The original NumberPlate02 directory has not been modified or integrated into the running Studio. The synthetic contract test checks fixture conversion only. Live ANPR, future route prediction, verified actual vehicle routes, production authentication and operational deployment are not implemented. Do not describe the benchmark as ANPR recognition accuracy or present estimated routes as ground truth.

Suggested project description: “CityTrack Trajectory Studio is a local synthetic trajectory reconstruction prototype that combines timestamped observations, confidence validation, SQLite storage, directed shortest-path routing on a cached OpenStreetMap graph, interactive GIS visualization, and controlled benchmark evaluation.”
