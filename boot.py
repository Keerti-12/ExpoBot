#!/usr/bin/env python3
import os, re, glob, subprocess, time, random, threading
import serial

# ==========================================
# CONFIG
# ==========================================
DETECTNET_BIN = "/media/expobot/114/jetson-inference/build/aarch64/bin/detectnet"
NETWORK = "ssd-mobilenet-v2"

GREETINGS_DIR = "/media/expobot/114/jetson-inference/build/greetings_wav"
EXPLAIN_DIR = "/media/expobot/114/jetson-inference/build/explain_wav"
BOOT_AUDIO_DIR = "/media/expobot/114/jetson-inference/build/boot_audio"

PERSON_TIMEOUT = 1.2
SERIAL_BAUD = 9600
current_audio_proc = None

# ==========================================
# AUDIO
# ==========================================
def find_audio_device():
    try:
        out = subprocess.check_output(["aplay", "-l"], universal_newlines=True)
        for line in out.split("\n"):
            if "card" in line and "device" in line and "tegra" not in line.lower():
                return "plughw:1,0"
    except:
        pass
    return "default"

def play_boot_audio(audio_device):
    print("[BOOT] Playing startup audio...")

    if not os.path.exists(BOOT_AUDIO_DIR):
        return

    files = [f for f in os.listdir(BOOT_AUDIO_DIR) if f.endswith(".wav")]
    if not files:
        return

    file = random.choice(files)
    path = os.path.join(BOOT_AUDIO_DIR, file)

    try:
        subprocess.Popen(["aplay", "-q", "-D", audio_device, path]).wait()
        print("[BOOT] Audio finished")
    except:
        pass

# ==========================================
# HARDWARE
# ==========================================
def find_camera_device():
    cams = glob.glob('/dev/video*')
    return cams[0] if cams else None

def connect_arduinos():
    uno, mega = None, None

    while not uno or not mega:

        if not uno:
            for port in glob.glob('/dev/ttyACM*'):
                try:
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(2)
                    s.write(b"WHOAMI\n")
                    if "UNO" in s.readline().decode():
                        uno = s
                        print("[SYSTEM] UNO connected")
                except: pass

        if not mega:
            for port in glob.glob('/dev/ttyUSB*'):
                try:
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(3)
                    s.write(b"WHOAMI\n")
                    if "MEGA" in s.readline().decode():
                        mega = s
                        print("[SYSTEM] MEGA connected")
                except: pass

        time.sleep(1)

    return uno, mega

# ==========================================
# STATUS
# ==========================================
def send_msg(ser, msg):
    try:
        ser.write((msg + "\n").encode())
    except:
        pass

def send_status(uno, msg):
    print("[STATUS]", msg)
    send_msg(uno, msg)

# ==========================================
# DETECTOR
# ==========================================
class Detector:
    def __init__(self, cam):
        self.cam = cam
        self.proc = None
        self.last_seen = 0

    def start(self):
        if not self.cam:
            return
        self.proc = subprocess.Popen(
            [DETECTNET_BIN, f"--network={NETWORK}", self.cam],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
        )
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.proc.stdout:
            if "person" in line.lower():
                self.last_seen = time.time()

# ==========================================
# MAIN
# ==========================================
def main():

    # 🔊 Start audio thread (NON-BLOCKING)
    audio_device = find_audio_device()
    threading.Thread(target=play_boot_audio, args=(audio_device,), daemon=True).start()

    print("[SYSTEM] Boot audio running in parallel...")

    # ⚙️ Detect hardware in parallel
    camera = find_camera_device()
    uno, mega = connect_arduinos()

    # 📡 Send status
    send_status(uno, "AUDIO_OK")
    send_status(uno, "CAMERA_OK" if camera else "CAMERA_FAIL")
    send_status(uno, "UNO_CONNECTED")
    send_status(uno, "MEGA_CONNECTED")

    # 🤖 Start AI
    detector = Detector(camera)
    detector.start()

    print("[SYSTEM] Fully ready while audio is playing 🚀")

    while True:

        # 🚫 Filter PROX
        if mega and mega.in_waiting:
            msg = mega.readline().decode().strip()
            if msg and not msg.startswith("PROX:"):
                send_status(uno, msg)

        time.sleep(0.05)

if __name__ == "__main__":
    main()
