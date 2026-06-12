import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../design/stitch_components.dart';
import '../design/stitch_layout.dart';
import '../design/stitch_tokens.dart';
import '../l10n/strings.dart';

class TaskSetupScreen extends StatefulWidget {
  const TaskSetupScreen({
    super.key,
    required this.api,
    required this.onStarted,
    required this.onAuthInvalid,
  });

  final InkMomentApi api;
  final ValueChanged<Map<String, dynamic>> onStarted;
  final ValueChanged<Object> onAuthInvalid;

  @override
  State<TaskSetupScreen> createState() => _TaskSetupScreenState();
}

class _TaskSetupScreenState extends State<TaskSetupScreen> {
  String _engine = 'fast';
  String _folder = '';
  Map<String, dynamic>? _peek;
  String _error = '';
  bool _busy = false;

  Future<void> _pickFolder() async {
    final path = await getDirectoryPath(confirmButtonText: Zh.chooseFolder);
    if (path == null) return;
    if (!mounted) return;
    setState(() {
      _folder = path;
      _busy = true;
      _error = '';
    });
    try {
      final peek = await widget.api.peekFolder(path);
      if (!mounted) return;
      setState(() => _peek = peek);
    } catch (error) {
      if (!mounted) return;
      if (InkMomentApi.isAuthorizationFailure(error)) {
        widget.onAuthInvalid(error);
        return;
      }
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _start() async {
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final payload = await widget.api.startJob({
        'folder': _folder,
        'mode': 'copy',
        'engine': _engine,
        'prescreen_enabled': true,
      });
      if (!mounted) return;
      widget.onStarted({...payload, 'folder': _folder});
    } catch (error) {
      if (!mounted) return;
      if (InkMomentApi.isAuthorizationFailure(error)) {
        widget.onAuthInvalid(error);
        return;
      }
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final compact = StitchLayout.compact(context);
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1280),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _hero(context),
                const SizedBox(height: 20),
                compact ? _compactLayout(context) : _desktopLayout(context),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _hero(BuildContext context) {
    final count = _peek?['count'] ?? _peek?['total'];
    return StitchCard(
      padding: const EdgeInsets.all(24),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Row(
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
            child: const Icon(Icons.photo_library_outlined, color: StitchColors.accentDeep, size: 30),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Zh.chooseModeAndFolder,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        color: StitchColors.textPrimary,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 6),
                Text(
                  Zh.folderScanHint,
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
                    StitchPill(label: Zh.mode, value: _modeText(_engine)),
                    StitchPill(label: Zh.folder, value: _folder.isEmpty ? Zh.folderNotSelected : _folder),
                    StitchPill(
                      label: Zh.status,
                      value: _busy
                          ? Zh.processing
                          : (count == null ? Zh.ready : Zh.scannedPhotos(count)),
                      color: _busy ? StitchColors.warning : StitchColors.accentDeep,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _desktopLayout(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 5,
          child: _modePanel(context),
        ),
        const SizedBox(width: 16),
        Expanded(
          flex: 6,
          child: Column(
            children: [
              _folderPanel(context),
              const SizedBox(height: 16),
              _summaryPanel(context),
            ],
          ),
        ),
      ],
    );
  }

  Widget _compactLayout(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _modePanel(context),
        const SizedBox(height: 16),
        _folderPanel(context),
        const SizedBox(height: 16),
        _summaryPanel(context),
      ],
    );
  }

  Widget _modePanel(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            Zh.mode,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: StitchColors.textPrimary,
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 6),
          Text(
            Zh.fullWorkflowDesc,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: StitchColors.textMuted,
                  height: 1.5,
                ),
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _modeCard(Zh.quickSelection, Zh.quickSelectionDesc, 'fast'),
              _modeCard(Zh.aiPrescreen, Zh.aiPrescreenDesc, 'expert'),
              _modeCard(Zh.fullWorkflow, Zh.fullWorkflowDesc, 'expert'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _folderPanel(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          StitchSectionHeader(
            eyebrow: Zh.folder,
            title: Zh.chooseFolder,
            description: Zh.folderScanHint,
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
                const Icon(Icons.folder_open_outlined, color: StitchColors.accentDeep),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    _folder.isEmpty ? Zh.folderNotSelected : _folder,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: _folder.isEmpty ? StitchColors.textMuted : StitchColors.textPrimary,
                          height: 1.45,
                        ),
                  ),
                ),
                const SizedBox(width: 12),
                OutlinedButton(
                  onPressed: _busy ? null : _pickFolder,
                  child: Text(_busy ? Zh.processing : Zh.chooseFolder),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _scanSummary(context),
          const SizedBox(height: 16),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton(
              onPressed: _folder.isEmpty || _busy ? null : _start,
              child: Text(_busy ? Zh.processing : Zh.startAnalyze),
            ),
          ),
        ],
      ),
    );
  }

  Widget _summaryPanel(BuildContext context) {
    final count = _peek?['count'] ?? _peek?['total'];
    return StitchCard(
      padding: const EdgeInsets.all(22),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x0E243527), blurRadius: 20, offset: Offset(0, 12))],
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
          const SizedBox(height: 14),
          StitchMetricCard(
            label: Zh.mode,
            value: _modeText(_engine),
          ),
          const SizedBox(height: 12),
          StitchMetricCard(
            label: Zh.folder,
            value: _folder.isEmpty ? Zh.folderNotSelected : Zh.folder,
            accent: StitchColors.accent,
          ),
          const SizedBox(height: 12),
          StitchMetricCard(
            label: Zh.noData,
            value: count == null ? Zh.ready : Zh.scannedPhotos(count),
            accent: StitchColors.winner,
          ),
          if (_error.isNotEmpty) ...[
            const SizedBox(height: 16),
            StitchWarning(message: _error),
          ],
        ],
      ),
    );
  }

  Widget _modeCard(String title, String description, String value) {
    final selected = _engine == value;
    return GestureDetector(
      onTap: _busy ? null : () => setState(() => _engine = value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        width: 234,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: selected ? StitchColors.accentSoft : StitchColors.cardGlow,
          border: Border.all(color: selected ? StitchColors.accent : StitchColors.borderSoft),
          borderRadius: BorderRadius.circular(StitchRadius.lg),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: selected ? StitchColors.accentDeep : StitchColors.textPrimary,
                    fontWeight: FontWeight.w800,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              description,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: StitchColors.textMuted,
                    height: 1.45,
                  ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _scanSummary(BuildContext context) {
    if (_peek == null) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: StitchColors.cardGlow,
          borderRadius: BorderRadius.circular(StitchRadius.lg),
          border: Border.all(color: StitchColors.borderSoft),
        ),
        child: Text(
          Zh.folderScanHint,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: StitchColors.textMuted,
                height: 1.45,
              ),
        ),
      );
    }
    final count = _peek?['count'] ?? _peek?['total'] ?? 0;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: StitchColors.cardGlow,
        borderRadius: BorderRadius.circular(StitchRadius.lg),
        border: Border.all(color: StitchColors.borderSoft),
      ),
      child: Row(
        children: [
          const Icon(Icons.photo_album_outlined, color: StitchColors.accentDeep),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              Zh.scannedPhotos(count),
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: StitchColors.textSecondary,
                    fontWeight: FontWeight.w700,
                  ),
            ),
          ),
        ],
      ),
    );
  }

  String _modeText(String value) => switch (value) {
        'fast' => Zh.quickSelection,
        'expert' => Zh.fullWorkflow,
        _ => Zh.fullWorkflow,
      };
}
