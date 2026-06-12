import 'package:flutter/material.dart';

import 'api/inkmoment_api.dart';
import 'api/json_utils.dart';
import 'auth/auth_gate.dart';
import 'design/stitch_components.dart';
import 'design/stitch_theme.dart';
import 'design/stitch_tokens.dart';
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
        _auth = {
          'authorized': false,
          'authenticated': false,
          'reason': 'auth_check_failed',
        };
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
      _auth = {
        'authorized': false,
        'authenticated': false,
        'reason': 'unauthenticated',
      };
      _error = error.toString();
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: Zh.appName,
      theme: buildStitchTheme(),
      home: _buildHome(),
    );
  }

  Widget _buildHome() {
    final api = _api;
    if (api == null) {
      return _BootScreen(message: _message, error: _error);
    }
    if (!_authorized) {
      return AuthGate(
        api: api,
        auth: _auth ?? emptyStringMap,
        error: _error,
        onAuthorized: _setAuth,
      );
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
    return StitchScaffold(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: StitchCard(
            padding: const EdgeInsets.all(28),
            backgroundColor: StitchColors.card,
            borderColor: StitchColors.borderSoft,
            shadows: const [BoxShadow(color: Color(0x12243527), blurRadius: 28, offset: Offset(0, 16))],
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: const [
                    StitchPill(label: Zh.appName, selected: true),
                    StitchPill(label: Zh.backend, value: Zh.connecting),
                    StitchPill(label: Zh.status, value: Zh.ready),
                  ],
                ),
                const SizedBox(height: 20),
                Text(
                  message,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: StitchColors.textPrimary,
                      ),
                ),
                const SizedBox(height: 10),
                Text(
                  Zh.operationHintText,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: StitchColors.textMuted,
                        height: 1.5,
                      ),
                ),
                if (error.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: StitchColors.warningSoft,
                      borderRadius: BorderRadius.circular(StitchRadius.md),
                      border: Border.all(color: StitchColors.warning.withValues(alpha: 0.28)),
                    ),
                    child: Text(
                      error,
                      style: const TextStyle(
                        color: StitchColors.warning,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
