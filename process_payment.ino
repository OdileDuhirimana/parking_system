#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 9
#define SS_PIN 10

MFRC522 rfid(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();

  Serial.println("--------------------------------");
  Serial.println("    Parking Fee Calculator");
  Serial.println("--------------------------------");
  Serial.println("Scan the RFID card to deduct parking fee...");
  Serial.println("--------------------------------");

  // Default key: FF FF FF FF FF FF
  for (byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }
}

void loop() {
  // Wait for a new RFID card
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return;
  }

  // Authenticate for block 5 (balance block)
  byte blockAddr = 5;
  MFRC522::StatusCode status = rfid.PCD_Authenticate(
    MFRC522::PICC_CMD_MF_AUTH_KEY_A, blockAddr, &key, &(rfid.uid));
  if (status != MFRC522::STATUS_OK) {
    Serial.print("Authentication failed: ");
    Serial.println(rfid.GetStatusCodeName(status));
    return;
  }

  // Read block 5: Get balance
  byte buffer[18];
  byte size = 18;
  status = rfid.MIFARE_Read(blockAddr, buffer, &size);
  if (status != MFRC522::STATUS_OK) {
    Serial.print("Read failed: ");
    Serial.println(rfid.GetStatusCodeName(status));
    return;
  }

  // Parse balance
  String cashStr = "";
  for (byte i = 0; i < 16; i++) {
    char c = (char)buffer[i];
    if (isDigit(c)) {
      cashStr += c;
    }
  }

  if (cashStr == "") {
    Serial.println("No balance found on the card.");
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    return;
  }

  long currentCash = cashStr.toInt();
  Serial.print("Current balance: ");
  Serial.println(currentCash);

  // Deduct fee
  long fee = 200;
  if (currentCash < fee) {
    Serial.println("Insufficient funds. Cannot deduct parking fee.");
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    return;
  }

  long newBalance = currentCash - fee;
  Serial.print("New balance after deduction: ");
  Serial.println(newBalance);

  // Write new balance back to block 5
  String newBalanceStr = String(newBalance);
  for (byte i = 0; i < 16; i++) {
    buffer[i] = (i < newBalanceStr.length()) ? newBalanceStr[i] : ' ';
  }

  status = rfid.MIFARE_Write(blockAddr, buffer, 16);
  if (status != MFRC522::STATUS_OK) {
    Serial.print("Write failed: ");
    Serial.println(rfid.GetStatusCodeName(status));
  } else {
    Serial.println("Updated balance successfully written to the card.");
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  delay(1000); // Wait for 1 second before restarting loop
}
