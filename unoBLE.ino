#include <ArduinoBLE.h>

// ===== BLE SETUP =====
BLEService uartService("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");
BLEByteCharacteristic rxCharacteristic(
  "6E400002-B5A3-F393-E0A9-E50E24DCCA9E",
  BLEWrite | BLEWriteWithoutResponse
);

void setup() {
  Serial.begin(9600);
  
  // Wait for serial connection to Jetson
  delay(2000); 

  if (!BLE.begin()) {
    Serial.println("[ERROR] BLE failed to start!");
    while (1);
  }

  BLE.setLocalName("RoverBLE");
  BLE.setAdvertisedService(uartService);
  uartService.addCharacteristic(rxCharacteristic);
  BLE.addService(uartService);
  BLE.advertise();

  Serial.println("[UNO] BLE Bridge Ready");
}

void loop() {
  BLEDevice central = BLE.central();

  if (central) {
    // While connected to the app
    while (central.connected()) {
      
      // 1. LISTEN FOR JETSON COMMANDS
      if (Serial.available()) {
        String msg = Serial.readStringUntil('\n');
        msg.trim();
        if (msg == "WHOAMI") {
          Serial.println("I_AM_UNO");
        }
      }

      // 2. LISTEN FOR BLE APP COMMANDS
      if (rxCharacteristic.written()) {
        char cmd = (char)rxCharacteristic.value();

        if (cmd == '1' || cmd == '2' || cmd == '3' || cmd == '4') {
          // Tell Jetson which project was selected
          Serial.print("TARGET:");
          Serial.println(cmd);
        } 
        else if (cmd == 'S') {
          // GLOBAL RESET INITIATED
          Serial.println("RESET_ALL");
        }
      }
    }
  } else {
    // Ensure we still answer the Jetson even if BLE isn't connected yet
    if (Serial.available()) {
        String msg = Serial.readStringUntil('\n');
        msg.trim();
        if (msg == "WHOAMI") {
          Serial.println("I_AM_UNO");
        }
    }
  }
}
