import 'package:flutter/material.dart';

import '../api/inkmoment_api.dart';
import '../analysis/analysis_screen.dart';
import '../arena/arena_screen.dart';
import '../export/export_screen.dart';
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
  String _summary = '等待新任务';
  String _message = '';

  void _go(WorkflowStep step, [String? summary]) {
    setState(() {
      _step = step;
      if (summary != null) _summary = summary;
    });
  }

  void _handleWorkflowError(Object error) {
    if (InkMomentApi.isAuthorizationFailure(error)) {
      widget.onAuthInvalid(error);
      return;
    }
    setState(() => _message = error.toString());
  }

  Future<void> _refreshAuth() async {
    try {
      final auth = await widget.api.authStatus(force: true);
      widget.onAuthChanged(auth);
      setState(() => _message = '授权状态已刷新');
    } catch (error) {
      _handleWorkflowError(error);
    }
  }

  Future<void> _logout() async {
    try {
      await widget.api.logout();
      widget.onAuthChanged(const {'authorized': false, 'authenticated': false, 'reason': 'unauthenticated'});
    } catch (error) {
      _handleWorkflowError(error);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _TopBar(step: _step),
          Expanded(
            child: Row(
              children: [
                _LeftRail(summary: _summary, step: _step),
                Expanded(child: _screen()),
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
          _StatusBar(runtime: widget.runtime, auth: widget.auth),
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
            onNewTask: () => _go(WorkflowStep.modeFolder, '等待新任务'),
            onAuthInvalid: widget.onAuthInvalid,
          ),
      };
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.step});
  final WorkflowStep step;

  @override
  Widget build(BuildContext context) {
    final steps = WorkflowStep.values;
    return Container(
      height: 86,
      padding: const EdgeInsets.symmetric(horizontal: 18),
      decoration: const BoxDecoration(color: Color(0xFF161D19), border: Border(bottom: BorderSide(color: Color(0xFF2F3632)))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 10),
          const Text('InkMoment', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          Row(
            children: [
              for (final item in steps)
                Expanded(
                  child: Container(
                    margin: const EdgeInsets.only(right: 8),
                    height: 28,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: item == step ? const Color(0xFF10B981) : const Color(0xFF242C27),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(item.label, style: TextStyle(color: item == step ? Colors.black : Colors.white)),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _LeftRail extends StatelessWidget {
  const _LeftRail({required this.summary, required this.step});
  final String summary;
  final WorkflowStep step;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 240,
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(color: Color(0xFF0E1511), border: Border(right: BorderSide(color: Color(0xFF2F3632)))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('当前流程', style: TextStyle(color: Color(0xFFBBCABF))),
        const SizedBox(height: 8),
        Text(step.label, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        Text(summary, maxLines: 4, overflow: TextOverflow.ellipsis),
        const Spacer(),
        const Text('授权正常\n后端就绪', style: TextStyle(color: Color(0xFF4EDEA3))),
      ]),
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
  });

  final WorkflowStep step;
  final Map<String, dynamic> auth;
  final String message;
  final VoidCallback onRefreshAuth;
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 300,
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(color: Color(0xFF161D19), border: Border(left: BorderSide(color: Color(0xFF2F3632)))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('上下文检查器', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 16),
        _line('当前步骤', step.label),
        _line('授权账号', (auth['account'] as Map?)?['email']?.toString() ?? '已授权'),
        _line('操作提示', '按当前步骤完成必要操作后继续'),
        if (message.isNotEmpty) _line('状态', message),
        const Spacer(),
        OutlinedButton(onPressed: onRefreshAuth, child: const Text('刷新授权')),
        OutlinedButton(onPressed: onLogout, child: const Text('退出登录')),
      ]),
    );
  }

  Widget _line(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFFBBCABF))),
          Text(value),
        ]),
      );
}

class _StatusBar extends StatelessWidget {
  const _StatusBar({required this.runtime, required this.auth});
  final SidecarController runtime;
  final Map<String, dynamic> auth;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 34,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: const BoxDecoration(color: Color(0xFF09100C), border: Border(top: BorderSide(color: Color(0xFF2F3632)))),
      child: Row(children: [
        Text('后端：${runtime.apiBaseUrl.isEmpty ? '连接中' : '就绪'}'),
        const SizedBox(width: 18),
        Text('授权：${auth['authorized'] == true ? '有效' : '异常'}'),
        const Spacer(),
        Text('日志 ${runtime.logs.length} 条'),
      ]),
    );
  }
}
