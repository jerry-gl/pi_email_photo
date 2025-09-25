"""
Flask web app for monitoring photos captured by a Raspberry Pi.

Features:
- Shows the total number of photos recorded in a log file.
- Homepage (/) displays the photo count.
- '/check-photos' page lists up to the MAX_RECENT_PHOTOS most recent photos.
- Handles missing log entries and missing photo files gracefully.
"""

import os
import logging
from flask import Flask, url_for, render_template
from config import PHOTOS_DIR, LOG_FILE, STATIC_DIR

# ------------------ Configuration ------------------ #
MAX_RECENT_PHOTOS: int = 10

# ------------------ Logging ------------------ #
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ------------------ Flask App ------------------ #
app = Flask(__name__)

# ------------------ Helpers ------------------ #
def get_photo_count() -> int:
    """
    Return the number of photos logged in the log file.

    Returns:
        int: Number of valid photo entries.
    """
    if not os.path.exists(LOG_FILE):
        return 0

    with open(LOG_FILE, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    return len(lines)


# ------------------ Routes ------------------ #
@app.route("/")
def index():
    """
    Render the homepage with a button linking to /check-photos
    and display the total number of photos recorded.
    """
    photo_count = get_photo_count()
    return render_template("index.html", photo_count=photo_count)


@app.route("/check-photos")
def check_photos():
    """
    Display the most recent photos logged in photo_logs.txt, with error handling.
    """
    if not os.path.exists(LOG_FILE):
        return render_template("check_photos.html", photos=None, message="No photos found.")

    # Read filenames from the log file
    with open(LOG_FILE, "r") as f:
        filenames = [line.strip() for line in f if line.strip()]

    # Show only the most recent photos
    recent_photos = filenames[-MAX_RECENT_PHOTOS:]

    photos = []
    for filename in recent_photos:
        try:
            photo_path = os.path.join(PHOTOS_DIR, filename)
            if not os.path.exists(photo_path):
                continue  # Skip if the file is missing

            # Compute path relative to static folder
            relative_path = os.path.relpath(photo_path, STATIC_DIR)
            photo_url = url_for("static", filename=relative_path)
            photos.append(photo_url)

        except Exception as e:
            logging.error(f"Could not display {filename}: {e}", exc_info=True)

    if not photos:
        return render_template("check_photos.html", photos=None, message="No photos available.")

    return render_template("check_photos.html", photos=photos, message=None)


# ------------------ Main Entry ------------------ #
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)