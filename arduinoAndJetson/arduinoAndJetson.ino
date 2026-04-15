#include <ArduinoBLE.h>
#include <AccelStepper.h>

// ===== STEPPER PINS =====
#define L_STEP 4
#define L_DIR 5
#define L_EN 7

#define R_STEP 2
#define R_DIR 3
#define R_EN 6

// ===== IR SENSOR PINS =====
#define S1 8
#define S2 9
#define S3 10
#define S4 11
#define S5 12

AccelStepper leftMotor(AccelStepper::DRIVER, L_STEP, L_DIR);
AccelStepper rightMotor(AccelStepper::DRIVER, R_STEP, R_DIR);

// ===== PID SETTINGS =====
float Kp = 45;
float Kd = 220;
int baseSpeed = 200;

float previousError = 0;

// ===== BLE SETUP =====
BLEService uartService("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");
BLEByteCharacteristic rxCharacteristic(
  "6E400002-B5A3-F393-E0A9-E50E24DCCA9E",
  BLEWrite | BLEWriteWithoutResponse
);

// ===== STATES =====
enum Mode {
  IDLE,
  BLE_MODE,
  RUNNING
};

Mode currentMode = IDLE;

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(9600);

  pinMode(L_EN, OUTPUT);
  pinMode(R_EN, OUTPUT);
  digitalWrite(L_EN, LOW);
  digitalWrite(R_EN, LOW);

  pinMode(S1, INPUT);
  pinMode(S2, INPUT);
  pinMode(S3, INPUT);
  pinMode(S4, INPUT);
  pinMode(S5, INPUT);

  rightMotor.setPinsInverted(true, false, false);

  leftMotor.setMaxSpeed(800);
  rightMotor.setMaxSpeed(800);

  if (!BLE.begin()) {
    Serial.println("[ERROR] BLE failed!");
    while (1);
  }

  BLE.setLocalName("RoverBLE");
  BLE.setAdvertisedService(uartService);
  uartService.addCharacteristic(rxCharacteristic);
  BLE.addService(uartService);
  BLE.advertise();

  Serial.println("[SYSTEM] Ready - Waiting for PERSON");
}

// ==========================================
// LINE FOLLOWING
// ==========================================
void followLineForward() {
  int s1 = digitalRead(S1);
  int s2 = digitalRead(S2);
  int s3 = digitalRead(S3);
  int s4 = digitalRead(S4);
  int s5 = digitalRead(S5);

  float error = 0;
  bool lineDetected = false;

  if (s1 == LOW) { error = -2; lineDetected = true; }
  else if (s2 == LOW) { error = -1; lineDetected = true; }
  else if (s3 == LOW) { error = 0; lineDetected = true; }
  else if (s4 == LOW) { error = 1; lineDetected = true; }
  else if (s5 == LOW) { error = 2; lineDetected = true; }

  if (lineDetected) {
    float derivative = error - previousError;
    float correction = (Kp * error) + (Kd * derivative);
    previousError = error;

    correction = constrain(correction, -150, 150);

    int dynamicBase = baseSpeed - (abs(error) * 40);
    dynamicBase = constrain(dynamicBase, 60, baseSpeed);

    leftMotor.setSpeed(dynamicBase - correction);
    rightMotor.setSpeed(dynamicBase + correction);
  } 
  else {
    leftMotor.setSpeed(0);
    rightMotor.setSpeed(0);
  }
}

// ==========================================
// STOP MOTORS
// ==========================================
void stopMotors() {
  leftMotor.setSpeed(0);
  rightMotor.setSpeed(0);
}

// ==========================================
// RUN PROJECT (LINE FOLLOW)
// ==========================================
void runProject() {
  Serial.println("MOVING");   // 🔥 Notify Jetson

  previousError = 0;

  unsigned long startTime = millis();

  while (millis() - startTime < 5000) {
    followLineForward();
    leftMotor.runSpeed();
    rightMotor.runSpeed();
  }

  stopMotors();

  Serial.println("DONE");     // 🔥 Notify Jetson
}

// ==========================================
// BLE HANDLER
// ==========================================
void handleBLE() {
  BLEDevice central = BLE.central();

  if (central) {
    Serial.println("[BLE] Connected");

    while (central.connected()) {

      if (rxCharacteristic.written()) {
        char cmd = (char)rxCharacteristic.value();

        Serial.print("[BLE RECEIVED]: ");
        Serial.println(cmd);

        // 🔥 START PROJECT ONLY ON USER INPUT
        if (cmd == 'F' || cmd == 'A') {
          currentMode = RUNNING;
          runProject();
          currentMode = IDLE;
          return;
        }

        if (cmd == 'S') {
          stopMotors();
        }
      }

      leftMotor.runSpeed();
      rightMotor.runSpeed();
    }

    Serial.println("[BLE] Disconnected");
    BLE.advertise();
  }
}

// ==========================================
// MAIN LOOP
// ==========================================
void loop() {

  // 🔹 SERIAL FROM JETSON
  if (Serial.available()) {
    String data = Serial.readStringUntil('\n');
    data.trim();

    Serial.print("[JETSON → ARDUINO]: ");
    Serial.println(data);

    // ✅ PERSON → STOP EVERYTHING
    if (data == "PERSON") {
      Serial.println("[STATE] Person detected → stopping robot");
      stopMotors();
      currentMode = IDLE;
    }

    // ✅ ENABLE BLE AFTER GREETING
    else if (data == "ASK_PROJECT") {
      Serial.println("[STATE] Waiting for project selection via BLE");
      currentMode = BLE_MODE;
    }
  }

  // 🔹 STATE MACHINE
  if (currentMode == BLE_MODE) {
    handleBLE();
  }

  leftMotor.runSpeed();
  rightMotor.runSpeed();
}