# InkMoment 桌面签名与公证流程

> 当前状态：桌面 release workflow 已能产出 macOS DMG 与 Windows NSIS EXE，
> 但 macOS job 仍显式使用 `--no-sign`。本文只定义启用签名/公证的步骤与
> GitHub Actions secrets 模板，不默认切换发布链。

## 目标边界

- macOS：使用 Developer ID Application 证书签名，并完成 Apple notarization。
- Windows：签名 NSIS 安装包，降低 SmartScreen 与未受信任发布者提示。
- 不改变 sidecar 构建、`scripts/build_desktop_release.py` 入口或产物路径。
- 不把证书、私钥、PFX、`.p8` 文件提交到仓库。

参考：

- Tauri macOS signing: <https://v2.tauri.app/distribute/sign/macos/>
- Tauri Windows signing: <https://v2.tauri.app/distribute/sign/windows/>
- Tauri CLI environment variables: <https://v2.tauri.app/reference/environment-variables/>

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

当前 `.github/workflows/desktop-release.yml` 的 macOS matrix 为：

```yaml
build_args: --ci --no-sign
```

启用正式签名时改为：

```yaml
build_args: --ci
```

并在 `Build installer` 步骤注入 macOS secrets：

```yaml
env:
  APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}
  APPLE_CERTIFICATE_PASSWORD: ${{ secrets.APPLE_CERTIFICATE_PASSWORD }}
  APPLE_ID: ${{ secrets.APPLE_ID }}
  APPLE_PASSWORD: ${{ secrets.APPLE_PASSWORD }}
  APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
  APPLE_SIGNING_IDENTITY: ${{ secrets.APPLE_SIGNING_IDENTITY }}
```

首次排障时可以临时加 `--skip-stapling`，但正式 release 不建议跳过 stapling。

### 本地验证

```bash
npm run desktop:release:mac -- --ci
python3 scripts/verify_desktop_release.py --bundle dmg --profile release
xcrun stapler validate "src-tauri/target/release/bundle/dmg/"*.dmg
spctl -a -vv --type open "src-tauri/target/release/bundle/dmg/"*.dmg
```

## Windows NSIS Code Signing

Windows 签名路线取决于证书形态。2023-06-01 之后签发的 OV/EV 证书通常不再是
简单可导出的私钥文件，优先按证书商或 Azure Trusted Signing 文档选择实现。

### 路线 A：PFX 可导入证书

适用于已有可导入 `.pfx` 的证书。

| Secret | 说明 |
| :--- | :--- |
| `WINDOWS_CERTIFICATE` | `.pfx` 的 base64 内容 |
| `WINDOWS_CERTIFICATE_PASSWORD` | `.pfx` 导出密码 |
| `TAURI_WINDOWS_SIGNTOOL_PATH` | 可选；指定 `signtool.exe` 路径 |

在 Windows job 的 `Build installer` 前增加证书导入步骤：

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

适用于 Azure Trusted Signing、EV token、远程 HSM 或证书商 CLI。Tauri 支持在
`src-tauri/tauri.conf.json` 的 `bundle.windows.signCommand` 配置自定义签名命令。

常见 secrets：

| Secret | 说明 |
| :--- | :--- |
| `AZURE_CLIENT_ID` | Entra ID application client ID |
| `AZURE_CLIENT_SECRET` | Entra ID client secret |
| `AZURE_TENANT_ID` | Azure tenant ID |
| `AZURE_TRUSTED_SIGNING_ENDPOINT` | Trusted Signing endpoint |
| `AZURE_TRUSTED_SIGNING_ACCOUNT` | Trusted Signing account |
| `AZURE_TRUSTED_SIGNING_PROFILE` | Certificate profile |

只有选定实际签名服务后，才应把 `signCommand` 写入 `tauri.conf.json`。不要在没有
证书商 CLI 验证的情况下提交占位命令。

### Windows 验证

```powershell
npm run desktop:release:win -- --ci
python scripts/verify_desktop_release.py --bundle nsis --profile release
Get-AuthenticodeSignature "src-tauri\target\release\bundle\nsis\*.exe"
```

期望 `Get-AuthenticodeSignature` 返回 `Status: Valid`，`SignerCertificate`
显示预期发布主体。

## 灰度与回滚

1. 先在 `workflow_dispatch` 手动触发，不随 tag 自动发布。
2. macOS 先验证 DMG 可以通过 `stapler validate` 与 `spctl`。
3. Windows 先下载 artifact，用干净虚拟机安装，确认发布者与启动行为。
4. 如签名失败，回滚方式是：
   - macOS matrix 恢复 `build_args: --ci --no-sign`。
   - 移除新增 signing env / certificate import step。
   - 保留本文档与 secrets，等待证书链路修复后再启用。

## 不纳入本轮的事项

- Tauri updater 包签名与增量更新。
- Microsoft Store / Mac App Store 上架流程。
- 证书采购与组织实名审核。
- Windows EV token 的人工插拔或本地 agent 流程。
