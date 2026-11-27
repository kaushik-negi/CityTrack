"""Create fabricated samples for an offline dashboard demonstration; no real footage."""
from pathlib import Path
from citytrack_video import export, make_row

if __name__ == '__main__':
    out = Path(__file__).resolve().parent / 'video_full_results'
    if out.exists():
        raise SystemExit('Output already exists; no files changed.')
    rows = [make_row(tid, frame, 10, cls, (x, y, x+40, y+20), .95, 960, 540)
            for tid, cls, start, y in ((1, 2, 0, 160), (2, 7, 10, 290), (3, 5, 20, 380))
            for frame in range(start, start+30)
            for x in [100 + (frame-start)*20]]
    export(out, rows, 5.0)
    print('Fabricated demo only, not video-derived:', out)
