def connect_arduinos():
    """Dynamically grabs the active ports based on chip type, ignoring the shifting numbers."""
    print("[SYSTEM] Connecting to Arduino ports dynamically...")
    uno_serial = None
    mega_serial = None
    
    # glob.glob reads the active ports connected right at this second
    usb_ports = glob.glob('/dev/ttyUSB*') # Always the Mega (CH340 clone chip)
    acm_ports = glob.glob('/dev/ttyACM*') # Always the Uno (Native USB chip)

    # ------------------------------------------------
    # 1. CONNECT TO MEGA
    # ------------------------------------------------
    if usb_ports:
        mega_port = usb_ports[0] # Grab whatever number it is today (0, 1, or 2)
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
                print(f"[SYSTEM] ✓ MEGA successfully verified on {mega_port}")
            else:
                print(f"[SYSTEM] ⚠ MEGA failed verification. Responded: {response}")
        except Exception as e:
            print(f"[SYSTEM] ⚠ MEGA port error: {e}")
    else:
        print("[SYSTEM] ⚠ FATAL: No /dev/ttyUSB* ports found! Is the Mega plugged in?")

    # ------------------------------------------------
    # 2. CONNECT TO UNO
    # ------------------------------------------------
    if acm_ports:
        uno_port = acm_ports[0] # Grab whatever number it is today
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
                print(f"[SYSTEM] ✓ UNO successfully verified on {uno_port}")
            else:
                print(f"[SYSTEM] ⚠ UNO failed verification. Responded: {response}")
        except Exception as e:
            print(f"[SYSTEM] ⚠ UNO port error: {e}")
    else:
        print("[SYSTEM] ⚠ FATAL: No /dev/ttyACM* ports found! Is the Uno plugged in?")

    # ------------------------------------------------
    # 3. FINAL SAFETY CHECK
    # ------------------------------------------------
    if not uno_serial or not mega_serial:
        print("\n[SYSTEM] ⚠ FATAL: Could not connect to both Arduinos.")
        
    return uno_serial, mega_serial
