def connect_arduinos():
    """Directly connects to known hardware ports for instant booting."""
    print("[SYSTEM] Connecting directly to known Arduino ports...")
    uno_serial = None
    mega_serial = None
    
    # ------------------------------------------------
    # 1. CONNECT TO MEGA (/dev/ttyUSB0)
    # ------------------------------------------------
    mega_port = '/dev/ttyUSB0'
    try:
        print(f"[SYSTEM] Attempting MEGA on {mega_port}...")
        s_mega = serial.Serial(mega_port, SERIAL_BAUD, timeout=1)
        time.sleep(3.5)  # The Mega still needs 3.5s to wake up!
        
        s_mega.reset_input_buffer()
        s_mega.write(b"WHOAMI\n")
        time.sleep(0.5)
        
        response = s_mega.readline().decode('utf-8', errors='ignore').strip()
        if "I_AM_MEGA" in response:
            mega_serial = s_mega
            print(f"[SYSTEM] \u2713 MEGA successfully verified on {mega_port}")
        else:
            print(f"[SYSTEM] \u26A0 MEGA failed verification. Responded: {response}")
    except Exception as e:
        print(f"[SYSTEM] \u26A0 MEGA port error: {e}")

    # ------------------------------------------------
    # 2. CONNECT TO UNO (/dev/ttyACM0)
    # ------------------------------------------------
    # Assuming your Uno R4 is on ACM0. If it's on ACM1, change this variable:
    uno_port = '/dev/ttyACM0' 
    try:
        print(f"[SYSTEM] Attempting UNO on {uno_port}...")
        s_uno = serial.Serial(uno_port, SERIAL_BAUD, timeout=1)
        time.sleep(2)  # Uno wakes up faster
        
        s_uno.reset_input_buffer()
        s_uno.write(b"WHOAMI\n")
        time.sleep(0.5)
        
        response = s_uno.readline().decode('utf-8', errors='ignore').strip()
        if "I_AM_UNO" in response:
            uno_serial = s_uno
            print(f"[SYSTEM] \u2713 UNO successfully verified on {uno_port}")
        else:
            print(f"[SYSTEM] \u26A0 UNO failed verification. Responded: {response}")
    except Exception as e:
        print(f"[SYSTEM] \u26A0 UNO port error: {e}")

    # ------------------------------------------------
    # 3. FINAL SAFETY CHECK
    # ------------------------------------------------
    if not uno_serial or not mega_serial:
        print("\n[SYSTEM] \u26A0 FATAL: Could not connect to both Arduinos.")
        print("[SYSTEM] \u2192 Did you unplug them and plug them back into different USB slots?")
        
    return uno_serial, mega_serial
