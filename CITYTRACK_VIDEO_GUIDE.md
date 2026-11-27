# CityTrack — Phase 20 local demonstration

## Requirements
Keep the existing CityTrack project intact. Add `citytrack_final.py` to the project root, alongside the Phase 19 modules. Python 3.12 was used on the demonstrated Windows system. The launcher and saved-result reports require no new packages. The original video processing tool has its own Ultralytics and imageio-ffmpeg dependencies.

## Startup (PowerShell)

```powershell
cd "D:\City-Track-chatgpt\CityTrack"
python citytrack_final.py --check
python citytrack_final.py --test
python citytrack_final.py
```

Stop any previously running server on port 8002 before launching. Open http://127.0.0.1:8002/highway. The five views are `/`, `/analytics`, `/video`, `/video-map` and `/highway`. For synchronized preview, select the same original clip in the browser, reset, then play. Matching duration alone does not prove that the selected file is the original.

## Saved inputs
- `citytrack_osm_network.json`: cached OSM graph for synthetic geographic journeys.
- `trajectory_import_demo.sqlite3`: synthetic observation database.
- `video_full_results/video_map.html`: saved anonymous single-clip trajectory report, read by the video views.
- `video_full_results/video_observations.csv` and `video_observations.sqlite3`: existing observations.
- `highway.webm`: original clip used for the optional local video preview.

Keep the existing Python modules; the final launcher delegates to them and does not replace them.

## Reports and benchmark

```powershell
python citytrack_final.py --traffic-report
start traffic_report\traffic_summary.html
python citytrack_final.py --evaluation
python citytrack_final.py --reports
```

For a second traffic report, use `--traffic-report --out traffic_report_2` to avoid overwriting the first. Aggregate reports contain category-level fragment and sample counts, not unique vehicle counts, individual identities, or position histories.

## Demonstrated results and limitations
The user's video dashboard reported 353 track fragments and 10,587 observations over 60 seconds. Category fragment counts were 294 car, 38 truck, 18 bus and 3 motorcycle. These are model classifications, not verified ground truth. The video map uses an arbitrary illustrative geographic placement, and the highway background is schematic. Neither is a calibrated real-world trajectory. No plate recognition, cross-camera vehicle linkage, or future movement prediction is implemented. The historical synthetic route engine uses a cached OSM graph, not observed GPS paths. Accuracy metrics from the earlier six-fixture benchmark do not establish real-world accuracy.

The Phase 20 launcher test run passed 86 tests across five suites using controlled fixtures; actual local OSM and video data and browser playback must be verified on the user's machine.
