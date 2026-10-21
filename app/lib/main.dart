import 'package:flutter/material.dart';

import 'device_screen.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const PcFlashApp());
}

class PcFlashApp extends StatelessWidget {
  const PcFlashApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PhoneCtl Flash',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.build(),
      home: const DeviceScreen(),
    );
  }
}
