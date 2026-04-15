#include <ArduinoBLE.h>
#include <AccelStepper.h>

// ===== STEPPER PINS =====
#define L_STEP 4
#define L_DIR 5
#define L_EN 7

#define R_STEP 2
#define R_DIR 3
#define R_EN 6

// ===== IR SENSOR PINS (Front Array) =====
#define S1 8
#define S2 9
#define S3 10
#define S4 11
#define S5 12

AccelStepper leftMotor(AccelStepper::DRIVER, L_STEP, L_DIR);
AccelStepper rightMotor(AccelStepper::DRIVER, R_STEP, R_DIR);

// ===== SIMPLE PID SETTINGS =====
float Kp = 45;    // Steering strength
float Kd = 220;   // Shock absorber (dampens wobble)
int baseSpeed = 200; // Normal driving speed

float previousError = 0;

// ===== BLE SETUP =====
BLEService uartService("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");
BLEByteCharacteristic rxCharacteristic(
  "6E400002-B5A3-F393-E0A9-E50E24DCCA9E",
  BLEWrite | BLEWriteWithoutResponse
);

char currentMode = 'S'; 

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

  // Hardware fix: Ensures both wheels drive forward together
  rightMotor.setPinsInverted(true, false, false); 

  leftMotor.setMaxSpeed(800);
  rightMotor.setMaxSpeed(800);

  if (!BLE.begin()) {
    while (1);
  }

  BLE.setLocalName("RoverBLE");
  BLE.setAdvertisedService(uartService);
  uartService.addCharacteristic(rxCharacteristic);
  BLE.addService(uartService);
  BLE.advertise();
}

// ==========================================
//   SIMPLE FORWARD PID TRACING
// ==========================================
void followLineForward() {
  int s1 = digitalRead(S1);
  int s2 = digitalRead(S2);
  int s3 = digitalRead(S3);
  int s4 = digitalRead(S4);
  int s5 = digitalRead(S5);

  float error = 0;
  bool lineDetected = false;

  // 1. Find the Line
  if (s1 == LOW) { error = -2; lineDetected = true; }
  else if (s2 == LOW) { error = -1; lineDetected = true; }
  else if (s3 == LOW) { error = 0; lineDetected = true; }
  else if (s4 == LOW) { error = 1; lineDetected = true; }
  else if (s5 == LOW) { error = 2; lineDetected = true; }

  // 2. Drive the Motors
  if (lineDetected) {
    // Calculate the correction using PID
    float derivative = error - previousError;
    float correction = (Kp * error) + (Kd * derivative);
    previousError = error; 

    // Smooth the turning
    correction = constrain(correction, -150, 150); 
    
    // Slow down on curves
    int dynamicBase = baseSpeed - (abs(error) * 40); 
    dynamicBase = constrain(dynamicBase, 60, baseSpeed); 

    // Apply speed to wheels
    leftMotor.setSpeed(dynamicBase - correction);
    rightMotor.setSpeed(dynamicBase + correction);
  } 
  else {
    // If the line is completely lost, stop the motors safely.
    leftMotor.setSpeed(0);
    rightMotor.setSpeed(0);
  }
}

// ==========================================
//                 MAIN LOOP
// ==========================================
void loop() {
  BLEDevice central = BLE.central();

  if (central) {
    while (central.connected()) {
      
      if (rxCharacteristic.written()) {
        char cmd = (char)rxCharacteristic.value();
        
        if (cmd == 'S') {
          currentMode = 'S';
        } else if (cmd == 'F' || cmd == 'A') {
          currentMode = 'F';
          previousError = 0; // Reset memory when starting
        }
      }

      if (currentMode == 'S') {
        leftMotor.setSpeed(0);
        rightMotor.setSpeed(0);
      } else if (currentMode == 'F') {
        followLineForward(); 
      }

      leftMotor.runSpeed();
      rightMotor.runSpeed();
    }

    // Safety Stop on disconnect
    leftMotor.setSpeed(0);
    rightMotor.setSpeed(0);
    currentMode = 'S';
    BLE.advertise();
  }
}