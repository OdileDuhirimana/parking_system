import serial
import csv
import time
from datetime import datetime
import sys
import os
from serial.tools import list_ports

CSV_FILE = 'plates_log.csv'
RATE_PER_HOUR = 200

def detect_serial_port():
    """Automatically detect an available serial port."""
    ports = list_ports.comports()
    if not ports:
        print("Error: No serial ports detected. Please connect a serial device and try again.")
        sys.exit(1)
    
    # Filter for USB or ACM ports (common for USB-to-serial adapters)
    usb_ports = [port.device for port in ports if 'USB' in port.device or 'ACM' in port.device]
    
    if not usb_ports:
        print("Error: No USB or ACM serial ports found. Available ports:")
        for port in ports:
            print(f"- {port.device} ({port.description})")
        sys.exit(1)
    
    if len(usb_ports) > 1:
        print("Warning: Multiple USB/ACM ports detected. Selecting the first one.")
        print("Available ports:")
        for port in usb_ports:
            print(f"- {port}")
    
    selected_port = usb_ports[0]
    print(f"Selected serial port: {selected_port}")
    return selected_port

def initialize_serial():
    """Initialize the serial connection with error handling."""
    try:
        port = detect_serial_port()
        ser = serial.Serial(port, 9600, timeout=2)
        time.sleep(2)  # Wait for connection to stabilize
        print(f"Connected to serial port: {port}")
        return ser
    except serial.SerialException as e:
        print(f"Error opening serial port {port}: {e}")
        print("Please check the device connection and permissions (e.g., ensure user is in 'dialout' group).")
        sys.exit(1)

def ensure_csv_file():
    """Ensure the CSV file exists with the correct headers."""
    if not os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Plate Number', 'Payment Status', 'Timestamp', 'Amount Paid'])
            print(f"Created new CSV file: {CSV_FILE}")
        except PermissionError:
            print(f"Error: No write permission for {CSV_FILE}. Please check file permissions.")
            sys.exit(1)
    else:
        if not os.access(CSV_FILE, os.W_OK):
            print(f"Error: No write permission for {CSV_FILE}. Please check file permissions.")
            sys.exit(1)

def read_serial_line(ser):
    while True:
        if ser.in_waiting:
            return ser.readline().decode().strip()

def parse_data(line):
    try:
        parts = line.split(';')
        plate = parts[0].split(':')[1]
        balance = float(parts[1].split(':')[1])
        return plate, balance
    except Exception as e:
        print(f"Error parsing data: {e}")
        return None, None

def lookup_plate(plate):
    try:
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            unpaid_entries = [
                row for row in reader
                if row['Plate Number'] == plate and row['Payment Status'] == '0'
            ]
        
        if unpaid_entries:
            unpaid_entries.sort(key=lambda x: datetime.strptime(x['Timestamp'], "%Y-%m-%d %H:%M:%S"), reverse=True)
            entry_time = datetime.strptime(unpaid_entries[0]['Timestamp'], '%Y-%m-%d %H:%M:%S')
            return entry_time
        
        return None
    except FileNotFoundError:
        print(f"Error: {CSV_FILE} not found.")
        return None
    except PermissionError:
        print(f"Error: No read permission for {CSV_FILE}.")
        return None

def update_payment_status(plate, amount_due):
    try:
        rows = []
        updated = False
        with open(CSV_FILE, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

        header = rows[0]
        timestamp_index = header.index("Timestamp")
        
        unpaid_entries = [
            (i, row) for i, row in enumerate(rows[1:], start=1)
            if row[0] == plate and row[1] == '0'
        ]

        if unpaid_entries:
            unpaid_entries.sort(key=lambda x: datetime.strptime(x[1][timestamp_index], "%Y-%m-%d %H:%M:%S"), reverse=True)
            latest_index = unpaid_entries[0][0]
            rows[latest_index][1] = '1'  # Mark as paid
            if len(rows[latest_index]) <= 3:  # Ensure 'Amount Paid' column exists
                rows[latest_index].append(str(amount_due))
            else:
                rows[latest_index][3] = str(amount_due)
            updated = True

        if updated:
            with open(CSV_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(rows)
    except PermissionError:
        print(f"Error: No write permission for {CSV_FILE}.")
    except Exception as e:
        print(f"Error updating CSV: {e}")

def main():
    print("Welcome to Parking Management System 👋\n")
    print("Please follow the instructions below to process your payment.\n")
    
    # Ensure CSV file exists
    ensure_csv_file()
    
    # Initialize serial connection
    ser = initialize_serial()

    while True:
        print("Please place your payment card on the reader...")
        line = read_serial_line(ser)
        if "PLATE:" in line:
            print(f"\n[RECEIVED] Card data detected: {line}")
            plate, balance = parse_data(line)
            if plate is None or balance is None:
                continue
            
            entry_time = lookup_plate(plate)
            if not entry_time:
                print(f"[ERROR] No unpaid entry found for plate {plate}. Please try again or contact support.")
                continue

            print(f"\n[INFO] Card Details:")
            print(f"Plate Number: {plate}")
            print(f"Current Balance: {balance} RWF")
            
            duration_hours = (datetime.now() - entry_time).total_seconds() / 3600
            amount_due = round(duration_hours * RATE_PER_HOUR, 2)
            print(f"\n[INFO] Parking Duration: {duration_hours:.2f} hours")
            print(f"Amount Due: {amount_due} RWF")

            if balance < amount_due:
                print(f"[ERROR] Insufficient balance ({balance} RWF) to cover payment ({amount_due} RWF).")
                print("Please recharge your card at the payment kiosk and try again.")
                ser.write(f"INSUFFICIENT\n".encode())
                continue
            
            print(f"\n[INFO] Sufficient balance detected. Processing payment of {amount_due} RWF...")
            print("Please keep your card on the reader until payment is confirmed.")
            
            # Reduce balance
            new_balance = balance - amount_due
            ser.write(f"{amount_due}\n".encode())

            response = read_serial_line(ser)
            amount_due = round(amount_due, 2)
            new_balance = round(new_balance, 2)
            if response == "DONE":
                update_payment_status(plate, amount_due)
                print(f"\n[SUCCESS] Payment of {amount_due} RWF completed successfully for {plate}!")
                print(f"Updated Card Details:")
                print(f"Plate Number: {plate}")
                print(f"Remaining Balance: {new_balance} RWF")
                print("You may now remove your card. Thank you for using our parking system!")
            elif response == "INSUFFICIENT":
                print(f"[FAILED] Payment failed due to insufficient balance on card.")
                print("Please recharge your card and try again.")
            else:
                print(f"[ERROR] Unexpected response from card reader: {response}. Please try again or contact support.")
            
            print("\nReady for next transaction. Please place your card on the reader...")

if __name__ == "__main__":
    main()