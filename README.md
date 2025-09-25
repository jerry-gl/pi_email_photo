
# Raspberry Pi PIR Motion Detector with Email Alerts and Web Dashboard

## Overview
This project uses a Raspberry Pi with a PIR motion sensor, camera, and LEDs to detect motion, capture photos, and send them via email. A Flask-based web dashboard is also included to monitor the number of captured photos and view recent snapshots.

## Features
- **Motion Detection**: PIR sensor detects motion.
- **LED Indicators**:
  - **Red LED**: Lights up when motion is detected.
  - **Yellow LED**: Blinks while motion is continuously detected (not in cooldown).
  - **Green LED**: Flashes after a successful email is sent.
- **Camera Capture**: Takes a photo if motion lasts longer than a threshold.
- **Email Alerts**: Sends the photo as an email attachment.
- **Cooldown System**: Prevents multiple triggers within a short time window.
- **Web Dashboard**:
  - Homepage displays total photo count.
  - `/check-photos` page lists the 10 most recent photos.

## Hardware Requirements
- Raspberry Pi 4 (or compatible)
- PIR motion sensor
- 3 LEDs (Red, Yellow, Green) with resistors
- Raspberry Pi Camera Module (Picamera2 supported)
- Internet connection for email and dashboard

## Software Requirements
- Python 3
- Libraries: `gpiozero`, `picamera2`, `opencv-python`, `flask`, `yagmail`, `python-dotenv`

## Setup Instructions
1. Clone this repository to your Raspberry Pi.
   ```bash
   git clone <your-repo-url>
   cd raspberrypi_udemy
   ```
2. Create a Python virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Configure your `.env` file with email credentials:
   ```env
   SENDER_EMAIL=your_email@gmail.com
   PASSWORD=your_password_or_app_password
   RECEIVER_EMAIL=recipient_email@gmail.com
   ```
4. Run the motion detection program:
   ```bash
   python main.py
   ```
5. Run the Flask dashboard:
   ```bash
   python check.py
   ```
   Then open `http://<raspberry-pi-ip>:8080` in your browser.

## File Descriptions
- **main.py**: Handles motion detection, camera preview, photo capture, email sending, and LED control.
- **check.py**: Flask web application for monitoring photos and displaying recent captures.
- **config.py**: Configuration file for GPIO pins, directories, and system settings.
- **logs/**: Directory containing logs of captured photos.
- **photos/**: Directory where captured photos are saved.

## Future Improvements
- Add authentication to the web dashboard.
- Support for video recording.
- Add cloud storage integration (Google Drive, Dropbox, etc.).
- Push notifications in addition to email.

---
Developed as part of a Raspberry Pi project.
