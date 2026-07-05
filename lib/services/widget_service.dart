import 'package:dio/dio.dart';
import 'package:home_widget/home_widget.dart';
import 'package:shared_preferences/shared_preferences.dart';

class WidgetService {
  static const String _prefKey = 'widget_public_key';
  static const String _prefName = 'widget_device_name';

  static Future<String?> getWidgetPublicKey() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_prefKey);
  }

  static Future<void> setWidgetDeviceKey(String publicKey, String deviceName) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefKey, publicKey);
    await prefs.setString(_prefName, deviceName);
    await _fetchAndUpdateWidget(publicKey, deviceName);
  }

  static Future<bool> getShowSubtext() async {
    final val = await HomeWidget.getWidgetData<String>('show_subtext', defaultValue: 'false');
    return val == 'true';
  }

  static Future<String> getSubtextMode() async {
    final val = await HomeWidget.getWidgetData<String>('subtext_mode', defaultValue: 'cm');
    return val ?? 'cm';
  }

  static Future<void> setShowSubtext(bool show) async {
    await HomeWidget.saveWidgetData('show_subtext', show ? 'true' : 'false');
    await _triggerUpdate();
  }

  static Future<void> setSubtextMode(String mode) async {
    await HomeWidget.saveWidgetData('subtext_mode', mode);
    await _triggerUpdate();
  }

  static Future<void> _triggerUpdate() async {
    await HomeWidget.updateWidget(androidName: 'WaterLevelWidgetProvider');
  }

  static Future<void> saveSensorWidgetData({
    required String deviceName,
    required String percent,
    required String level,
    required String liters,
  }) async {
    await HomeWidget.saveWidgetData('deviceName', deviceName);
    await HomeWidget.saveWidgetData('percent', percent);
    await HomeWidget.saveWidgetData('level', level);
    await HomeWidget.saveWidgetData('liters', liters);
    await HomeWidget.updateWidget(androidName: 'WaterLevelWidgetProvider');
  }

  static Future<void> _fetchAndUpdateWidget(String publicKey, String deviceName) async {
    try {
      final dio = Dio(BaseOptions(
        baseUrl: 'https://waterlevel.pro',
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 15),
      ));
      final response = await dio.get('/data-api', queryParameters: {'key': publicKey});
      if (response.statusCode != 200 || response.data is! Map) return;

      final data = response.data as Map;
      double emptyLevel = double.tryParse(data['empty_level']?.toString() ?? '') ?? 200.0;
      double topMargin = double.tryParse(data['top_margin']?.toString() ?? '') ?? 0.0;
      if (emptyLevel == 0) emptyLevel = 1.0;
      if (topMargin < 0) topMargin = 0;

      double waterHeight = 0;
      if (data['water_height_cm'] != null) {
        waterHeight = double.tryParse(data['water_height_cm'].toString()) ?? 0.0;
      } else {
        double distance = double.tryParse(data['distance']?.toString() ?? '0') ?? 0;
        double clampedDist = distance.clamp(topMargin, emptyLevel);
        waterHeight = (emptyLevel - clampedDist).clamp(0, double.infinity);
      }

      double usable = (emptyLevel - topMargin);
      if (usable <= 0) usable = 1.0;
      double fillPct = (waterHeight / usable).clamp(0.0, 1.0);

      String liters = '';
      if (data['current_liters'] != null) {
        liters = '${double.tryParse(data['current_liters'].toString())?.toStringAsFixed(0) ?? '0'} L';
      }

      await saveSensorWidgetData(
        deviceName: deviceName,
        percent: '${(fillPct * 100).toStringAsFixed(0)}%',
        level: '${waterHeight.toStringAsFixed(1)} cm',
        liters: liters,
      );
    } catch (_) {}
  }
}
