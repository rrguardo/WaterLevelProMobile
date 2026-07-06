import 'dart:async';
import 'package:flutter/material.dart';
import '../api/api_client.dart';
import '../services/widget_service.dart';
import 'widgets/water_tank_widget.dart';

class DeviceDetailScreen extends StatefulWidget {
  final Map<String, dynamic> device;

  const DeviceDetailScreen({super.key, required this.device});

  @override
  State<DeviceDetailScreen> createState() => _DeviceDetailScreenState();
}

class _DeviceDetailScreenState extends State<DeviceDetailScreen> {
  bool _isLoading = true;
  bool _isToggling = false;
  Map<String, dynamic>? _hardwareData;
  Timer? _pollingTimer;

  @override
  void initState() {
    super.initState();
    _fetchHardwareData();
    // Poll every 5 seconds
    _pollingTimer = Timer.periodic(Duration(seconds: 5), (timer) {
      _fetchHardwareData();
    });
  }

  @override
  void dispose() {
    _pollingTimer?.cancel();
    super.dispose();
  }

  Future<bool> _fetchHardwareData() async {
    try {
      final publicKey = widget.device['public_key'];
      final type = widget.device['type'];
      dynamic response;
      
      if (type == 1) { // Sensor - use /data-api for full data with settings
        response = await ApiClient().getSensorDataExtended(publicKey);
      } else if (type == 3) { // Relay
        response = await ApiClient().getRelayData(publicKey);
      }

      if (response != null && response.statusCode == 200 && response.data is Map) {
        if (mounted) {
          setState(() {
            _hardwareData = response.data;
            _isLoading = false;
          });
        }
        if (type == 1 && mounted) {
          _updateWidgetWithSensorData(response.data);
        }
        return true;
      }
    } catch (e) {
      // Handle or ignore polling errors
    }
    return false;
  }

  Future<void> _setAsWidgetSensor() async {
    await WidgetService.setWidgetDeviceKey(
      widget.device['public_key'] as String,
      widget.device['name'] as String? ?? 'Water Level',
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Sensor set as widget target'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  void _updateWidgetWithSensorData(Map<String, dynamic> data) {
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
      double fillPercentage = (waterHeight / usable).clamp(0.0, 1.0);

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

      WidgetService.saveSensorWidgetData(
        deviceName: widget.device['name'] ?? 'Water Level',
        percent: '${(fillPercentage * 100).toStringAsFixed(0)}%',
        level: '${waterHeight.toStringAsFixed(1)} cm',
        liters: liters,
        voltage: voltage,
        isOnline: isOnline,
      );
    } catch (_) {}
  }

  Future<void> _toggleRelay(bool turnOn) async {
    if (_isToggling) return;
    setState(() => _isToggling = true);
    final publicKey = widget.device['public_key'];
    try {
      await ApiClient().toggleRelay(publicKey, turnOn);
      bool confirmed = await _fetchHardwareData();
      if (!confirmed || _hardwareData?['status'] != (turnOn ? 1 : 0)) {
        for (int i = 0; i < 12; i++) {
          await Future.delayed(const Duration(seconds: 2));
          await _fetchHardwareData();
          if (_hardwareData?['status'] == (turnOn ? 1 : 0)) break;
        }
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Failed to toggle relay')));
    }
    if (mounted) setState(() => _isToggling = false);
  }

  Widget _buildSensorView() {
    if (_hardwareData == null) return Container();
    
    double distance = 0;
    try {
      distance = double.parse(_hardwareData!['distance'].toString());
    } catch (_) {}

    double emptyLevel = double.tryParse(_hardwareData!['empty_level']?.toString() ?? '') ?? 200.0;
    double topMargin = double.tryParse(_hardwareData!['top_margin']?.toString() ?? '') ?? 0.0;
    if (emptyLevel == 0) emptyLevel = 1.0;
    if (topMargin < 0) topMargin = 0;

    double waterHeight = 0;
    if (_hardwareData!['water_height_cm'] != null) {
      waterHeight = double.tryParse(_hardwareData!['water_height_cm'].toString()) ?? 0.0;
    } else {
      double clampedDist = distance;
      if (clampedDist > emptyLevel) clampedDist = emptyLevel;
      if (clampedDist < topMargin) clampedDist = topMargin;
      waterHeight = emptyLevel - clampedDist;
      if (waterHeight < 0) waterHeight = 0;
    }

    double usable = (emptyLevel - topMargin);
    if (usable <= 0) usable = 1.0;
    double fillPercentage = (waterHeight / usable).clamp(0.0, 1.0);

    String volumeText = '';
    if (_hardwareData!['current_liters'] != null) {
      double liters = double.tryParse(_hardwareData!['current_liters'].toString()) ?? 0.0;
      volumeText = '${liters.toStringAsFixed(0)} L';
    }

    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [Colors.blueAccent.withValues(alpha: 0.15), Colors.cyanAccent.withValues(alpha: 0.05)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.blueAccent.withValues(alpha: 0.2)),
          ),
          child: Row(
            children: [
              Container(
                padding: EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.blueAccent.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(Icons.water, color: Colors.blueAccent, size: 24),
              ),
              SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Water Level', style: TextStyle(color: Colors.grey[400], fontSize: 13)),
                  SizedBox(height: 2),
                  Text('${(fillPercentage * 100).toStringAsFixed(0)}%',
                    style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
                ],
              ),
            ],
          ),
        ),
        SizedBox(height: 20),
        Builder(
          builder: (context) {
            final screenWidth = MediaQuery.of(context).size.width;
            final tankWidth = screenWidth * 0.6;
            return WaterTankWidget(
              fillPercentage: fillPercentage,
              width: tankWidth,
              height: tankWidth * 1.4,
            );
          },
        ),
        SizedBox(height: 32),
        _buildInfoCard('Distance', '$distance cm', Icons.sensors, Colors.teal),
        if (volumeText.isNotEmpty) _buildInfoCard('Volume', volumeText, Icons.water_drop, Colors.lightBlue),
        _buildInfoCard('Voltage', '${_hardwareData!['voltage'] ?? 0} v', Icons.battery_charging_full, Colors.amber),
        _buildInfoCard('Signal', '${_hardwareData!['rssi'] ?? 0} dBm', Icons.signal_cellular_alt, Colors.green),
        _buildInfoCard('Last Update', '${_hardwareData!['diff_time'] ?? 0}s ago', Icons.history, Colors.orange),
        SizedBox(height: 4),
        _buildInfoCard('Empty Level', '$emptyLevel cm', Icons.arrow_upward, Colors.blueGrey),
        _buildInfoCard('Top Margin', '$topMargin cm', Icons.arrow_downward, Colors.indigo),
      ],
    );
  }

  Widget _buildRelayView() {
    if (_hardwareData == null) return Container();
    
    int status = _hardwareData!['status'] ?? 0;
    bool isOn = status == 1;

    final Color statusColor = isOn ? Colors.greenAccent : Colors.redAccent;
    final Color statusBg = isOn ? Colors.green.withValues(alpha: 0.1) : Colors.red.withValues(alpha: 0.1);

    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: EdgeInsets.all(24),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: _isToggling
                  ? [Colors.blueGrey.withValues(alpha: 0.3), Colors.blueGrey.withValues(alpha: 0.1)]
                  : [statusBg, statusBg.withValues(alpha: 0.3)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: _isToggling
                  ? Colors.blueAccent.withValues(alpha: 0.3)
                  : statusColor.withValues(alpha: 0.3),
              width: 1.5,
            ),
          ),
          child: Column(
            children: [
              Stack(
                alignment: Alignment.center,
                children: [
                  Opacity(
                    opacity: _isToggling ? 0.3 : 1.0,
                    child: Icon(
                      isOn ? Icons.power_settings_new : Icons.power_settings_new,
                      size: 80,
                      color: statusColor,
                    ),
                  ),
                  if (_isToggling)
                    const CircularProgressIndicator(color: Colors.blueAccent),
                ],
              ),
              SizedBox(height: 12),
              Container(
                padding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                decoration: BoxDecoration(
                  color: _isToggling
                      ? Colors.blueAccent.withValues(alpha: 0.15)
                      : statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  _isToggling ? 'UPDATING...' : (isOn ? 'PUMP ON' : 'PUMP OFF'),
                  style: TextStyle(
                    color: _isToggling ? Colors.blueAccent : statusColor,
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.2,
                  ),
                ),
              ),
            ],
          ),
        ),
        SizedBox(height: 28),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _buildActionButton(
              label: 'TURN ON',
              icon: Icons.power,
              color: Colors.green,
              onTap: _isToggling ? null : () => _toggleRelay(true),
              isLoading: _isToggling,
            ),
            _buildActionButton(
              label: 'TURN OFF',
              icon: Icons.power_off,
              color: Colors.red,
              onTap: _isToggling ? null : () => _toggleRelay(false),
              isLoading: _isToggling,
            ),
          ],
        ),
        SizedBox(height: 32),
        _buildInfoCard('Signal', '${_hardwareData!['rssi'] ?? 0} dBm', Icons.signal_cellular_alt, Colors.green),
        _buildInfoCard('Last Update', '${_hardwareData!['diff_time'] ?? 0}s ago', Icons.history, Colors.orange),
        if (_hardwareData!['events'] is List && (_hardwareData!['events'] as List).isNotEmpty) ...[
          SizedBox(height: 4),
          Container(
            width: double.infinity,
            padding: EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.amber.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: Colors.amber.withValues(alpha: 0.2)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.warning_amber_rounded, color: Colors.amber, size: 18),
                    SizedBox(width: 8),
                    Text('Events', style: TextStyle(color: Colors.amber, fontSize: 13, fontWeight: FontWeight.w600)),
                  ],
                ),
                SizedBox(height: 8),
                ...(_hardwareData!['events'] as List).map((e) => Padding(
                  padding: EdgeInsets.only(bottom: 4),
                  child: Row(
                    children: [
                      Icon(Icons.circle, size: 6, color: Colors.amber[300]),
                      SizedBox(width: 8),
                      Expanded(child: Text('$e', style: TextStyle(color: Colors.amber[100], fontSize: 13))),
                    ],
                  ),
                )),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildActionButton({
    required String label,
    required IconData icon,
    required Color color,
    required VoidCallback? onTap,
    required bool isLoading,
  }) {
    return Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        splashColor: Colors.white.withValues(alpha: 0.15),
        highlightColor: Colors.white.withValues(alpha: 0.05),
        child: AnimatedContainer(
          duration: Duration(milliseconds: 200),
          width: 140,
          padding: EdgeInsets.symmetric(vertical: 16),
          decoration: BoxDecoration(
            gradient: onTap == null
                ? LinearGradient(colors: [Colors.grey[700]!, Colors.grey[600]!])
                : LinearGradient(colors: [color, color.withValues(alpha: 0.7)]),
            borderRadius: BorderRadius.circular(16),
            boxShadow: onTap == null
                ? []
                : [BoxShadow(color: color.withValues(alpha: 0.3), blurRadius: 8, offset: Offset(0, 4))],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              isLoading
                  ? SizedBox(
                      width: 20, height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white),
                    )
                  : Icon(icon, color: Colors.white, size: 26),
              SizedBox(height: 6),
              Text(label, style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.8)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInfoCard(String title, String value, IconData icon, Color iconColor) {
    return Card(
      color: Colors.grey[850],
      margin: EdgeInsets.symmetric(vertical: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: iconColor.withValues(alpha: 0.15), width: 1),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Container(
              padding: EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: iconColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: iconColor, size: 22),
            ),
            SizedBox(width: 14),
            Expanded(
              child: Text(title, style: TextStyle(color: Colors.grey[400], fontSize: 14)),
            ),
            Text(value, style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final type = widget.device['type'];
    final name = widget.device['name'] ?? 'Device';

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(name, style: TextStyle(color: Colors.white)),
        backgroundColor: Colors.grey[900],
        iconTheme: IconThemeData(color: Colors.white),
        actions: type == 1
            ? [
                IconButton(
                  icon: Icon(Icons.widgets_outlined, color: Colors.cyanAccent),
                  tooltip: 'Set as widget sensor',
                  onPressed: _setAsWidgetSensor,
                ),
              ]
            : null,
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator(color: Colors.blueAccent))
          : SingleChildScrollView(
              padding: EdgeInsets.all(16.0),
              child: type == 1 ? _buildSensorView() : _buildRelayView(),
            ),
    );
  }
}
