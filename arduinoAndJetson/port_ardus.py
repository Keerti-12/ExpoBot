def connect_arduinos():
    """
    Bulletproof connection manager. Scans all ports and blocks the entire 
    program in a loop until BOTH the Uno and Mega are verified.
    """
    print("\n[SYSTEM] =========================================")
    print("[SYSTEM] Hunting for Arduinos...")
    
    uno_serial = None
    mega_serial = None
    
    # Block the script from moving forward until BOTH are found
    while not uno_serial or not mega_serial:
        
        # ------------------------------------------------
        # 1. HUNT FOR THE MEGA (CH340 Chips -> /dev/ttyUSB*)
        # ------------------------------------------------
        if not mega_serial:
            usb_ports = glob.glob('/dev/ttyUSB*')
            for port in usb_ports:
                try:
                    print(f"[SYSTEM] Probing {port} for MEGA...")
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(3.5)  # Mega slow bootloader delay
                    
                    s.reset_input_buffer()
                    s.write(b"WHOAMI\n")
                    time.sleep(0.5)
                    
                    response = s.readline().decode('utf-8', errors='ignore').strip()
                    if "I_AM_MEGA" in response:
                        mega_serial = s
                        print(f"[SYSTEM] \u2713 MEGA locked in on {port}")
                        break  # Stop checking USB ports, we found it!
                    else:
                        s.close() # CRITICAL: Free up the port if it's the wrong device
                except Exception as e:
                    print(f"[SYSTEM] \u26A0 Skipping {port}: {e}")
                    pass

        # ------------------------------------------------
        # 2. HUNT FOR THE UNO (Native USB Chips -> /dev/ttyACM*)
        # ------------------------------------------------
        if not uno_serial:
            acm_ports = glob.glob('/dev/ttyACM*')
            for port in acm_ports:
                try:
                    print(f"[SYSTEM] Probing {port} for UNO...")
                    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
                    time.sleep(2.5)  # Uno R4 boot delay
                    
                    s.reset_input_buffer()
                    s.write(b"WHOAMI\n")
                    time.sleep(0.5)
                    
                    response = s.readline().decode('utf-8', errors='ignore').strip()
                    if "I_AM_UNO" in response:
                        uno_serial = s
                        print(f"[SYSTEM] \u2713 UNO locked in on {port}")
                        break  # Stop checking ACM ports, we found it!
                    else:
                        s.close() # CRITICAL: Free up the port if it's the wrong device
                except Exception as e:
                    print(f"[SYSTEM] \u26A0 Skipping {port}: {e}")
                    pass

        # ------------------------------------------------
        # 3. CHECK STATUS & RETRY
        # ------------------------------------------------
        if not uno_serial or not mega_serial:
            missing = []
            if not uno_serial: missing.append("UNO")
            if not mega_serial: missing.append("MEGA")
            
            print(f"[SYSTEM] \u231B Still waiting for {', '.join(missing)}... Retrying in 2 seconds.")
            time.sleep(2) # Prevent spamming the terminal, wait before scanning again

    print("[SYSTEM] =========================================")
    print("[SYSTEM] \u2713 ALL HARDWARE CONNECTED AND VERIFIED")
    print("[SYSTEM] =========================================\n")
            
    return uno_serial, mega_serial
