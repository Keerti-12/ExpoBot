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
BOOT_AUDIO_DIR = "/media/expobot/114/jetson-inference/build/boot_audio"   # ✅ NEW

PERSON_TIMEOUT = 1.2
SERIAL_BAUD = 9600
current_audio_proc = None

# ==========================================
# ROBUST AUTO-DETECTION
# ==========================================
def find_audio_device(max_retries=15, delay_seconds=2):
    print("[SYSTEM] Scanning for USB Audio Hardware...")
    for attempt in range(max_retries):
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
    print("[SYSTEM] Scanning for Camera Hardware...")
    ports = glob.glob('/dev/video*')
    if ports:
        ports.sort()
        print(f"[SYSTEM] ✓ Camera Found: {ports[0]}")
        return ports[0]
    return "/dev/video0"

def connect_arduinos():
    print("\n[SYSTEM] =========================================")
    print("[SYSTEM] Hunting for Arduinos...")
    uno_serial = None
    mega_serial = None
    
    while not uno_serial or not mega_serial:
        if not mega_serial:
            for port in glob.glob('/dev/ttyUSB*'):
                try:
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(3.5)
                    s.reset_input_buffer()
                    s.write(b"WHOAMI\n")
                    time.sleep(0.5)
                    response = s.readline().decode('utf-8', errors='ignore').strip()
                    if "I_AM_MEGA" in response:
                        mega_serial = s
                        print(f"[SYSTEM] ✓ MEGA locked in on {port}")
                        break 
                    else:
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
                    response = s.readline().decode('utf-8', errors='ignore').strip()
                    if "I_AM_UNO" in response:
                        uno_serial = s
                        print(f"[SYSTEM] ✓ UNO locked in on {port}")
                        break
                    else:
                        s.close()
                except: pass

        if not uno_serial or not mega_serial:
            missing = []
            if not uno_serial: missing.append("UNO")
            if not mega_serial: missing.append("MEGA")
            print(f"[SYSTEM] ⏳ Waiting for {', '.join(missing)}... Retrying in 2 seconds.")
            time.sleep(2)

    print("[SYSTEM] =========================================")
    print("[SYSTEM] ✓ ALL HARDWARE CONNECTED")
    print("[SYSTEM] =========================================\n")
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
    print(f"[AUDIO] Playing: {os.path.basename(filepath)}")
    current_audio_proc = subprocess.Popen(["aplay", "-q", "-D", AUDIO_DEVICE, filepath])

def play_random_greeting():
    files = [f for f in os.listdir(GREETINGS_DIR) if f.endswith(".wav")]
    if files: play_audio(os.path.join(GREETINGS_DIR, random.choice(files)))

def play_project(project_id):
    filepath = os.path.join(EXPLAIN_DIR, f"project{project_id}.wav")
    if os.path.exists(filepath): play_audio(filepath)
    else: print(f"[AUDIO ERROR] File not found: {filepath}")

def is_audio_playing():
    global current_audio_proc
    if current_audio_proc:
        return current_audio_proc.poll() is None
    return False

# ==========================================
# ✅ NEW: BOOT AUDIO FUNCTION
# ==========================================
def play_boot_audio_once():
    if not os.path.exists(BOOT_AUDIO_DIR):
        print("[BOOT AUDIO] Folder not found, skipping...")
        return

    files = [f for f in os.listdir(BOOT_AUDIO_DIR) if f.endswith(".wav")]
    if not files:
        print("[BOOT AUDIO] No files found.")
        return

    filepath = os.path.join(BOOT_AUDIO_DIR, random.choice(files))
    print("[BOOT AUDIO] Playing startup audio...")
    
    proc = subprocess.Popen(["aplay", "-q", "-D", AUDIO_DEVICE, filepath])
    proc.wait()   # ✅ ensures it plays fully ONCE before system continues

# ==========================================
# AI CAMERA & SERIAL COMMUNICATION
# ==========================================
class Detector:
    def __init__(self):
        self.proc = None
        self.last_seen = 0

    def start(self):
        if not self.proc:
            print("[CAMERA] Starting AI Inference Engine...")
            self.proc = subprocess.Popen(
                [DETECTNET_BIN, f"--network={NETWORK}", CAMERA_DEV],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
            )
            threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.proc.stdout:
            if "person" in line.lower(): self.last_seen = time.time()

    def stop(self):
        if self.proc:
            print("[CAMERA] Pausing AI Engine...")
            self.proc.terminate()
            self.proc = None

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
        if ser: threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        while True:
            try:
                if self.ser and self.ser.in_waiting:
                    msg = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if not msg: continue
                    
                    if self.name == "UNO":
                        if msg == "RESET_ALL":
                            self.reset_flag = True
                        elif msg.startswith("TARGET:"):
                            self.target_project = msg.split(":")[1]
                            self.status = "TARGET_RECEIVED"
                            print(f"[BLE → JETSON] User selected Project {self.target_project}")
                            
                    elif self.name == "MEGA":
                        if msg in ["MOVING", "DONE", "PAUSED", "RESET_ACK"]:
                            self.status = msg
                            print(f"[MEGA → JETSON] Status: {msg}")
                        elif msg.startswith("CHECKPOINT:"):
                            print(f"[MEGA → JETSON] {msg}")
                        elif msg.startswith("PROX:"):
                            print(f"[MEGA SENSOR] {msg}")
                        else:
                            print(f"[MEGA DEBUG] {msg}")
            except:
                time.sleep(0.1)

# ==========================================
# MAIN STATE MACHINE
# ==========================================
def main():
    uno_ser, mega_ser = connect_arduinos()

    # ✅ PLAY BOOT AUDIO ONCE HERE
    play_boot_audio_once()

    uno = ArduinoListener(uno_ser, "UNO")
    mega = ArduinoListener(mega_ser, "MEGA")
    
    detector = Detector()
    detector.start()

    current_state = "SEARCHING"

    try:
        while True:
            if uno.reset_flag:
                print("\n[!!!] EMERGENCY RESET TRIGGERED [!!!]")
                stop_audio()                 
                send_msg(mega_ser, "RESET")  
                uno.reset_flag = False
                uno.status = "IDLE"
                mega.status = "IDLE"
                detector.start()             
                current_state = "SEARCHING"
                print("[SYSTEM] Bot reset. Ready for new person.\n")
                continue 

            now = time.time()
            person_visible = detector.last_seen and (now - detector.last_seen < PERSON_TIMEOUT)

            if current_state == "SEARCHING":
                if person_visible:
                    current_state = "GREETING"
                    print("\n[STATE] → GREETING")
                    send_msg(mega_ser, "STOP")
                    play_random_greeting()

            elif current_state == "GREETING":
                if not is_audio_playing():
                    current_state = "WAITING_BLE"
                    print("\n[STATE] → WAITING_BLE")
                    send_msg(uno_ser, "ASK_PROJECT")

            elif current_state == "WAITING_BLE":
                if not person_visible:
                    print("\n[STATE] → SEARCHING (Person Left)")
                    current_state = "SEARCHING"
                elif uno.status == "TARGET_RECEIVED":
                    current_state = "NAVIGATING"
                    print("\n[STATE] → NAVIGATING")
                    detector.stop() 
                    send_msg(mega_ser, f"GO:{uno.target_project}")
                    uno.status = "IDLE" 

            elif current_state == "NAVIGATING":
                if mega.status == "DONE":
                    current_state = "EXPLAINING"
                    print("\n[STATE] → EXPLAINING")
                    play_project(uno.target_project)
                    mega.status = "IDLE" 

            elif current_state == "EXPLAINING":
                if not is_audio_playing():
                    print("\n[STATE] → SEARCHING (Cycle Complete)")
                    detector.start()
                    current_state = "SEARCHING"

            time.sleep(0.05) 

    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down...")
        detector.stop()
        stop_audio()
        if uno_ser: uno_ser.close()
        if mega_ser: mega_ser.close()

if __name__ == "__main__":
    main()
