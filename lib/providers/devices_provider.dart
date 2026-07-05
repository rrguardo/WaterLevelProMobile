import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';
import '../services/background_service.dart';

class DevicesProvider extends ChangeNotifier {
  bool _isLoading = false;
  List<dynamic> _devices = [];

  bool get isLoading => _isLoading;
  List<dynamic> get devices => _devices;

  Future<void> fetchDevices() async {
    _isLoading = true;
    notifyListeners();
    try {
      final response = await ApiClient().getDevices();
      if (response.statusCode == 200 && response.data['devices'] != null) {
        _devices = response.data['devices'];
        await _saveWidgetDevice();
        await registerWidgetBackgroundTask();
      }
    } catch (e) {
      _devices = [];
    }
    _isLoading = false;
    notifyListeners();
  }

  Future<void> _saveWidgetDevice() async {
    for (final device in _devices) {
      if (device['type'] == 1) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('widget_public_key', device['public_key'] ?? '');
        await prefs.setString('widget_device_name', device['name'] ?? 'Water Level');
        break;
      }
    }
  }
}
