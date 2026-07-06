import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/inkmoment_api.dart';
import '../analysis/analysis_screen.dart';
import '../arena/arena_screen.dart';
import '../design/stitch_components.dart';
import '../design/stitch_layout.dart';
import '../design/stitch_tokens.dart';
import '../export/export_screen.dart';
import '../l10n/strings.dart';
import '../review/review_screen.dart';
import '../runtime/sidecar_controller.dart';
import '../task/task_setup_screen.dart';
import 'workflow_state.dart';

class WorkflowShell extends StatefulWidget {
  const WorkflowShell({
    super.key,
    required this.api,
    required this.auth,
    required this.runtime,
    required this.onAuthInvalid,
    required this.onAuthChanged,
  });

  final InkMomentApi api;
  final Map<String, dynamic> auth;
  final SidecarController runtime;
  final ValueChanged<Object> onAuthInvalid;
  final ValueChanged<Map<String, dynamic>> onAuthChanged;

  @override
  State<WorkflowShell> createState() => _WorkflowShellState();
}

class _WorkflowShellState extends State<WorkflowShell> {
  WorkflowStep _step = WorkflowStep.modeFolder;
  String _summary = Zh.quickSelection;
  String _engineValue = 'fast';   // 实际 engine 字符串
  String _folder = '';             // 已选照片文件夹
  String _message = '';
  bool _checking = false;

  void _go(WorkflowStep step, [String? summary]) {
    setState(() {
      _step = step;
      if (summary != null && summary.isNotEmpty) _summary = summary;
    });
  }

  void _resetTask() {
    setState(() {
      _step = WorkflowStep.modeFolder;
      _summary = Zh.quickSelection;
      _engineValue = 'fast';
      _folder = '';
      _message = '';
    });
  }

  void _handleWorkflowError(Object error) {
    if (!mounted) return;
    if (InkMomentApi.isAuthorizationFailure(error)) {
      widget.onAuthInvalid(error);
      return;
    }
    setState(() => _message = error.toString());
  }

  Future<void> _checkMode() async {
    if (_checking) return;
    setState(() { _checking = true; _message = '检查中…'; });
    try {
      final result = await widget.api.depPreflight({
        'engine': _engineValue,
        'folder': _folder,
        'include_folder': false,
      });
      if (!mounted) return;
      final missing = (result['missing'] as List?) ?? [];
      final warnings = (result['warnings'] as List?) ?? [];
      if (missing.isEmpty) {
        setState(() => _message = '模式：$_summary\n依赖：全部就绪 ✓');
      } else {
        final items = missing.map((m) {
          final label = m['label']?.toString() ?? '';
          final detail = m['detail']?.toString() ?? '';
          return '$label：$detail';
        }).join('\n');
        setState(() => _message = '模式：$_summary\n缺失依赖：\n$items');
      }
      if (warnings.isNotEmpty) {
        final w = warnings.map((e) => e.toString()).join('\n');
        setState(() => _message = '$_message\n警告：$w');
      }
    } catch (error) {
      _handleWorkflowError(error);
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _checkResource() async {
    if (_checking) return;
    setState(() { _checking = true; _message = '检查资源中…'; });
    try {
      final result = await widget.api.depPreflight({
        'engine': _engineValue,
        'folder': _folder,
        'include_folder': false,
      });
      if (!mounted) return;
      final missing = (result['missing'] as List?) ?? [];
      final autoFixable = missing.where((m) => m['downloadable'] == true || m['repairable'] == true).toList();

      if (missing.isEmpty) {
        setState(() => _message = '资源检查：全部就绪 ✓\n无需下载');
        return;
      }

      if (autoFixable.isEmpty) {
        setState(() => _message = '缺失依赖：\n${_formatMissing(missing)}\n需重新打包完整依赖或手动处理，无法自动下载。');
        return;
      }

      setState(() => _message = '发现 ${autoFixable.length} 项可处理依赖，正在启动下载…');
      await widget.api.depDownload({'engine': _engineValue});
      if (!mounted) return;
      final status = await showDialog<Map<String, dynamic>>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _DependencyDownloadDialog(api: widget.api),
      );
      if (!mounted) return;
      if (status?['status'] == 'cancelled') {
        setState(() => _message = status?['message']?.toString() ?? '已停止资源下载');
        return;
      }
      if (status?['status'] == 'error') {
        setState(() => _message = '资源下载失败：${status?['error'] ?? status?['message'] ?? ''}');
        return;
      }
      final after = await widget.api.depPreflight({
        'engine': _engineValue,
        'folder': _folder,
        'include_folder': false,
      });
      if (!mounted) return;
      final remaining = (after['missing'] as List?) ?? [];
      setState(() {
        _message = remaining.isEmpty
            ? '资源检查：全部就绪 ✓'
            : '下载完成，但仍缺失：\n${_formatMissing(remaining)}\n这些不是模型下载能解决的资源。';
      });
    } catch (error) {
      _handleWorkflowError(error);
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  String _formatMissing(List missing) {
    return missing.map((m) {
      final label = m['label']?.toString() ?? '';
      final detail = m['detail']?.toString() ?? '';
      return detail.isEmpty ? label : '$label：$detail';
    }).join('\n');
  }

  Future<void> _copyCheckResult() async {
    final text = _message.isNotEmpty ? _message : '暂无检查结果';
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('已复制到剪贴板'), duration: Duration(seconds: 2)),
    );
  }

  Future<void> _refreshAuth() async {
    try {
      final auth = await widget.api.authStatus(force: true);
      if (!mounted) return;
      widget.onAuthChanged(auth);
      setState(() => _message = Zh.authRefreshed);
    } catch (error) {
      _handleWorkflowError(error);
    }
  }

  Future<void> _logout() async {
    try {
      await widget.api.logout();
      if (!mounted) return;
      widget.onAuthChanged(const {
        'authorized': false,
        'authenticated': false,
        'reason': 'unauthenticated',
      });
    } catch (error) {
      _handleWorkflowError(error);
    }
  }

  bool get _authorized => widget.auth['authorized'] == true;

  @override
  Widget build(BuildContext context) {
    final compact = StitchLayout.compact(context);
    return Scaffold(
      body: StitchScaffold(
        padding: const EdgeInsets.all(24),
        child: compact ? _compactLayout(context) : _desktopLayout(context),
      ),
    );
  }

  Widget _desktopLayout(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _LeftRail(summary: _summary, folder: _folder, step: _step, onReset: _resetTask),
        const SizedBox(width: 24),
        Expanded(child: _screen()),
        const SizedBox(width: 24),
        _RightInspector(
          step: _step,
          auth: widget.auth,
          runtime: widget.runtime,
          message: _message,
          checking: _checking,
          authorized: _authorized,
          summary: _summary,
          folder: _folder,
          onCheckMode: _checkMode,
          onCheckResource: _checkResource,
          onCopyResult: _copyCheckResult,
          onRefreshAuth: _refreshAuth,
          onLogout: _logout,
        ),
      ],
    );
  }

  Widget _compactLayout(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _LeftRail(summary: _summary, folder: _folder, step: _step, onReset: _resetTask, compact: true),
          const SizedBox(height: 18),
          _screen(),
          const SizedBox(height: 18),
          _RightInspector(
            step: _step,
            auth: widget.auth,
            runtime: widget.runtime,
            message: _message,
            checking: _checking,
            authorized: _authorized,
            summary: _summary,
            folder: _folder,
            onCheckMode: _checkMode,
            onCheckResource: _checkResource,
            onCopyResult: _copyCheckResult,
            onRefreshAuth: _refreshAuth,
            onLogout: _logout,
            compact: true,
          ),
        ],
      ),
    );
  }

  Widget _screen() => switch (_step) {
    WorkflowStep.modeFolder => TaskSetupScreen(
      api: widget.api,
      onSelectionChanged: (payload) {
        setState(() {
          _engineValue = payload['engine']?.toString() ?? 'fast';
          _summary = payload['engine_label']?.toString() ?? Zh.quickSelection;
          _folder = payload['folder']?.toString() ?? _folder;
          _message = '';
        });
      },
      onStarted: (payload) {
        setState(() {
          _engineValue = payload['engine']?.toString() ?? 'fast';
          _folder = payload['folder']?.toString() ?? '';
        });
        _go(
          WorkflowStep.analyze,
          payload['engine_label']?.toString() ?? Zh.quickSelection,
        );
      },
      onAuthInvalid: widget.onAuthInvalid,
    ),
    WorkflowStep.analyze => AnalysisScreen(
      api: widget.api,
      onReview: () => _go(WorkflowStep.review),
      onAuthInvalid: widget.onAuthInvalid,
    ),
    WorkflowStep.review => ReviewScreen(
      api: widget.api,
      onSelect: () => _go(WorkflowStep.select),
      onAuthInvalid: widget.onAuthInvalid,
    ),
    WorkflowStep.select => ArenaScreen(
      api: widget.api,
      onExport: () => _go(WorkflowStep.export),
      onAuthInvalid: widget.onAuthInvalid,
    ),
    WorkflowStep.export => ExportScreen(
      api: widget.api,
      onBackToSelect: () => _go(WorkflowStep.select),
      onNewTask: _resetTask,
      onAuthInvalid: widget.onAuthInvalid,
    ),
  };
}

class _LeftRail extends StatelessWidget {
  const _LeftRail({
    required this.summary,
    required this.folder,
    required this.step,
    required this.onReset,
    this.compact = false,
  });

  final String summary;
  final String folder;
  final WorkflowStep step;
  final VoidCallback onReset;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: compact ? double.infinity : StitchLayout.leftRailWidth,
      child: StitchCard(
        padding: const EdgeInsets.all(26),
        backgroundColor: StitchColors.card,
        borderColor: StitchColors.borderSoft,
        radius: StitchRadius.lg,
        shadows: StitchShadow.soft,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _BrandBlock(compact: compact),
            const SizedBox(height: 42),
            if (compact)
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final item in WorkflowStep.values) _CompactStepChip(step: item, selected: item == step),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text('$summary · ${folder.isEmpty ? Zh.folderNotSelected : folder}', style: StitchTextStyles.muted),
                  if (step != WorkflowStep.modeFolder) ...[
                    const SizedBox(height: 10),
                    OutlinedButton.icon(
                      onPressed: onReset,
                      icon: const Icon(Icons.arrow_back_rounded, size: 16),
                      label: const Text('重新选择模式/文件夹'),
                    ),
                  ],
                ],
              )
            else
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final item in WorkflowStep.values) ...[
                      _StepRailItem(step: item, selected: item == step),
                      if (item != WorkflowStep.export) const SizedBox(height: 18),
                    ],
                    const Spacer(),
                    Container(height: 1, color: StitchColors.borderSoft),
                    const SizedBox(height: 22),
                    Text(Zh.taskSummary, style: StitchTextStyles.muted),
                    const SizedBox(height: 8),
                    Text(summary, style: StitchTextStyles.sectionTitle),
                    const SizedBox(height: 8),
                    Text(
                      folder.isEmpty ? Zh.folderNotSelected : folder,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: StitchTextStyles.muted,
                    ),
                    if (step != WorkflowStep.modeFolder) ...[
                      const SizedBox(height: 14),
                      OutlinedButton.icon(
                        onPressed: onReset,
                        icon: const Icon(Icons.arrow_back_rounded, size: 16),
                        label: const Text('重新选择模式/文件夹'),
                      ),
                    ],
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _BrandBlock extends StatelessWidget {
  const _BrandBlock({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: compact ? MainAxisSize.min : MainAxisSize.max,
      children: [
        Container(
          width: 58,
          height: 58,
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [StitchColors.warmBackground, StitchColors.accentDeep],
            ),
            borderRadius: BorderRadius.circular(StitchRadius.md),
          ),
        ),
        const SizedBox(width: 14),
        const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(Zh.appDisplayName, style: StitchTextStyles.brandTitle),
            SizedBox(height: 4),
            Text(Zh.localPrivateRun, style: StitchTextStyles.muted),
          ],
        ),
      ],
    );
  }
}

class _StepRailItem extends StatelessWidget {
  const _StepRailItem({required this.step, required this.selected});

  final WorkflowStep step;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      decoration: BoxDecoration(
        color: selected ? StitchColors.accentSoft : Colors.transparent,
        borderRadius: BorderRadius.circular(StitchRadius.sm),
        border: Border(left: BorderSide(color: selected ? StitchColors.accentDeep : Colors.transparent, width: 5)),
      ),
      child: Text(
        step.label,
        style: TextStyle(
          color: selected ? StitchColors.textPrimary : StitchColors.textSecondary,
          fontWeight: selected ? FontWeight.w800 : FontWeight.w500,
          fontSize: 17,
        ),
      ),
    );
  }
}

class _CompactStepChip extends StatelessWidget {
  const _CompactStepChip({required this.step, required this.selected});

  final WorkflowStep step;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return StitchPill(label: step.label, selected: selected);
  }
}

class _RightInspector extends StatelessWidget {
  const _RightInspector({
    required this.step,
    required this.auth,
    required this.runtime,
    required this.message,
    required this.checking,
    required this.authorized,
    required this.summary,
    required this.folder,
    required this.onCheckMode,
    required this.onCheckResource,
    required this.onCopyResult,
    required this.onRefreshAuth,
    required this.onLogout,
    this.compact = false,
  });

  final WorkflowStep step;
  final Map<String, dynamic> auth;
  final SidecarController runtime;
  final String message;
  final bool checking;
  final bool authorized;
  final String summary;
  final String folder;
  final VoidCallback onCheckMode;
  final VoidCallback onCheckResource;
  final VoidCallback onCopyResult;
  final VoidCallback onRefreshAuth;
  final VoidCallback onLogout;
  final bool compact;

  void _showLogs(BuildContext context) {
    final logs = runtime.logs;
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('${Zh.logs}（${logs.length} ${Zh.logUnit}）'),
        content: SizedBox(
          width: 560,
          height: 400,
          child: logs.isEmpty
              ? const Center(child: Text('暂无日志'))
              : ListView.separated(
                  itemCount: logs.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
                    child: SelectableText(
                      logs[i],
                      style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                    ),
                  ),
                ),
        ),
        actions: [
          TextButton(
            onPressed: () => Clipboard.setData(ClipboardData(text: logs.join('\n'))),
            child: const Text('复制全部'),
          ),
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('关闭')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final children = [
      Align(
        alignment: Alignment.centerRight,
        child: _AuthBadge(authorized: authorized),
      ),
      const SizedBox(height: 18),
      _InspectorCard(label: Zh.mode, value: summary, highlighted: true),
      if (folder.isNotEmpty) ...[
        const SizedBox(height: 12),
        _InspectorCard(label: Zh.photoFolder, value: folder),
      ],
      const SizedBox(height: 12),
      _InspectorCard(
        label: Zh.runtimeResource,
        value: runtime.apiBaseUrl.isEmpty ? Zh.pendingCheck : Zh.ready,
      ),
      if (message.isNotEmpty) ...[
        const SizedBox(height: 12),
        StitchCard(
          padding: const EdgeInsets.all(14),
          backgroundColor: StitchColors.accentSoft,
          borderColor: StitchColors.accent,
          radius: StitchRadius.sm,
          shadows: const [],
          child: SelectableText(
            message,
            style: StitchTextStyles.muted.copyWith(fontSize: 12, height: 1.6),
          ),
        ),
      ],
      const SizedBox(height: 24),
      StitchCard(
        padding: const EdgeInsets.all(20),
        backgroundColor: StitchColors.card,
        borderColor: StitchColors.borderSoft,
        radius: StitchRadius.md,
        shadows: const [],
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(Zh.dependencyCheck, style: StitchTextStyles.muted),
            const SizedBox(height: 14),
            FilledButton(
              onPressed: checking ? null : onCheckMode,
              child: Text(checking ? '检查中…' : Zh.checkCurrentMode),
            ),
            const SizedBox(height: 10),
            FilledButton.tonal(
              onPressed: checking ? null : onCheckResource,
              child: Text(checking ? '检查中…' : Zh.checkProcessingResource),
            ),
            const SizedBox(height: 10),
            OutlinedButton(
              onPressed: onCopyResult,
              child: const Text(Zh.copyCheckResult),
            ),
          ],
        ),
      ),
      const SizedBox(height: 16),
      GestureDetector(
        onTap: () => _showLogs(context),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
          decoration: BoxDecoration(
            color: StitchColors.logButton,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.notes_rounded, color: Colors.white, size: 16),
              const SizedBox(width: 8),
              Text(
                '${Zh.logs}  ${runtime.logs.length} ${Zh.logUnit}',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13),
              ),
            ],
          ),
        ),
      ),
      if (!compact) const Spacer(),
    ];

    return SizedBox(
      width: compact ? double.infinity : StitchLayout.rightInspectorWidth,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
  }
}

class _DependencyDownloadDialog extends StatefulWidget {
  const _DependencyDownloadDialog({required this.api});

  final InkMomentApi api;

  @override
  State<_DependencyDownloadDialog> createState() => _DependencyDownloadDialogState();
}

class _DependencyDownloadDialogState extends State<_DependencyDownloadDialog> {
  Timer? _timer;
  Map<String, dynamic> _status = const {'status': 'pending', 'progress': 0, 'message': '正在读取下载进度…'};
  bool _cancelling = false;

  @override
  void initState() {
    super.initState();
    _poll();
    _timer = Timer.periodic(const Duration(milliseconds: 700), (_) => _poll());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  bool get _terminal => const {'done', 'error', 'cancelled', 'idle'}.contains(_status['status']);

  Future<void> _poll() async {
    try {
      final status = await widget.api.depDownloadStatus();
      if (!mounted) return;
      setState(() => _status = status);
      if (_terminal) _timer?.cancel();
    } catch (error) {
      if (!mounted) return;
      setState(() => _status = {'status': 'error', 'error': error.toString(), 'progress': 0});
      _timer?.cancel();
    }
  }

  Future<void> _cancel() async {
    setState(() => _cancelling = true);
    try {
      final status = await widget.api.depDownloadCancel();
      if (!mounted) return;
      setState(() => _status = status);
    } finally {
      if (mounted) setState(() => _cancelling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rawProgress = _status['progress'];
    final progress = rawProgress is num ? rawProgress.clamp(0, 100).toDouble() : 0.0;
    final message = (_status['error'] ?? _status['message'] ?? '').toString();
    final cancelable = _status['cancelable'] == true && !_cancelling && !_terminal;
    return AlertDialog(
      title: const Text('资源下载进度'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            LinearProgressIndicator(value: progress <= 0 ? null : progress / 100),
            const SizedBox(height: 14),
            Text('${progress.toInt()}% · ${_status['status'] ?? ''}'),
            const SizedBox(height: 8),
            SelectableText(message.isEmpty ? '正在处理资源…' : message),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelable ? _cancel : null,
          child: Text(_cancelling ? '正在终止…' : '终止下载'),
        ),
        TextButton(
          onPressed: _terminal ? () => Navigator.pop(context, _status) : null,
          child: const Text('关闭'),
        ),
      ],
    );
  }
}

class _AuthBadge extends StatelessWidget {
  const _AuthBadge({required this.authorized});

  final bool authorized;

  @override
  Widget build(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderFaint,
      radius: 999,
      shadows: StitchShadow.soft,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
              color: authorized ? StitchColors.accentDeep : StitchColors.warning,
              borderRadius: BorderRadius.circular(999),
            ),
          ),
          const SizedBox(width: 10),
          Text(authorized ? Zh.authValidFull : Zh.authAbnormal, style: StitchTextStyles.sectionTitle),
        ],
      ),
    );
  }
}

class _InspectorCard extends StatelessWidget {
  const _InspectorCard({required this.label, required this.value, this.highlighted = false});

  final String label;
  final String value;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(24),
      backgroundColor: highlighted ? StitchColors.cardGlow : StitchColors.card,
      borderColor: highlighted ? StitchColors.accent : StitchColors.borderSoft,
      radius: StitchRadius.md,
      shadows: const [],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: StitchTextStyles.muted),
          const SizedBox(height: 10),
          Text(value, maxLines: 2, overflow: TextOverflow.ellipsis, style: StitchTextStyles.sectionTitle),
        ],
      ),
    );
  }
}
