import cv2
from ultralytics import YOLO
import os
import time
import serial
import serial.tools.list_ports
import csv
from collections import Counter
import pytesseract
import platform
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('car_entry.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
try:
    model = YOLO('best.pt')
    logger.info("YOLO model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load YOLO model: {e}")
    exit(1)
save_dir = 'plates'
os.makedirs(save_dir, exist_ok=True)
csv_file = 'plates_log.csv'
if not os.path.exists(csv_file):
    try:
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Plate Number', 'Payment Status', 'Timestamp'])
        logger.info(f"Created CSV file: {csv_file}")
    except Exception as e:
        logger.error(f"Failed to create CSV file: {e}")
        exit(1)
def detect_arduino_port():
    """Detect Arduino port automatically"""
    try:
        ports = list(serial.tools.list_ports.comports())
        system = platform.system()
        logger.info(f"Detecting Arduino port on {system}")
        for port in ports:
            if system == "Linux":
                if "ttyUSB" in port.device or "ttyACM" in port.device:
                    logger.info(f"Arduino detected on {port.device}")
                    return port.device
            elif system == "Darwin":
                if "usbmodem" in port.device or "usbserial" in port.device:
                    logger.info(f"Arduino detected on {port.device}")
                    return port.device
            elif system == "Windows":
                if "COM" in port.device:
                    logger.info(f"Arduino detected on {port.device}")
                    return port.device
        logger.warning("No Arduino port detected")
        return None
    except Exception as e:
        logger.error(f"Error detecting Arduino port: {e}")
        return None
arduino_port = detect_arduino_port()
arduino = None
if arduino_port:
    try:
        arduino = serial.Serial(arduino_port, 9600, timeout=1)
        time.sleep(2) 
        logger.info(f"Connected to Arduino on {arduino_port}")
    except serial.SerialException as e:
        logger.error(f"Failed to connect to Arduino: {e}")
else:
    logger.warning("Running in camera-only mode")
def read_distance(arduino):
    """Read distance from Arduino with proper error handling"""
    try:
        if arduino and arduino.in_waiting > 0:
            line = arduino.readline().decode('utf-8').strip()
            if line:
                distance = float(line)
                if distance < 0:
                    logger.warning("Invalid distance reading: negative value")
                    return None
                logger.debug(f"Distance read: {distance} cm")
                return distance
    except (serial.SerialException, ValueError, UnicodeDecodeError) as e:
        logger.error(f"Error reading distance: {e}")
    return None
try:
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("Failed to open video capture")
        exit(1)
    logger.info("Video capture initialized")
except Exception as e:
    logger.error(f"Error initializing video capture: {e}")
    exit(1)
plate_buffer = []
entry_cooldown = 300 
last_saved_plate = None
last_entry_time = 0
results = None
logger.info("System ready. Press 'q' to exit")
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            logger.warning("Failed to capture frame")
            continue
        
        distance = read_distance(arduino)
        
        if distance is not None:
            logger.info(f"Distance: {distance} cm")
            
            if distance <= 50:
                try:
                    results = model(frame)
                    logger.debug("License plate detection completed")
                    
                    for result in results:
                        for box in result.boxes:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            if x2 <= x1 or y2 <= y1:
                                logger.warning("Invalid bounding box coordinates")
                                continue
                            
                            plate_img = frame[y1:y2, x1:x2]
                            
                            try:
                                gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                                thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                                
                                plate_text = pytesseract.image_to_string(
                                    thresh,
                                    config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                                ).strip().replace(" ", "")
                                
                                if "RA" in plate_text:
                                    start_idx = plate_text.find("RA")
                                    plate_candidate = plate_text[start_idx:]
                                    
                                    if len(plate_candidate) >= 7:
                                        plate_candidate = plate_candidate[:7]
                                        prefix, digits, suffix = plate_candidate[:3], plate_candidate[3:6], plate_candidate[6]
                                        
                                        if (prefix.isalpha() and prefix.isupper() and
                                            digits.isdigit() and suffix.isalpha() and suffix.isupper()):
                                            
                                            logger.info(f"Valid plate detected: {plate_candidate}")
                                            plate_buffer.append(plate_candidate)
                                            
                                            timestamp_str = time.strftime('%Y%m%d_%H%M%S')
                                            image_filename = f"{plate_candidate}_{timestamp_str}.jpg"
                                            save_path = os.path.join(save_dir, image_filename)
                                            try:
                                                cv2.imwrite(save_path, plate_img)
                                                logger.info(f"Plate image saved: {save_path}")
                                            except Exception as e:
                                                logger.error(f"Failed to save plate image: {e}")
                                            
                                            cv2.imshow("Plate", plate_img)
                                            cv2.imshow("Processed", thresh)
                                            
                                            if len(plate_buffer) >= 3:
                                                most_common = Counter(plate_buffer).most_common(1)[0][0]
                                                current_time = time.time()
                                                
                                                if (most_common != last_saved_plate or
                                                    (current_time - last_entry_time) > entry_cooldown):
                                                    
                                                    try:
                                                        with open(csv_file, 'a', newline='') as f:
                                                            writer = csv.writer(f)
                                                            writer.writerow([
                                                                most_common,
                                                                0,  
                                                                time.strftime('%Y-%m-%d %H:%M:%S')
                                                            ])
                                                        logger.info(f"Plate {most_common} logged to CSV")
                                                    except Exception as e:
                                                        logger.error(f"Failed to log to CSV: {e}")
                                                        continue
                                                    
                                                    if arduino:
                                                        try:
                                                            arduino.write(b'1')
                                                            logger.info("Opening gate (sent '1')")
                                                            time.sleep(15) 
                                                            arduino.write(b'0')
                                                            logger.info("Closing gate (sent '0')")
                                                        except serial.SerialException as e:
                                                            logger.error(f"Gate control error: {e}")
                                                    
                                                    last_saved_plate = most_common
                                                    last_entry_time = current_time
                                                else:
                                                    logger.info("Duplicate plate within 5 min window, skipped")
                                                
                                                plate_buffer.clear()
                                        
                                        else:
                                            logger.warning(f"Invalid plate format: {plate_candidate}")
                                    else:
                                        logger.warning(f"Plate text too short: {plate_candidate}")
                                else:
                                    logger.debug("No 'RA' found in plate text")
                            except Exception as e:
                                logger.error(f"Error processing plate image: {e}")
                except Exception as e:
                    logger.error(f"Error during plate detection: {e}")
        
        if distance is not None and distance <= 50 and results is not None:
            annotated_frame = results[0].plot()
        else:
            annotated_frame = frame
        
        cv2.imshow('Webcam Feed', annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            logger.info("Exit command received")
            break
except KeyboardInterrupt:
    logger.info("System interrupted by user")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
finally:
    logger.info("Initiating system shutdown")
    cap.release()
    if arduino:
        try:
            arduino.close()
            logger.info("Arduino connection closed")
        except Exception as e:
            logger.error(f"Error closing Arduino connection: {e}")
    cv2.destroyAllWindows()
    logger.info("System shutdown complete")
