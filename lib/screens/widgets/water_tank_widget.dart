import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:sensors_plus/sensors_plus.dart';

class WaterTankWidget extends StatefulWidget {
  final double fillPercentage;
  final double width;
  final double height;

  const WaterTankWidget({
    super.key,
    required this.fillPercentage,
    required this.width,
    required this.height,
  });

  @override
  State<WaterTankWidget> createState() => _WaterTankWidgetState();
}

class _WaterTankWidgetState extends State<WaterTankWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  StreamSubscription<AccelerometerEvent>? _accelerometerSubscription;
  double _tiltAngle = 0.0;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3), // Slower, more natural wave animation
    )..repeat();

    _accelerometerSubscription =
        accelerometerEventStream().listen((AccelerometerEvent event) {
      if (!mounted) return;
      setState(() {
        _tiltAngle = -math.atan2(event.x, event.y);
        if (_tiltAngle > math.pi / 4) _tiltAngle = math.pi / 4;
        if (_tiltAngle < -math.pi / 4) _tiltAngle = -math.pi / 4;
      });
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    _accelerometerSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Make the widget a perfect circle based on minimum dimension
    final double size = math.min(widget.width, widget.height);

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 1. Dark container base with outer shadows (neumorphism effect)
          Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF1E222D),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.6),
                  blurRadius: 20,
                  offset: const Offset(10, 10),
                ),
                BoxShadow(
                  color: Colors.white.withValues(alpha: 0.05),
                  blurRadius: 20,
                  offset: const Offset(-10, -10),
                ),
              ],
            ),
          ),
          
          // 2. Liquid animation clipped as a circle
          ClipOval(
            child: AnimatedBuilder(
              animation: _animationController,
              builder: (context, child) {
                return CustomPaint(
                  size: Size(size, size),
                  painter: _WaterPainter(
                    fillPercentage: widget.fillPercentage,
                    animationValue: _animationController.value,
                    tiltAngle: _tiltAngle,
                  ),
                );
              },
            ),
          ),
          
          // 3. Glass highlight / Inner shadow for 3D spherical volume
          Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                center: const Alignment(-0.3, -0.4),
                radius: 1.0,
                colors: [
                  Colors.white.withValues(alpha: 0.25),
                  Colors.white.withValues(alpha: 0.0),
                  Colors.black.withValues(alpha: 0.4),
                  Colors.black.withValues(alpha: 0.8),
                ],
                stops: const [0.0, 0.4, 0.75, 1.0],
              ),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.15),
                width: 1.5,
              ),
            ),
          ),
          
          // 4. Percentage Text Overlay
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '${(widget.fillPercentage * 100).toStringAsFixed(0)}%',
                style: TextStyle(
                  fontSize: size * 0.22,
                  fontWeight: FontWeight.w900,
                  color: Colors.white,
                  letterSpacing: 1.2,
                  shadows: [
                    Shadow(
                      color: Colors.black.withValues(alpha: 0.8),
                      offset: const Offset(2, 2),
                      blurRadius: 8,
                    ),
                    Shadow(
                      color: const Color(0xFF00E5FF).withValues(alpha: 0.5),
                      offset: const Offset(0, 0),
                      blurRadius: 15,
                    ),
                  ],
                ),
              ),
              Text(
                'LEVEL',
                style: TextStyle(
                  fontSize: size * 0.07,
                  fontWeight: FontWeight.w600,
                  color: Colors.white.withValues(alpha: 0.8),
                  letterSpacing: 3.0,
                  shadows: [
                    Shadow(
                      color: Colors.black.withValues(alpha: 0.8),
                      offset: const Offset(1, 1),
                      blurRadius: 4,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _WaterPainter extends CustomPainter {
  final double fillPercentage;
  final double animationValue;
  final double tiltAngle;

  _WaterPainter({
    required this.fillPercentage,
    required this.animationValue,
    required this.tiltAngle,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (fillPercentage <= 0.0) return;

    final waterHeight = size.height * fillPercentage;
    final waterTop = size.height - waterHeight;

    // Define three layers of waves for better depth
    _drawWave(
      canvas,
      size,
      waterTop,
      waveFrequency: 1.2,
      waveAmplitude: 12.0,
      phaseOffset: math.pi,
      color: const Color(0xFF005FFF).withValues(alpha: 0.4),
      heightOffset: -5.0,
    );

    _drawWave(
      canvas,
      size,
      waterTop,
      waveFrequency: 1.5,
      waveAmplitude: 10.0,
      phaseOffset: math.pi / 2,
      color: const Color(0xFF00B4D8).withValues(alpha: 0.5),
      heightOffset: -2.0,
    );

    _drawWave(
      canvas,
      size,
      waterTop,
      waveFrequency: 1.1,
      waveAmplitude: 8.0,
      phaseOffset: 0.0,
      gradient: const LinearGradient(
        colors: [
          Color(0xFF00E5FF),
          Color(0xFF005FFF),
        ],
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
      ),
    );
  }

  void _drawWave(
    Canvas canvas,
    Size size,
    double waterTop, {
    required double waveFrequency,
    required double waveAmplitude,
    required double phaseOffset,
    Color? color,
    LinearGradient? gradient,
    double heightOffset = 0.0,
  }) {
    final path = Path();
    path.moveTo(0, size.height);

    for (double i = 0.0; i <= size.width; i++) {
      final waveX = (i / size.width) * waveFrequency * math.pi * 2 +
          (animationValue * math.pi * 2) +
          phaseOffset;
      final waveY = math.sin(waveX) * waveAmplitude;

      final dx = i - size.width / 2;
      final tiltY = math.tan(tiltAngle) * dx;

      double y = waterTop + waveY + tiltY + heightOffset;

      if (i == 0.0) {
        path.lineTo(0, y);
      } else {
        path.lineTo(i, y);
      }
    }

    path.lineTo(size.width, size.height);
    path.close();

    final paint = Paint()..style = PaintingStyle.fill;
    
    if (gradient != null) {
      paint.shader = gradient.createShader(
        Rect.fromLTWH(0, waterTop - waveAmplitude, size.width, size.height - waterTop + waveAmplitude),
      );
    } else if (color != null) {
      paint.color = color;
    }

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _WaterPainter oldDelegate) {
    return oldDelegate.fillPercentage != fillPercentage ||
        oldDelegate.animationValue != animationValue ||
        oldDelegate.tiltAngle != tiltAngle;
  }
}
