# Validation and limitations

Prior Windows demonstrations showed all three synthetic scenarios, the image-coordinate video report, illustrative geographic placement, highway view and aggregate report. The last reported localhost error was not independently resolved. Fresh release tests run on Linux with a standard-library-only setup; live OSM download, fresh dependency installation and Windows browser rendering require local verification. Automated tests use controlled fixtures, not a measured real highway ground truth. No future-location or real cross-camera matching capability is included.

Release-candidate checks: 62 Highway Studio/backend tests, 4 synthetic compatibility tests, 9 evaluation tests, 7 scenario report tests and 4 final report tests passed (86 total). The fabricated video fixture produced 3 fragments and 90 samples; aggregate CSV/HTML, evaluation HTML and fictional scenario reports generated successfully. The packaged archive excludes all these generated outputs.
