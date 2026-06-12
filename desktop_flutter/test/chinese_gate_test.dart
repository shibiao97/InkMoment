import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:inkmoment_desktop/src/api/inkmoment_api.dart';
import 'package:inkmoment_desktop/src/auth/auth_gate.dart';
import 'package:inkmoment_desktop/src/design/stitch_theme.dart';
import 'package:inkmoment_desktop/src/design/stitch_tokens.dart';
import 'package:inkmoment_desktop/src/l10n/strings.dart';
import 'package:inkmoment_desktop/src/workflow/workflow_state.dart';

void main() {
  test('核心流程文案使用中文', () {
    expect(
      WorkflowStep.values.map((step) => step.label),
      containsAll(['模式 / 文件夹', '分析', '复核', '选片', '导出']),
    );
    expect(Zh.loginTitle, '登录并确认授权');
    expect(Zh.startAnalyze, '开始分析');
    expect(Zh.startExport, '开始批量导出');
    expect(Zh.registerAndBind, '注册并绑定本机');
    expect(Zh.unbindDevice, '解除设备绑定');
    expect(Zh.contextInspector, '上下文检查器');
    expect(Zh.appName, 'InkMoment');
    expect(Zh.authBrand, 'InkMoment 授权');
    expect(Zh.account, '账号');
    expect(Zh.authorization, '授权');
    expect(Zh.service, '服务');
    expect(Zh.chooseModeAndFolder, '选择模式与照片文件夹');
    expect(Zh.reviewTitle, 'AI 初筛复核');
    expect(Zh.arenaTitle, '双图对比选片');
    expect(Zh.exportWinners, '导出胜出照片');
    expect(Zh.completed, '已完成');
    expect(Zh.total, '总数');
    expect(Zh.progress, '进度');
    expect(Zh.formatLabel, '导出格式');
    expect(Zh.backendConnected, '后端已连接');
    expect(Zh.backendHealthFailed, '后端健康检查失败');
    expect(Zh.healthEndpointUnavailable, '无法访问 /api/health');
    expect(Zh.statusLabel('running'), '导出中');
    expect(Zh.statusLabel('unknown'), '未知');
  });

  test('Stitch 主题使用浅色摄影工作台配色', () {
    final theme = buildStitchTheme();
    expect(theme.brightness, Brightness.light);
    expect(theme.scaffoldBackgroundColor, StitchColors.background);
    expect(theme.colorScheme.primary, StitchColors.accentDeep);
    expect(theme.colorScheme.surface, StitchColors.card);
  });

  testWidgets('未授权时显示中文启动门禁', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: AuthGate(
          api: InkMomentApi('http://127.0.0.1:9'),
          auth: const {
            'authorized': false,
            'authenticated': false,
            'configured': true,
            'reason': 'unauthenticated',
          },
          onAuthorized: (_) {},
        ),
      ),
    );

    expect(find.text(Zh.authBrand), findsOneWidget);
    expect(find.text(Zh.loginTitle), findsWidgets);
    expect(find.text(Zh.account), findsOneWidget);
    expect(find.text(Zh.signedOut), findsWidgets);
    expect(find.text(Zh.authorization), findsOneWidget);
    expect(find.text(Zh.service), findsOneWidget);
    expect(find.text(Zh.serviceConfigured), findsOneWidget);
    expect(find.text(Zh.login), findsWidgets);
    expect(find.text(Zh.register), findsOneWidget);
    expect(find.text(Zh.email), findsOneWidget);
    expect(find.text(Zh.password), findsOneWidget);
  });

  testWidgets('已登录但未开通时显示兑换和设备操作中文', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: AuthGate(
          api: InkMomentApi('http://127.0.0.1:9'),
          auth: const {
            'authorized': false,
            'authenticated': true,
            'configured': true,
            'reason': 'not_activated',
          },
          onAuthorized: (_) {},
        ),
      ),
    );

    expect(find.text(Zh.notActivated), findsWidgets);
    expect(find.text(Zh.cdk), findsOneWidget);
    expect(find.text(Zh.redeem), findsOneWidget);
    expect(find.text(Zh.refreshAuth), findsOneWidget);
    expect(find.text(Zh.unbindReason), findsOneWidget);
    expect(find.text(Zh.unbindDevice), findsOneWidget);
    expect(find.text(Zh.logout), findsOneWidget);
  });

  test('授权失败错误会回到门禁', () {
    expect(
      InkMomentApi.isAuthorizationFailure(
        ApiException('请先登录账号', code: 'unauthenticated', status: 401),
      ),
      isTrue,
    );
    expect(
      InkMomentApi.isAuthorizationFailure(
        ApiException(
          '授权服务不可用',
          code: 'auth_server_not_configured',
          status: 503,
        ),
      ),
      isTrue,
    );
    expect(
      InkMomentApi.isAuthorizationFailure(
        ApiException('普通错误', code: 'bad_request', status: 400),
      ),
      isFalse,
    );
  });
}
