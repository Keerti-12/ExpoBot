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

#define PROXIMITY_PIN A0

AccelStepper leftMotor(AccelStepper::DRIVER, L_STEP, L_DIR);
AccelStepper rightMotor(AccelStepper::DRIVER, R_STEP, R_DIR);

// ===== PID SETTINGS =====
float Kp = 45;
float Kd = 220;
int baseSpeed = 200;
float previousError = 0;

// ===== SYSTEM STATE =====
enum State { IDLE, MOVING };
State currentState = IDLE;

int currentProjectCount = 0;
int targetProject = 0;
char direction = 'F';

// Proximity tracking
unsigned long lastCheckpointTime = 0;
bool isOnCheckpoint = false;
int triggerThreshold = 850;
int clearThreshold = 950;

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

  // Allow time for Jetson serial connection to stabilize
  delay(2000); 
  Serial.println("[MEGA] Ready");
}

void stopMotors() {
  leftMotor.setSpeed(0);
  rightMotor.setSpeed(0);
  leftMotor.runSpeed();
  rightMotor.runSpeed();
}

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
  } else {
    stopMotors();
  }
}

void followLineBackward() {
  // Simple reverse for now, can add reverse PID later if needed
  leftMotor.setSpeed(-baseSpeed);
  rightMotor.setSpeed(-baseSpeed);
}

void checkCheckpoints() {
  int proxVal = analogRead(PROXIMITY_PIN);

  // Trigger Logic
  if (proxVal < triggerThreshold && !isOnCheckpoint) {
    isOnCheckpoint = true;
    lastCheckpointTime = millis();
    
    if (direction == 'F') currentProjectCount++;
    else currentProjectCount--;
  } 
  // Clear Logic (Debounced)
  else if (proxVal > clearThreshold && isOnCheckpoint) {
    if (millis() - lastCheckpointTime > 800) {
      isOnCheckpoint = false;
    }
  }

  // Did we arrive?
  if (currentProjectCount == targetProject) {
    currentState = IDLE;
    stopMotors();
    Serial.println("DONE"); // Jetson is waiting for this exact string
  }
}

void loop() {
  // 1. NON-BLOCKING SERIAL LISTENER
  if (Serial.available() > 0) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    // Jetson ping to identify which board is which
    if (msg == "WHOAMI") {
      Serial.println("I_AM_MEGA");
    }
    // Jetson says stop (Person detected)
    else if (msg == "PERSON" || msg == "STOP") {
      currentState = IDLE;
      stopMotors();
    }
    // Jetson sets a target (e.g., "GO:3")
    else if (msg.startsWith("GO:")) {
      targetProject = msg.substring(3).toInt();
      if (targetProject == currentProjectCount) {
        Serial.println("DONE"); // Already there
      } else {
        direction = (targetProject > currentProjectCount) ? 'F' : 'B';
        currentState = MOVING;
        Serial.println("MOVING");
      }
    }
  }

  // 2. STATE EXECUTION
  if (currentState == MOVING) {
    if (direction == 'F') {
      followLineForward();
    } else {
      followLineBackward();
    }
    checkCheckpoints();
    leftMotor.runSpeed();
    rightMotor.runSpeed();
  } else {
    // Ensure motors hold completely still when IDLE
    stopMotors();
  }
}
