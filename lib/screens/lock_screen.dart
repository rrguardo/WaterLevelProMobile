import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';

class LockScreen extends StatefulWidget {
  const LockScreen({super.key});

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _authenticate());
  }

  Future<void> _authenticate() async {
    final auth = Provider.of<AuthProvider>(context, listen: false);
    final success = await auth.authenticateBiometric();
    if (!mounted) return;
    if (success) {
      await auth.onBiometricSuccess();
    }
  }

  Future<void> _fallbackToPassword() async {
    final email = await Provider.of<AuthProvider>(context, listen: false).getSavedEmail();
    if (!mounted) return;
    final passCtrl = TextEditingController();
    final password = await showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.grey[900],
        title: Text('Enter Password', style: TextStyle(color: Colors.white)),
        content: TextField(
          controller: passCtrl,
          obscureText: true,
          style: TextStyle(color: Colors.white),
          decoration: InputDecoration(
            hintText: email ?? 'Password',
            hintStyle: TextStyle(color: Colors.grey),
            enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.grey)),
            focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.blueAccent)),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text('Cancel', style: TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, passCtrl.text),
            child: Text('Unlock', style: TextStyle(color: Colors.blueAccent)),
          ),
        ],
      ),
    );
    if (password != null && password.isNotEmpty && mounted) {
      final auth = Provider.of<AuthProvider>(context, listen: false);
      await auth.onBiometricSuccess();
    } else if (mounted) {
      _authenticate();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.lock_outline, size: 64, color: Colors.blueAccent),
            SizedBox(height: 24),
            Text(
              'WaterLevel.Pro',
              style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 16),
            Text(
              'Authenticate to continue',
              style: TextStyle(color: Colors.grey, fontSize: 14),
            ),
            SizedBox(height: 32),
            CircularProgressIndicator(color: Colors.blueAccent),
            SizedBox(height: 32),
            TextButton(
              onPressed: _fallbackToPassword,
              child: Text('Use password instead', style: TextStyle(color: Colors.grey[400])),
            ),
          ],
        ),
      ),
    );
  }
}
