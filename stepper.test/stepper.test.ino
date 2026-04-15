// --- Pin Definitions ---
const int leftStep  = 2;
const int leftDir   = 3;
const int leftEna   = 6;

const int rightStep = 4;
const int rightDir  = 5;
const int rightEna  = 7;

// --- Variables ---
int speedPercent = 0;     // 0–100
int motorDelay = 4000;    // actual delay
char currentCommand = 'X';
String currentDir = "STOP";

unsigned long lastStatusPrint = 0;

void setup() {
  Serial.begin(9600);

  pinMode(leftStep, OUTPUT);
  pinMode(leftDir, OUTPUT);
  pinMode(leftEna, OUTPUT);

  pinMode(rightStep, OUTPUT);
  pinMode(rightDir, OUTPUT);
  pinMode(rightEna, OUTPUT);

  Serial.println("=== ROBOT DEBUG MODE STARTED ===");
  Serial.println("Waiting for commands...");
}

void loop() {

  // 🔹 Read Serial Input
  if (Serial.available() > 0) {

    if (isdigit(Serial.peek())) {
      speedPercent = Serial.parseInt();
      speedPercent = constrain(speedPercent, 0, 100);

      motorDelay = map(speedPercent, 0, 100, 4000, 200);

      Serial.println();
      Serial.println("---- SPEED UPDATE ----");
      Serial.print("Speed Received: ");
      Serial.print(speedPercent);
      Serial.println("%");

      Serial.print("Motor Delay: ");
      Serial.println(motorDelay);
      Serial.println("----------------------");
    }
    else {
      char cmd = toupper(Serial.read());

      if (cmd == 'W' || cmd == 'A' || cmd == 'S' || cmd == 'D' || cmd == 'X') {
        currentCommand = cmd;

        Serial.println();
        Serial.println("---- COMMAND RECEIVED ----");
        Serial.print("Command: ");
        Serial.println(cmd);
        Serial.println("--------------------------");
      }
    }
  }

  executeCommand();

  // 🔹 Print robot status every 1 second
  if (millis() - lastStatusPrint > 1000) {
    lastStatusPrint = millis();

    Serial.println();
    Serial.println("===== ROBOT STATUS =====");
    Serial.print("Direction: ");
    Serial.println(currentDir);

    Serial.print("Speed: ");
    Serial.print(speedPercent);
    Serial.println("%");

    Serial.print("Delay: ");
    Serial.println(motorDelay);

    Serial.println("========================");
  }
}

// --- Command Execution ---
void executeCommand() {
  switch(currentCommand) {
    case 'W': moveForward(); break;
    case 'S': moveBackward(); break;
    case 'A': turnLeft(); break;
    case 'D': turnRight(); break;
    case 'X': stopMotors(); break;
  }
}

// --- Motion Engine ---
void stepMotors(bool leftFwd, bool rightFwd, bool active, String label) {

  currentDir = label;

  if(!active || speedPercent == 0) {
    digitalWrite(leftEna, HIGH);
    digitalWrite(rightEna, HIGH);
    return;
  }

  digitalWrite(leftEna, LOW);
  digitalWrite(rightEna, LOW);

  digitalWrite(leftDir, leftFwd ? HIGH : LOW);
  digitalWrite(rightDir, rightFwd ? HIGH : LOW);

  digitalWrite(leftStep, HIGH);
  digitalWrite(rightStep, HIGH);
  delayMicroseconds(motorDelay);

  digitalWrite(leftStep, LOW);
  digitalWrite(rightStep, LOW);
  delayMicroseconds(motorDelay);
}

// --- Movements ---
void moveForward()  { stepMotors(true, true, true, "FORWARD"); }
void moveBackward() { stepMotors(false, false, true, "BACKWARD"); }
void turnLeft()     { stepMotors(false, true, true, "LEFT"); }
void turnRight()    { stepMotors(true, false, true, "RIGHT"); }
void stopMotors()   { stepMotors(true, true, false, "STOP"); }