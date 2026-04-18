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

// ===== PROXIMITY SENSOR PIN =====
#define PROXIMITY_PIN A0

AccelStepper leftMotor(AccelStepper::DRIVER, L_STEP, L_DIR);
AccelStepper rightMotor(AccelStepper::DRIVER, R_STEP, R_DIR);

// ===== PID SETTINGS =====
float Kp = 45;
float Kd = 220;
int baseSpeed = 200;

float previousError = 0;

// ===== CHECKPOINT TRACKING =====
int currentProjectCount = 0;

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

  pinMode(PROXIMITY_PIN, INPUT);

  // Invert right motor if necessary based on your wiring
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

  Serial.println("[SYSTEM] Ready - Waiting for PERSON from Jetson");
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

void followLineBackward() {
  leftMotor.setSpeed(-baseSpeed);
  rightMotor.setSpeed(-baseSpeed);
}

void stopMotors() {
  leftMotor.setSpeed(0);
  rightMotor.setSpeed(0);
}

// ==========================================
// TARGET PROJECT LOGIC (WITH JETSON SYNC)
// ==========================================
void runToProject(int targetProject) {
  if (targetProject == currentProjectCount) {
    Serial.print("Already at Project: ");
    Serial.println(currentProjectCount);
    // Tell Jetson we are done immediately so it can explain
    Serial.println("DONE"); 
    return;
  }

  // 🔥 CRITICAL: Tells Jetson run.py to pause camera
  Serial.println("MOVING"); 

  char direction = (targetProject > currentProjectCount) ? 'F' : 'B';
  previousError = 0;
  
  unsigned long lastSensorPrint = 0;
  unsigned long lastCheckpointTime = 0; 

  int triggerThreshold = 850; 
  int clearThreshold = 950;   

  bool isOnCheckpoint = (analogRead(PROXIMITY_PIN) < triggerThreshold); 

  while (currentProjectCount != targetProject) {
    int proxVal = analogRead(PROXIMITY_PIN);

    // Limit prints so we don't overflow the Jetson's serial buffer
    if (millis() - lastSensorPrint > 250) {
      Serial.print("PROX: ");
      Serial.print(proxVal);
      Serial.print(" | FLAG: ");
      Serial.println(isOnCheckpoint ? "LOCKED" : "CLEAR");
      lastSensorPrint = millis();
    }

    // --- 1. TRIGGER LOGIC (< 850) ---
    if (proxVal < triggerThreshold) {
      if (!isOnCheckpoint) {
        if (direction == 'F') currentProjectCount++;
        else currentProjectCount--;
        
        isOnCheckpoint = true; 
        lastCheckpointTime = millis(); 
        
        Serial.print("Passed Checkpoint! Count is now: ");
        Serial.println(currentProjectCount);
      }
    } 
    // --- 2. UNLOCK LOGIC (> 950 + 800ms Delay) ---
    else if (proxVal > clearThreshold) {
      if (isOnCheckpoint && (millis() - lastCheckpointTime > 800)) {
        isOnCheckpoint = false; 
      }
    }

    // --- MANUAL STOP FROM APP ---
    if (rxCharacteristic.written()) {
      char emergencyCmd = (char)rxCharacteristic.value();
      if (emergencyCmd == 'S') {
        Serial.println("MANUAL STOP TRIGGERED!");
        break; 
      }
    }

    // --- TARGET REACHED ---
    if (currentProjectCount == targetProject) {
      break; 
    }

    // --- MOVEMENT ---
    if (direction == 'F') {
      followLineForward();
    } else {
      followLineBackward(); 
    }

    leftMotor.runSpeed();
    rightMotor.runSpeed();
  }

  stopMotors();
  Serial.print("ARRIVED AT PROJECT: ");
  Serial.println(currentProjectCount); 

  // 🔥 CRITICAL: Tells Jetson run.py to resume camera and play explanation
  Serial.println("DONE"); 
}

// ==========================================
// BLE HANDLER
// ==========================================
void handleBLE() {
  BLEDevice central = BLE.central();

  if (central) {
    Serial.println("[BLE] App Connected!");

    while (central.connected()) {
      // Check for Jetson commands even while connected to BLE
      if (Serial.available()) {
        String data = Serial.readStringUntil('\n');
        data.trim();
        if (data == "PERSON") {
          stopMotors();
          currentMode = IDLE;
          return; // Exit BLE handler to stop everything
        }
      }

      if (rxCharacteristic.written()) {
        char cmd = (char)rxCharacteristic.value();

        Serial.print("BLE COMMAND RECEIVED: ");
        Serial.println(cmd);

        if (cmd == '1' || cmd == '2' || cmd == '3' || cmd == '4') {
          int target = cmd - '0'; 
          currentMode = RUNNING;
          runToProject(target);
          currentMode = IDLE; // Wait for next Jetson cycle
          return;
        }
        
        if (cmd == 'S') {
          stopMotors();
        }
      }

      leftMotor.runSpeed();
      rightMotor.runSpeed();
    }

    Serial.println("[BLE] App Disconnected. Advertising again...");
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

    // ✅ PERSON → STOP EVERYTHING
    if (data == "PERSON") {
      stopMotors();
      currentMode = IDLE;
    }

    // ✅ ENABLE BLE AFTER GREETING
    else if (data == "ASK_PROJECT") {
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