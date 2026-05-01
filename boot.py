#!/usr/bin/env python3
import os, re, glob, subprocess, time, random, threading
import serial

# ==========================================
# CONFIGURATION
# ==========================================
DETECTNET_BIN = "/media/expobot/114/jetson-inference/build/aarch64/bin/detectnet"
NETWORK = "ssd-mobilenet-v2"

GREETINGS_DIR = "/media/expobot/114/jetson-inference/build/greetings_wav"
EXPLAIN_DIR = "/media/expobot/114/jetson-inference/build/explain_wav"
BOOT_DIR = "/media/expobot/114/jetson-inference/build/boot_wav"

PERSON_TIMEOUT = 1.2
SERIAL_BAUD = 9600
current_audio_proc = None

# ==========================================
# HARDWARE DETECTION
# ==========================================
def find_audio_device(max_retries=15, delay_seconds=2):
    print("[SYSTEM] Scanning for USB Audio Hardware...")
    for _ in range(max_retries):
        try:
            output = subprocess.check_output(["aplay", "-l"], stderr=subprocess.STDOUT, universal_newlines=True)
            for line in output.split('\n'):
                match = re.search(r"card (\d+): .*? \[(.*?)\], device (\d+)", line)
                if match:
                    card_num, card_name, dev_num = match.groups()
                    if "tegra" in card_name.lower(): continue
                    dev_str = f"plughw:{card_num},{dev_num}"
                    print(f"[SYSTEM] ✓ Audio Found: {dev_str}")
                    return dev_str
            time.sleep(delay_seconds)
        except:
            time.sleep(delay_seconds)
    return "default"

def find_camera_device():
    ports = glob.glob('/dev/video*')
    if ports:
        ports.sort()
        print(f"[SYSTEM] ✓ Camera Found: {ports[0]}")
        return ports[0]
    return "/dev/video0"

def connect_arduinos():
    print("\n[SYSTEM] Hunting for Arduinos...")
    uno_serial, mega_serial = None, None

    while not uno_serial or not mega_serial:

        if not mega_serial:
            for port in glob.glob('/dev/ttyUSB*'):
                try:
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(3.5)
                    s.reset_input_buffer()
                    s.write(b"WHOAMI\n")
                    time.sleep(0.5)
                    if "I_AM_MEGA" in s.readline().decode(errors='ignore'):
                        mega_serial = s
                        print(f"[SYSTEM] ✓ MEGA on {port}")
                        break
                    s.close()
                except: pass

        if not uno_serial:
            for port in glob.glob('/dev/ttyACM*'):
                try:
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(2.5)
                    s.reset_input_buffer()
                    s.write(b"WHOAMI\n")
                    time.sleep(0.5)
                    if "I_AM_UNO" in s.readline().decode(errors='ignore'):
                        uno_serial = s
                        print(f"[SYSTEM] ✓ UNO on {port}")
                        break
                    s.close()
                except: pass

        if not uno_serial or not mega_serial:
            print("[SYSTEM] Waiting for hardware...")
            time.sleep(2)

    return uno_serial, mega_serial

AUDIO_DEVICE = find_audio_device()
CAMERA_DEV = find_camera_device()

# ==========================================
# AUDIO ENGINE
# ==========================================
def stop_audio():
    global current_audio_proc
    if current_audio_proc:
        current_audio_proc.terminate()
        current_audio_proc = None

def play_audio(filepath):
    global current_audio_proc
    stop_audio()
    print(f"[AUDIO] {os.path.basename(filepath)}")
    current_audio_proc = subprocess.Popen(["aplay", "-q", "-D", AUDIO_DEVICE, filepath])

def play_random_greeting():
    files = [f for f in os.listdir(GREETINGS_DIR) if f.endswith(".wav")]
    if files:
        play_audio(os.path.join(GREETINGS_DIR, random.choice(files)))

def play_project(pid):
    path = os.path.join(EXPLAIN_DIR, f"project{pid}.wav")
    if os.path.exists(path):
        play_audio(path)

def is_audio_playing():
    global current_audio_proc
    return current_audio_proc and current_audio_proc.poll() is None

# ==========================================
# 🔊 RANDOM BOOT AUDIO (BLOCKING)
# ==========================================
def play_boot_audio():
    if not os.path.exists(BOOT_DIR):
        print("[BOOT] boot_wav folder missing")
        return

    files = [f for f in os.listdir(BOOT_DIR) if f.endswith(".wav")]
    if not files:
        print("[BOOT] No boot files")
        return

    file = random.choice(files)
    path = os.path.join(BOOT_DIR, file)

    print(f"[BOOT] Playing: {file}")
    proc = subprocess.Popen(["aplay", "-D", AUDIO_DEVICE, path])

    while proc.poll() is None:
        time.sleep(0.1)

# ==========================================
# DETECTOR
# ==========================================
class Detector:
    def __init__(self):
        self.proc = None
        self.last_seen = 0

    def start(self):
        if not self.proc:
            print("[CAMERA] Started")
            self.proc = subprocess.Popen(
                [DETECTNET_BIN, f"--network={NETWORK}", CAMERA_DEV],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
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

# ==========================================
# SERIAL
# ==========================================
def send_msg(ser, msg):
    if ser:
        try: ser.write((msg + "\n").encode())
        except: pass

class ArduinoListener:
    def __init__(self, ser, name):
        self.ser = ser
        self.name = name
        self.status = "IDLE"
        self.target_project = "1"
        self.reset_flag = False
        if ser:
            threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        while True:
            try:
                if self.ser.in_waiting:
                    msg = self.ser.readline().decode(errors='ignore').strip()

                    if self.name == "UNO":
                        if msg == "RESET_ALL":
                            self.reset_flag = True
                        elif msg.startswith("TARGET:"):
                            self.target_project = msg.split(":")[1]
                            self.status = "TARGET_RECEIVED"

                    elif self.name == "MEGA":
                        if msg in ["MOVING", "DONE"]:
                            self.status = msg
            except:
                time.sleep(0.1)

# ==========================================
# MAIN
# ==========================================
def main():

    # 🔊 BOOT AUDIO
    play_boot_audio()

    # 🔌 CONNECT HARDWARE
    uno_ser, mega_ser = connect_arduinos()
    uno = ArduinoListener(uno_ser, "UNO")
    mega = ArduinoListener(mega_ser, "MEGA")

    detector = Detector()
    detector.start()

    state = "SEARCHING"

    while True:

        if uno.reset_flag:
            stop_audio()
            send_msg(mega_ser, "RESET")
            uno.reset_flag = False
            state = "SEARCHING"
            detector.start()
            continue

        now = time.time()
        person = detector.last_seen and (now - detector.last_seen < PERSON_TIMEOUT)

        if state == "SEARCHING":
            if person:
                state = "GREETING"
                send_msg(mega_ser, "STOP")
                play_random_greeting()

        elif state == "GREETING":
            if not is_audio_playing():
                state = "WAITING_BLE"
                send_msg(uno_ser, "ASK_PROJECT")

        elif state == "WAITING_BLE":
            if not person:
                state = "SEARCHING"
            elif uno.status == "TARGET_RECEIVED":
                state = "NAVIGATING"
                detector.stop()
                send_msg(mega_ser, f"GO:{uno.target_project}")
                uno.status = "IDLE"

        elif state == "NAVIGATING":
            if mega.status == "DONE":
                state = "EXPLAINING"
                play_project(uno.target_project)
                mega.status = "IDLE"

        elif state == "EXPLAINING":
            if not is_audio_playing():
                detector.start()
                state = "SEARCHING"

        time.sleep(0.05)

if __name__ == "__main__":
    main()
