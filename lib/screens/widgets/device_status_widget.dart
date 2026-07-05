import 'package:flutter/material.dart';

class DeviceStatusWidget extends StatelessWidget {
  final int deviceType;
  final double? fillPercentage;
  final bool? isPumpOn;

  const DeviceStatusWidget({
    super.key,
    required this.deviceType,
    this.fillPercentage,
    this.isPumpOn,
  });

  @override
  Widget build(BuildContext context) {
    if (deviceType == 1) {
      return _buildSensorStatus();
    }
    return _buildRelayStatus();
  }

  Widget _buildSensorStatus() {
    final double pct = (fillPercentage ?? 0).clamp(0.0, 1.0);
    final Color waterColor = pct > 0.5
        ? Colors.blueAccent
        : (pct > 0.2 ? Colors.cyanAccent : Colors.redAccent);

    return Container(
      width: 52,
      height: 52,
      decoration: BoxDecoration(
        color: Colors.grey[900],
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: waterColor.withValues(alpha: 0.2), width: 1),
      ),
      child: Stack(
        alignment: Alignment.bottomCenter,
        children: [
          Container(
            width: 44,
            height: 44 * pct,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Colors.blueAccent.withValues(alpha: 0.6),
                  waterColor.withValues(alpha: 0.3),
                ],
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
              ),
              borderRadius: BorderRadius.only(
                bottomLeft: Radius.circular(10),
                bottomRight: Radius.circular(10),
              ),
            ),
          ),
          Center(
            child: Text(
              '${(pct * 100).round()}%',
              style: TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRelayStatus() {
    final bool on = isPumpOn ?? false;
    return Container(
      width: 52,
      height: 52,
      decoration: BoxDecoration(
        color: Colors.grey[900],
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: on
              ? Colors.greenAccent.withValues(alpha: 0.3)
              : Colors.redAccent.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            on ? Icons.power : Icons.power_off,
            color: on ? Colors.greenAccent : Colors.redAccent,
            size: 20,
          ),
          SizedBox(height: 2),
          Text(
            on ? 'ON' : 'OFF',
            style: TextStyle(
              color: on ? Colors.greenAccent : Colors.redAccent,
              fontSize: 10,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}
