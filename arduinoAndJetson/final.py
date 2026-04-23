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

# ==========================================
# ROBUST AUTO-DETECTION (HARDWARE HUNTERS)
# ==========================================

def find_audio_device(max_retries=15, delay_seconds=2):
    """Scans for USB Audio. Waits out the Linux boot sequence if necessary."""
    print("[SYSTEM] Scanning for USB Audio Hardware...")
    for attempt in range(max_retries):
        try:
            output = subprocess.check_output(["aplay", "-l"], stderr=subprocess.STDOUT, universal_newlines=True)
            for line in output.split('\n'):
                # Matches format: "card 1: Device [USB Audio Device], device 0..."
                match = re.search(r"card (\d+): .*? \[(.*?)\], device (\d+)", line)
                if match:
                    card_num, card_name, dev_num = match.groups()
                    if "tegra" in card_name.lower():
                        continue # Ignore Nvidia onboard HDMI
                    
                    dev_str = f"plughw:{card_num},{dev_num}"
                    print(f"[SYSTEM] \u2713 Audio Found: {card_name} mapped to {dev_str}")
                    return dev_str

            print(f"[SYSTEM] Audio Attempt {attempt + 1}/{max_retries}: Not found yet. Waiting...")
            time.sleep(delay_seconds)
        except Exception as e:
            print(f"[SYSTEM] Audio check error: {e}. Retrying...")
            time.sleep(delay_seconds)

    print("[SYSTEM] \u26A0 FATAL: USB Audio not found. Falling back to default.")
    return "default"

def find_camera_device():
    """Dynamically finds the first available video port, prioritizing /dev/video0."""
    print("[SYSTEM] Scanning for Camera Hardware...")
    ports = glob.glob('/dev/video*')
    if ports:
        ports.sort() # Ensure /dev/video0 is picked first if multiple exist
        print(f"[SYSTEM] \u2713 Camera Found: {ports[0]}")
        return ports[0]
    
    print("[SYSTEM] \u26A0 FATAL: No camera found. Defaulting to /dev/video0")
    return "/dev/video0"

def find_arduino():
    """Scans USB and ACM ports for the Arduino connection."""
    print("[SYSTEM] Scanning for Arduino Controller...")
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    for p in ports:
        try:
            s = serial.Serial(p, SERIAL_BAUD, timeout=1)
            time.sleep(2) # Give Arduino time to reset after serial connection
            print(f"[SYSTEM] \u2713 Arduino Connected at {p}")
            return s
        except Exception as e:
            continue
    print("[SYSTEM] \u26A0 FATAL: Arduino not found!")
    return None

# Initialize Hardware Globals
AUDIO_DEVICE = find_audio_device()
CAMERA_DEV = find_camera_device()

# ==========================================
# AUDIO PLAYBACK FUNCTIONS
# ==========================================

def play_random(folder):
    files = [f for f in os.listdir(folder) if f.endswith(".wav")]
    if not files:
        print("[AUDIO] No files found in", folder)
        return
    f = random.choice(files)
    print(f"[AUDIO] Playing Greeting: {f}")
    # subprocess.call is blocking - it waits for audio to finish before Python continues
    subprocess.call(["aplay", "-q", "-D", AUDIO_DEVICE, os.path.join(folder, f)])

def play_project(project_id):
    filename = f"project{project_id}.wav"
    filepath = os.path.join(EXPLAIN_DIR, filename)
    if os.path.exists(filepath):
        print(f"[AUDIO] Playing Explanation: {filename}")
        subprocess.call(["aplay", "-q", "-D", AUDIO_DEVICE, filepath])
    else:
        print(f"[AUDIO ERROR] File not found: {filepath}")

# ==========================================
# AI CAMERA THREAD (DETECTNET)
# ==========================================

class Detector:
    def __init__(self):
        self.proc = None
        self.last_seen = 0

    def start(self):
        print("[CAMERA] Starting AI Inference Engine...")
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
            print("[CAMERA] Pausing AI Inference (Saving CPU during movement)...")
            self.proc.terminate()
            self.proc = None

# ==========================================
# SERIAL LISTENER THREAD
# ==========================================

def send_to_arduino(ser, msg):
    if not ser: return
    try:
        ser.write((msg + "\n").encode())
        print(f"[MASTER \u2192 SLAVE] {msg}")
    except Exception as e:
        print("[SERIAL ERROR] Failed to send:", e)

class SerialListener:
    def __init__(self, ser):
        self.ser = ser
        self.arduino_state = "IDLE"
        self.target_project = "1"
        self.thread = threading.Thread(target=self.listen, daemon=True)

    def start(self):
        if self.ser:
            self.thread.start()

    def listen(self):
        while True:
            try:
                if self.ser and self.ser.in_waiting:
                    msg = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if not msg: continue
                    
                    # Parse incoming commands
                    if msg == "MOVING":
                        self.arduino_state = "MOVING"
                        print("[SLAVE \u2192 MASTER] Status: MOVING")
                    elif msg == "DONE":
                        self.arduino_state = "DONE"
                        print("[SLAVE \u2192 MASTER] Status: ARRIVED")
                    elif msg.startswith("PROX:"):
                        pass # Ignore spammy sensor prints to keep terminal clean
                    else:
                        print(f"[SLAVE \u2192 MASTER] {msg}")

            except Exception as e:
                print("[SERIAL READ ERROR]", e)
                time.sleep(0.5)

# ==========================================
# MAIN STATE MACHINE
# ==========================================

def main():
    print("\n" + "="*40)
    print(" EXPOBOT MASTER CONTROL INITIALIZING")
    print("="*40 + "\n")

    ser = find_arduino()
    listener = SerialListener(ser)
    listener.start()

    detector = Detector()
    detector.start()

    # Master States: SEARCHING, GREETING, WAITING_BLE, NAVIGATING, EXPLAINING
    current_state = "SEARCHING"

    try:
        while True:
            now = time.time()
            person_visible = detector.last_seen and (now - detector.last_seen < PERSON_TIMEOUT)

            # --- STATE: SEARCHING ---
            if current_state == "SEARCHING":
                if person_visible:
                    current_state = "GREETING"
                    print("\n[STATE] \u2192 GREETING (Person Detected!)")
                    
                    # Tell Arduino to stop everything
                    send_to_arduino(ser, "PERSON")
                    
                    # Play greeting (This blocks until audio finishes)
                    play_random(GREETINGS_DIR)
                    
                    # After greeting, transition to waiting for BLE input
                    current_state = "WAITING_BLE"
                    print("\n[STATE] \u2192 WAITING_BLE")
                    send_to_arduino(ser, "ASK_PROJECT")

            # --- STATE: WAITING_BLE ---
            elif current_state == "WAITING_BLE":
                # If the person walks away before selecting, reset to searching
                if not person_visible:
                    print("\n[STATE] \u2192 SEARCHING (Person Left)")
                    current_state = "SEARCHING"
                
                # If the Arduino app triggers a movement
                elif listener.arduino_state == "MOVING":
                    current_state = "NAVIGATING"
                    print("\n[STATE] \u2192 NAVIGATING")
                    detector.stop() # Turn off camera while moving

            # --- STATE: NAVIGATING ---
            elif current_state == "NAVIGATING":
                # We do nothing here but wait for the Arduino to arrive
                if listener.arduino_state == "DONE":
                    current_state = "EXPLAINING"
                    print("\n[STATE] \u2192 EXPLAINING")

            # --- STATE: EXPLAINING ---
            elif current_state == "EXPLAINING":
                # Extract target from listener (Assuming Arduino printed it, or we rely on the flow)
                # Note: In your current Uno code, the Uno doesn't send the target back to Jetson. 
                # If Uno printed "ARRIVED AT PROJECT: 3", we'd parse it. 
                # For now, we will use the listener's target_project if you update the Uno to send "TARGET:X"
                
                play_project(listener.target_project)
                
                # Reset for the next interaction
                print("\n[STATE] \u2192 SEARCHING (Cycle Complete)")
                listener.arduino_state = "IDLE"
                detector.start()
                current_state = "SEARCHING"

            time.sleep(0.1) # Main loop throttle

    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Expobot...")
        detector.stop()
        if ser: ser.close()

if __name__ == "__main__":
    main()
