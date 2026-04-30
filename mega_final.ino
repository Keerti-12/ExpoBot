#include <AccelStepper.h>

// ===== STEPPER PINS =====
#define L_STEP 4
#define L_DIR 5
#define L_EN 7

#define R_STEP 2
#define R_DIR 3
#define R_EN 6

// ===== FRONT IR SENSOR PINS =====
#define S1 8
#define S2 9
#define S3 10
#define S4 11
#define S5 12

// ===== REAR IR SENSOR PINS =====
// Ensure RS1 is the far-left sensor when looking out the BACK of the bot.
#define RS1 22
#define RS2 24
#define RS3 26
#define RS4 28
#define RS5 30

// ===== PROXIMITY SENSOR PIN =====
#define PROXIMITY_PIN A0

AccelStepper leftMotor(AccelStepper::DRIVER, L_STEP, L_DIR);
AccelStepper rightMotor(AccelStepper::DRIVER, R_STEP, R_DIR);

// ===== PID SETTINGS =====
float Kp = 45;
float Kd = 220;
int baseSpeed = 300; 
float previousError = 0;

// ===== SYSTEM STATE =====
enum State { IDLE, MOVING };
State currentState = IDLE;

int currentProjectCount = 0;
int targetProject = 0;
char direction = 'F';

// ===== PROXIMITY TRACKING =====
unsigned long lastCheckpointTime = 0;
unsigned long lastProxPrint = 0; 
bool isOnCheckpoint = false;
int triggerThreshold = 850; 
int clearThreshold = 880; 

void setup() {
  Serial.begin(9600);

  pinMode(L_EN, OUTPUT);
  pinMode(R_EN, OUTPUT);
  digitalWrite(L_EN, LOW);
  digitalWrite(R_EN, LOW);

  // Front Array
  pinMode(S1, INPUT);
  pinMode(S2, INPUT);
  pinMode(S3, INPUT);
  pinMode(S4, INPUT);
  pinMode(S5, INPUT);

  // Rear Array
  pinMode(RS1, INPUT);
  pinMode(RS2, INPUT);
  pinMode(RS3, INPUT);
  pinMode(RS4, INPUT);
  pinMode(RS5, INPUT);

  // Motor Inversions (Ensure both drive forward correctly)
  leftMotor.setPinsInverted(true, false, false); 
  rightMotor.setPinsInverted(false, false, false);

  leftMotor.setMaxSpeed(1000);
  rightMotor.setMaxSpeed(1000);

  delay(2000); 
  Serial.println("[MEGA] Motion Controller Ready");
}

void stopMotors() {
  leftMotor.setSpeed(0);
  rightMotor.setSpeed(0);
  leftMotor.runSpeed();
  rightMotor.runSpeed();
}

// ========================================================
// FORWARD PID LOGIC (Uses S1 - S5)
// ========================================================
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

    // Apply correct forward steering fix
    leftMotor.setSpeed(dynamicBase + correction);
    rightMotor.setSpeed(dynamicBase - correction);
  } else {
    stopMotors();
  }
}

// ========================================================
// BACKWARD PID LOGIC (Uses RS1 - RS5)
// ========================================================
void followLineBackward() {
  int rs1 = digitalRead(RS1);
  int rs2 = digitalRead(RS2);
  int rs3 = digitalRead(RS3);
  int rs4 = digitalRead(RS4);
  int rs5 = digitalRead(RS5);

  float error = 0;
  bool lineDetected = false;

  if (rs1 == LOW) { error = -2; lineDetected = true; }
  else if (rs2 == LOW) { error = -1; lineDetected = true; }
  else if (rs3 == LOW) { error = 0; lineDetected = true; }
  else if (rs4 == LOW) { error = 1; lineDetected = true; }
  else if (rs5 == LOW) { error = 2; lineDetected = true; }

  if (lineDetected) {
    float derivative = error - previousError;
    float correction = (Kp * error) + (Kd * derivative);
    previousError = error;

    correction = constrain(correction, -150, 150);
    int dynamicBase = baseSpeed - (abs(error) * 40);
    dynamicBase = constrain(dynamicBase, 60, baseSpeed);

    // Apply negative speeds with reverse steering math
    leftMotor.setSpeed(-dynamicBase - correction);
    rightMotor.setSpeed(-dynamicBase + correction);
  } else {
    stopMotors();
  }
}

void checkCheckpoints() {
  int proxVal = analogRead(PROXIMITY_PIN);

  // --- SAFE TELEMETRY TO JETSON (Printed 4 times a second) ---
  if (millis() - lastProxPrint > 250) {
    Serial.print("PROX:");
    Serial.println(proxVal);
    lastProxPrint = millis();
  }

  // 1. TRIGGER LOGIC
  if (proxVal < triggerThreshold && !isOnCheckpoint) {
    // 500ms debounce to prevent double-counting
    if (millis() - lastCheckpointTime > 500) {
      isOnCheckpoint = true;
      lastCheckpointTime = millis();
      
      if (direction == 'F') currentProjectCount++;
      else currentProjectCount--;
      
      // Send the exact checkpoint count to the Jetson
      Serial.print("CHECKPOINT:");
      Serial.println(currentProjectCount);
    }
  } 
  
  // 2. CLEAR LOGIC (Tighter threshold to un-trap the state)
  else if (proxVal > clearThreshold && isOnCheckpoint) {
    isOnCheckpoint = false;
  }

  // 3. TARGET REACHED LOGIC
  if (currentProjectCount == targetProject && currentState == MOVING) {
    currentState = IDLE;
    stopMotors();
    Serial.println("DONE"); 
  }
}

void loop() {
  if (Serial.available() > 0) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    if (msg == "WHOAMI") {
      Serial.println("I_AM_MEGA");
    }
    else if (msg == "STOP") {
      currentState = IDLE;
      stopMotors();
      Serial.println("PAUSED");
    }
    else if (msg == "RESET") {
      currentState = IDLE;
      stopMotors();
      currentProjectCount = 0; 
      targetProject = 0;
      previousError = 0;
      Serial.println("RESET_ACK");
    }
    else if (msg.startsWith("GO:")) {
      targetProject = msg.substring(3).toInt();
      
      if (targetProject == currentProjectCount) {
        Serial.println("DONE"); 
      } else {
        direction = (targetProject > currentProjectCount) ? 'F' : 'B';
        currentState = MOVING;
        previousError = 0; // Wipe the old error clean for the new direction
        Serial.println("MOVING");
      }
    }
  }

  if (currentState == MOVING) {
    if (direction == 'F') followLineForward();
    else followLineBackward();
    
    checkCheckpoints();
    leftMotor.runSpeed();
    rightMotor.runSpeed();
  } else {
    stopMotors();
  }
}
