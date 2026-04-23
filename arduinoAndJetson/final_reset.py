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

PERSON_TIMEOUT = 1.2
SERIAL_BAUD = 9600

# Global process tracker so we can kill audio instantly
current_audio_proc = None

# ==========================================
# ROBUST AUTO-DETECTION (HARDWARE HUNTERS)
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
                    print(f"[SYSTEM] \u2713 Audio Found: {dev_str}")
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
        print(f"[SYSTEM] \u2713 Camera Found: {ports[0]}")
        return ports[0]
    return "/dev/video0"

def connect_arduinos():
    """Finds all USB serial devices, pings them, and assigns Uno/Mega."""
    print("[SYSTEM] Scanning for Arduinos...")
    uno_serial = None
    mega_serial = None
    
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    for p in ports:
        try:
            s = serial.Serial(p, SERIAL_BAUD, timeout=1)
            time.sleep(2) # Wait for Arduino to reset on connection
            
            # Send the ping
            s.write(b"WHOAMI\n")
            time.sleep(0.5)
            
            # Read the response
            response = s.readline().decode('utf-8', errors='ignore').strip()
            
            if "I_AM_UNO" in response:
                uno_serial = s
                print(f"[SYSTEM] \u2713 UNO connected on {p}")
            elif "I_AM_MEGA" in response:
                mega_serial = s
                print(f"[SYSTEM] \u2713 MEGA connected on {p}")
        except Exception as e:
            continue
            
    if not uno_serial or not mega_serial:
        print("[SYSTEM] \u26A0 FATAL: Could not find BOTH Arduinos! Check cables.")
        
    return uno_serial, mega_serial

AUDIO_DEVICE = find_audio_device()
CAMERA_DEV = find_camera_device()

# ==========================================
# NON-BLOCKING AUDIO ENGINE
# ==========================================
def stop_audio():
    """Instantly kills any currently playing audio."""
    global current_audio_proc
    if current_audio_proc:
        current_audio_proc.terminate()
        current_audio_proc = None

def play_audio(filepath):
    """Plays audio without blocking the Python loop."""
    global current_audio_proc
    stop_audio() # Kill old audio before starting new
    print(f"[AUDIO] Playing: {os.path.basename(filepath)}")
    current_audio_proc = subprocess.Popen(["aplay", "-q", "-D", AUDIO_DEVICE, filepath])

def play_random_greeting():
    files = [f for f in os.listdir(GREETINGS_DIR) if f.endswith(".wav")]
    if files:
        play_audio(os.path.join(GREETINGS_DIR, random.choice(files)))

def play_project(project_id):
    filepath = os.path.join(EXPLAIN_DIR, f"project{project_id}.wav")
    if os.path.exists(filepath):
        play_audio(filepath)
    else:
        print(f"[AUDIO ERROR] File not found: {filepath}")

def is_audio_playing():
    """Checks if the subprocess is still running."""
    global current_audio_proc
    if current_audio_proc:
        return current_audio_proc.poll() is None
    return False

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
            if "person" in line.lower():
                self.last_seen = time.time()

    def stop(self):
        if self.proc:
            print("[CAMERA] Pausing AI Engine...")
            self.proc.terminate()
            self.proc = None

def send_msg(ser, msg):
    if ser:
        try:
            ser.write((msg + "\n").encode())
        except: pass

class ArduinoListener:
    """A generic threaded listener for both Uno and Mega"""
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
                if self.ser and self.ser.in_waiting:
                    msg = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if not msg: continue
                    
                    # --- UNO LOGIC (BLE Bridge) ---
                    if self.name == "UNO":
                        if msg == "RESET_ALL":
                            self.reset_flag = True
                        elif msg.startswith("TARGET:"):
                            self.target_project = msg.split(":")[1]
                            self.status = "TARGET_RECEIVED"
                            print(f"[BLE \u2192 JETSON] User selected Project {self.target_project}")
                            
                    # --- MEGA LOGIC (Motion) ---
                    elif self.name == "MEGA":
                        if msg in ["MOVING", "DONE", "PAUSED", "RESET_ACK"]:
                            self.status = msg
                            print(f"[MEGA \u2192 JETSON] Status: {msg}")

            except Exception as e:
                time.sleep(0.1)

# ==========================================
# MAIN STATE MACHINE
# ==========================================
def main():
    print("\n" + "="*40)
    print(" EXPOBOT MASTER CONTROL INITIALIZING")
    print("="*40 + "\n")

    # Connect hardware
    uno_ser, mega_ser = connect_arduinos()
    uno = ArduinoListener(uno_ser, "UNO")
    mega = ArduinoListener(mega_ser, "MEGA")
    
    detector = Detector()
    detector.start()

    current_state = "SEARCHING"

    try:
        while True:
            # ---------------------------------------------------------
            # 1. EMERGENCY RESET TRAP (Highest Priority)
            # ---------------------------------------------------------
            if uno.reset_flag:
                print("\n[!!!] EMERGENCY RESET TRIGGERED FROM APP [!!!]")
                stop_audio()                 # Cut off any talking instantly
                send_msg(mega_ser, "RESET")  # Tell Mega to cut motors & reset memory
                uno.reset_flag = False
                uno.status = "IDLE"
                mega.status = "IDLE"
                
                # Restart camera if it was paused and go back to start
                detector.start()             
                current_state = "SEARCHING"
                print("[SYSTEM] Bot reset. Ready for new person.\n")
                continue # Skip the rest of the loop and start fresh

            # ---------------------------------------------------------
            # 2. NORMAL BEHAVIOR LOGIC
            # ---------------------------------------------------------
            now = time.time()
            person_visible = detector.last_seen and (now - detector.last_seen < PERSON_TIMEOUT)

            # --- STATE: SEARCHING ---
            if current_state == "SEARCHING":
                if person_visible:
                    current_state = "GREETING"
                    print("\n[STATE] \u2192 GREETING")
                    send_msg(mega_ser, "STOP") # Ensure bot holds still
                    play_random_greeting()

            # --- STATE: GREETING ---
            elif current_state == "GREETING":
                # Wait for the audio track to finish playing
                if not is_audio_playing():
                    current_state = "WAITING_BLE"
                    print("\n[STATE] \u2192 WAITING_BLE")
                    # Tell Uno it can start looking for app inputs
                    send_msg(uno_ser, "ASK_PROJECT")

            # --- STATE: WAITING_BLE ---
            elif current_state == "WAITING_BLE":
                if not person_visible:
                    print("\n[STATE] \u2192 SEARCHING (Person Left)")
                    current_state = "SEARCHING"
                
                elif uno.status == "TARGET_RECEIVED":
                    current_state = "NAVIGATING"
                    print("\n[STATE] \u2192 NAVIGATING")
                    
                    detector.stop() # Save CPU while moving
                    
                    # Tell Mega exactly where to go
                    send_msg(mega_ser, f"GO:{uno.target_project}")
                    uno.status = "IDLE" # Reset Uno flag

            # --- STATE: NAVIGATING ---
            elif current_state == "NAVIGATING":
                # Wait for the Mega to reply "DONE"
                if mega.status == "DONE":
                    current_state = "EXPLAINING"
                    print("\n[STATE] \u2192 EXPLAINING")
                    play_project(uno.target_project)
                    mega.status = "IDLE" # Reset Mega flag

            # --- STATE: EXPLAINING ---
            elif current_state == "EXPLAINING":
                # Wait for the explanation audio to finish
                if not is_audio_playing():
                    print("\n[STATE] \u2192 SEARCHING (Cycle Complete)")
                    detector.start()
                    current_state = "SEARCHING"

            time.sleep(0.05) # Loop timing

    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down...")
        detector.stop()
        stop_audio()
        if uno_ser: uno_ser.close()
        if mega_ser: mega_ser.close()

if __name__ == "__main__":
    main()
