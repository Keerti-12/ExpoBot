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
BOOT_AUDIO_DIR = "/media/expobot/114/jetson-inference/build/boot_audio"

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
                    if "tegra" in card_name.lower():
                        continue
                    dev_str = f"plughw:{card_num},{dev_num}"
                    print(f"[SYSTEM] ✓ Audio Found: {dev_str}")
                    return dev_str
        except:
            pass
        time.sleep(delay_seconds)

    print("[SYSTEM] ⚠ Using default audio device")
    return "default"


def find_camera_device():
    print("[SYSTEM] Scanning for Camera Hardware...")
    ports = glob.glob('/dev/video*')
    if ports:
        ports.sort()
        print(f"[SYSTEM] ✓ Camera Found: {ports[0]}")
        return ports[0]
    print("[SYSTEM] ⚠ No camera found")
    return None


def connect_arduinos():
    print("\n[SYSTEM] Hunting for Arduinos...")
    uno, mega = None, None

    while not uno or not mega:
        # UNO
        if not uno:
            for port in glob.glob('/dev/ttyACM*'):
                try:
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(2.5)
                    s.reset_input_buffer()
                    s.write(b"WHOAMI\n")
                    time.sleep(0.5)
                    if "I_AM_UNO" in s.readline().decode():
                        uno = s
                        print(f"[SYSTEM] ✓ UNO connected ({port})")
                        break
                    else:
                        s.close()
                except:
                    pass

        # MEGA
        if not mega:
            for port in glob.glob('/dev/ttyUSB*'):
                try:
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(3.5)
                    s.reset_input_buffer()
                    s.write(b"WHOAMI\n")
                    time.sleep(0.5)
                    if "I_AM_MEGA" in s.readline().decode():
                        mega = s
                        print(f"[SYSTEM] ✓ MEGA connected ({port})")
                        break
                    else:
                        s.close()
                except:
                    pass

        if not uno or not mega:
            print("[SYSTEM] Waiting for hardware...")
            time.sleep(2)

    print("[SYSTEM] ✓ ALL HARDWARE CONNECTED\n")
    return uno, mega


# ==========================================
# STATUS SENDER
# ==========================================
def send_msg(ser, msg):
    if ser:
        try:
            ser.write((msg + "\n").encode())
        except:
            pass


def send_status(uno_ser, msg):
    print(f"[STATUS] {msg}")
    send_msg(uno_ser, msg)


# ==========================================
# BOOT AUDIO
# ==========================================
def play_boot_audio(audio_device):
    print("[BOOT] Playing startup audio...")

    if not os.path.exists(BOOT_AUDIO_DIR):
        print("[BOOT] No folder found")
        return

    files = [f for f in os.listdir(BOOT_AUDIO_DIR) if f.endswith(".wav")]
    if not files:
        print("[BOOT] No audio files")
        return

    selected = random.choice(files)
    filepath = os.path.join(BOOT_AUDIO_DIR, selected)

    print(f"[BOOT] Playing: {selected}")

    try:
        proc = subprocess.Popen(["aplay", "-q", "-D", audio_device, filepath])
        proc.wait()
    except Exception as e:
        print(f"[BOOT ERROR] {e}")


# ==========================================
# AUDIO ENGINE
# ==========================================
def stop_audio():
    global current_audio_proc
    if current_audio_proc:
        current_audio_proc.terminate()
        current_audio_proc = None


def play_audio(filepath, audio_device):
    global current_audio_proc
    stop_audio()
    print(f"[AUDIO] Playing: {os.path.basename(filepath)}")
    current_audio_proc = subprocess.Popen(["aplay", "-q", "-D", audio_device, filepath])


def play_random_greeting(audio_device):
    files = [f for f in os.listdir(GREETINGS_DIR) if f.endswith(".wav")]
    if files:
        play_audio(os.path.join(GREETINGS_DIR, random.choice(files)), audio_device)


def play_project(project_id, audio_device):
    filepath = os.path.join(EXPLAIN_DIR, f"project{project_id}.wav")
    if os.path.exists(filepath):
        play_audio(filepath, audio_device)


def is_audio_playing():
    global current_audio_proc
    return current_audio_proc and current_audio_proc.poll() is None


# ==========================================
# DETECTOR
# ==========================================
class Detector:
    def __init__(self, camera_dev):
        self.proc = None
        self.last_seen = 0
        self.camera_dev = camera_dev

    def start(self):
        if self.camera_dev and not self.proc:
            print("[CAMERA] Starting AI Engine...")
            self.proc = subprocess.Popen(
                [DETECTNET_BIN, f"--network={NETWORK}", self.camera_dev],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
            )
            threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.proc.stdout:
            if "person" in line.lower():
                self.last_seen = time.time()

    def stop(self):
        if self.proc:
            print("[CAMERA] Stopping AI Engine...")
            self.proc.terminate()
            self.proc = None


# ==========================================
# MAIN
# ==========================================
def main():

    # Detect hardware
    audio_device = find_audio_device()
    camera_dev = find_camera_device()

    # Boot audio
    time.sleep(1)
    play_boot_audio(audio_device)
    time.sleep(1)

    # Connect boards
    uno_ser, mega_ser = connect_arduinos()

    # Send hardware status
    send_status(uno_ser, "AUDIO_OK" if audio_device else "AUDIO_FAIL")
    send_status(uno_ser, "CAMERA_OK" if camera_dev else "CAMERA_FAIL")
    send_status(uno_ser, "UNO_CONNECTED")
    send_status(uno_ser, "MEGA_CONNECTED")

    detector = Detector(camera_dev)
    detector.start()

    current_state = "SEARCHING"

    try:
        while True:

            # ===== READ MEGA (FILTER PROX) =====
            if mega_ser and mega_ser.in_waiting:
                msg = mega_ser.readline().decode().strip()
                if msg and not msg.startswith("PROX:"):
                    send_status(uno_ser, msg)

            now = time.time()
            person_visible = detector.last_seen and (now - detector.last_seen < PERSON_TIMEOUT)

            if current_state == "SEARCHING":
                if person_visible:
                    current_state = "GREETING"
                    send_msg(mega_ser, "STOP")
                    play_random_greeting(audio_device)

            elif current_state == "GREETING":
                if not is_audio_playing():
                    current_state = "WAITING_BLE"

            elif current_state == "WAITING_BLE":
                if not person_visible:
                    current_state = "SEARCHING"

            elif current_state == "NAVIGATING":
                pass

            elif current_state == "EXPLAINING":
                if not is_audio_playing():
                    detector.start()
                    current_state = "SEARCHING"

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("[SYSTEM] Shutdown")
        detector.stop()
        stop_audio()


if __name__ == "__main__":
    main()
