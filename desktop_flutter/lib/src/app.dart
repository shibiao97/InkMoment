import 'package:flutter/material.dart';

import 'api/inkmoment_api.dart';
import 'api/json_utils.dart';
import 'auth/auth_gate.dart';
import 'l10n/strings.dart';
import 'runtime/sidecar_controller.dart';
import 'workflow/workflow_shell.dart';

class InkMomentDesktopApp extends StatefulWidget {
  const InkMomentDesktopApp({super.key});

  @override
  State<InkMomentDesktopApp> createState() => _InkMomentDesktopAppState();
}

class _InkMomentDesktopAppState extends State<InkMomentDesktopApp> {
  final _runtime = SidecarController();
  InkMomentApi? _api;
  Map<String, dynamic>? _auth;
  String _message = Zh.booting;
  String _error = '';

  bool get _authorized => _auth?['authorized'] == true;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  @override
  void dispose() {
    _runtime.dispose();
    super.dispose();
  }

  Future<void> _boot() async {
    final status = await _runtime.start();
    if (!mounted) return;
    if (!status.ready) {
      setState(() {
        _message = status.message;
        _error = status.error;
      });
      return;
    }
    final api = InkMomentApi(status.apiBaseUrl);
    try {
      final auth = await api.authStatus(force: true);
      if (!mounted) return;
      setState(() {
        _api = api;
        _auth = auth;
        _message = status.message;
        _error = '';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _api = api;
        _auth = {'authorized': false, 'authenticated': false, 'reason': 'auth_check_failed'};
        _error = error.toString();
      });
    }
  }

  void _setAuth(Map<String, dynamic> auth) {
    setState(() {
      _auth = auth;
      _error = '';
    });
  }

  void _markUnauthorized(Object error) {
    setState(() {
      _auth = {'authorized': false, 'authenticated': false, 'reason': 'unauthenticated'};
      _error = error.toString();
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: Zh.appName,
      theme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF10B981),
          brightness: Brightness.dark,
          surface: const Color(0xFF161D19),
        ),
        scaffoldBackgroundColor: const Color(0xFF0E1511),
        useMaterial3: true,
      ),
      home: _buildHome(),
    );
  }

  Widget _buildHome() {
    final api = _api;
    if (api == null) {
      return _BootScreen(message: _message, error: _error);
    }
    if (!_authorized) {
      return AuthGate(api: api, auth: _auth ?? emptyStringMap, error: _error, onAuthorized: _setAuth);
    }
    return WorkflowShell(
      api: api,
      auth: _auth ?? emptyStringMap,
      runtime: _runtime,
      onAuthInvalid: _markUnauthorized,
      onAuthChanged: _setAuth,
    );
  }
}

class _BootScreen extends StatelessWidget {
  const _BootScreen({required this.message, required this.error});

  final String message;
  final String error;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Container(
          width: 420,
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            border: Border.all(color: const Color(0xFF2F3632)),
            borderRadius: BorderRadius.circular(8),
            color: const Color(0xFF161D19),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(Zh.appName, style: TextStyle(fontSize: 13, color: Color(0xFF4EDEA3))),
              const SizedBox(height: 8),
              Text(message, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
              if (error.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text(error, style: const TextStyle(color: Color(0xFFFFB95F))),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
