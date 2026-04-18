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

// ===== ULTRASONIC SENSOR PINS =====
#define TRIG_PIN A0
#define ECHO_PIN A1

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
// ULTRASONIC FUNCTION
// ==========================================
long getDistanceCM() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  // 30000us timeout prevents motor stuttering if no echo is received (limits range to ~5m)
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); 
  
  if (duration == 0) return 999; // Out of range or error
  return duration * 0.034 / 2;
}

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

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

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
    Serial.println("DONE"); 
    return;
  }

  Serial.println("MOVING"); 

  char direction = (targetProject > currentProjectCount) ? 'F' : 'B';
  previousError = 0;
  
  unsigned long lastSensorPrint = 0;
  unsigned long lastCheckpointTime = 0; 

  int triggerThreshold = 15;  // < 15 cm triggers a checkpoint
  int clearThreshold = 25;    // > 25 cm clears the lock to prevent double-counting   

  // Initialize flag based on starting distance
  bool isOnCheckpoint = (getDistanceCM() < triggerThreshold); 

  while (currentProjectCount != targetProject) {
    long distCM = getDistanceCM();

    // Transmit distance to Jetson and Arduino Serial Monitor every 250ms
    if (millis() - lastSensorPrint > 250) {
      Serial.print("DIST:");
      Serial.println(distCM);
      lastSensorPrint = millis();
    }

    // --- 1. TRIGGER LOGIC (< 15 cm) ---
    if (distCM < triggerThreshold) {
      if (!isOnCheckpoint) {
        if (direction == 'F') currentProjectCount++;
        else currentProjectCount--;
        
        isOnCheckpoint = true; 
        lastCheckpointTime = millis(); 
        
        Serial.print("Passed Checkpoint! Count is now: ");
        Serial.println(currentProjectCount);
      }
    } 
    // --- 2. UNLOCK LOGIC (> 25 cm + 800ms Delay) ---
    else if (distCM > clearThreshold) {
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
          
          // 🔥 SYNC: Tell Jetson which project was selected so it queues the right audio
          Serial.print("TARGET:");
          Serial.println(target);

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
