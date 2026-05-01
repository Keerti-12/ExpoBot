#include <ArduinoBLE.h>

// ==========================================
// BLE UUIDs (must match your app)
// ==========================================
BLEService uartService("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");

// App → UNO → Jetson
BLECharacteristic rxCharacteristic(
  "6E400002-B5A3-F393-E0A9-E50E24DCCA9E",
  BLEWrite | BLEWriteWithoutResponse,
  20
);

// UNO → App (NEW: Notify)
BLECharacteristic txCharacteristic(
  "6E400003-B5A3-F393-E0A9-E50E24DCCA9E",
  BLENotify,
  20
);

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(9600);
  delay(2000);

  if (!BLE.begin()) {
    Serial.println("[ERROR] BLE failed!");
    while (1);
  }

  BLE.setLocalName("RoverBLE");
  BLE.setAdvertisedService(uartService);

  uartService.addCharacteristic(rxCharacteristic);
  uartService.addCharacteristic(txCharacteristic);

  BLE.addService(uartService);
  BLE.advertise();

  Serial.println("[UNO] BLE Bridge Ready");
}

// ==========================================
// SEND STATUS TO APP
// ==========================================
void sendToApp(String msg) {
  if (BLE.connected()) {
    txCharacteristic.writeValue(msg.c_str());
  }
}

// ==========================================
// MAIN LOOP
// ==========================================
void loop() {
  BLEDevice central = BLE.central();

  if (central) {
    Serial.println("[UNO] App Connected");

    while (central.connected()) {

      // ======================================
      // 1. FROM JETSON → APP (Forwarding)
      // ======================================
      if (Serial.available()) {
        String msg = Serial.readStringUntil('\n');
        msg.trim();

        if (msg.length() == 0) return;

        // Special handshake
        if (msg == "WHOAMI") {
          Serial.println("I_AM_UNO");
        } else {
          sendToApp(msg);   // 🔥 Forward everything to app
        }
      }

      // ======================================
      // 2. FROM APP → JETSON
      // ======================================
      if (rxCharacteristic.written()) {

        int len = rxCharacteristic.valueLength();
        if (len <= 0) return;

        uint8_t buffer[20];
        rxCharacteristic.readValue(buffer, len);

        char cmd = (char)buffer[0];

        // 🎯 Project selection
        if (cmd == '1' || cmd == '2' || cmd == '3' || cmd == '4') {
          Serial.print("TARGET:");
          Serial.println(cmd);
        }

        // 🛑 STOP / RESET
        else if (cmd == 'S') {
          Serial.println("RESET_ALL");
        }
      }
    }

    Serial.println("[UNO] App Disconnected");
  }

  // ======================================
  // STILL RESPOND TO JETSON (NO BLE)
  // ======================================
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    if (msg == "WHOAMI") {
      Serial.println("I_AM_UNO");
    }
  }
}
