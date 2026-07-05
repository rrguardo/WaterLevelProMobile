# API Setup Guide (Self-Hosted)

By default, the WaterLevel.Pro mobile app connects to the official cloud platform (`https://waterlevel.pro`). However, because this is an open-source project, you can easily host your own backend server and point this mobile app to your custom domain.

## Changing API Endpoints

All the network configuration for the mobile app is centralized in a single file: `lib/constants.dart`.

To point the app to your own self-hosted backend, follow these steps:

1. Open `lib/constants.dart` in your IDE.
2. Locate the following constants:
   ```dart
   const String USER_API_BASE_URL = "https://waterlevel.pro/users-api-mobile";
   const String HARDWARE_API_BASE_URL = "https://api.waterlevel.pro";
   const String RECAPTCHA_PUBLIC_KEY = "6Lf-ZnMsAAAAAP256Liv5ztCgwipso2UHkCCKOvy";
   ```
3. Change `USER_API_BASE_URL` to match your domain's mobile API prefix (e.g., `https://yourdomain.com/users-api-mobile`).
4. Change `HARDWARE_API_BASE_URL` to point to your hardware telemetry API endpoint (e.g., `https://api.yourdomain.com`).
5. Change `RECAPTCHA_PUBLIC_KEY` to the Site Key you obtained from the Google reCAPTCHA v2 console for your specific domain. If your local backend is running in `DEV_MODE=True`, you can leave this blank or ignore it, as the server will skip the verification.

## Local Testing (Emulator)

If you are running the Flask backend on your local machine and want to test the app using an Android Emulator, remember that `localhost` on Android refers to the device itself. You should use the special IP alias `10.0.2.2`.

Example for local testing:
```dart
const String USER_API_BASE_URL = "http://10.0.2.2/users-api-mobile";
const String HARDWARE_API_BASE_URL = "http://10.0.2.2:88"; // Or whichever port your API runs on
```

## Security Notice

- Make sure your self-hosted backend serves traffic over `https://` if possible, as modern mobile operating systems (iOS and Android) require secure connections by default (App Transport Security / Network Security Configuration).
- If you must use `http://` for local testing, ensure your `AndroidManifest.xml` and `Info.plist` are configured to allow cleartext traffic.
