#!/usr/bin/env python3
import os, re, glob, subprocess, time, random, threading
import serial

# ------------------- CONFIG -------------------
DETECTNET_BIN = "/media/expobot/114/jetson-inference/build/aarch64/bin/detectnet"
NETWORK = "ssd-mobilenet-v2"
CAMERA_DEV = "/dev/video0"

GREETINGS_DIR = "/media/expobot/114/jetson-inference/build/greetings_wav"
EXPLAIN_DIR = "/media/expobot/114/jetson-inference/build/explain_wav"

PERSON_TIMEOUT = 1.2

# ------------------- AUDIO SYSTEM (UPGRADED) -------------------

AUDIO_DEVICE = "default"
AUDIO_LOCK = threading.Lock()

def find_working_audio_device():
    print("[AUDIO] Searching for working audio device...")

    try:
        output = subprocess.check_output(["aplay", "-l"], universal_newlines=True)
        devices = []

        for line in output.split("\n"):
            match = re.search(r"card (\d+): .* device (\d+)", line)
            if match:
                card, dev = match.groups()
                devices.append(f"plughw:{card},{dev}")

        # pick test file
        test_file = None
        for f in os.listdir(GREETINGS_DIR):
            if f.endswith(".wav"):
                test_file = os.path.join(GREETINGS_DIR, f)
                break

        if not test_file:
            print("[AUDIO ERROR] No test WAV file found!")
            return "default"

        for dev in devices:
            print(f"[AUDIO TEST] Trying {dev}")
            result = subprocess.run(
                ["aplay", "-D", dev, test_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            if result.returncode == 0:
                print(f"[AUDIO] Using device: {dev}")
                return dev

        print("[AUDIO WARNING] No working device found, fallback to default")
        return "default"

    except Exception as e:
        print("[AUDIO ERROR]", e)
        return "default"


def play_audio(filepath):
    global AUDIO_DEVICE

    with AUDIO_LOCK:  # prevent overlapping audio
        for attempt in range(3):
            print(f"[AUDIO] Attempt {attempt+1} on {AUDIO_DEVICE}")

            result = subprocess.run(
                ["aplay", "-D", AUDIO_DEVICE, filepath],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return True

            print("[AUDIO ERROR]", result.stderr.strip())

            # 🔥 Try to recover by finding new device
            print("[AUDIO] Re-detecting audio device...")
            AUDIO_DEVICE = find_working_audio_device()

            time.sleep(0.3)

        print("[AUDIO FAILURE] Could not play audio")
        return False


def play_random(folder):
    files = [f for f in os.listdir(folder) if f.endswith(".wav")]

    if not files:
        print("[AUDIO] No files in", folder)
        return

    f = random.choice(files)
    filepath = os.path.join(folder, f)

    print(f"[AUDIO] Playing Greeting: {f}")
    threading.Thread(target=play_audio, args=(filepath,), daemon=True).start()


def play_project(project_id):
    filename = f"project{project_id}.wav"
    filepath = os.path.join(EXPLAIN_DIR, filename)

    if os.path.exists(filepath):
        print(f"[AUDIO] Playing Explanation: {filename}")
        play_audio(filepath)
    else:
        print(f"[AUDIO ERROR] File not found: {filepath}")


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
        self.target_project = "1"
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

                    if msg.startswith("TARGET:"):
                        self.target_project = msg.split(":")[1]
                        print(f"[ARDUINO → JETSON] Target: {self.target_project}")
                    else:
                        print(f"[ARDUINO → JETSON] {msg}")

                    if msg == "MOVING":
                        self.state = "MOVING"
                    elif msg == "DONE":
                        self.state = "DONE"

            except Exception as e:
                print("[SERIAL ERROR]", e)


# ------------------- MAIN -------------------

def main():
    global AUDIO_DEVICE

    # 🔥 detect working audio once at startup
    AUDIO_DEVICE = find_working_audio_device()

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

        if seen and not person_present and not explaining:
            person_present = True
            print("[INFO] PERSON detected")

            send(ser, "PERSON")

            play_random(GREETINGS_DIR)

            time.sleep(2)
            send(ser, "ASK_PROJECT")

        if not seen:
            person_present = False

        if listener and listener.state == "MOVING" and not camera_paused:
            detector.stop()
            camera_paused = True

        if listener and listener.state == "DONE" and not explaining:
            explaining = True

            print(f"[SYSTEM] Explaining Project {listener.target_project}")
            play_project(listener.target_project)

            print("[SYSTEM] Restarting camera")
            detector.start()

            camera_paused = False
            listener.state = "IDLE"
            explaining = False

        time.sleep(0.05)


# ------------------- ENTRY -------------------

if __name__ == "__main__":
    main()