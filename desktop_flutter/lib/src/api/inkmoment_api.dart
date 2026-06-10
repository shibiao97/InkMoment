import 'dart:convert';
import 'dart:io';

class InkMomentApi {
  InkMomentApi(this.baseUrl);

  final String baseUrl;
  final _client = HttpClient();

  static const _authorizationCodes = {
    'unauthenticated',
    'expired',
    'revoked',
    'device_mismatch',
    'not_activated',
    'auth_server_not_configured',
    'auth_server_unavailable',
    'auth_not_configured',
  };

  Future<Map<String, dynamic>> getJson(String path) async {
    return _send('GET', path);
  }

  Future<Map<String, dynamic>> postJson(String path, [Map<String, dynamic>? body]) async {
    return _send('POST', path, body);
  }

  Future<Map<String, dynamic>> _send(String method, String path, [Map<String, dynamic>? body]) async {
    final request = await _client.openUrl(method, Uri.parse('$baseUrl$path'));
    request.headers.contentType = ContentType.json;
    if (body != null) request.write(jsonEncode(body));
    final response = await request.close();
    final text = await utf8.decodeStream(response);
    final data = text.isEmpty ? <String, dynamic>{} : jsonDecode(text) as Map<String, dynamic>;
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(
        data['error']?.toString() ?? '请求失败',
        code: data['code']?.toString() ?? '',
        status: response.statusCode,
      );
    }
    return data;
  }

  Future<Map<String, dynamic>> authStatus({bool force = false}) => getJson('/api/auth/status${force ? '?force=1' : ''}');
  Future<Map<String, dynamic>> login(String email, String password) => postJson('/api/auth/login', {'email': email, 'password': password});
  Future<Map<String, dynamic>> register(String email, String password, String name) => postJson('/api/auth/register', {'email': email, 'password': password, 'display_name': name});
  Future<Map<String, dynamic>> redeem(String code) => postJson('/api/auth/redeem', {'code': code});
  Future<Map<String, dynamic>> logout() => postJson('/api/auth/logout');
  Future<Map<String, dynamic>> unbindDevice(String reason) => postJson('/api/auth/device/unbind', {'confirm_penalty': true, 'reason': reason});
  Future<Map<String, dynamic>> peekFolder(String folder) => postJson('/api/peek_folder', {'folder': folder});
  Future<Map<String, dynamic>> startJob(Map<String, dynamic> payload) => postJson('/api/start', payload);
  Future<Map<String, dynamic>> getJob() => getJson('/api/job');
  Future<Map<String, dynamic>> cancelJob() => postJson('/api/cancel_job');
  Future<Map<String, dynamic>> getStatus() => getJson('/api/status');
  Future<Map<String, dynamic>> getAutoRejected() => getJson('/api/auto_rejected');
  Future<Map<String, dynamic>> confirmPrescreen() => postJson('/api/confirm_prescreen');
  Future<Map<String, dynamic>> getPreviewGroups() => getJson('/api/preview_groups');
  Future<Map<String, dynamic>> getGroup() => getJson('/api/group');
  Future<Map<String, dynamic>> choose(String loser) => postJson('/api/choose', {'loser': loser});
  Future<Map<String, dynamic>> skipGroup() => postJson('/api/skip_group');
  Future<Map<String, dynamic>> undo() => postJson('/api/undo');
  Future<Map<String, dynamic>> getWinners() => getJson('/api/winners');
  Future<Map<String, dynamic>> previewExport(Map<String, dynamic> payload) => postJson('/api/export/preview', payload);
  Future<Map<String, dynamic>> startExport(Map<String, dynamic> payload) => postJson('/api/export/start', payload);
  Future<Map<String, dynamic>> exportStatus() => getJson('/api/export/status');
  Future<Map<String, dynamic>> cancelExport() => postJson('/api/export/cancel');
  Future<Map<String, dynamic>> openExportOutDir() => postJson('/api/export/open_out_dir');

  String imageUrl(Object? path, {int width = 1200}) {
    final value = path?.toString() ?? '';
    if (value.isEmpty) return '';
    final query = Uri(queryParameters: {'path': value, 'w': width.toString()}).query;
    return '$baseUrl/api/image?$query';
  }

  static bool isAuthorizationFailure(Object error) {
    if (error is! ApiException) return false;
    if (error.status == 401) return true;
    return _authorizationCodes.contains(error.code);
  }
}

class ApiException implements Exception {
  ApiException(this.message, {this.code = '', this.status = 0});
  final String message;
  final String code;
  final int status;

  @override
  String toString() => message;
}
