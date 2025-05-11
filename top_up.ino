#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 9
#define SS_PIN 10

MFRC522 rfid(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

String licensePlate = "";
long initialBalance = 0;
bool dataEntered = false;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();

  Serial.println("--------------------------------");
  Serial.println("    Parking Fee Writer");
  Serial.println("--------------------------------");

  // Default key
  for (byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }

  Serial.println("Enter license plate:");
}

void loop() {
  // Step 1: Get user input
  if (!dataEntered) {
    if (Serial.available()) {
      licensePlate = Serial.readStringUntil('\n');
      licensePlate.trim();
      Serial.println("Enter initial balance:");
      while (!Serial.available()); // wait for balance
      initialBalance = Serial.readStringUntil('\n').toInt();
      dataEntered = true;
      Serial.println("Now scan an RFID card to write the data...");
    }
    return;
  }

  // Step 2: Scan RFID card
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return;
  }

  byte blockAddr = 4;
  MFRC522::StatusCode status = rfid.PCD_Authenticate(
    MFRC522::PICC_CMD_MF_AUTH_KEY_A, blockAddr, &key, &(rfid.uid));
  if (status != MFRC522::STATUS_OK) {
    Serial.print("Authentication failed: ");
    Serial.println(rfid.GetStatusCodeName(status));
    return;
  }

  // Write license plate
  byte buffer[18];
  byte size = 18;
  licensePlate.getBytes(buffer, size);
  status = rfid.MIFARE_Write(blockAddr, buffer, 16);
  if (status != MFRC522::STATUS_OK) {
    Serial.print("Write failed: ");
    Serial.println(rfid.GetStatusCodeName(status));
    return;
  }
  Serial.println("License plate written.");

  // Write balance to block 5
  String balanceStr = String(initialBalance);
  for (byte i = 0; i < 16; i++) {
    buffer[i] = (i < balanceStr.length()) ? balanceStr[i] : ' ';
  }
  blockAddr = 5;
  status = rfid.MIFARE_Write(blockAddr, buffer, 16);
  if (status != MFRC522::STATUS_OK) {
    Serial.print("Write failed: ");
    Serial.println(rfid.GetStatusCodeName(status));
    return;
  }
  Serial.println("Balance written successfully.");

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  // Reset for next card
  dataEntered = false;
  Serial.println("\nEnter license plate for next card:");
  delay(1000);
}
