import serial
import time
import csv
import os
import argparse
from datetime import datetime

def print_boxed_message(message, border_char="=", width=60):
    border = border_char * width
    padding = " " * ((width - len(message) - 2) // 2)
    print(f"\n{border}")
    print(f"|{padding}{message}{padding}{' ' if len(message) % 2 else ''}|")
    print(f"{border}\n")

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def read_last_unpaid_entry(csv_path, plate):
    try:
        with open(csv_path, 'r') as file:
            reader = csv.DictReader(file)
            entries = [row for row in reader if row['Plate Number'] == plate and row['Payment Status'] == '0']
            return entries[-1] if entries else None
    except FileNotFoundError:
        print_boxed_message("Creating CSV Log File...", "!")
        with open(csv_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Plate Number', 'Payment Status', 'Timestamp', 'Payment Timestamp'])
        return None
    except Exception as e:
        print_boxed_message(f"CSV Read Error: {e}", "!")
        return None

def update_payment_status(csv_path, plate, entry_timestamp):
    try:
        rows = []
        payment_time = get_timestamp()
        with open(csv_path, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['Plate Number'] == plate and row['Timestamp'] == entry_timestamp and row['Payment Status'] == '0':
                    row['Payment Status'] = '1'
                    row['Payment Timestamp'] = payment_time
                rows.append(row)

        with open(csv_path, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=['Plate Number', 'Payment Status', 'Timestamp', 'Payment Timestamp'])
            writer.writeheader()
            writer.writerows(rows)
        return payment_time
    except Exception as e:
        print_boxed_message(f"CSV Update Error: {e}", "!")
        return None

def main(serial_port):
    log_file = os.path.expanduser("~/plates_log.csv")

    try:
        ser = serial.Serial(serial_port, 9600, timeout=1)
        time.sleep(2)  # Allow serial to initialize
    except serial.SerialException as e:
        print_boxed_message(f"Serial Port Error: {e}", "!")
        return

    print_boxed_message("Linux Parking System Ready", "=")
    print(f"[{get_timestamp()}] Listening on {serial_port}...\n")

    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                if line.startswith("DATA:"):
                    try:
                        plate, cash = line[5:].split(',')
                        cash = int(cash)
                    except ValueError:
                        print_boxed_message("Invalid Data Format", "!")
                        continue

                    print_boxed_message("Data Received", "-")
                    print(f"[{get_timestamp()}] Plate: {plate} | Balance: {cash} units\n")

                    if cash <= 200:
                        print_boxed_message("Insufficient Balance", "!")
                        continue

                    last_entry = read_last_unpaid_entry(log_file, plate)
                    if not last_entry:
                        print_boxed_message("No Unpaid Entry Found", "!")
                        hours = 0
                    else:
                        entry_time = datetime.strptime(last_entry['Timestamp'], "%Y-%m-%d %H:%M:%S")
                        time_diff = datetime.now() - entry_time
                        hours = time_diff.total_seconds() / 3600

                    minutes = hours * 60
                    charge = 0
                    if minutes > 30:
                        charge = ((minutes - 30 + 29) // 30) * 100

                    if charge > cash:
                        print_boxed_message("Charge Exceeds Balance", "!")
                        continue

                    ser.write(f"CHARGE:{charge}\n".encode())
                    print_boxed_message("Charge Sent to Arduino", "-")
                    print(f"[{get_timestamp()}] Plate: {plate} | Duration: {hours:.2f} hrs | Charge: {charge} units\n")

                    response = ser.readline().decode('utf-8').strip()
                    if response == "DONE":
                        if last_entry:
                            payment_time = update_payment_status(log_file, plate, last_entry['Timestamp'])
                            if payment_time:
                                print_boxed_message("Payment Processed", "-")
                                print(f"[{get_timestamp()}] Paid at: {payment_time} | New Balance: {cash - charge}\n")
                        print_boxed_message("Gate Opened", "=")
                    else:
                        print_boxed_message(f"Arduino Error: {response}", "!")
            time.sleep(0.1)

    except KeyboardInterrupt:
        print_boxed_message("Program Terminated by User", "=")
    finally:
        ser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Linux Parking Payment System")
    parser.add_argument("--port", type=str, required=True, help="Serial port (e.g., /dev/ttyUSB0)")
    args = parser.parse_args()
    main(args.port)
