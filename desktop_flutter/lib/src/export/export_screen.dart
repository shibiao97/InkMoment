import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../design/stitch_components.dart';
import '../design/stitch_layout.dart';
import '../design/stitch_tokens.dart';
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
    final compact = StitchLayout.compact(context);
    final preview = _preview?['image_b64']?.toString();
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1300),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _hero(context),
                const SizedBox(height: 20),
                compact ? _compactLayout(context, preview) : _desktopLayout(context, preview),
                const SizedBox(height: 18),
                if (_error.isNotEmpty) ...[
                  StitchWarning(message: _error),
                  const SizedBox(height: 18),
                ],
                _actionBar(context),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _hero(BuildContext context) {
    final status = _status?['status'];
    final done = _status?['done'] ?? 0;
    final total = _status?['total'] ?? 0;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
          Container(
            width: 60,
            height: 60,
            decoration: BoxDecoration(
              color: StitchColors.accentSoft,
              borderRadius: BorderRadius.circular(StitchRadius.lg),
              border: Border.all(color: StitchColors.borderSoft),
            ),
            child: const Icon(Icons.outbox_outlined, color: StitchColors.accentDeep, size: 30),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Zh.exportWinners,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        color: StitchColors.textPrimary,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 6),
                Text(
                  Zh.previewWatermarkHint,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: StitchColors.textMuted,
                        height: 1.5,
                      ),
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    StitchPill(label: Zh.formatLabel, value: _formatText(_format)),
                    StitchPill(label: Zh.quality, value: _quality.round().toString()),
                    StitchPill(
                      label: Zh.status,
                      value: Zh.statusLabel(status),
                      color: status == 'running' ? StitchColors.winner : StitchColors.accentDeep,
                    ),
                    StitchPill(label: Zh.noData, value: '$done / $total'),
                  ],
                ),
              ],
            ),
          ),
        ],
      );
  }

  Widget _desktopLayout(BuildContext context, String? preview) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 5,
          child: _settingsCard(context),
        ),
        const SizedBox(width: 16),
        Expanded(
          flex: 7,
          child: Column(
            children: [
              _previewCard(context, preview),
              const SizedBox(height: 16),
              _statusCard(context),
            ],
          ),
        ),
      ],
    );
  }

  Widget _compactLayout(BuildContext context, String? preview) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _settingsCard(context),
        const SizedBox(height: 16),
        _previewCard(context, preview),
        const SizedBox(height: 16),
        _statusCard(context),
      ],
    );
  }

  Widget _settingsCard(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.md,
      shadows: const [],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          StitchSectionHeader(
            eyebrow: Zh.export,
            title: Zh.exportWinners,
            description: Zh.operationHintText,
          ),
          const SizedBox(height: 18),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: StitchColors.cardGlow,
              borderRadius: BorderRadius.circular(StitchRadius.lg),
              border: Border.all(color: StitchColors.borderSoft),
            ),
            child: Row(
              children: [
                Text(
                  Zh.originalFile,
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        color: StitchColors.textPrimary,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const Spacer(),
                DropdownButton<String>(
                  value: _format,
                  items: const [
                    DropdownMenuItem(value: 'jpeg', child: Text('JPEG')),
                    DropdownMenuItem(value: 'tiff', child: Text('TIFF')),
                    DropdownMenuItem(value: 'original', child: Text(Zh.originalFile)),
                  ],
                  onChanged: (value) => setState(() => _format = value ?? 'jpeg'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: StitchColors.cardGlow,
              borderRadius: BorderRadius.circular(StitchRadius.lg),
              border: Border.all(color: StitchColors.borderSoft),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      Zh.quality,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            color: StitchColors.textPrimary,
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const Spacer(),
                    Text(
                      _quality.round().toString(),
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            color: StitchColors.accentDeep,
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                  ],
                ),
                Slider(
                  value: _quality,
                  min: 1,
                  max: 100,
                  divisions: 99,
                  onChanged: (value) => setState(() => _quality = value),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          StitchWarning(message: Zh.previewWatermarkHint),
        ],
      ),
    );
  }

  Widget _previewCard(BuildContext context, String? preview) {
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.md,
      shadows: const [],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          StitchSectionHeader(
            eyebrow: Zh.previewExport,
            title: Zh.previewWatermarkHint,
            description: Zh.operationHintText,
          ),
          const SizedBox(height: 18),
          AspectRatio(
            aspectRatio: 4 / 3,
            child: Container(
              decoration: BoxDecoration(
                color: StitchColors.cardGlow,
                borderRadius: BorderRadius.circular(StitchRadius.lg),
                border: Border.all(color: StitchColors.borderSoft),
              ),
              child: Center(
                child: preview == null
                    ? const StitchEmptyState(message: Zh.previewWatermarkHint)
                    : ClipRRect(
                        borderRadius: BorderRadius.circular(StitchRadius.lg),
                        child: Image.memory(base64Decode(preview), fit: BoxFit.contain),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusCard(BuildContext context) {
    final status = _status?['status'];
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.md,
      shadows: const [],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            Zh.status,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: StitchColors.textPrimary,
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 12),
          StitchMetricCard(
            label: Zh.status,
            value: Zh.statusLabel(status),
            accent: StitchColors.accentDeep,
          ),
          const SizedBox(height: 12),
          StitchMetricCard(
            label: Zh.exportStatusLine(status, _status?['done'] ?? 0, _status?['total'] ?? 0),
            value: '${_status?['done'] ?? 0}/${_status?['total'] ?? 0}',
            accent: StitchColors.winner,
          ),
          if (_status != null) ...[
            const SizedBox(height: 12),
            Text(
              Zh.exportStatusLine(status, _status?['done'] ?? 0, _status?['total'] ?? 0),
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: StitchColors.textSecondary,
                    fontWeight: FontWeight.w700,
                  ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _actionBar(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(16),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [],
      child: Wrap(
        spacing: 10,
        runSpacing: 10,
        alignment: WrapAlignment.end,
        children: [
          OutlinedButton(
            onPressed: _previewExport,
            child: const Text(Zh.previewExport),
          ),
          FilledButton(
            onPressed: _startExport,
            child: const Text(Zh.startExport),
          ),
          OutlinedButton(
            onPressed: _cancelExport,
            child: const Text(Zh.cancelExport),
          ),
          OutlinedButton(
            onPressed: _openOutput,
            child: const Text(Zh.openOutput),
          ),
          OutlinedButton(
            onPressed: widget.onNewTask,
            child: const Text(Zh.newTask),
          ),
        ],
      ),
    );
  }

  String _formatText(String value) => switch (value) {
        'jpeg' => 'JPEG',
        'tiff' => 'TIFF',
        'original' => Zh.originalFile,
        _ => value.toUpperCase(),
      };
}
