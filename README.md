# 🛡️ WinUSB-Guardian

**WinUSB-Guardian** is a robust, real-time USB management and security tool for Windows. It provides advanced monitoring and automated blocking of unauthorized USB storage devices to protect your system from data injection and malicious payloads.

## ✨ Key Features

- **🚀 Real-time Monitoring**: Detects USB storage devices (`USBSTOR`) the moment they are connected using WMI event watchers.
- **🚫 Automated Blocking**: Instantly disables unauthorized USB devices at the system level using `pnputil` and native Windows APIs.
- **📑 Whitelist Management**: Maintain a persistent `usb_whitelist.json` file to allow trusted devices based on their unique serial numbers.
- **🛡️ AutoRun Protection**: Automatically disables Windows AutoRun/AutoPlay system-wide to prevent the execution of malicious `autorun.inf` files.
- **🔄 Smart Recovery**: Automatically detects and recovers devices that were left in a disabled state from previous sessions.
- **💻 Admin-Aware**: Automatically requests elevation to Administrator privileges if needed.

## 🛠️ Installation

### Prerequisites

- **Windows 10 or 11**
- **Python 3.10+**
- Administrator privileges

### Dependencies

Install the required Python libraries:

```powershell
pip install wmi pywin32
```

## 🚀 Usage

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/WinUSB-Guardian.git
   cd WinUSB-Guardian
   ```

2. **Run the manager**:
   ```powershell
   python usb_manager.py
   ```

3. **Whitelist a device**:
   - When an unauthorized device is blocked, its **Device ID** will be printed in the terminal.
   - Manually add the serial number (the last part of the Device ID) to `usb_whitelist.json`.
   - Example `usb_whitelist.json`:
     ```json
     [
         "0358923100002084"
     ]
     ```

## 📂 Project Structure

- `usb_manager.py`: The main controller that handles detection, blocking, and whitelisting.
- `usb_detector.py`: A lightweight script for monitoring connection events.
- `usb_whitelist.json`: (Generated) Stores the serial numbers of allowed devices.
- `usb_events.log`: (Generated) Detailed logs of all connection and blocking events.

## ⚠️ Security Notice

This tool is designed to enhance security, but physical security is also paramount. Ensure your laptop is configured to **Lock on Lid Close** and requires a password on wake-up to mitigate HID-based (keyboard emulation) attacks.

## 📄 License

Apache License 2.0. See `LICENSE` for details.
