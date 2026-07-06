import 'package:dio/dio.dart';
import 'package:home_widget/home_widget.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';

const String _taskName = 'fetchWaterLevel';

@pragma('vm:entry-point')
void widgetBackgroundCallback() {
  Workmanager().executeTask((task, inputData) async {
    if (task != _taskName) return false;
    try {
      final prefs = await SharedPreferences.getInstance();
      final String? publicKey = prefs.getString('widget_public_key');
      final String? deviceName = prefs.getString('widget_device_name');
      if (publicKey == null || publicKey.isEmpty) return false;

      final dio = Dio(BaseOptions(
        baseUrl: 'https://waterlevel.pro',
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 15),
      ));

      final response = await dio.get('/data-api', queryParameters: {'key': publicKey});
      if (response.statusCode != 200 || response.data is! Map) return false;

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

      String voltage = '';
      final v = data['voltage'];
      if (v != null) {
        final double volt = double.tryParse(v.toString()) ?? 0;
        voltage = '${volt.toStringAsFixed(1)}V';
      }

      final diffTime = data['diff_time'];
      final int secondsSinceUpdate = int.tryParse(diffTime?.toString() ?? '') ?? 0;
      final bool isOnline = secondsSinceUpdate < 300;

      await HomeWidget.saveWidgetData('deviceName', deviceName ?? 'Water Level');
      await HomeWidget.saveWidgetData('percent', '${(fillPct * 100).toStringAsFixed(0)}%');
      await HomeWidget.saveWidgetData('level', '${waterHeight.toStringAsFixed(1)} cm');
      await HomeWidget.saveWidgetData('liters', liters);
      await HomeWidget.saveWidgetData('voltage', voltage);
      await HomeWidget.saveWidgetData('isOnline', isOnline ? 'true' : 'false');
      await HomeWidget.updateWidget(androidName: 'WaterLevelWidgetProvider');

      return true;
    } catch (_) {
      return false;
    }
  });
}

Future<void> registerWidgetBackgroundTask() async {
      await Workmanager().registerPeriodicTask(
    _taskName,
    _taskName,
    frequency: const Duration(minutes: 15),
    constraints: Constraints(
      networkType: NetworkType.connected,
    ),
    existingWorkPolicy: ExistingPeriodicWorkPolicy.replace,
  );
}
