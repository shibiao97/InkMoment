import 'package:flutter/material.dart';

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
        const SizedBox(width: 28),
        Expanded(child: _screen()),
        const SizedBox(width: 28),
        _RightInspector(
          step: _step,
          auth: widget.auth,
          runtime: widget.runtime,
          message: _message,
          authorized: _authorized,
          summary: _summary,
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
            authorized: _authorized,
            summary: _summary,
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
    required this.authorized,
    required this.summary,
    required this.onRefreshAuth,
    required this.onLogout,
    this.compact = false,
  });

  final WorkflowStep step;
  final Map<String, dynamic> auth;
  final SidecarController runtime;
  final String message;
  final bool authorized;
  final String summary;
  final VoidCallback onRefreshAuth;
  final VoidCallback onLogout;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final children = [
      Align(
        alignment: Alignment.centerRight,
        child: _AuthBadge(authorized: authorized),
      ),
      const SizedBox(height: 18),
      _InspectorCard(label: Zh.mode, value: summary, highlighted: true),
      const SizedBox(height: 16),
      const _InspectorCard(label: Zh.photoFolder, value: Zh.folderNotSelected),
      const SizedBox(height: 16),
      _InspectorCard(
        label: Zh.runtimeResource,
        value: runtime.apiBaseUrl.isEmpty ? Zh.pendingCheck : Zh.ready,
      ),
      const SizedBox(height: 34),
      StitchCard(
        padding: const EdgeInsets.all(26),
        backgroundColor: StitchColors.card,
        borderColor: StitchColors.borderSoft,
        radius: StitchRadius.md,
        shadows: const [],
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(Zh.runtimeResource, style: StitchTextStyles.muted),
            const SizedBox(height: 8),
            Text('$summary${Zh.dependencyCheck}', style: StitchTextStyles.sectionTitle),
            const SizedBox(height: 28),
            FilledButton(onPressed: onRefreshAuth, child: const Text(Zh.checkCurrentMode)),
            const SizedBox(height: 16),
            FilledButton.tonal(onPressed: onRefreshAuth, child: const Text(Zh.checkProcessingResource)),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: message.isEmpty ? null : onLogout, child: const Text(Zh.copyCheckResult)),
          ],
        ),
      ),
      if (!compact) const Spacer(),
      Align(
        alignment: Alignment.bottomRight,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          decoration: BoxDecoration(
            color: StitchColors.logButton,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text('${Zh.logs} ${runtime.logs.length}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800)),
        ),
      ),
    ];

    return SizedBox(
      width: compact ? double.infinity : StitchLayout.rightInspectorWidth,
      child: compact
          ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children)
          : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
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
