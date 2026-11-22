import json
import logging
import os

import firebase_admin
from firebase_admin import credentials, db

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def _load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Missing {CONFIG_PATH}. Copy config.example.json to config.json "
            f"and fill in your actual Firebase credentials filename, database URL, and camera_id."
        )
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


_config = _load_config()
CAMERA_ID = os.environ.get("CAMERA_ID", _config.get("camera_id", "Camera 1"))


def _init_firebase():
    cred_path = os.path.join(os.path.dirname(__file__), _config["firebase_credentials_file"])

    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"Firebase credentials file not found at {cred_path}. "
            f"Check 'firebase_credentials_file' in config.json points to your actual key file."
        )

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        "databaseURL": _config["firebase_database_url"]
    })
    logger.info(f"Firebase initialized successfully. Running as {CAMERA_ID}")
    # Each camera writes under its own node so car IDs from different
    # cameras never collide or overwrite each other.
    return db.reference(f"/detections/{CAMERA_ID}")


try:
    ref = _init_firebase()
except Exception as e:
    logger.error(f"Firebase initialization failed: {e}")
    raise


def update_data(data):
    """Push the current detections dict to this camera's node in Firebase.
    Uses the default CAMERA_ID (single-camera / legacy gui.py usage)."""
    update_camera_data(CAMERA_ID, data)


def update_camera_data(camera_id, data):
    """Push detections for a SPECIFIC camera, by ID. Used by the multi-camera
    server (app.py), where several cameras run in one process at once."""
    try:
        db.reference(f"/detections/{camera_id}").set(data)
        logger.info(f"[{camera_id}] Database updated successfully.")
    except Exception as e:
        logger.error(f"[{camera_id}] Failed to update database: {e}")


def log_history(camera_id, record):
    """Permanently append one detection event to the history log.
    Unlike update_camera_data (which OVERWRITES the live table on every
    frame), this uses push() to add a new, permanent entry every time —
    nothing here is ever erased, even if the camera restarts."""
    try:
        entry = list(record)
        entry.insert(0, camera_id)  # so history rows remember which camera saw them
        db.reference(f"/history/{camera_id}").push(entry)
    except Exception as e:
        logger.error(f"[{camera_id}] Failed to write history log: {e}")