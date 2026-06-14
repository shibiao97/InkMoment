# InkMoment 桌面签名与公证流程

> 当前状态：默认桌面 release workflow 已切到 `desktop_flutter/`，产出 macOS Flutter DMG
> 与 Windows Flutter zip。本文只定义启用签名/公证的步骤与 GitHub Actions secrets 模板。

## 目标边界

- macOS：使用 Developer ID Application 证书签名，并完成 Apple notarization。
- Windows：当前先分发 Flutter release zip；如后续增加 NSIS/Inno 安装器，再签名安装器。
- 不改变 sidecar 构建、`scripts/build_desktop_release.py` 入口或 `dist/flutter-desktop/` 产物路径。
- 不把证书、私钥、PFX、`.p8` 文件提交到仓库。

参考：

- Apple notarization: <https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution>
- Windows SignTool: <https://learn.microsoft.com/windows/win32/seccrypto/signtool>

## macOS Developer ID + Notarization

### 必备账号与证书

1. Apple Developer Program 账号。
2. `Developer ID Application` 证书，导出为 `.p12`。
3. `.p12` 导出密码。
4. Notarization 凭据，二选一：
   - Apple ID 路径：Apple ID、app-specific password、Team ID。
   - App Store Connect API 路径：Issuer ID、Key ID、`.p8` 私钥文件。

### GitHub Secrets 模板

推荐先用 Apple ID 路径，字段更少：

| Secret | 说明 |
| :--- | :--- |
| `APPLE_CERTIFICATE` | `.p12` 证书的 base64 内容：`openssl base64 -A -in DeveloperID.p12` |
| `APPLE_CERTIFICATE_PASSWORD` | 导出 `.p12` 时设置的密码 |
| `APPLE_ID` | Apple Developer 账号邮箱 |
| `APPLE_PASSWORD` | Apple app-specific password，不是登录密码 |
| `APPLE_TEAM_ID` | Apple Developer Team ID |
| `APPLE_SIGNING_IDENTITY` | 可选；例如 `Developer ID Application: Example Inc (TEAMID)` |

如果改用 App Store Connect API，把 `APPLE_ID` / `APPLE_PASSWORD` /
`APPLE_TEAM_ID` 替换为：

| Secret | 说明 |
| :--- | :--- |
| `APPLE_API_ISSUER` | App Store Connect issuer ID |
| `APPLE_API_KEY` | Key ID |
| `APPLE_API_KEY_P8` | `.p8` 私钥文件全文 |

CI 中需要把 `APPLE_API_KEY_P8` 写入临时文件，并设置 `APPLE_API_KEY_PATH`
指向该文件。

### Workflow 启用点

当前 `.github/workflows/desktop-release.yml` 的 macOS matrix 已使用 Flutter DMG：

```yaml
bundle: dmg
artifact_path: dist/flutter-desktop/macos/release/*.dmg
```

启用正式签名时，在 `Build Flutter desktop release` 步骤注入 macOS secrets：

```yaml
env:
  APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}
  APPLE_CERTIFICATE_PASSWORD: ${{ secrets.APPLE_CERTIFICATE_PASSWORD }}
  APPLE_ID: ${{ secrets.APPLE_ID }}
  APPLE_PASSWORD: ${{ secrets.APPLE_PASSWORD }}
  APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
  APPLE_SIGNING_IDENTITY: ${{ secrets.APPLE_SIGNING_IDENTITY }}
```

Flutter DMG 目前由 `scripts/build_desktop_release.py` 创建；接入签名时需要在该脚本中对
`.app` 做 Developer ID 签名，再创建/公证/staple DMG。

### 本地验证

```bash
npm run desktop:release:mac -- --ci
python3 scripts/verify_desktop_release.py --bundle dmg --profile release
xcrun stapler validate "dist/flutter-desktop/macos/release/"*.dmg
spctl -a -vv --type open "dist/flutter-desktop/macos/release/"*.dmg
```

## Windows Code Signing

Windows 当前默认产物是 Flutter release zip。签名路线取决于后续是否增加安装器：
若仍分发 zip，可签名 zip 内 `.exe` 后再压缩；若增加 NSIS/Inno/MSIX，则签名安装器。
2023-06-01 之后签发的 OV/EV 证书通常不再是简单可导出的私钥文件，优先按证书商或
Azure Trusted Signing 文档选择实现。

### 路线 A：PFX 可导入证书

适用于已有可导入 `.pfx` 的证书。

| Secret | 说明 |
| :--- | :--- |
| `WINDOWS_CERTIFICATE` | `.pfx` 的 base64 内容 |
| `WINDOWS_CERTIFICATE_PASSWORD` | `.pfx` 导出密码 |
| `TAURI_WINDOWS_SIGNTOOL_PATH` | 可选；指定 `signtool.exe` 路径 |

在 Windows job 的 `Build Flutter desktop release` 前增加证书导入步骤：

```yaml
- name: Import Windows certificate
  if: runner.os == 'Windows'
  shell: pwsh
  env:
    WINDOWS_CERTIFICATE: ${{ secrets.WINDOWS_CERTIFICATE }}
    WINDOWS_CERTIFICATE_PASSWORD: ${{ secrets.WINDOWS_CERTIFICATE_PASSWORD }}
  run: |
    New-Item -ItemType Directory -Path certificate
    Set-Content -Path certificate/certificate.txt -Value $env:WINDOWS_CERTIFICATE
    certutil -decode certificate/certificate.txt certificate/certificate.pfx
    $password = ConvertTo-SecureString -String $env:WINDOWS_CERTIFICATE_PASSWORD -Force -AsPlainText
    Import-PfxCertificate -FilePath certificate/certificate.pfx -CertStoreLocation Cert:\CurrentUser\My -Password $password
```

### 路线 B：Azure Trusted Signing / 自定义签名命令

适用于 Azure Trusted Signing、EV token、远程 HSM 或证书商 CLI。接入前先确定
Windows 最终分发形态是 zip 内 exe、NSIS/Inno 安装器还是 MSIX。

常见 secrets：

| Secret | 说明 |
| :--- | :--- |
| `AZURE_CLIENT_ID` | Entra ID application client ID |
| `AZURE_CLIENT_SECRET` | Entra ID client secret |
| `AZURE_TENANT_ID` | Azure tenant ID |
| `AZURE_TRUSTED_SIGNING_ENDPOINT` | Trusted Signing endpoint |
| `AZURE_TRUSTED_SIGNING_ACCOUNT` | Trusted Signing account |
| `AZURE_TRUSTED_SIGNING_PROFILE` | Certificate profile |

只有选定实际签名服务后，才应把签名步骤写入 workflow 或 release builder。不要在没有
证书商 CLI 验证的情况下提交占位命令。

### Windows 验证

```powershell
npm run desktop:release:win -- --ci
python scripts/verify_desktop_release.py --bundle zip --profile release
Expand-Archive "dist\flutter-desktop\windows\*.zip" -DestinationPath "$env:TEMP\inkmoment-flutter"
Get-AuthenticodeSignature "$env:TEMP\inkmoment-flutter\*.exe"
```

期望 `Get-AuthenticodeSignature` 返回 `Status: Valid`，`SignerCertificate`
显示预期发布主体。

## 灰度与回滚

1. 先在 `workflow_dispatch` 手动触发，不随 tag 自动发布。
2. macOS 先验证 DMG 可以通过 `stapler validate` 与 `spctl`。
3. Windows 先下载 artifact，用干净虚拟机解压/运行，确认发布者与启动行为；如后续有安装器，再执行安装验收。
4. 如签名失败，回滚方式是：
   - macOS 签名步骤从 workflow/release builder 中移除，回到未签名 DMG。
   - 移除新增 signing env / certificate import step。
   - 保留本文档与 secrets，等待证书链路修复后再启用。

## 不纳入本轮的事项

- 旧 Tauri updater 包签名与增量更新。
- Microsoft Store / Mac App Store 上架流程。
- 证书采购与组织实名审核。
- Windows EV token 的人工插拔或本地 agent 流程。
