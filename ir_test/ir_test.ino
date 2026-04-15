#include <AccelStepper.h>

// ===== STEPPER PINS =====
// Left Motor
#define L_STEP 4
#define L_DIR 5
#define L_EN 7

// Right Motor
#define R_STEP 2
#define R_DIR 3
#define R_EN 6

// ===== IR SENSOR PINS =====
#define S1 8
#define S2 9
#define S3 10
#define S4 11
#define S5 12

// ===== STEPPER OBJECTS =====
AccelStepper leftMotor(AccelStepper::DRIVER, L_STEP, L_DIR);
AccelStepper rightMotor(AccelStepper::DRIVER, R_STEP, R_DIR);

// ===== SPEED SETTINGS =====
int baseSpeed = 700;
int turnSpeed = 300;

void setup() {
  // Enable pins
  pinMode(L_EN, OUTPUT);
  pinMode(R_EN, OUTPUT);
  digitalWrite(L_EN, LOW);  // enable driver
  digitalWrite(R_EN, LOW);

  // IR pins
  pinMode(S1, INPUT);
  pinMode(S2, INPUT);
  pinMode(S3, INPUT);
  pinMode(S4, INPUT);
  pinMode(S5, INPUT);

  // Stepper speed
  leftMotor.setMaxSpeed(600);
  rightMotor.setMaxSpeed(600);

  Serial.begin(9600);
}

// ===== MOVEMENT FUNCTIONS =====
void forward() {
  leftMotor.setSpeed(baseSpeed);
  rightMotor.setSpeed(baseSpeed);
}

void left() {
  leftMotor.setSpeed(turnSpeed);
  rightMotor.setSpeed(baseSpeed);
}

void right() {
  leftMotor.setSpeed(baseSpeed);
  rightMotor.setSpeed(turnSpeed);
}

void sharpLeft() {
  leftMotor.setSpeed(-baseSpeed);
  rightMotor.setSpeed(baseSpeed);
}

void sharpRight() {
  leftMotor.setSpeed(baseSpeed);
  rightMotor.setSpeed(-baseSpeed);
}

void stopBot() {
  leftMotor.setSpeed(0);
  rightMotor.setSpeed(0);
}

// ===== LOOP =====
void loop() {

  int s1 = digitalRead(S1);
  int s2 = digitalRead(S2);
  int s3 = digitalRead(S3);
  int s4 = digitalRead(S4);
  int s5 = digitalRead(S5);

  // Debug
  Serial.print(s1); Serial.print(" ");
  Serial.print(s2); Serial.print(" ");
  Serial.print(s3); Serial.print(" ");
  Serial.print(s4); Serial.print(" ");
  Serial.println(s5);

  // ===== LINE FOLLOWING (BLACK = LOW) =====
  if (s3 == LOW) {
    forward();
  }
  else if (s2 == LOW) {
    right();
  }
  else if (s4 == LOW) {
    left();
  }
  else if (s1 == LOW) {
    sharpRight();
  }
  else if (s5 == LOW) {
    sharpLeft();
  }
  else {
    stopBot();
  }

  // IMPORTANT: keep motors running
  leftMotor.runSpeed();
  rightMotor.runSpeed();
}
