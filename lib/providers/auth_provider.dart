import 'package:flutter/foundation.dart';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';
import '../api/api_client.dart';

class AuthProvider extends ChangeNotifier {
  bool _isLoggedIn = false;
  bool _isLoading = false;
  bool _isInitializing = true;
  bool _needsBiometric = false;
  Map<String, dynamic>? _user;
  final FlutterSecureStorage _secure = const FlutterSecureStorage();
  final LocalAuthentication _localAuth = LocalAuthentication();

  bool get isLoggedIn => _isLoggedIn;
  bool get isLoading => _isLoading;
  bool get isInitializing => _isInitializing;
  bool get needsBiometric => _needsBiometric;
  Map<String, dynamic>? get user => _user;

  Future<void> init() async {
    final hasBiometric = await _secure.containsKey(key: 'biometric_enabled');
    if (hasBiometric) {
      _needsBiometric = true;
      _isInitializing = false;
      notifyListeners();
      return;
    }
    await checkLoginStatus();
  }

  Future<void> onBiometricSuccess() async {
    _needsBiometric = false;
    await checkLoginStatus();
  }

  Future<bool> isBiometricDeviceAvailable() async {
    try {
      return await _localAuth.canCheckBiometrics || await _localAuth.isDeviceSupported();
    } catch (_) {
      return false;
    }
  }

  Future<bool> authenticateBiometric() async {
    try {
      return await _localAuth.authenticate(
        localizedReason: 'Unlock WaterLevel.Pro',
        biometricOnly: true,
      );
    } catch (_) {
      return false;
    }
  }

  Future<String?> getSavedEmail() async {
    try {
      return await _secure.read(key: 'saved_email');
    } catch (_) {
      return null;
    }
  }

  Future<bool> enableBiometric(String email, String password) async {
    try {
      await _secure.write(key: 'saved_email', value: email);
      await _secure.write(key: 'saved_password', value: password);
      await _secure.write(key: 'biometric_enabled', value: 'true');
      _needsBiometric = false;
      notifyListeners();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> disableBiometric() async {
    await _secure.delete(key: 'saved_email');
    await _secure.delete(key: 'saved_password');
    await _secure.delete(key: 'biometric_enabled');
    _needsBiometric = false;
    notifyListeners();
  }

  Future<void> checkLoginStatus() async {
    _isInitializing = true;
    notifyListeners();
    try {
      final response = await ApiClient().getMe();
      if (response.statusCode == 200 && response.data['user'] != null) {
        _user = response.data['user'];
        _isLoggedIn = true;
      } else {
        _isLoggedIn = false;
      }
    } catch (e) {
      _isLoggedIn = false;
    }
    _isInitializing = false;
    notifyListeners();
  }

  Future<bool> login(String email, String password, String recaptchaToken) async {
    _isLoading = true;
    notifyListeners();
    try {
      final response = await ApiClient().login(email, password, recaptchaToken);
      if (response.statusCode == 200 && response.data['success'] == true) {
        _user = response.data['user'];
        _isLoggedIn = true;
        _isLoading = false;
        notifyListeners();
        return true;
      }
    } on DioException catch (_) {
      // Handle error
    }
    _isLoading = false;
    notifyListeners();
    return false;
  }

  Future<bool> register(String email, String password, String recaptchaToken) async {
    _isLoading = true;
    notifyListeners();
    try {
      final response = await ApiClient().register(email, password, recaptchaToken);
      if (response.statusCode == 201 && response.data['success'] == true) {
        _isLoading = false;
        notifyListeners();
        return true;
      }
    } on DioException catch (_) {
      // Handle error
    }
    _isLoading = false;
    notifyListeners();
    return false;
  }

  Future<void> logout() async {
    _isLoading = true;
    notifyListeners();
    try {
      await ApiClient().logout();
    } catch (_) {}
    await disableBiometric();
    _user = null;
    _isLoggedIn = false;
    _isLoading = false;
    notifyListeners();
  }
}
