#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

ESP8266WebServer server(80);

const char* AP_SSID = "MEGA_ROBOT";
const char* AP_PASS = "12345678";

int currentProject = 1;
int targetProject = 1;

int timePerProject = 2000; // testing only

bool moving = false;
unsigned long moveStartTime = 0;
int stepsRemaining = 0;
char moveDirection = 'X';

void sendCmd(char c) {
  Serial.print("JCMD=");
  Serial.println(c);
}

String htmlPage() {
  return R"HTML(
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Project Navigation</title>
<style>
body { font-family: Arial; text-align:center; padding-top:40px; }
input { font-size:22px; padding:10px; width:150px; }
button { font-size:22px; padding:10px 20px; margin-left:10px; }
</style>
</head>
<body>

<h2>Enter Project Number</h2>
<p>Current Project: <span id="cur">1</span></p>

<input type="number" id="proj" placeholder="Project #" />
<button onclick="go()">Go</button>

<script>
function go(){
  let p = document.getElementById("proj").value;
  fetch('/go?p=' + p)
  .then(r => r.text())
  .then(t => alert(t));
}
</script>

</body>
</html>
)HTML";
}

void handleRoot() {
  server.send(200, "text/html", htmlPage());
}

void handleGo() {
  if (!server.hasArg("p")) {
    server.send(400, "text/plain", "Enter project number");
    return;
  }

  targetProject = server.arg("p").toInt();

  int diff = targetProject - currentProject;

  if (diff == 0) {
    server.send(200, "text/plain", "Already at that project");
    return;
  }

  stepsRemaining = abs(diff);

  if (diff > 0) {
    moveDirection = 'W'; // forward
  } else {
    moveDirection = 'S'; // backward
  }

  moving = true;
  moveStartTime = millis();

  sendCmd(moveDirection);

  server.send(200, "text/plain", "Moving to project " + String(targetProject));
}

void setup() {
  Serial.begin(9600);

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);

  server.on("/", handleRoot);
  server.on("/go", handleGo);

  server.begin();
}

void loop() {
  server.handleClient();

  if (moving) {
    if (millis() - moveStartTime >= timePerProject) {

      stepsRemaining--;

      if (moveDirection == 'W')
        currentProject++;
      else
        currentProject--;

      moveStartTime = millis();

      if (stepsRemaining <= 0) {
        moving = false;
        sendCmd('X'); // stop
      }
    }
  }
}