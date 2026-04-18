#!/usr/bin/env python3
import os, glob, subprocess, time, random, threading
import serial

# ------------------- CONFIG -------------------
DETECTNET_BIN = "/media/expobot/114/jetson-inference/build/aarch64/bin/detectnet"
NETWORK = "ssd-mobilenet-v2"
CAMERA_DEV = "/dev/video0"

GREETINGS_DIR = "/media/expobot/114/jetson-inference/build/greetings_wav"
EXPLAIN_DIR = "/media/expobot/114/jetson-inference/build/explain_wav"

AUDIO_DEVICE = "plughw:Audio,0"
PERSON_TIMEOUT = 1.2

# ------------------- GLOBALS -------------------
audio_process = None

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
def stop_audio():
    global audio_process
    if audio_process and audio_process.poll() is None:
        print("[AUDIO] Stopping audio")
        audio_process.terminate()
        audio_process = None

def play_audio(filepath):
    global audio_process
    stop_audio()
    print(f"[AUDIO] Playing: {os.path.basename(filepath)}")
    audio_process = subprocess.Popen(
        ["aplay", "-q", "-D", AUDIO_DEVICE, filepath]
    )

def play_random(folder):
    files = [f for f in os.listdir(folder) if f.endswith(".wav")]
    if not files:
        print("[AUDIO] No files")
        return
    f = random.choice(files)
    play_audio(os.path.join(folder, f))

def play_project_audio(project_num):
    if project_num is None:
        print("[AUDIO] No project selected")
        return

    filepath = os.path.join(EXPLAIN_DIR, f"project{project_num}.wav")

    if not os.path.exists(filepath):
        print("[AUDIO] File not found:", filepath)
        return

    play_audio(filepath)

# ------------------- DETECTOR -------------------
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
        self.project = None
        self.stop_flag = False
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        while True:
            try:
                if self.ser.in_waiting:
                    msg = self.ser.readline().decode().strip()

                    if msg:
                        print(f"[ARDUINO → JETSON] {msg}")

                    if msg.startswith("PROJECT:"):
                        self.project = int(msg.split(":")[1])
                        print(f"[SYSTEM] Project Selected: {self.project}")

                    elif msg == "MOVING":
                        self.state = "MOVING"

                    elif msg == "DONE":
                        self.state = "DONE"

                    elif msg == "STOP":
                        print("[SYSTEM] STOP RECEIVED")
                        self.stop_flag = True

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

    # 🔥 FIX: allow camera warmup
    time.sleep(1)

    person_present = False
    camera_paused = False
    explaining = False
    last_trigger_time = 0
    COOLDOWN = 3  # seconds

    # 🔥 FIX: detect person already present at boot
    if detector.last_seen:
        print("[BOOT] Person already present")

        send(ser, "PERSON")
        play_random(GREETINGS_DIR)

        time.sleep(2)
        send(ser, "ASK_PROJECT")

        person_present = True
        last_trigger_time = time.time()

    while True:

        # -------- GLOBAL STOP --------
        if listener and listener.stop_flag:
            print("[SYSTEM] EXECUTING STOP")

            stop_audio()
            detector.start()

            listener.state = "IDLE"
            listener.project = None
            listener.stop_flag = False

            explaining = False
            camera_paused = False
            person_present = False

        now = time.time()
        seen = detector.last_seen and (now - detector.last_seen < PERSON_TIMEOUT)

        # -------- PERSON DETECTION --------
        if seen and not explaining:
            if not person_present and (now - last_trigger_time > COOLDOWN):

                print("[INFO] PERSON detected")

                send(ser, "PERSON")
                play_random(GREETINGS_DIR)

                time.sleep(2)
                send(ser, "ASK_PROJECT")

                last_trigger_time = now

            person_present = True
        else:
            person_present = False

        # -------- MOVING --------
        if listener and listener.state == "MOVING" and not camera_paused:
            detector.stop()
            camera_paused = True

        # -------- DONE --------
        if listener and listener.state == "DONE" and not explaining:
            explaining = True

            play_project_audio(listener.project)

            # wait until audio finishes OR STOP
            while audio_process and audio_process.poll() is None:
                if listener.stop_flag:
                    break
                time.sleep(0.1)

            detector.start()
            camera_paused = False

            listener.state = "IDLE"
            listener.project = None
            explaining = False

        time.sleep(0.05)

# ------------------- ENTRY -------------------
if __name__ == "__main__":
    main()