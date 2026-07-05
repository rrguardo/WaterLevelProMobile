// ==========================================
// GLOBAL APPLICATION CONFIGURATION
// ==========================================

/// Base URL for the Users API (Handles sessions, login, registration, listing devices).
/// By default, it points to the WaterLevel.Pro cloud server.
const String userApiBaseUrl = "https://waterlevel.pro/users-api-mobile";

/// Base URL for the Hardware API (Reading S1 sensors and controlling R1 relays).
/// By default, it points to the api subdomain of WaterLevel.Pro.
const String hardwareApiBaseUrl = "https://api.waterlevel.pro";

/// Google reCAPTCHA v2 Public Key.
/// Required to pass security validations on the backend Login and Registration.
const String recaptchaPublicKey = "6Lf-ZnMsAAAAAP256Liv5ztCgwipso2UHkCCKOvy";
