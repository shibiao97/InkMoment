import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../api/json_utils.dart';
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
  String _summary = Zh.waitingTask;
  String _message = '';

  void _go(WorkflowStep step, [String? summary]) {
    setState(() {
      _step = step;
      if (summary != null) _summary = summary;
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
        padding: const EdgeInsets.all(20),
        child: compact ? _compactLayout(context) : _desktopLayout(context),
      ),
    );
  }

  Widget _desktopLayout(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _HeaderBar(
          step: _step,
          summary: _summary,
          authorized: _authorized,
          auth: widget.auth,
        ),
        const SizedBox(height: 16),
        Expanded(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _LeftRail(summary: _summary, step: _step),
              const SizedBox(width: 16),
              Expanded(child: _contentArea(context)),
              const SizedBox(width: 16),
              _RightInspector(
                step: _step,
                auth: widget.auth,
                message: _message,
                onRefreshAuth: _refreshAuth,
                onLogout: _logout,
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        _StatusBar(runtime: widget.runtime, auth: widget.auth),
      ],
    );
  }

  Widget _compactLayout(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _HeaderBar(
            step: _step,
            summary: _summary,
            authorized: _authorized,
            auth: widget.auth,
          ),
          const SizedBox(height: 16),
          _contentArea(context),
          const SizedBox(height: 16),
          _RightInspector(
            step: _step,
            auth: widget.auth,
            message: _message,
            onRefreshAuth: _refreshAuth,
            onLogout: _logout,
            compact: true,
          ),
          const SizedBox(height: 16),
          _StatusBar(runtime: widget.runtime, auth: widget.auth),
        ],
      ),
    );
  }

  Widget _contentArea(BuildContext context) {
    return StitchCard(
      padding: EdgeInsets.zero,
      backgroundColor: StitchColors.card,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [BoxShadow(color: Color(0x10243527), blurRadius: 22, offset: Offset(0, 14))],
      child: ClipRRect(
        borderRadius: BorderRadius.circular(StitchRadius.xl),
        child: ColoredBox(
          color: StitchColors.card,
          child: _screen(),
        ),
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
      onNewTask: () => _go(WorkflowStep.modeFolder, Zh.waitingTask),
      onAuthInvalid: widget.onAuthInvalid,
    ),
  };
}

class _HeaderBar extends StatelessWidget {
  const _HeaderBar({
    required this.step,
    required this.summary,
    required this.auth,
    required this.authorized,
  });

  final WorkflowStep step;
  final String summary;
  final Map<String, dynamic> auth;
  final bool authorized;

  @override
  Widget build(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(18),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.xl,
      shadows: const [],
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: StitchColors.accentSoft,
              borderRadius: BorderRadius.circular(StitchRadius.lg),
              border: Border.all(color: StitchColors.borderSoft),
            ),
            child: const Icon(Icons.photo_camera_outlined, color: StitchColors.accentDeep),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Zh.appName,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: StitchColors.textPrimary,
                      ),
                ),
                const SizedBox(height: 4),
                Text(
                  summary,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: StitchColors.textMuted,
                      ),
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    StitchPill(label: Zh.currentFlow, value: step.label),
                    StitchPill(label: Zh.account, value: _accountLabel(auth)),
                    StitchPill(
                      label: Zh.authorization,
                      value: authorized ? Zh.authNormal : _reasonText(auth['reason']),
                      color: authorized ? StitchColors.accentDeep : StitchColors.warning,
                    ),
                    const StitchPill(label: Zh.backend, value: Zh.ready),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _accountLabel(Map<String, dynamic> auth) {
    final account = asStringMap(auth['account']);
    final email = account?['email']?.toString();
    if (email == null || email.isEmpty) return Zh.authorizedFallback;
    return email;
  }

  String _reasonText(Object? reason) => switch (reason?.toString()) {
        'active' => Zh.authorized,
        'unauthenticated' => Zh.signedOut,
        'not_activated' => Zh.notActivated,
        'expired' => Zh.expired,
        'revoked' => Zh.revoked,
        'device_mismatch' => Zh.deviceMismatch,
        'auth_server_not_configured' => Zh.authServerNotConfigured,
        'auth_not_configured' => Zh.authServerNotConfigured,
        'auth_server_unavailable' => Zh.authServerUnavailable,
        'auth_check_failed' => Zh.authCheckFailed,
        null || '' => Zh.signedOut,
        _ => Zh.authPending,
      };
}

class _LeftRail extends StatelessWidget {
  const _LeftRail({required this.summary, required this.step});

  final String summary;
  final WorkflowStep step;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 258,
      child: StitchCard(
        padding: const EdgeInsets.all(18),
        backgroundColor: StitchColors.card,
        borderColor: StitchColors.borderSoft,
        radius: StitchRadius.xl,
        shadows: const [BoxShadow(color: Color(0x10243527), blurRadius: 22, offset: Offset(0, 14))],
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              Zh.currentFlow,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: StitchColors.textPrimary,
                    fontWeight: FontWeight.w800,
                  ),
            ),
            const SizedBox(height: 12),
            Text(
              step.label,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: StitchColors.textPrimary,
                    fontWeight: FontWeight.w800,
                  ),
            ),
            const SizedBox(height: 10),
            Text(
              summary,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: StitchColors.textMuted,
                    height: 1.5,
                  ),
            ),
            const SizedBox(height: 18),
            Text(
              Zh.modeFolderStep,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: StitchColors.textMuted,
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final item in WorkflowStep.values) ...[
                    _StepRailItem(step: item, selected: item == step),
                    if (item != WorkflowStep.export) const SizedBox(height: 10),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 18),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: StitchColors.cardGlow,
                borderRadius: BorderRadius.circular(StitchRadius.lg),
                border: Border.all(color: StitchColors.borderSoft),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    Zh.operationHint,
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          color: StitchColors.textMuted,
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    Zh.operationHintText,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: StitchColors.textSecondary,
                          height: 1.45,
                        ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
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
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: selected ? StitchColors.accentSoft : StitchColors.cardGlow,
        borderRadius: BorderRadius.circular(StitchRadius.lg),
        border: Border.all(color: selected ? StitchColors.accent : StitchColors.borderSoft),
      ),
      child: Row(
        children: [
          Container(
            width: 24,
            height: 24,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: selected ? StitchColors.accentDeep : StitchColors.card,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: selected ? StitchColors.accentDeep : StitchColors.borderSoft),
            ),
            child: Text(
              '${step.index + 1}',
              style: TextStyle(
                color: selected ? Colors.white : StitchColors.textMuted,
                fontWeight: FontWeight.w800,
                fontSize: 12,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              step.label,
              style: TextStyle(
                color: selected ? StitchColors.accentDeep : StitchColors.textSecondary,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RightInspector extends StatelessWidget {
  const _RightInspector({
    required this.step,
    required this.auth,
    required this.message,
    required this.onRefreshAuth,
    required this.onLogout,
    this.compact = false,
  });

  final WorkflowStep step;
  final Map<String, dynamic> auth;
  final String message;
  final VoidCallback onRefreshAuth;
  final VoidCallback onLogout;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: compact ? double.infinity : 314,
      child: StitchCard(
        padding: const EdgeInsets.all(18),
        backgroundColor: StitchColors.card,
        borderColor: StitchColors.borderSoft,
        radius: StitchRadius.xl,
        shadows: const [BoxShadow(color: Color(0x10243527), blurRadius: 22, offset: Offset(0, 14))],
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              Zh.contextInspector,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: StitchColors.textPrimary,
                    fontWeight: FontWeight.w800,
                  ),
            ),
            const SizedBox(height: 14),
            _line(context, Zh.currentStep, step.label),
            _line(context, Zh.authorizedAccount, _accountLabel()),
            _line(context, Zh.authorization, _reasonText(auth['reason'])),
            _line(context, Zh.operationHint, Zh.operationHintText),
            if (message.isNotEmpty) _line(context, Zh.status, message),
            if (compact) const SizedBox(height: 8) else const Spacer(),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: onRefreshAuth,
                child: const Text(Zh.refreshAuth),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: onLogout,
                child: const Text(Zh.logout),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _line(BuildContext context, String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: StitchColors.textMuted,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: StitchColors.textSecondary,
                  height: 1.35,
                ),
          ),
        ],
      ),
    );
  }

  String _accountLabel() {
    final account = asStringMap(auth['account']);
    final email = account?['email']?.toString();
    if (email == null || email.isEmpty) return Zh.authorizedFallback;
    return email;
  }

  String _reasonText(Object? reason) => switch (reason?.toString()) {
        'active' => Zh.authorized,
        'unauthenticated' => Zh.signedOut,
        'not_activated' => Zh.notActivated,
        'expired' => Zh.expired,
        'revoked' => Zh.revoked,
        'device_mismatch' => Zh.deviceMismatch,
        'auth_server_not_configured' => Zh.authServerNotConfigured,
        'auth_not_configured' => Zh.authServerNotConfigured,
        'auth_server_unavailable' => Zh.authServerUnavailable,
        'auth_check_failed' => Zh.authCheckFailed,
        null || '' => Zh.signedOut,
        _ => Zh.authPending,
      };
}

class _StatusBar extends StatelessWidget {
  const _StatusBar({required this.runtime, required this.auth});

  final SidecarController runtime;
  final Map<String, dynamic> auth;

  @override
  Widget build(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      backgroundColor: StitchColors.cardGlow,
      borderColor: StitchColors.borderSoft,
      radius: StitchRadius.lg,
      shadows: const [],
      child: Row(
        children: [
          Text(
            '${Zh.backend}：${runtime.apiBaseUrl.isEmpty ? Zh.connecting : Zh.ready}',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: StitchColors.textMuted,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(width: 18),
          Text(
            '${Zh.authorization}：${auth['authorized'] == true ? Zh.authValid : Zh.authAbnormal}',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: StitchColors.textMuted,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const Spacer(),
          Text(
            '${Zh.logs} ${runtime.logs.length} ${Zh.logUnit}',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: StitchColors.textMuted,
                  fontWeight: FontWeight.w700,
                ),
          ),
        ],
      ),
    );
  }
}
