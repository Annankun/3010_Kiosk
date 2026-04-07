**Course:** SYSC 3010  
**Group Number:** L1G3  
**TA:** Albert Lin  

**Team Members:**
- Annan Jiang
- Ben Gorman
- John Patterson
- Laavanya Nayar
---

## Project Summary

The Souper Kiosk is an automated soup vending system that allows customers to order customized soups through a mobile web interface and have them prepared and dispensed by a distributed Raspberry Pi-based machine. Customers browse a menu of six soup bases (Chicken Broth, Tomato Soup, Beef Broth, Vegetable Soup, Mushroom Soup, Miso Soup) and six toppings (Broccoli, Carrots, Chicken, Tofu, Croutons, Cheese) via a Firebase-hosted webpage. Upon placing an order, a QR code is generated for the customer to use at pickup.

The system is distributed across **four Raspberry Pi nodes**, each responsible for a specific stage of soup preparation:

1. **Kiosk Node** — Central coordinator that polls Firebase for new orders, manages SQLite inventory, and orchestrates the workflow across kitchen components.
2. **Boiler Node** — Heats water to the target temperature and dispenses the soup base into the mixing vessel.
3. **Mixer Node** — Blends the soup base with powder ingredients and controls stirring speed.
4. **Garnish Node** — Dispenses selected toppings into the finished soup and performs final quality checks.

Each node communicates via Firebase Realtime Database. Order history and inventory levels are tracked locally in an SQLite database on the Kiosk node, and a reporting tool allows monthly revenue and popularity statistics to be viewed at any time.

---

## Repository Structure

```
3010_L1G3/
├── README.md                  # This file
├── Souper_Kiosk/              # Kiosk Node (coordinator)
│   ├── kiosk.py               # Main coordinator: polls Firebase, drives kitchen workflow
│   ├── scanner.py             # Pickup station: scans QR codes, validates order readiness
│   ├── db.py                  # SQLite database module (orders, inventory, stats)
│   ├── config.py              # Firebase project configuration
│   ├── firebase.json          # Firebase hosting configuration
│   ├── mobile.html            # Customer-facing ordering web interface
│   ├── send_order.py          # Dev utility to push test orders to Firebase
│   ├── watch_all.py           # Kitchen component status monitor
│   ├── stats.py               # Monthly revenue and sales reporting CLI
│   ├── test_all.py            # Unit test suite (mocked hardware/Firebase)
│   ├── public/                # Firebase Hosting deployment directory
│   │   ├── index.html         # Default hosting landing page
│   │   └── mobile.html        # Deployed customer ordering interface
│   └── soupercomputer-f0dad-firebase-adminsdk-*.json  # Firebase service account key
│
├── Boiler/                    # Boiler Node
│   ├── boiler_final.py        # Heats water, dispenses soup base
│   ├── pin_control.py         # GPIO control for solenoids & heating pad
│   ├── temp_sensor.py         # Reads DS18B20 temperature sensor
│   └── filter.py              # Temperature filtering & averaging
│
├── Mixer/                     # Mixer Node
│   └── MIXER_NODE.py          # Controls motor & powder dispenser via BTS7960 H-bridge
│
└── Garnish/                   # Garnish Node
    └── garnish_node.py        # Dispenses toppings, monitors bowl presence via ultrasonic sensor
```

---

## Installation Instructions

### Hardware Required (Per Node)

**Kiosk Node (Raspberry Pi):**
- Raspberry Pi (any model with GPIO support)
- WiFi/Ethernet connectivity to Firebase

**Boiler Node (Raspberry Pi):**
- Heating pad (12V relay controlled)
- DS18B20 temperature sensor (1-wire protocol)
- 2× solenoid valves (water inlet, soup outlet)
- 5V relay module or GPIO transistors

**Mixer Node (Raspberry Pi):**
- DC motor (stirrer)
- BTS7960 H-bridge motor driver
- Servo motor (powder indexer/door — 360° continuous rotation)

**Garnish Node (Raspberry Pi):**
- HC-SR04 ultrasonic distance sensor (bowl presence detection)
- 2× servo motors (indexer & hopper door — 360° continuous rotation)
- SenseHAT (status LED display)

### Network Setup

All four Raspberry Pis must be on the same WiFi network and have access to Firebase. Update `config.py` on each node with your Firebase credentials:

```python
FIREBASE_CONFIG = {
    "apiKey": "YOUR_API_KEY",
    "authDomain": "YOUR_PROJECT.firebaseapp.com",
    "databaseURL": "https://YOUR_PROJECT-default-rtdb.firebaseio.com",
    "projectId": "YOUR_PROJECT",
    "storageBucket": "YOUR_PROJECT.firebasestorage.app"
}
```

### Software Setup (All Nodes)

1. **Clone the repository** on each Raspberry Pi:
   ```bash
   git clone https://github.com/annankun/3010_kiosk.git
   cd 3010_L1G3
   ```

2. **Install common dependencies** (all nodes):
   ```bash
   pip install pyrebase4 RPi.GPIO
   ```

3. **Install node-specific dependencies:**

   **Kiosk Node:**
   ```bash
   cd Souper_Kiosk
   pip install opencv-python pyzbar picamera2
   ```

   **Boiler Node:**
   ```bash
   cd Boiler
   # (DS18B20 drivers already built into Raspberry Pi OS)
   ```

   **Mixer Node:**
   ```bash
   cd Mixer
   # (Uses only RPi.GPIO, already installed)
   ```

   **Garnish Node:**
   ```bash
   cd Garnish
   pip install gpiozero sense-hat
   ```

4. **Set up Firebase Hosting** (Kiosk node only):
   ```bash
   npm install -g firebase-tools
   firebase login
   cd Souper_Kiosk/public
   firebase deploy --only hosting
   ```

5. **Initialize the local database** (Kiosk node):
   The SQLite database (`souper_kiosk.db`) is created automatically on first run.

---

## How to Run

### 1. Start the Boiler Node (Raspberry Pi #2)
```bash
cd Boiler
python boiler_final.py
```
Expected output: `Listening for pending orders...`

### 2. Start the Mixer Node (Raspberry Pi #3)
```bash
cd Mixer
python MIXER_NODE.py
```
Expected output: `--- MIXER NODE READY ---`

### 3. Start the Garnish Node (Raspberry Pi #4)
```bash
cd Garnish
python garnish_node.py
```
Expected output: `--- GARNISH NODE READY ---`

### 4. Start the Kiosk Coordinator (Raspberry Pi #1)
```bash
cd Souper_Kiosk
python kiosk.py
```
Expected output: `Kiosk worker started. Waiting for pending orders...`

### 5. Start the Pickup Scanner (Can run on any Raspberry Pi, including Kiosk)
```bash
cd Souper_Kiosk
python scanner.py
```
Expected output: `QR scanner started. Press Ctrl+C to stop.`

### 6. Customer Places Order
Customers open the Firebase-hosted URL in their browser, select a soup and toppings, and place an order. A QR code is displayed upon order confirmation.

### 7. View Statistics
```bash
cd Souper_Kiosk
python stats.py
```

---

## Verifying Your Installation

### Kiosk Coordinator
You should see status updates as orders flow through the system:
```
[EVENT] Boiler ready. Checking safety interlocks...
[EVENT] Bowl is present. Starting powder and mixing sequence...
[SUCCESS] Mixing done. Signalling garnish node.
[SUCCESS] Garnish added. Order Complete.
Order [key] => ready
```

### Scanner
Point the camera at a valid order QR code:
- **Valid scan:** Order is marked `ready`, deleted from Firebase, and removed from queue.
- **Invalid scan:** Order does not exist or is not yet ready.

### Web Interface
Opening the Firebase Hosting URL displays the soup ordering menu with all 6 soup types and 6 toppings.

### Kitchen Nodes
Each node prints status updates to stdout:
- **Boiler:** `Heating Done!` → `Order finished!` → `status: complete`
- **Mixer:** `Mixing complete. Motor stopped.` → `status: complete`
- **Garnish:** `Dispense Sequence Complete.` → `status: complete`

### Run Unit Tests (Kiosk Node)
No hardware required — all external dependencies are mocked:
```bash
cd Souper_Kiosk
python -m pytest test_all.py -v
```
All tests should pass.

---

## Firebase Realtime Database Schema

The system uses the following Firebase structure:

```
/
├── orders/
│   └── {orderKey}/
│       ├── soup_type: "Tomato Soup"
│       ├── toppings: ["Broccoli", "Carrots"]
│       ├── total: 10.99
│       ├── status: "pending" | "processing" | "ready" | "cancelled"
│       └── timestamp: 1700000000000
│
├── inventory/
│   ├── "Chicken Broth": 10
│   ├── "Broccoli": 20
│   └── ...
│
├── boiler/
│   └── status: "idle" | "heating" | "ready" | "complete" | "error_no_bowl"
│
├── mixer/
│   └── status: "idle" | "mixing" | "complete" | "error_no_bowl"
│
├── garnish/
│   ├── status: "idle" | "dispensing" | "complete" | "error_no_bowl"
│   └── bowl_present: true | false
│
└── system/
    └── status: "online" | "emergency"
```

---

## Troubleshooting

**Orders not appearing on Kiosk:**
- Verify all nodes are connected to Firebase (check `config.py` credentials).
- Check Firebase Realtime Database rules allow reads/writes.

**Scanner not detecting QR codes:**
- Ensure picamera2 module is installed: `sudo apt install -y python3-picamera2`
- Test camera with: `libcamera-hello`

**Boiler/Mixer/Garnish nodes crash on import:**
- Verify GPIO libraries installed: `pip install RPi.GPIO gpiozero sense-hat`
- Check pins are not already in use by other processes.

**Temperature sensor not reading:**
- Verify 1-wire interface is enabled: `raspi-config` → Interfacing Options → 1-Wire
- Check DS18B20 wiring (VCC, GND, DATA + 4.7kΩ pull-up resistor).



