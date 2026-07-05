import 'dart:async';
import 'package:flutter/material.dart';
import 'package:home_widget/home_widget.dart';
import 'package:provider/provider.dart';
import '../api/api_client.dart';
import '../providers/auth_provider.dart';
import '../providers/devices_provider.dart';
import '../services/widget_service.dart';
import 'login_screen.dart';
import 'device_detail_screen.dart';
import 'widgets/device_status_widget.dart';


class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final Map<String, dynamic> _liveData = {};
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<DevicesProvider>(context, listen: false).fetchDevices();
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  void _startPolling(List<dynamic> devices) {
    _pollTimer?.cancel();
    _fetchAllLiveData(devices);
    _pollTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      _fetchAllLiveData(devices);
    });
  }

  Future<void> _fetchAllLiveData(List<dynamic> devices) async {
    for (final device in devices) {
      try {
        final pk = device['public_key'] as String;
        final int type = device['type'] ?? 1;
        if (type == 1) {
          final resp = await ApiClient().getSensorDataExtended(pk);
          if (resp.statusCode == 200) {
            _liveData[pk] = resp.data;
          }
        } else if (type == 3) {
          final resp = await ApiClient().getRelayData(pk);
          if (resp.statusCode == 200) {
            _liveData[pk] = resp.data;
          }
        }
      } catch (_) {}
    }
    if (mounted) setState(() {});
    _updateWidgetFromLiveData();
  }

  void _updateWidgetFromLiveData() async {
    final widgetKey = await WidgetService.getWidgetPublicKey();
    if (widgetKey == null) return;
    final data = _liveData[widgetKey];
    if (data is! Map || !data.containsKey('empty_level')) return;

    try {
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

      WidgetService.saveSensorWidgetData(
        deviceName: 'Water Level',
        percent: '${(fillPct * 100).toStringAsFixed(0)}%',
        level: '${waterHeight.toStringAsFixed(1)} cm',
        liters: liters,
      );
    } catch (_) {}
  }

  Future<void> _showWidgetPicker(List<dynamic> devices) async {
    final sensors = devices.where((d) => d['type'] == 1).toList();
    if (sensors.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No S1 sensors available for widget')),
      );
      return;
    }

    final currentKey = await WidgetService.getWidgetPublicKey();

    final selected = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      backgroundColor: Colors.grey[900],
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Select sensor for widget',
                style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 16),
            ...sensors.map((s) => ListTile(
                  leading: Icon(Icons.water_drop, color: Colors.cyanAccent),
                  title: Text(s['name'] ?? 'Sensor', style: TextStyle(color: Colors.white)),
                  subtitle: Text(s['public_key'] ?? '', style: TextStyle(color: Colors.grey, fontSize: 12)),
                  trailing: s['public_key'] == currentKey
                      ? Icon(Icons.check_circle, color: Colors.cyanAccent)
                      : null,
                  onTap: () => Navigator.pop(ctx, s),
                )),
          ],
        ),
      ),
    );

    if (selected == null) return;
    final pk = selected['public_key'] as String;
    final name = selected['name'] as String? ?? 'Water Level';

    await WidgetService.setWidgetDeviceKey(pk, name);
    try {
      await HomeWidget.requestPinWidget(androidName: 'WaterLevelWidgetProvider');
    } catch (_) {}
  }

  Future<void> _showWidgetSettings() async {
    final showSubtext = await WidgetService.getShowSubtext();
    final subtextMode = await WidgetService.getSubtextMode();

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => _WidgetSettingsDialog(
        initialShowSubtext: showSubtext,
        initialMode: subtextMode,
      ),
    );

    if (result == null || !mounted) return;
    await WidgetService.setShowSubtext(result['showSubtext'] as bool);
    await WidgetService.setSubtextMode(result['subtextMode'] as String);
  }

  void _logout() async {
    _pollTimer?.cancel();
    final auth = Provider.of<AuthProvider>(context, listen: false);
    await auth.logout();
    if (!mounted) return;
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => LoginScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = Provider.of<AuthProvider>(context);
    final devicesProvider = Provider.of<DevicesProvider>(context);

    if (devicesProvider.devices.isNotEmpty && _pollTimer == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _startPolling(devicesProvider.devices);
      });
    }

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text('Dashboard', style: TextStyle(color: Colors.white)),
        backgroundColor: Colors.grey[900],
        iconTheme: IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: Icon(Icons.widgets_outlined),
            tooltip: 'Add widget to home screen',
            onPressed: () => _showWidgetPicker(devicesProvider.devices),
          ),
          PopupMenuButton<String>(
            icon: Icon(Icons.more_vert, color: Colors.white),
            onSelected: (v) async {
              if (v == 'biometric') {
                final auth = Provider.of<AuthProvider>(context, listen: false);
                final canBio = await auth.isBiometricDeviceAvailable();
                if (!mounted) return;
                if (canBio) {
                  final savedEmail = await auth.getSavedEmail();
                  if (savedEmail != null) {
                    await auth.disableBiometric();
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('Biometric unlock disabled')),
                    );
                  } else {
                    final enable = await showDialog<bool>(
                      context: context,
                      builder: (ctx) => AlertDialog(
                        backgroundColor: Colors.grey[900],
                        title: Text('Enable biometric unlock?', style: TextStyle(color: Colors.white)),
                        content: Text('Use fingerprint or face to unlock the app.',
                            style: TextStyle(color: Colors.grey[300])),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(ctx, false),
                            child: Text('Cancel', style: TextStyle(color: Colors.grey)),
                          ),
                          TextButton(
                            onPressed: () => Navigator.pop(ctx, true),
                            child: Text('Enable', style: TextStyle(color: Colors.blueAccent)),
                          ),
                        ],
                      ),
                    );
                    if (enable == true && mounted) {
                      await auth.enableBiometric(
                        auth.user?['email'] ?? '',
                        '',
                      );
                    }
                  }
                } else {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Biometric not available on this device')),
                  );
                }
              } else if (v == 'widget_settings') {
                _showWidgetSettings();
              } else if (v == 'logout') {
                _logout();
              }
            },
            itemBuilder: (_) => [
              PopupMenuItem(value: 'widget_settings', child: Row(
                children: [
                  Icon(Icons.widgets, color: Colors.cyanAccent, size: 20),
                  SizedBox(width: 10),
                  Text('Widget settings'),
                ],
              )),
              PopupMenuItem(value: 'biometric', child: Row(
                children: [
                  Icon(Icons.fingerprint, color: Colors.blueAccent, size: 20),
                  SizedBox(width: 10),
                  Text('Biometric unlock'),
                ],
              )),
              PopupMenuItem(value: 'logout', child: Row(
                children: [
                  Icon(Icons.logout, color: Colors.redAccent, size: 20),
                  SizedBox(width: 10),
                  Text('Logout'),
                ],
              )),
            ],
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (auth.user != null) ...[
              Text(
                'Welcome,',
                style: TextStyle(color: Colors.grey, fontSize: 16),
              ),
              Text(
                auth.user!['email'] ?? 'User',
                style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 24),
            ],
            Text(
              'Your Devices',
              style: TextStyle(color: Colors.blueAccent, fontSize: 18, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 16),
            Expanded(
              child: devicesProvider.isLoading
                  ? Center(child: CircularProgressIndicator(color: Colors.blueAccent))
                  : devicesProvider.devices.isEmpty
                      ? Center(child: Text('No devices found.', style: TextStyle(color: Colors.grey)))
                      : ListView.builder(
                          itemCount: devicesProvider.devices.length,
                          itemBuilder: (context, index) {
                            final device = devicesProvider.devices[index];
                            final int type = device['type'] ?? 1;
                            final bool isSensor = type == 1;
                            final Color accentColor = isSensor ? Colors.cyanAccent : Colors.amber;
                            final IconData icon = isSensor ? Icons.water_drop : Icons.power_settings_new;
                            final pk = device['public_key'] as String;
                            final live = _liveData[pk];

                            double? fillPct;
                            bool? pumpOn;
                            if (live != null) {
                              if (isSensor) {
                                final double? el = double.tryParse(live['empty_level']?.toString() ?? '');
                                final double? tm = double.tryParse(live['top_margin']?.toString() ?? '');
                                final double? dist = double.tryParse(live['distance']?.toString() ?? '');
                                if (el != null && tm != null && dist != null) {
                                  final double usable = (el - tm).clamp(0.1, double.infinity);
                                  final double clamped = dist.clamp(tm, el);
                                  fillPct = ((el - clamped) / usable).clamp(0.0, 1.0);
                                }
                              } else {
                                pumpOn = live['status'] == 1;
                              }
                            }

                            return Card(
                              color: Colors.grey[850],
                              margin: EdgeInsets.symmetric(vertical: 6),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(14),
                                side: BorderSide(color: accentColor.withValues(alpha: 0.15), width: 1),
                              ),
                              child: InkWell(
                                borderRadius: BorderRadius.circular(14),
                                onTap: () async {
                                  await Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                      builder: (_) => DeviceDetailScreen(device: device),
                                    ),
                                  );
                                  _fetchAllLiveData(devicesProvider.devices);
                                },
                                child: Padding(
                                  padding: EdgeInsets.all(14),
                                  child: Row(
                                    children: [
                                      Container(
                                        padding: EdgeInsets.all(10),
                                        decoration: BoxDecoration(
                                          color: accentColor.withValues(alpha: 0.12),
                                          borderRadius: BorderRadius.circular(12),
                                        ),
                                        child: Icon(icon, color: accentColor, size: 26),
                                      ),
                                      SizedBox(width: 14),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              device['name'] ?? 'Unknown',
                                              style: TextStyle(
                                                color: Colors.white,
                                                fontSize: 16,
                                                fontWeight: FontWeight.w600,
                                              ),
                                            ),
                                            SizedBox(height: 3),
                                            Text(
                                              device['type_name'] ?? '',
                                              style: TextStyle(color: Colors.grey[500], fontSize: 13),
                                            ),
                                          ],
                                        ),
                                      ),
                                      SizedBox(width: 10),
                                      DeviceStatusWidget(
                                        deviceType: type,
                                        fillPercentage: fillPct,
                                        isPumpOn: pumpOn,
                                      ),
                                      SizedBox(width: 8),
                                      Container(
                                        padding: EdgeInsets.all(6),
                                        decoration: BoxDecoration(
                                          color: accentColor.withValues(alpha: 0.08),
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                        child: Icon(Icons.chevron_right, color: accentColor, size: 20),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WidgetSettingsDialog extends StatefulWidget {
  final bool initialShowSubtext;
  final String initialMode;
  const _WidgetSettingsDialog({required this.initialShowSubtext, required this.initialMode});

  @override
  State<_WidgetSettingsDialog> createState() => _WidgetSettingsDialogState();
}

class _WidgetSettingsDialogState extends State<_WidgetSettingsDialog> {
  late bool _showSubtext;
  late String _mode;

  @override
  void initState() {
    super.initState();
    _showSubtext = widget.initialShowSubtext;
    _mode = widget.initialMode;
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: Colors.grey[900],
      title: Text('Widget Settings', style: TextStyle(color: Colors.white)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SwitchListTile(
            title: Text('Show extra info', style: TextStyle(color: Colors.white, fontSize: 14)),
            subtitle: Text('Display cm / device name below %', style: TextStyle(color: Colors.grey[400], fontSize: 12)),
            value: _showSubtext,
            activeColor: Colors.cyanAccent,
            onChanged: (v) => setState(() => _showSubtext = v),
            contentPadding: EdgeInsets.zero,
          ),
          if (_showSubtext) ...[
            SizedBox(height: 8),
            Text('Info mode:', style: TextStyle(color: Colors.grey[300], fontSize: 13)),
            ...['cm', 'name', 'both'].map((m) => RadioListTile<String>(
              title: Text({
                'cm': 'Water level (cm)',
                'name': 'Device name',
                'both': 'Name + level',
              }[m]!, style: TextStyle(color: Colors.white, fontSize: 13)),
              value: m,
              groupValue: _mode,
              activeColor: Colors.cyanAccent,
              onChanged: (v) => setState(() => _mode = v!),
              contentPadding: EdgeInsets.zero,
              dense: true,
            )),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text('Cancel', style: TextStyle(color: Colors.grey)),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context, {
            'showSubtext': _showSubtext,
            'subtextMode': _mode,
          }),
          child: Text('Apply', style: TextStyle(color: Colors.blueAccent)),
        ),
      ],
    );
  }
}
