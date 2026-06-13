import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../l10n/strings.dart';

class RuntimeStatus {
  const RuntimeStatus({
    required this.ready,
    required this.message,
    this.apiBaseUrl = '',
    this.pid,
    this.error = '',
  });

  final bool ready;
  final String message;
  final String apiBaseUrl;
  final int? pid;
  final String error;
}

class SidecarController {
  final status = StreamController<RuntimeStatus>.broadcast();
  final logs = <String>[];
  Process? _process;
  String apiBaseUrl = '';

  Future<RuntimeStatus> start() async {
    final configuredBase = Platform.environment['INKMOMENT_FLUTTER_API_BASE'];
    if (configuredBase != null && configuredBase.trim().isNotEmpty) {
      apiBaseUrl = configuredBase.replaceAll(RegExp(r'/$'), '');
      final healthy = await _waitForHealth(apiBaseUrl);
      final next = RuntimeStatus(
        ready: healthy,
        message: healthy ? Zh.backendConnected : Zh.backendHealthFailed,
        apiBaseUrl: apiBaseUrl,
        error: healthy ? '' : Zh.healthEndpointUnavailable,
      );
      status.add(next);
      return next;
    }

    final python = _pythonExecutable();
    final appPath = _findAppPy();
    if (appPath == null) {
      final next = const RuntimeStatus(
        ready: false,
        message: Zh.backendStartFailed,
        error: Zh.appPyMissing,
      );
      status.add(next);
      return next;
    }

    try {
      _process = await Process.start(
        python,
        [
          appPath.path,
          '--host',
          '127.0.0.1',
          '--port',
          '0',
          '--no-browser',
          '--json-ready',
        ],
        workingDirectory: appPath.parent.path,
        environment: _sidecarEnvironment(),
      );
    } catch (error) {
      final next = RuntimeStatus(
        ready: false,
        message: Zh.backendStartFailed,
        error: error.toString(),
      );
      status.add(next);
      return next;
    }
    _process!.stderr
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen(_appendLog);
    final ready = Completer<RuntimeStatus>();
    _process!.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen((line) async {
          _appendLog(line);
          if (ready.isCompleted) return;
          final payload = _decodeReadyPayload(line);
          if (payload == null) return;
          if (payload['event'] == 'ready' && payload['port'] != null) {
            apiBaseUrl = 'http://127.0.0.1:${payload['port']}';
            final healthy = await _waitForHealth(apiBaseUrl);
            if (ready.isCompleted) return;
            ready.complete(
              RuntimeStatus(
                ready: healthy,
                message: healthy ? Zh.ready : Zh.backendHealthFailed,
                apiBaseUrl: apiBaseUrl,
                pid: payload['pid'] is int ? payload['pid'] as int : null,
                error: healthy ? '' : Zh.healthEndpointUnavailable,
              ),
            );
          }
        });

    final next = await ready.future.timeout(
      const Duration(seconds: 60),
      onTimeout: () => const RuntimeStatus(
        ready: false,
        message: Zh.backendStartTimeout,
        error: Zh.readyJsonTimeout,
      ),
    );
    status.add(next);
    return next;
  }

  void dispose() {
    _process?.kill();
    _process = null;
    status.close();
  }

  void _appendLog(String line) {
    if (line.trim().isEmpty) return;
    logs.add(line);
    if (logs.length > 300) logs.removeAt(0);
  }

  Map<String, dynamic>? _decodeReadyPayload(String line) {
    try {
      final payload = jsonDecode(line);
      return payload is Map<String, dynamic> ? payload : null;
    } on FormatException {
      return null;
    }
  }

  Future<bool> _waitForHealth(String baseUrl) async {
    final client = HttpClient();
    final deadline = DateTime.now().add(const Duration(seconds: 20));
    try {
      while (DateTime.now().isBefore(deadline)) {
        try {
          final request = await client.getUrl(Uri.parse('$baseUrl/api/health'));
          final response = await request.close();
          await response.drain();
          if (response.statusCode >= 200 && response.statusCode < 300) {
            return true;
          }
        } catch (error) {
          _appendLog(Zh.healthCheckWaiting(error));
        }
        await Future<void>.delayed(const Duration(milliseconds: 350));
      }
      return false;
    } finally {
      client.close(force: true);
    }
  }

  String _pythonExecutable() {
    final configured = Platform.environment['INKMOMENT_PYTHON'];
    if (configured != null && configured.isNotEmpty) return configured;
    final local = File('../.venv/bin/python');
    if (local.existsSync()) return local.path;
    return Platform.isWindows ? 'python' : 'python3';
  }

  File? _findAppPy() {
    for (final candidate in [
      File('../app.py'),
      File('app.py'),
      File('../../app.py'),
    ]) {
      if (candidate.existsSync()) return candidate.absolute;
    }
    return null;
  }

  Map<String, String> _sidecarEnvironment() {
    final env = Map<String, String>.from(Platform.environment);
    final authUrl = env['INKMOMENT_AUTH_SERVER_URL'];
    if (authUrl != null && authUrl.trim().isNotEmpty) {
      env['INKMOMENT_AUTH_SERVER_URL'] = authUrl.trim();
    }
    return env;
  }
}
