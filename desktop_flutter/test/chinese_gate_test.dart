import 'package:flutter_test/flutter_test.dart';
import 'package:inkmoment_desktop/src/api/inkmoment_api.dart';
import 'package:inkmoment_desktop/src/l10n/strings.dart';
import 'package:inkmoment_desktop/src/workflow/workflow_state.dart';

void main() {
  test('核心流程文案使用中文', () {
    expect(WorkflowStep.values.map((step) => step.label), containsAll(['模式 / 文件夹', '分析', '复核', '选片', '导出']));
    expect(Zh.loginTitle, '登录并确认授权');
    expect(Zh.startAnalyze, '开始分析');
    expect(Zh.startExport, '开始批量导出');
  });

  test('授权失败错误会回到门禁', () {
    expect(
      InkMomentApi.isAuthorizationFailure(ApiException('请先登录账号', code: 'unauthenticated', status: 401)),
      isTrue,
    );
    expect(
      InkMomentApi.isAuthorizationFailure(ApiException('授权服务不可用', code: 'auth_server_not_configured', status: 503)),
      isTrue,
    );
    expect(
      InkMomentApi.isAuthorizationFailure(ApiException('普通错误', code: 'bad_request', status: 400)),
      isFalse,
    );
  });
}
