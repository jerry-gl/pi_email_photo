"""
Program: Raspberry Pi PIR Motion Detector with Camera and Email Alert

Purpose:
    Monitor motion using a PIR sensor. When continuous motion is detected for a specified duration,
    capture a photo using the Pi camera and send it via email to a predefined address.

Features:
    - RED LED: Lights up immediately when motion is detected.
    - YELLOW LED: Blinks every second during continuous motion detection (non-cooldown).
    - GREEN LED: Blinks rapidly three times after a successful email is sent.
    - Cooldown period to prevent multiple captures/emails within a short timeframe.
    - Camera preview window running in a separate thread.
    - Graceful cleanup of GPIO and camera resources on exit.

Configuration:
    - PIR sensor pin: GPIO 4
    - LEDs pins: RED (17), YELLOW (27), GREEN (22)
    - Motion threshold: 5 seconds continuous motion before triggering capture
    - Cooldown duration: 30 seconds between captures/emails
    - Email credentials and recipient configured via environment variables (.env)

"""

""" 
Threading Overview:

1. Main Thread:
   - Executes the `main()` function.
   - Registers cleanup handlers and starts the camera preview.
   - Sets up PIR sensor callbacks.
   - Remains mostly idle using `signal.pause()` to keep the program running.

2. Camera Preview Thread (1 thread):
   - Started by `start_preview()`.
   - Continuously captures frames from the PiCamera2 and displays them in a preview window using OpenCV.
   - Runs until the preview_stop_event is set.

3. Yellow LED Blinking Thread(s) (1 per blink session, potentially multiple over time):
   - Started by `start_yellow_blink()` or `start_flash_yellow()`.
   - Toggles the YELLOW LED on/off at specified intervals.
   - Daemon threads that stop automatically when the corresponding flag (`yellow_blinking` or `yellow_flash`) is set to False.

4. Green LED Flash Thread (1 per flash event):
   - Started by `flash_green()`.
   - Blinks the GREEN LED a fixed number of times to indicate successful email sent.
   - Daemon thread.

5. Motion Handler Thread (1 thread):
   - Started in `main()` via `threading.Thread(target=handle_motion, daemon=True)`.
   - Continuously monitors the duration of detected motion.
   - Captures photos and sends email if motion exceeds threshold and cooldown is inactive.

6. Cooldown Timer Thread (1 per cooldown event):
   - Started within `handle_motion()` after a photo/email event.
   - Sets `cooldown_active` flag for `COOLDOWN_DURATION_SECONDS` to prevent repeated triggers.

Summary:
- Main thread: 1
- Active threads at any given time: 
    - 1 Camera preview thread
    - 1 Motion handler thread
    - 0-1 Yellow LED blinking or flashing thread
    - 0-1 Green LED flashing thread (only when email sent)
    - 0-1 Cooldown timer thread (only during cooldown)
- Total threads created during runtime: multiple daemon threads for LED blinking/flashing and cooldown, plus the main preview and motion threads.
"""


# --- Imports ---
from gpiozero import MotionSensor, LED
import signal
import threading
import time
import atexit
import os
import logging
import cv2
from picamera2 import Picamera2
import yagmail
from pathlib import Path
from config import (
    PIR_PIN, LED_PINS, PHOTOS_DIR, FRAME_SIZE, WINDOW_NAME, LOGS_DIR, LOG_FILE,
    SENDER_EMAIL, PASSWORD, RECEIVER_EMAIL, SUBJECT, BODY,
    MOTION_THRESHOLD_SECONDS, COOLDOWN_DURATION_SECONDS,
    YELLOW_FLASH_INTERVAL_SECONDS, GREEN_FLASH_COUNT,
    GREEN_FLASH_INTERVAL_SECONDS,
)

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# --- Global Variables ---
pir = MotionSensor(PIR_PIN)
leds = {name: LED(pin) for name, pin in LED_PINS.items()}

yellow_blinking = False
yellow_flash = False
cooldown_active = False
motion_start_time = None  # Timestamp when motion started

picam2 = None

# Threading synchronization
lock = threading.Lock()
preview_stop_event = threading.Event()

# ------------------ Utility Functions ------------------ #
def ensure_directory(path: str) -> None:
    """
    Ensure the directory exists; create it if it doesn't.

    Args:
        path: Directory path to ensure exists.
    """
    if not os.path.exists(path):
        os.makedirs(path)
        logging.info(f"Created directory: {path}")

def timestamped_filename(prefix: str, ext: str) -> str:
    """
    Generate a filename with a timestamp in the format YYYY-MM-DD_HH-MM-SS.

    Args:
        prefix: String prefix for the filename.
        ext: File extension.
    Returns:
        Filename string with timestamp.
    """
    now = time.localtime()
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", now)
    return f"{prefix}_{timestamp}.{ext}"

def save_photo(frame) -> str:
    """
    Save a photo frame to disk with a timestamped filename.

    Args:
        frame: The image/frame to save.
    Returns:
        The filename where the photo is saved.
    """
    ensure_directory(PHOTOS_DIR)
    filename = os.path.join(PHOTOS_DIR, timestamped_filename("photo", "jpg"))
    cv2.imwrite(filename, frame)
    logging.info(f"Photo saved: {filename}")
    log_photo_path(filename)
    return filename

def log_photo_path(photo_path: str) -> None:
    """
    Append the saved photo path to a log file inside LOGS_DIR.
    Creates the log file if it does not exist.

    Args:
        photo_path: Path to the photo file.
    """
    ensure_directory(LOGS_DIR)
    filename_only = os.path.basename(photo_path)

    try:
        with open(LOG_FILE, "a") as f:
            f.write(filename_only + "\n")
        logging.info(f"[LOG] Photo path logged: {filename_only}")
    except Exception as e:
        logging.error(f"[ERROR] Could not log photo path: {e}", exc_info=True)

# ------------------ Motion LED Handlers ------------------ #
def start_red():
    """
    Turn on the RED LED to indicate motion detected.
    """
    leds["red"].on()
    logging.info("[MOTION] Detected: RED LED ON")

def stop_red():
    """
    Turn off the RED LED to indicate no motion.
    """
    leds["red"].off()
    logging.info("[MOTION] NOT detected: RED LED OFF")

def motion_led_on():
    """
    Handler called when PIR sensor detects motion.
    Starts RED LED and yellow blinking if not in cooldown.
    """
    global motion_start_time
    start_red()
    motion_start_time = time.time()
    if not cooldown_active:
        start_yellow_blink()

def motion_led_off():
    """
    Handler called when PIR sensor stops detecting motion.
    Stops RED LED and yellow blinking.
    """
    global motion_start_time
    stop_red()
    stop_yellow_blink()
    motion_start_time = None

def start_yellow_blink() -> None:
    """
    Begin blinking the YELLOW LED every second while motion is detected.
    Runs in a daemon thread.
    """
    global yellow_blinking
    yellow_blinking = True

    def _blink_yellow() -> None:
        seconds = 0
        half_cycles = 0
        logging.info(f"[COUNTER] YELLOW elapsed {seconds} second")
        while yellow_blinking:
            leds["yellow"].toggle()
            half_cycles += 1
            if half_cycles % 2 == 0:
                seconds += 1
                logging.info(f"[COUNTER] YELLOW elapsed {seconds} seconds")
            time.sleep(0.5)
        leds["yellow"].off()  # Ensure LED is off when blinking stops
        return None

    threading.Thread(target=_blink_yellow, daemon=True).start()
    return None

def stop_yellow_blink() -> None:
    """
    Stop blinking the YELLOW LED.
    """
    global yellow_blinking
    yellow_blinking = False
    logging.info(f"[COUNTER] YELLOW Stopped")
    return None

def start_flash_yellow(interval: float = YELLOW_FLASH_INTERVAL_SECONDS) -> None:
    """
    Blink the YELLOW LED at a specified interval in a daemon thread.

    Args:
        interval: Time in seconds between ON and OFF states.
    """
    global yellow_flash
    yellow_flash = True
    logging.info(f"[NOTIFICATION] Flashing YELLOW LED")

    def _flash_yellow() -> None:
        while yellow_flash:
            leds["yellow"].on()
            time.sleep(interval)
            leds["yellow"].off()
            time.sleep(interval)
        return None

    threading.Thread(target=_flash_yellow, daemon=True).start()
    return None

def stop_flash_yellow() -> None:
    """
    Stop flashing the YELLOW LED.
    """
    global yellow_flash
    yellow_flash = False
    leds["yellow"].off()
    logging.info(f"[NOTIFICATION] Stopped flashing YELLOW LED")
    return None


def flash_green(times: int = GREEN_FLASH_COUNT, interval: float = GREEN_FLASH_INTERVAL_SECONDS) -> None:
    """
    Blink the GREEN LED a specified number of times quickly in a daemon thread.

    Args:
        times: Number of blinks.
        interval: Time in seconds between ON and OFF states.
    """
    def _flash_green() -> None:
        for _ in range(times):
            leds["green"].on()
            time.sleep(interval)
            leds["green"].off()
            time.sleep(interval)
        logging.info(f"[NOTIFICATION] GREEN LED Flashed")
        return None

    threading.Thread(target=_flash_green, daemon=True).start()
    return None

# ------------------ Camera Functions ------------------ #
def start_preview() -> None:
    """
    Initialize the camera and start the preview window in a separate thread.
    Allows live preview without blocking main program.
    """
    global picam2
    picam2 = Picamera2()

    # Adjusting RGB
    config = picam2.create_still_configuration(main={"size": FRAME_SIZE})
    picam2.configure(config)
    picam2.set_controls({"AwbEnable": True})

    picam2.start()

    def _preview_loop() -> None:
        try:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
            while not preview_stop_event.is_set():
                frame = picam2.capture_array()
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                cv2.imshow(WINDOW_NAME, frame_bgr)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    preview_stop_event.set()
            cv2.waitKey(1)  # Process any remaining frames
        except Exception as e:
            logging.error(f"Preview error: {e}", exc_info=True)
        finally:
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) >= 1:
                cv2.destroyWindow(WINDOW_NAME)
            picam2.stop()
            logging.info("[CAMERA] Preview thread stopped cleanly.")
        return None

    threading.Thread(target=_preview_loop, daemon=True).start()
    return None

def take_photo() -> str:
    """
    Capture a single photo frame from the camera and save it.

    Returns:
        Filename of the saved photo.
    Raises:
        RuntimeError: If camera is not initialized.
    """
    if picam2 is None:
        raise RuntimeError("Camera not initialized. Call start_preview() first.")

    frame = picam2.capture_array()
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    filename = save_photo(frame_bgr)
    return filename

# ------------------ Email Functions ------------------ #
def send_email(photo_filename: str):
    """
    Send an email with the captured photo attached.

    Args:
        photo_filename: Path to the photo file to attach.
    Raises:
        ValueError: If email password is not set in environment variables.
        FileNotFoundError: If the photo file does not exist.
    """
    if not PASSWORD:
        raise ValueError("Email password not set in environment variables.")

    yag = yagmail.SMTP(SENDER_EMAIL, PASSWORD)

    attachment_path = Path(photo_filename)
    if not attachment_path.exists():
        raise FileNotFoundError(f"Attachment not found: {attachment_path}")

    yag.send(
        to=RECEIVER_EMAIL,
        subject=SUBJECT,
        contents=BODY,
        attachments=str(attachment_path),
    )
    logging.info(f"Email sent successfully with attachment: {attachment_path}")

# ------------------ Cleanup Functions ------------------ #
def cleanup():
    """
    Gracefully stop threads, release GPIO and camera resources,
    and exit the program.
    """
    global picam2
    logging.info("[CLEANUP] Stopping threads and releasing resources...")

    preview_stop_event.set()
    time.sleep(0.2)  # Allow preview thread to stop

    # Turn off and close LEDs
    for led in leds.values():
        try:
            led.off()
        except Exception as e:
            logging.warning(f"LED off error: {e}")
        try:
            led.close()
        except Exception as e:
            logging.warning(f"LED close error: {e}")

    # Close PIR sensor
    try:
        pir.close()
    except Exception as e:
        logging.warning(f"PIR sensor close error: {e}")

    # Stop camera
    if picam2 is not None:
        try:
            picam2.stop()
            picam2 = None
            logging.info("Camera stopped")
        except Exception as e:
            logging.warning(f"Camera stop error: {e}")

    logging.info("[CLEANUP] All GPIOs and camera released. Exiting program.")
    exit(0)

# ------------------ Motion Handler ------------------ #
def reset_motion_timer():
    """
    Reset the motion start time to None.
    """
    global motion_start_time
    motion_start_time = None
    return None

def cooldown_timer():
    """
    Set cooldown flag for COOLDOWN_DURATION_SECONDS to prevent
    repeated photo capture and email sending.
    """
    global cooldown_active
    logging.info(f"[COOLDOWN] Started ({COOLDOWN_DURATION_SECONDS}s)")
    time.sleep(COOLDOWN_DURATION_SECONDS)
    cooldown_active = False
    logging.info(f"[COOLDOWN] Ended")
    return None

def handle_motion():
    """
    Continuously monitor motion duration. If motion lasts longer than
    MOTION_THRESHOLD_SECONDS and not in cooldown, capture photo and send email.
    Runs in a daemon thread.
    """
    global cooldown_active
    while True:
        if motion_start_time and not cooldown_active:
            duration = time.time() - motion_start_time
            if duration >= MOTION_THRESHOLD_SECONDS:
                stop_yellow_blink()
                logging.info("[MOTION] Motion threshold reached. Taking photo and sending email...")
                start_flash_yellow()
                email_sent = False
                try:
                    photo_file = take_photo()
                    send_email(photo_file)
                    email_sent = True
                except Exception as e:
                    logging.error(f"[ERROR] Failed to capture photo or send email: {e}", exc_info=True)
                finally:
                    if email_sent:
                        flash_green()
                    stop_flash_yellow()
                    cooldown_active = True
                    threading.Thread(target=cooldown_timer, daemon=True).start()
                    reset_motion_timer()
        time.sleep(0.2)
    return None

# ------------------ Main Program ------------------ #
def main():
    """
    Main entry point for the Raspberry Pi PIR motion detector program.
    Sets up hardware, camera preview, motion handlers, and runs until interrupted.
    """
    # --- Startup Message ---
    logging.info("Starting program... please wait, initializing camera...")

    # Optional: simulate small steps if initialization takes time
    for step in ["Setting up GPIOs", "Starting camera preview", "Registering PIR sensor"]:
        logging.info(f"Loading: {step}...")
        time.sleep(0.5)  # short delay to simulate progress

    # --- Cleanup Handlers ---
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda sig, frame: cleanup())

    # --- Camera Preview ---
    start_preview()
    logging.info("[CAMERA] Preview started")

    # --- PIR Callbacks ---
    pir.when_motion = motion_led_on
    pir.when_no_motion = motion_led_off
    logging.info("[PIR] Motion detection callbacks registered")

    # --- Start Motion Handler Thread ---
    threading.Thread(target=handle_motion, daemon=True).start()
    logging.info("[SYSTEM] Motion handler started")

    logging.info("Program fully loaded. Monitoring motion now.")
    signal.pause()
    return None

if __name__ == "__main__":
    main()
