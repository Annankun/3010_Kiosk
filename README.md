# Souper Kiosk

**Course:** ELEC 3010  
**Group Number:** [Group Number]  
**TA:** [TA Name]  

**Team Members:**
- Annan Jiang

---

## Project Summary

The Souper Kiosk is an automated soup vending system that allows customers to order customized soups through a mobile web interface and have them prepared and dispensed by a Raspberry Pi-controlled machine. Customers browse a menu of six soup bases (Chicken Broth, Tomato Soup, Beef Broth, Vegetable Soup, Mushroom Soup, Miso Soup) and six toppings (Broccoli, Carrots, Chicken, Tofu, Croutons, Cheese) via a Firebase-hosted webpage. Upon placing an order, a QR code is generated for the customer to use at pickup.

On the hardware side, a Raspberry Pi acts as the central controller, polling Firebase for new orders and coordinating three kitchen sub-components — a boiler, a mixer, and a garnish dispenser — to prepare each soup. Once the order is ready, the customer scans their QR code at a pickup station (also Raspberry Pi-powered with a camera) to retrieve their order. Green and red LEDs provide visual confirmation of valid or invalid scans.

Order history and inventory levels are tracked locally in an SQLite database, and a reporting tool allows monthly revenue and popularity statistics to be viewed at any time.

---

## Repository Structure

```
3010_Kiosk/
├── README.md                  # This file
└── Souper_Kiosk/              # Main application code
    ├── kiosk.py               # Main coordinator: polls Firebase, drives kitchen components
    ├── scanner.py             # Pickup station: scans QR codes, controls LEDs via GPIO
    ├── db.py                  # SQLite database module (orders, inventory, stats)
    ├── config.py              # Firebase project configuration
    ├── firebase.json          # Firebase hosting configuration
    ├── mobile.html            # Customer-facing ordering web interface
    ├── send_order.py          # Dev utility to push test orders to Firebase
    ├── watch_all.py           # Kitchen component status monitor
    ├── stats.py               # Monthly revenue and sales reporting CLI
    ├── test_all.py            # Unit test suite (mocked hardware/Firebase)
    ├── souper_qr.png          # QR code image used for ordering
    └── public/                # Firebase Hosting deployment directory
        ├── index.html         # Default hosting landing page
        └── mobile.html        # Deployed customer ordering interface
```

---

## Installation Instructions

### Hardware Required
- Raspberry Pi (any model with GPIO, camera support)
- Raspberry Pi Camera Module
- 2 LEDs (green and red) with appropriate resistors
- Kitchen hardware components: Boiler, Mixer, Garnish dispenser (connected via Firebase)

### Wiring
| Component      | GPIO Pin |
|----------------|----------|
| Emergency Stop | 23       |
| Green LED      | 17       |
| Red LED        | 27       |

### Software Setup

1. **Clone the repository** on your Raspberry Pi:
   ```bash
   git clone https://github.com/annankun/3010_kiosk.git
   cd 3010_Kiosk/Souper_Kiosk
   ```

2. **Install Python dependencies:**
   ```bash
   pip install pyrebase4 opencv-python pyzbar picamera2 RPi.GPIO
   ```

3. **Set up Firebase:**
   - Create a Firebase project at [firebase.google.com](https://firebase.google.com)
   - Enable Realtime Database and Hosting
   - Download your service account credentials JSON and replace `soupercomputer-f0dad-firebase-adminsdk-fbsvc-e43fdbaf74.json`
   - Update `config.py` with your Firebase project's API key and database URL

4. **Deploy the web interface to Firebase Hosting:**
   ```bash
   npm install -g firebase-tools
   firebase login
   firebase deploy --only hosting
   ```

5. **Initialize the local database:**
   The SQLite database (`orders.db`) is created automatically on first run.

---

## How to Run

### 1. Start the Main Kiosk Controller (Raspberry Pi)
This process polls Firebase for new orders and coordinates kitchen hardware:
```bash
cd Souper_Kiosk
python kiosk.py
```

### 2. Start the Pickup Scanner (Raspberry Pi)
Run this on the pickup station Raspberry Pi (can be the same Pi):
```bash
python scanner.py
```

### 3. Customer Orders
Customers open the Firebase-hosted URL (from `firebase.json`) on their phone, select a soup and toppings, and place an order. A QR code is displayed upon order confirmation.

### 4. View Statistics
```bash
python stats.py
```

---

## Verifying Your Installation

You should see the following when everything is working correctly:

- **`kiosk.py` running:** The terminal prints `Listening for orders...` and shows status updates as orders are received and processed (e.g., `Order received: Tomato Soup + Broccoli` → `Boiler done` → `Mixer done` → `Order ready`).

- **`scanner.py` running:** The terminal prints `Scanner ready. Waiting for QR code...`. Pointing the camera at a valid order QR code lights the **green LED** and prints `Order picked up successfully`. An invalid or already-collected QR lights the **red LED**.

- **Web interface:** Opening the Firebase Hosting URL shows the soup ordering menu with all 6 soup types and 6 toppings selectable.

- **Run unit tests** to verify all modules work correctly (no hardware required):
  ```bash
  cd Souper_Kiosk
  python -m pytest test_all.py -v
  ```
  All tests should pass.
