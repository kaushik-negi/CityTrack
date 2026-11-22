"""
app.py — Multi-camera live ANPR server

Runs the same detection pipeline as gui.py (YOLO vehicle detection + SORT
tracking + line-crossing + plate OCR + Firebase logging), but:
  - handles MULTIPLE cameras at once, in ONE running process
  - streams the annotated video into a browser (MJPEG) instead of opening
    a desktop window
  - lets you add a camera by calling an API from the website, instead of
    typing a stream URL and an environment variable in a terminal

Run it with:
    python app.py

Then open citytrack.html — its Camera Network tab talks to this server
automatically on http://localhost:5000
"""

import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, request, jsonify
from ultralytics import YOLO

from sort.sort import Sort
from util import get_car, get_time, parseNo, output_Result
from readPlateImg2 import process_image
from check_cross import check_vehicle_crossing
from Setfirebase import update_camera_data, log_history

try:
    from color_detect import get_vehicle_color
except ImportError:
    def get_vehicle_color(car_crop):
        return "Unknown"

app = Flask(__name__)

# Models are loaded ONCE and shared across every camera thread — this is
# what makes running several cameras in one process efficient.
print("Loading models... (this can take a few seconds)")
coco_model = YOLO('yolov8n.pt')
license_plate_detector = YOLO('models/best2.pt')
print("Models loaded.")

VEHICLES = [2, 3, 5, 7]
VIRTUAL_LINE_Y = [100, 300, 310, 320, 330, 360, 380]

# One entry per running camera: {"frame": latest annotated frame, "stop": bool}
cameras = {}
lock = threading.Lock()


def camera_worker(camera_id, source):
    mot_tracker = Sort()
    src = int(source) if source.strip().isdigit() else source
    cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        print(f"[{camera_id}] Could not open source: {source}")
        with lock:
            cameras[camera_id]["stop"] = True
        return

    Number_Plate = {}
    result_ = {}
    frame_nmr = -1

    while True:
        with lock:
            if cameras.get(camera_id, {}).get("stop"):
                break

        frame_nmr += 1
        ret, frame = cap.read()
        if not ret:
            # Stream hiccup (common on WiFi) — wait briefly and keep trying
            # instead of ending the whole camera.
            time.sleep(0.5)
            continue

        detections = coco_model(frame, verbose=False)[0]
        detections_ = []
        for detection in detections.boxes.data.tolist():
            x1, y1, x2, y2, score, class_id = detection
            if int(class_id) in VEHICLES:
                detections_.append([x1, y1, x2, y2, score])
        if not detections_:
            detections_ = np.empty((0, 5))
        track_ids = mot_tracker.update(np.asarray(detections_))

        for line in range(len(VIRTUAL_LINE_Y)):
            cv2.line(frame, (0, VIRTUAL_LINE_Y[line]), (1600, VIRTUAL_LINE_Y[line]), (255, 255, 255), 1)
            crossed, at, byId = check_vehicle_crossing(
                track_ids, frame_nmr, VIRTUAL_LINE_Y[line], line, len(VIRTUAL_LINE_Y)
            )

            if not crossed:
                continue

            # Capture the vehicle's color from its own tracked box (works
            # even if the plate is never successfully read).
            vehicle_color = "Unknown"
            for t in track_ids:
                tx1, ty1, tx2, ty2, t_id = t
                if int(t_id) == int(byId):
                    car_crop = frame[int(ty1):int(ty2), int(tx1):int(tx2)]
                    vehicle_color = get_vehicle_color(car_crop)
                    break

            plateDetected = False
            license_plates = license_plate_detector(frame, verbose=False)[0]
            for lp in license_plates.boxes.data.tolist():
                x1, y1, x2, y2, score, class_id = lp
                xcar1, ycar1, xcar2, ycar2, car_id = get_car(lp, track_ids)

                if car_id != -1 and car_id == byId:
                    license_plate_crop = frame[int(y1):int(y2), int(x1):int(x2), :]
                    time_ = get_time()
                    a_id, b_data = process_image(
                        license_plate_crop, car_id, line,
                        f"NumberPlate02/NumberC/{camera_id.replace(' ', '_')}_{time_}_{frame_nmr}_{car_id}.png"
                    )
                    result_ = output_Result(b_data, result_)
                    entry = list(parseNo(result_, car_id))
                    while len(entry) < 6:
                        entry.append("")
                    entry[5] = vehicle_color
                    Number_Plate[int(car_id)] = entry
                    log_history(camera_id, entry)
                    plateDetected = True

                if not plateDetected:
                    if int(car_id) in Number_Plate:
                        entry = list(Number_Plate[int(car_id)])
                    else:
                        entry = [''] * 6
                    entry[4] = 'Number Plate Not Detected'
                    entry[5] = vehicle_color
                    Number_Plate[int(car_id)] = entry
                    log_history(camera_id, entry)

        update_camera_data(camera_id, Number_Plate)

        with lock:
            if camera_id in cameras:
                cameras[camera_id]["frame"] = frame.copy()

    cap.release()
    print(f"[{camera_id}] Stopped.")


@app.route("/add_camera", methods=["POST"])
def add_camera():
    data = request.get_json(force=True)
    camera_id = (data.get("camera_id") or "").strip()
    source = (data.get("source") or "").strip()
    if not camera_id or not source:
        return jsonify({"error": "camera_id and source are required"}), 400

    with lock:
        already_running = camera_id in cameras and not cameras[camera_id].get("stop")
        if already_running:
            return jsonify({"status": "already running", "camera_id": camera_id})
        cameras[camera_id] = {"frame": None, "stop": False}

    t = threading.Thread(target=camera_worker, args=(camera_id, source), daemon=True)
    t.start()
    return jsonify({"status": "started", "camera_id": camera_id})


@app.route("/stop_camera", methods=["POST"])
def stop_camera():
    data = request.get_json(force=True)
    camera_id = (data.get("camera_id") or "").strip()
    with lock:
        if camera_id in cameras:
            cameras[camera_id]["stop"] = True
    return jsonify({"status": "stopping", "camera_id": camera_id})


@app.route("/cameras")
def list_cameras():
    with lock:
        return jsonify({cid: (not v.get("stop")) for cid, v in cameras.items()})


def mjpeg_generator(camera_id):
    while True:
        with lock:
            frame = cameras.get(camera_id, {}).get("frame")
        if frame is not None:
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
        time.sleep(0.05)


@app.route("/stream/<camera_id>")
def stream(camera_id):
    return Response(mjpeg_generator(camera_id), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    # Allow the dashboard (opened as a local file) to call this server.
    from flask_cors import CORS
    CORS(app)
    app.run(host="0.0.0.0", port=5000, threaded=True)