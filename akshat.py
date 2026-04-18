#!/usr/bin/env python3
import os, re, glob, subprocess, time, random, threading
import serial

# ------------------- CONFIG -------------------
DETECTNET_BIN = "/media/expobot/114/jetson-inference/build/aarch64/bin/detectnet"
NETWORK = "ssd-mobilenet-v2"
CAMERA_DEV = "/dev/video0"

GREETINGS_DIR = "/media/expobot/114/jetson-inference/build/greetings_wav"
EXPLAIN_DIR = "/media/expobot/114/jetson-inference/build/explain_wav"

AUDIO_DEVICE = "plughw:Audio,0"

PERSON_TIMEOUT = 1.2

# ------------------- SERIAL -------------------
def find_arduino():
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    for p in ports:
        try:
            s = serial.Serial(p, 9600, timeout=1)
            time.sleep(2)
            print(f"[SERIAL] Connected to {p}")
            return s
        except:
            continue
    return None

def send(ser, msg):
    try:
        ser.write((msg + "\n").encode())
        print(f"[JETSON → ARDUINO] {msg}")
    except Exception as e:
        print("[SERIAL SEND ERROR]", e)

# ------------------- AUDIO -------------------
def play_random(folder):
    files = [f for f in os.listdir(folder) if f.endswith(".wav")]
    if not files:
        print("[AUDIO] No files in", folder)
        return
    f = random.choice(files)
    print(f"[AUDIO] Playing Greeting: {f}")
    subprocess.call(["aplay", "-q", "-D", AUDIO_DEVICE, os.path.join(folder, f)])

def play_project(project_id):
    filename = f"project{project_id}.wav"
    filepath = os.path.join(EXPLAIN_DIR, filename)
    if os.path.exists(filepath):
        print(f"[AUDIO] Playing Explanation: {filename}")
        subprocess.call(["aplay", "-q", "-D", AUDIO_DEVICE, filepath])
    else:
        print(f"[AUDIO ERROR] File not found: {filepath}")

# ------------------- DETECTNET -------------------
class Detector:
    def __init__(self):
        self.proc = None
        self.last_seen = 0

    def start(self):
        print("[CAMERA] Starting detectnet")
        self.proc = subprocess.Popen(
            [DETECTNET_BIN, f"--network={NETWORK}", CAMERA_DEV],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.proc.stdout:
            if "person" in line.lower():
                self.last_seen = time.time()

    def stop(self):
        if self.proc:
            print("[CAMERA] Stopping detectnet")
            self.proc.terminate()
            self.proc = None

# ------------------- SERIAL LISTENER -------------------
class Listener:
    def __init__(self, ser):
        self.ser = ser
        self.state = "IDLE"
        self.target_project = "1" # Default fallback
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        while True:
            try:
                if self.ser.in_waiting:
                    msg = self.ser.readline().decode().strip()

                    if not msg:
                        continue
                    
                    # Parse dynamic incoming data
                    if msg.startswith("DIST:"):
                        dist_val = msg.split(":")[1]
                        print(f"[ARDUINO SENSOR] Ultrasonic Distance: {dist_val} cm")
                    elif msg.startswith("TARGET:"):
                        self.target_project = msg.split(":")[1]
                        print(f"[ARDUINO → JETSON] Target updated to Project {self.target_project}")
                    else:
                        print(f"[ARDUINO → JETSON] {msg}")

                    # State transitions
                    if msg == "MOVING":
                        self.state = "MOVING"
                    elif msg == "DONE":
                        self.state = "DONE"

            except Exception as e:
                print("[SERIAL ERROR]", e)

# ------------------- MAIN -------------------
def main():
    ser = find_arduino()
    listener = Listener(ser) if ser else None
    if listener:
        listener.start()

    detector = Detector()
    detector.start()

    person_present = False
    camera_paused = False
    explaining = False

    while True:
        now = time.time()
        seen = detector.last_seen and (now - detector.last_seen < PERSON_TIMEOUT)

        # -------- PERSON DETECTED --------
        if seen and not person_present and not explaining:
            person_present = True
            print("[INFO] PERSON detected")

            send(ser, "PERSON")

            play_random(GREETINGS_DIR)

            time.sleep(2)
            send(ser, "ASK_PROJECT")

        if not seen:
            person_present = False

        # -------- HANDLE MOVING --------
        if listener and listener.state == "MOVING" and not camera_paused:
            detector.stop()
            camera_paused = True

        # -------- HANDLE DONE --------
        if listener and listener.state == "DONE" and not explaining:
            explaining = True
            print(f"[SYSTEM] Starting explanation for Project {listener.target_project}")

            # Play the specific project file instead of random
            play_project(listener.target_project)

            print("[SYSTEM] Explanation done → restarting camera")

            detector.start()
            camera_paused = False
            listener.state = "IDLE"
            explaining = False

        time.sleep(0.05)

# ------------------- ENTRY -------------------
if __name__ == "__main__":
    main()
