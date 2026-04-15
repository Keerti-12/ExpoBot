#include <ArduinoBLE.h>
#include <AccelStepper.h>

// ===== MOTOR PINS =====
#define L_STEP 4
#define L_DIR 5
#define L_EN 7

#define R_STEP 2
#define R_DIR 3
#define R_EN 6

// ===== IR PINS =====
#define S1 8
#define S2 9
#define S3 10
#define S4 11
#define S5 12

AccelStepper leftMotor(1, L_STEP, L_DIR);
AccelStepper rightMotor(1, R_STEP, R_DIR);

// ===== PID =====
float Kp = 25;
float Ki = 0;
float Kd = 15;

int error = 0, lastError = 0;
float integral = 0, derivative = 0, correction = 0;
int lastErrorSign = 0;

// ===== SPEED =====
int baseSpeed = 400;

// ===== POSITION =====
int currentPosition = 1;
int targetPosition = 1;
bool navigationMode = false;
int direction = 0; // +1 forward, -1 backward

// ===== GAP DETECTION =====
bool inGap = false;
unsigned long gapStartTime = 0;
bool gapProcessed = false;

// ===== LINE LOST =====
unsigned long whiteStartTime = 0;
bool lineLost = false;

// ===== RECOVERY =====
unsigned long recoveryStart = 0;
unsigned long MAX_RECOVERY_TIME = 1500;

// ===== BLE =====
BLEService uartService("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");
BLEByteCharacteristic rxChar("6E400002-B5A3-F393-E0A9-E50E24DCCA9E", BLEWrite | BLEWriteWithoutResponse);

void setup() {
  Serial.begin(115200);

  pinMode(L_EN, OUTPUT);
  pinMode(R_EN, OUTPUT);
  digitalWrite(L_EN, LOW);
  digitalWrite(R_EN, LOW);

  pinMode(S1, INPUT);
  pinMode(S2, INPUT);
  pinMode(S3, INPUT);
  pinMode(S4, INPUT);
  pinMode(S5, INPUT);

  leftMotor.setMaxSpeed(800);
  rightMotor.setMaxSpeed(800);

  // BLE
  BLE.begin();
  BLE.setLocalName("RoverBLE");
  BLE.setAdvertisedService(uartService);
  uartService.addCharacteristic(rxChar);
  BLE.addService(uartService);
  BLE.advertise();

  Serial.println("System Ready");
}

// ===== LOOP =====
void loop() {

  BLEDevice central = BLE.central();

  if (central) {
    while (central.connected()) {

      if (rxChar.written()) {
        char cmd = (char)rxChar.value();
        processCommand(cmd);
      }

      if (navigationMode) {

        updateLineStatus();

        if (lineLost) {
          handleRecovery();
        } else {
          recoveryStart = 0;
          decideDirection();
          pidLineFollow();
          detectGap();
        }
      }

      leftMotor.runSpeed();
      rightMotor.runSpeed();
    }

    stopBot();
    BLE.advertise();
  }
}

// ===== COMMAND =====
void processCommand(char cmd) {

  if (cmd == 'S') {
    navigationMode = false;
    stopBot();
    Serial.println("STOP");
    return;
  }

  if (cmd >= '1' && cmd <= '9') {
    targetPosition = cmd - '0';
    navigationMode = true;

    Serial.print("Target: ");
    Serial.println(targetPosition);
  }
}

// ===== DIRECTION =====
void decideDirection() {
  if (targetPosition > currentPosition) direction = 1;
  else if (targetPosition < currentPosition) direction = -1;
  else direction = 0;
}

// ===== PID LINE FOLLOW =====
void pidLineFollow() {

  int s1 = digitalRead(S1);
  int s2 = digitalRead(S2);
  int s3 = digitalRead(S3);
  int s4 = digitalRead(S4);
  int s5 = digitalRead(S5);

  if      (s1 == LOW) error = -2;
  else if (s2 == LOW) error = -1;
  else if (s3 == LOW) error = 0;
  else if (s4 == LOW) error = 1;
  else if (s5 == LOW) error = 2;
  else error = lastError;

  if (error > 0) lastErrorSign = 1;
  else if (error < 0) lastErrorSign = -1;

  integral += error;
  derivative = error - lastError;
  correction = Kp * error + Ki * integral + Kd * derivative;
  lastError = error;

  int leftSpeed  = baseSpeed - correction;
  int rightSpeed = baseSpeed + correction;

  if (direction == -1) {
    leftSpeed  = -leftSpeed;
    rightSpeed = -rightSpeed;
  }

  leftSpeed  = constrain(leftSpeed, -800, 800);
  rightSpeed = constrain(rightSpeed, -800, 800);

  leftMotor.setSpeed(leftSpeed);
  rightMotor.setSpeed(rightSpeed);
}

// ===== GAP DETECTION =====
void detectGap() {

  int s1 = digitalRead(S1);
  int s2 = digitalRead(S2);
  int s3 = digitalRead(S3);
  int s4 = digitalRead(S4);
  int s5 = digitalRead(S5);

  bool isWhite = (s1 && s2 && s3 && s4 && s5);

  if (isWhite && !inGap) {
    inGap = true;
    gapStartTime = millis();
    gapProcessed = false;
  }

  if (!isWhite && inGap) {

    unsigned long gapDuration = millis() - gapStartTime;

    if (gapDuration > 50 && !gapProcessed) {

      currentPosition += direction;

      Serial.print("Position: ");
      Serial.println(currentPosition);

      gapProcessed = true;
    }

    inGap = false;
  }

  if (currentPosition == targetPosition) {
    Serial.println("Reached Target!");
    navigationMode = false;
    stopBot();
  }
}

// ===== LINE STATUS =====
void updateLineStatus() {

  int s1 = digitalRead(S1);
  int s2 = digitalRead(S2);
  int s3 = digitalRead(S3);
  int s4 = digitalRead(S4);
  int s5 = digitalRead(S5);

  bool isWhite = (s1 && s2 && s3 && s4 && s5);

  if (isWhite) {
    if (whiteStartTime == 0) whiteStartTime = millis();

    if (millis() - whiteStartTime > 200) {
      lineLost = true;
    }
  } else {
    whiteStartTime = 0;
    lineLost = false;
  }
}

// ===== SMART RECOVERY =====
void handleRecovery() {

  if (recoveryStart == 0) recoveryStart = millis();

  unsigned long elapsed = millis() - recoveryStart;

  // Phase 1: Directional search
  if (elapsed < 500) {

    if (direction == 1) {
      leftMotor.setSpeed(200);
      rightMotor.setSpeed(400);
    }
    else if (direction == -1) {
      leftMotor.setSpeed(-200);
      rightMotor.setSpeed(-400);
    }
  }

  // Phase 2: Spin search
  else if (elapsed < MAX_RECOVERY_TIME) {

    if (lastErrorSign >= 0) {
      leftMotor.setSpeed(300);
      rightMotor.setSpeed(-300);
    } else {
      leftMotor.setSpeed(-300);
      rightMotor.setSpeed(300);
    }
  }

  // Phase 3: FAIL SAFE
  else {

    Serial.println("Line Ended → STOP");

    navigationMode = false;
    stopBot();
  }
}

// ===== STOP =====
void stopBot() {
  leftMotor.setSpeed(0);
  rightMotor.setSpeed(0);
}