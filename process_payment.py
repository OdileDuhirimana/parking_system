import serial
import time
import csv
import os

csv_file = 'plates_log.csv'

def mark_payment_success(plate_number):
    if not os.path.exists(csv_file):
        print("[ERROR] Log file does not exist.")
        return False

    updated = False
    rows = []

    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if row[0] == plate_number and row[1] == '0':
                row[1] = '1'
                updated = True
            rows.append(row)

    if updated:
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        print(f"[UPDATED] Payment marked for plate {plate_number}")
    else:
        print(f"[INFO] No unpaid record found for {plate_number}")

    return updated

def main(serial_port):
    try:
        ser = serial.Serial(serial_port, 9600, timeout=1)
        time.sleep(2)
    except serial.SerialException as e:
        print(f"Serial Port Error: {e}")
        return

    print("PC-side process payment system ready.")

    current_plate = None
    current_charge = None

    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                if line.startswith("PLATE:"):
                    current_plate = line[6:].strip().upper()
                    print(f"[RFID] Detected plate: {current_plate}")
                elif line.startswith("CHARGE:"):
                    current_charge = int(line[7:].strip())
                    print(f"[RFID] Parking charge: {current_charge} units")

                    # Mark payment
                    if current_plate:
                        success = mark_payment_success(current_plate)
                        if success:
                            ser.write("DONE\n".encode())
                        else:
                            ser.write("FAIL\n".encode())
                        current_plate = None
                        current_charge = None

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("Program terminated by user.")
    finally:
        ser.close()

if __name__ == "__main__":
    serial_port = input("Enter serial port (e.g., COM3 or /dev/ttyUSB0): ").strip()
    main(serial_port)
