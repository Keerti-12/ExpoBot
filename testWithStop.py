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

# ------------------- AUDIO -------------------
AUDIO_DEVICE = "default"
AUDIO_PROCESS = None
AUDIO_LOCK = threading.Lock()

def find_working_audio_device():
    try:
        output = subprocess.check_output(["aplay", "-l"], universal_newlines=True)
        devices = []

        for line in output.split("\n"):
            match = re.search(r"card (\d+): .* device (\d+)", line)
            if match:
                card, dev = match.groups()
                devices.append(f"plughw:{card},{dev}")

        for dev in devices:
            result = subprocess.run(
                ["aplay", "-D", dev, "/usr/share/sounds/alsa/Front_Center.wav"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if result.returncode == 0:
                print(f"[AUDIO] Using {dev}")
                return dev

        return "default"
    except:
        return "default"


def stop_audio():
    global AUDIO_PROCESS
    if AUDIO_PROCESS and AUDIO_PROCESS.poll() is None:
        print("[AUDIO] Stopping audio")
        AUDIO_PROCESS.terminate()
        AUDIO_PROCESS = None


def play_audio(filepath):
    global AUDIO_PROCESS, AUDIO_DEVICE

    stop_audio()

    for _ in range(3):
        AUDIO_PROCESS = subprocess.Popen(
            ["aplay", "-D", AUDIO_DEVICE, filepath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        if AUDIO_PROCESS.wait() == 0:
            AUDIO_PROCESS = None
            return

        AUDIO_DEVICE = find_working_audio_device()
        time.sleep(0.3)


def play_random():
    files = [f for f in os.listdir(GREETINGS_DIR) if f.endswith(".wav")]
    if not files:
        return
    f = random.choice(files)
    print(f"[AUDIO] Greeting: {f}")
    threading.Thread(target=play_audio, args=(os.path.join(GREETINGS_DIR, f),), daemon=True).start()


def play_project(pid):
    f = os.path.join(EXPLAIN_DIR, f"project{pid}.wav")
    if os.path.exists(f):
        print(f"[AUDIO] Explaining project {pid}")
        play_audio(f)


# ------------------- SERIAL -------------------
def find_arduino():
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    for p in ports:
        try:
            s = serial.Serial(p, 9600, timeout=1)
            time.sleep(2)
            print(f"[SERIAL] Connected {p}")
            return s
        except:
            continue
    return None

def send(ser, msg):
    if ser:
        ser.write((msg + "\n").encode())
        print(f"[JETSON → ARDUINO] {msg}")


# ------------------- DETECTOR -------------------
class Detector:
    def __init__(self):
        self.proc = None
        self.last_seen = 0

    def start(self):
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
            self.proc.terminate()
            self.proc = None


# ------------------- LISTENER -------------------
class Listener:
    def __init__(self, ser):
        self.ser = ser
        self.state = "IDLE"
        self.target = "1"
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            if self.ser and self.ser.in_waiting:
                msg = self.ser.readline().decode().strip()
                print(f"[ARDUINO → JETSON] {msg}")

                if msg.startswith("TARGET:"):
                    self.target = msg.split(":")[1]

                elif msg == "MOVING":
                    self.state = "MOVING"

                elif msg == "DONE":
                    self.state = "DONE"

                elif msg == "STOP_ALL":
                    self.state = "STOP_ALL"


# ------------------- MAIN -------------------
def main():
    global AUDIO_DEVICE

    AUDIO_DEVICE = find_working_audio_device()

    ser = find_arduino()
    listener = Listener(ser) if ser else None

    detector = Detector()
    detector.start()

    person_present = False
    camera_paused = False
    explaining = False

    while True:

        # 🔴 EMERGENCY STOP
        if listener and listener.state == "STOP_ALL":
            print("[SYSTEM] EMERGENCY STOP")

            stop_audio()
            detector.stop()
            time.sleep(0.5)
            detector.start()

            listener.state = "IDLE"
            person_present = False
            camera_paused = False
            explaining = False
            continue

        now = time.time()
        seen = detector.last_seen and (now - detector.last_seen < PERSON_TIMEOUT)

        # 👤 PERSON DETECTED
        if seen and not person_present and not explaining:
            person_present = True
            print("[SYSTEM] PERSON detected")

            send(ser, "PERSON")
            play_random()

            time.sleep(2)
            send(ser, "ASK_PROJECT")

        if not seen:
            person_present = False

        # 🚗 MOVING
        if listener and listener.state == "MOVING" and not camera_paused:
            print("[SYSTEM] MOVING → pause camera")
            stop_audio()
            detector.stop()
            camera_paused = True

        # ✅ DONE
        if listener and listener.state == "DONE" and not explaining:
            explaining = True

            print("[SYSTEM] Explaining")
            play_project(listener.target)

            detector.start()
            camera_paused = False
            listener.state = "IDLE"
            explaining = False

        time.sleep(0.05)


if __name__ == "__main__":
    main()