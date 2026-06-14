# Repository Guidelines

## Target Architecture

InkMoment's default desktop product is the native Flutter client in `desktop_flutter/`: choose mode/folder -> analyze -> prescreen review -> paired arena -> export. The installed entry must be Flutter Desktop, not legacy Vue/Tauri.

Runtime: Flutter Desktop -> Python Flask sidecar -> `inkmoment/` engines. Licensing is served by independent Flask `auth_server/`; the sidecar proxies auth state and guards core `/api/*` routes.

## Project Structure

- `desktop_flutter/lib/src/`: main client. `design/` holds Stitch tokens/components; `auth/`, `workflow/`, `analysis/`, `review/`, `arena/`, and `export/` map to stages.
- `server/`: local API, dependencies, runtime facade, selection, watermarking, config/notices, and auth proxy.
- `inkmoment/`: engines, grouping, LLM prescreening, quality scoring, and watermarking.
- `auth_server/`: authorization service and admin backend. Continue the blueprint/service/repository split.
- `frontend/`, `src-tauri/`, `static/vue/`: legacy shell. Do not hand-edit generated `static/vue/` assets.
- `tests/`, `desktop_flutter/test/`, `scripts/`, `docs/`: tests, release automation, and docs.

## Build, Test, And Release Commands

- `git status --short`: run before edits; expect dirty files.
- `uv run pytest`: Python regression tests.
- `uv run ruff check`: Python linting.
- `npm run quality:frontend`: legacy Vue lint/typecheck/tests.
- `python3 scripts/check_flutter_desktop.py --platform linux --build`: Flutter analyze/test/Linux build.
- `npm run desktop:release`, `npm run desktop:release:mac`, `npm run desktop:release:win`: Flutter packaging to `dist/flutter-desktop/`.
- `npm run desktop:release:tauri:mac` / `npm run desktop:release:tauri:win`: explicit legacy Tauri packaging only.
- `python3 scripts/verify_desktop_release.py --bundle zip --skip-native-check`: verify layout and sidecar.

JD Cloud is the Linux packaging source of truth; only claim release evidence after a current run.

## Coding Style And Data Rules

Prefer minimal changes within existing boundaries. Python uses Ruff with 120-column lines; Dart must be `dart format` compatible and use Stitch tokens. Put Chinese copy in `desktop_flutter/lib/src/l10n/strings.dart`.

Never fabricate AI scores, reasons, winners, license status, notices, config, exports, or build results. UI must render backend responses as returned. Avoid public API, database schema, authorization, and release-script changes unless compatibility, verification, rollback, and monitoring are documented.

## Testing Guidelines

Match verification to risk. Auth, CDK, device unbind, config/notices, export, watermark, selection, and sidecar changes need Python tests or smoke coverage. Flutter UI changes need `flutter analyze`, `flutter test`, and widgets. Photo quality must use the real backend path.

## Git And Review Discipline

Do not `reset`, `clean`, or revert unrelated dirty files. Keep commits scoped and imperative, for example `Align desktop workflow with Stitch UI`. PRs should include changed flow, verification commands, UI screenshots, release notes, and JD Cloud evidence for packaging.
