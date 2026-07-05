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
  String _message = '';
  bool _checking = false;

  void _go(WorkflowStep step, [String? summary]) {
    setState(() {
      _step = step;
      if (summary != null && summary.isNotEmpty) _summary = summary;
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
      final auth = await widget.api.authStatus(force: true);
      if (!mounted) return;
      widget.onAuthChanged(auth);
      final authorized = auth['authorized'] == true;
      final account = auth['account']?['email']?.toString() ?? '';
      final reason = auth['reason']?.toString() ?? '';
      setState(() {
        _message = authorized
            ? '模式：$_summary\n账号：$account\n授权：有效'
            : '模式：$_summary\n授权状态：$reason';
      });
    } catch (error) {
      _handleWorkflowError(error);
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _checkResource() async {
    if (_checking) return;
    setState(() { _checking = true; _message = '检查中…'; });
    try {
      final status = await widget.api.getStatus();
      if (!mounted) return;
      final job = status['job'];
      final jobStatus = job?['status']?.toString() ?? 'idle';
      final sidecar = widget.runtime.apiBaseUrl.isNotEmpty ? '已连接 ${widget.runtime.apiBaseUrl}' : '待启动';
      setState(() => _message = '后端：$sidecar\n任务状态：$jobStatus');
    } catch (error) {
      if (!mounted) return;
      final sidecar = widget.runtime.apiBaseUrl.isNotEmpty ? '已连接' : '未启动';
      setState(() { _message = '后端：$sidecar\n资源检查失败：${error.toString()}'; });
    } finally {
      if (mounted) setState(() => _checking = false);
    }
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
        _LeftRail(summary: _summary, step: _step),
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
          _LeftRail(summary: _summary, step: _step, compact: true),
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
      onStarted: (payload) => _go(WorkflowStep.analyze, payload['folder']?.toString()),
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
      onNewTask: () => _go(WorkflowStep.modeFolder, Zh.quickSelection),
      onAuthInvalid: widget.onAuthInvalid,
    ),
  };
}

class _LeftRail extends StatelessWidget {
  const _LeftRail({required this.summary, required this.step, this.compact = false});

  final String summary;
  final WorkflowStep step;
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
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final item in WorkflowStep.values) _CompactStepChip(step: item, selected: item == step),
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
                    Text(Zh.folderNotSelected, style: StitchTextStyles.muted),
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
