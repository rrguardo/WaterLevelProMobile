# WaterLevel.Pro Mobile App 📱💧

![Flutter](https://img.shields.io/badge/Flutter-02569B?style=for-the-badge&logo=flutter&logoColor=white)
![Dart](https://img.shields.io/badge/Dart-0175C2?style=for-the-badge&logo=dart&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)

The official (and Open Source) mobile application for connecting to the **WaterLevel.Pro** platform.
This application is built with Flutter, offering a fast and smooth dashboard with a modern "Dark Mode" design for the WaterLevel ecosystem.

## Features 🚀

- **Native Authentication**: Clean login and registration interface, featuring a native and invisible reCAPTCHA v2 integration (WebView-based) to ensure backend security.
- **Device List**: View all your registered sensors and relays right on the home screen.
- **Sensor Details (S1)**: Monitor the water level of your tanks or cisterns via an animated chart that updates in real-time, displaying distance, hardware voltage, and WiFi signal quality.
- **Relay Control (R1)**: Turn your mobile into a remote control. Observe the real-time status of your water pumps and instantly toggle them on or off with interactive buttons.
- **Live Polling**: Real-time hardware telemetry updates when viewing the device details screen.

## Prerequisites 📋

- Flutter SDK (recent stable release).
- Android Studio / Xcode (for emulation or physical deployment).

## Getting Started 🛠️

1. Clone this repository or download the source code.
2. Open your terminal in the root directory and install dependencies:
   ```bash
   flutter pub get
   ```
3. Connect your device or start an emulator.
4. Build and run the application:
   ```bash
   flutter run
   ```

## Configuration and Self-Hosting ⚙️

By default, this application connects to the official **WaterLevel.Pro** cloud. However, the code is open-source and ready to be pointed to a self-hosted environment.

Network configuration is centralized for your convenience. Simply navigate to `lib/constants.dart` and change the API URLs to match your own.

For more details, please review our guide:
👉 [**API Setup Guide (docs/API_SETUP.md)**](docs/API_SETUP.md)

## Built With 🧱

- [Flutter](https://flutter.dev/) - Native UI framework.
- [Dio](https://pub.dev/packages/dio) - Powerful HTTP client for Dart.
- [Provider](https://pub.dev/packages/provider) - Fast and simple state management.
- [Flutter reCAPTCHA v2](https://pub.dev/packages/flutter_recaptcha_v2_compat) - Implementation for integrating the backend's web native reCAPTCHA on a mobile device.

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
