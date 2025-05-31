import cv2
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
import csv
from collections import Counter
import random
import logging
import shutil
import platform
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('car_exit.log')
    ]
)
logger = logging.getLogger(__name__)

# Check Tesseract availability
def check_tesseract():
    try:
        tesseract_version = pytesseract.get_tesseract_version()
        logger.info(f"[SETUP] Tesseract version {tesseract_version} configured successfully")
    except Exception as e:
        logger.error(f"[SETUP ERROR] Tesseract not found or failed to initialize: {str(e)}")
        if platform.system() == "Linux":
            logger.error("Please install Tesseract: 'sudo apt install tesseract-ocr' or ensure it's in PATH")
        elif platform.system() == "Windows":
            logger.error("Please install Tesseract and set the path to tesseract.exe")
        sys.exit(1)

check_tesseract()

# Load YOLO model
try:
    model = YOLO('best.pt')
    logger.info("[SETUP] YOLO model loaded successfully")
except Exception as e:
    logger.error(f"[SETUP ERROR] Failed to load YOLO model: {str(e)}")
    sys.exit(1)

csv_file = 'plates_log.csv'

def detect_arduino_port():
    """Detect an Arduino or compatible USB serial port."""
    try:
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            logger.warning("[ARDUINO] No serial ports detected")
            return None

        # Common Arduino USB-to-serial vendor IDs
        arduino_vids = [
            '1A86',  # CH340/CH341 (WCH)
            '0403',  # FTDI
            '2341',  # Arduino official
            '10C4'   # CP2102 (Silicon Labs)
        ]

        # Filter for USB or ACM ports, prioritizing Arduino-like devices
        candidate_ports = []
        for port in ports:
            if ('USB' in port.device or 'ACM' in port.device or
                any(vid in port.hwid.upper() for vid in arduino_vids)):
                candidate_ports.append(port)
        
        if not candidate_ports:
            logger.warning("[ARDUINO] No USB/ACM or Arduino-compatible ports found. Available ports:")
            for port in ports:
                logger.warning(f"- {port.device} ({port.description}, VID:PID={port.vid}:{port.pid})")
            return None
        
        if len(candidate_ports) > 1:
            logger.warning("[ARDUINO] Multiple candidate ports detected, selecting first one:")
            for port in candidate_ports:
                logger.warning(f"- {port.device} ({port.description}, VID:PID={port.vid}:{port.pid})")
        
        selected_port = candidate_ports[0].device
        logger.info(f"[ARDUINO] Selected port: {selected_port} ({candidate_ports[0].description})")
        return selected_port
    except Exception as e:
        logger.error(f"[ARDUINO ERROR] Failed to detect serial port: {str(e)}")
        return None

# Initialize Arduino connection
arduino = None
arduino_port = detect_arduino_port()
if arduino_port:
    try:
        arduino = serial.Serial(arduino_port, 9600, timeout=1)
        time.sleep(2)
        logger.info(f"[ARDUINO] Successfully connected to Arduino on {arduino_port}")
    except serial.SerialException as e:
        logger.error(f"[ARDUINO ERROR] Failed to connect to Arduino on {arduino_port}: {str(e)}")
        logger.error("Ensure the device is connected and you have permissions (e.g., 'sudo usermod -a -G dialout $USER')")
        arduino = None

def mock_ultrasonic_distance():
    """Simulate ultrasonic sensor distance for testing."""
    try:
        distance = random.choice([random.randint(10, 40)] + [random.randint(60, 150)] * 10)
        logger.debug(f"[SENSOR] Measured distance: {distance} cm")
        return distance
    except Exception as e:
        logger.error(f"[SENSOR ERROR] Failed to get distance: {str(e)}")
        return None

def ensure_csv_file():
    """Ensure the CSV file exists with the correct headers."""
    if not os.path.exists(csv_file):
        try:
            with open(csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Plate Number', 'Payment Status', 'Timestamp', 'Amount Paid'])
            logger.info(f"[CSV] Created new CSV file: {csv_file}")
        except PermissionError:
            logger.error(f"[CSV ERROR] No write permission for {csv_file}. Please check file permissions.")
            sys.exit(1)
    else:
        if not os.access(csv_file, os.W_OK):
            logger.error(f"[CSV ERROR] No write permission for {csv_file}. Please check file permissions.")
            sys.exit(1)

def is_payment_complete(plate_number):
    """Check if payment is complete for the given plate number."""
    try:
        ensure_csv_file()
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Plate Number'] == plate_number and row['Payment Status'] == '1':
                    logger.info(f"[PAYMENT] Payment verified for plate {plate_number}")
                    return True
            logger.warning(f"[PAYMENT] No payment record found for plate {plate_number}")
            return False
    except Exception as e:
        logger.error(f"[PAYMENT ERROR] Failed to check payment status: {str(e)}")
        return False

# Initialize webcam
def initialize_webcam():
    """Initialize the webcam with error handling."""
    for index in range(3):  # Try indices 0 to 2
        try:
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                logger.info(f"[WEBCAM] Video capture initialized on index {index}")
                return cap
            cap.release()
        except Exception as e:
            logger.debug(f"[WEBCAM] Failed to open webcam on index {index}: {str(e)}")
    logger.error("[WEBCAM ERROR] Failed to initialize any webcam")
    sys.exit(1)

cap = initialize_webcam()
plate_buffer = []
logger.info("[EXIT SYSTEM] System initialized and ready. Press 'q' to quit.")

try:
    while True:
        try:
            ret, frame = cap.read()
            if not ret:
                logger.error("[WEBCAM ERROR] Failed to capture frame")
                break

            distance = mock_ultrasonic_distance()
            if distance is None:
                logger.error("[SENSOR ERROR] Invalid distance reading, skipping frame")
                continue
            logger.info(f"[SENSOR] Distance: {distance} cm")

            if distance <= 50:
                try:
                    results = model(frame)
                    logger.debug("[YOLO] Object detection completed")
                except Exception as e:
                    logger.error(f"[YOLO ERROR] Detection failed: {str(e)}")
                    continue

                for result in results:
                    for box in result.boxes:
                        try:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            plate_img = frame[y1:y2, x1:x2]

                            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                            blur = cv2.GaussianBlur(gray, (5, 5), 0)
                            thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

                            plate_text = pytesseract.image_to_string(
                                thresh,
                                config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                            ).strip().replace(" ", "")
                            logger.debug(f"[OCR] Raw plate text: {plate_text}")

                            if "RA" in plate_text:
                                start_idx = plate_text.find("RA")
                                plate_candidate = plate_text[start_idx:]
                                if len(plate_candidate) >= 7:
                                    plate_candidate = plate_candidate[:7]
                                    prefix, digits, suffix = plate_candidate[:3], plate_candidate[3:6], plate_candidate[6]
                                    if (prefix.isalpha() and prefix.isupper() and
                                        digits.isdigit() and suffix.isalpha() and suffix.isupper()):
                                        logger.info(f"[VALID] Plate detected: {plate_candidate}")
                                        plate_buffer.append(plate_candidate)

                                        if len(plate_buffer) >= 3:
                                            most_common = Counter(plate_buffer).most_common(1)[0][0]
                                            plate_buffer.clear()
                                            logger.info(f"[PLATE] Confirmed plate: {most_common}")

                                            if is_payment_complete(most_common):
                                                logger.info(f"[ACCESS GRANTED] Payment complete for {most_common}")
                                                if arduino:
                                                    try:
                                                        arduino.write(b'1')
                                                        logger.info("[GATE] Opening gate (sent '1')")
                                                        time.sleep(15)
                                                        arduino.write(b'0')
                                                        logger.info("[GATE] Closing gate (sent '0')")
                                                    except Exception as e:
                                                        logger.error(f"[GATE ERROR] Failed to control gate: {str(e)}")
                                            else:
                                                logger.warning(f"[ACCESS DENIED] Payment NOT complete for {most_common}")
                                                if arduino:
                                                    try:
                                                        arduino.write(b'2')
                                                        logger.info("[ALERT] Buzzer triggered (sent '2')")
                                                    except Exception as e:
                                                        logger.error(f"[ALERT ERROR] Failed to trigger buzzer: {str(e)}")

                            cv2.imshow("Plate", plate_img)
                            cv2.imshow("Processed", thresh)
                            time.sleep(0.5)
                        except Exception as e:
                            logger.error(f"[PROCESSING ERROR] Failed to process plate: {str(e)}")
                            continue

                annotated_frame = results[0].plot() if distance <= 50 else frame
            else:
                annotated_frame = frame

            cv2.imshow("Exit Webcam Feed", annotated_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                logger.info("[EXIT SYSTEM] User requested shutdown")
                break

        except Exception as e:
            logger.error(f"[MAIN LOOP ERROR] Unexpected error in main loop: {str(e)}")
            continue

except KeyboardInterrupt:
    logger.info("[EXIT SYSTEM] Program terminated by user")

finally:
    logger.info("[CLEANUP] Releasing resources")
    try:
        cap.release()
        logger.info("[CLEANUP] Webcam released")
    except Exception as e:
        logger.error(f"[CLEANUP ERROR] Failed to release webcam: {str(e)}")

    if arduino:
        try:
            arduino.close()
            logger.info("[CLEANUP] Arduino connection closed")
        except Exception as e:
            logger.error(f"[CLEANUP ERROR] Failed to close Arduino connection: {str(e)}")

    try:
        cv2.destroyAllWindows()
        logger.info("[CLEANUP] All windows closed")
    except Exception as e:
        logger.error(f"[CLEANUP ERROR] Failed to close windows: {str(e)}")

    logger.info("[EXIT SYSTEM] Program terminated")