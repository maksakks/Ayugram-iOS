# Статус модулей

Обновлено: 2026-10-23. Ни одна сборка в CI ещё не запускалась, поэтому «Готово»
означает «код написан и проверен чтением», а не «собрано и протестировано».

| Модуль | Статус | Файлы |
|---|---|---|
| Аудит | Готово | `docs/AUDIT.md` |
| CI workflow (unsigned/signed) | Код готов, не запускался | `.github/workflows/ios-build.yml`, `tools/ci/*` |
| Генерация тестовых профилей под наш Bundle ID | Проверено локально (10 профилей) | `tools/ci/generate-fake-codesigning.py` |
| Подстановка API credentials из Secrets | Проверено локально | `tools/ci/prepare-configuration.py` |
| Privacy Center | Код готов, не компилировался | `Swiftgram/SGSettingsUI/Sources/PrivacyCenterController.swift` |
| Локальный архив сообщений | Не начат | — |
| Брендинг | Не начат | — |
| Подписанная сборка | Ждёт Secrets и первой успешной unsigned-сборки | — |

## Privacy Center

Вход: Настройки Swiftgram → «Центр приватности».

- Supported: скрытие номера в интерфейсе настроек, подтверждение перед открытием историй.
- PartiallySupported: Stealth mode для историй. Клиент не отправляет `markStoryAsSeen`
  (`TelegramEngineMessages.swift`), но анонимность не гарантируется; это указано в UI.
  Переключатель показывается, только если `canUseStealthMode`.
- Unsupported (только текст, без переключателей): скрытие прочтений от сервера,
  невидимость в сети, гарантированно анонимный просмотр историй без Premium,
  восстановление неполученных сообщений.
- Ссылка на штатный экран «Конфиденциальность» Telegram для серверных настроек.

## GitHub Secrets для CI

| Secret | Нужен для |
|---|---|
| `RUFATGRAM_API_ID`, `RUFATGRAM_API_HASH` | вход в аккаунт (my.telegram.org) |
| `RUFATGRAM_TEAM_ID`, `RUFATGRAM_BUNDLE_ID` | подпись; без них остаются заглушки |
| `BUILD_CERTIFICATE_BASE64`, `P12_PASSWORD`, `KEYCHAIN_PASSWORD` | signed-сборка |
| `PROVISIONING_PROFILE_BASE64` или `PROFILES_JSON_BASE64` | signed-сборка |
