import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../l10n/strings.dart';

class ExportScreen extends StatefulWidget {
  const ExportScreen({
    super.key,
    required this.api,
    required this.onNewTask,
    required this.onAuthInvalid,
  });

  final InkMomentApi api;
  final VoidCallback onNewTask;
  final ValueChanged<Object> onAuthInvalid;

  @override
  State<ExportScreen> createState() => _ExportScreenState();
}

class _ExportScreenState extends State<ExportScreen> {
  String _format = 'jpeg';
  double _quality = 92;
  Map<String, dynamic>? _preview;
  Map<String, dynamic>? _status;
  String _error = '';
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _previewExport() async {
    try {
      final payload = await widget.api.previewExport(_payload());
      if (!mounted) return;
      setState(() {
        _preview = payload;
        _error = '';
      });
    } catch (error) {
      _handleError(error);
    }
  }

  Future<void> _startExport() async {
    try {
      await widget.api.startExport(_payload());
      await _pollStatus();
      if (!mounted) return;
      _timer?.cancel();
      _timer = Timer.periodic(const Duration(seconds: 1), (_) => _pollStatus());
    } catch (error) {
      _handleError(error);
    }
  }

  Future<void> _pollStatus() async {
    try {
      final status = await widget.api.exportStatus();
      if (!mounted) return;
      setState(() {
        _status = status;
        _error = '';
      });
      if (status['status'] != 'running') _timer?.cancel();
    } catch (error) {
      _handleError(error);
    }
  }

  Future<void> _cancelExport() async {
    try {
      await widget.api.cancelExport();
      await _pollStatus();
    } catch (error) {
      _handleError(error);
    }
  }

  Future<void> _openOutput() async {
    try {
      await widget.api.openExportOutDir();
    } catch (error) {
      _handleError(error);
    }
  }

  void _handleError(Object error) {
    if (!mounted) return;
    if (InkMomentApi.isAuthorizationFailure(error)) {
      widget.onAuthInvalid(error);
      return;
    }
    setState(() => _error = error.toString());
  }

  Map<String, dynamic> _payload() => {
        'format': _format,
        'quality': _quality.round(),
        'naming_pattern': '{stem}',
        'conflict_strategy': 'rename',
        'watermark': {
          'enabled': true,
          'template': 'A',
          'text': 'InkMoment',
          'position': {'x': 0.82, 'y': 0.90},
        },
      };

  @override
  Widget build(BuildContext context) {
    final preview = _preview?['image_b64']?.toString();
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('导出胜出照片', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        const SizedBox(height: 16),
        Row(children: [
          DropdownButton<String>(
            value: _format,
            items: const [
              DropdownMenuItem(value: 'jpeg', child: Text('JPEG')),
              DropdownMenuItem(value: 'tiff', child: Text('TIFF')),
              DropdownMenuItem(value: 'original', child: Text('原始文件')),
            ],
            onChanged: (value) => setState(() => _format = value ?? 'jpeg'),
          ),
          const SizedBox(width: 18),
          const Text('质量'),
          Expanded(child: Slider(value: _quality, min: 1, max: 100, divisions: 99, label: _quality.round().toString(), onChanged: (value) => setState(() => _quality = value))),
        ]),
        const SizedBox(height: 12),
        Expanded(
          child: Center(
            child: preview == null
                ? const Text('点击预览后显示水印效果')
                : Image.memory(base64Decode(preview), fit: BoxFit.contain),
          ),
        ),
        if (_status != null) Text('导出状态：${_statusLabel(_status?['status'])}  ${_status?['done'] ?? 0}/${_status?['total'] ?? 0}'),
        if (_error.isNotEmpty) Text(_error, style: const TextStyle(color: Color(0xFFFFB95F))),
        Wrap(spacing: 10, children: [
          OutlinedButton(onPressed: _previewExport, child: const Text('预览导出')),
          FilledButton(onPressed: _startExport, child: const Text(Zh.startExport)),
          OutlinedButton(onPressed: _cancelExport, child: const Text('取消导出')),
          OutlinedButton(onPressed: _openOutput, child: const Text(Zh.openOutput)),
          OutlinedButton(onPressed: widget.onNewTask, child: const Text(Zh.newTask)),
        ]),
      ]),
    );
  }

  String _statusLabel(Object? status) => switch (status?.toString()) {
        'idle' => '空闲',
        'running' => '导出中',
        'done' => '已完成',
        'cancelled' => '已取消',
        'error' => '失败',
        _ => '未知',
      };
}
