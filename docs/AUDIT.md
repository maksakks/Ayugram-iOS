# Аудит кодовой базы и план работ

Дата аудита: 2026-10-19. Аудит сделан на Windows 11 без macOS/Xcode, поэтому все
выводы о сборке, кроме явно отмеченных, получены чтением скриптов и конфигураций,
а не фактическим запуском компилятора.

## 1. Что лежит в рабочей директории

| Компонент | Факт |
|---|---|
| База | `Swiftgram 11.15` — форк `TelegramMessenger/Telegram-iOS` (git `2f746090`, 26 738 файлов) |
| Язык | Swift + Objective-C, C/C++, небольшой объём Python в `build-system/` |
| Система сборки | Bazel (правила в `MODULE.bazel`, `.bazelrc`, кастомные правила в `build-system/bazel-rules/`) |
| Xcode project | в репозитории отсутствует; генерируется командой `Make.py generateProject` (rules_xcodeproj) |
| Submodules | 278 верхнеуровневых модулей; локально инициализированы все, кроме 12 (см. п. 6) |
| Внешние зависимости | `third-party/` (WebRTC, libvpx, dav1d, TDLib, XcodeGen) |
| Тесты | `Tests/` содержит демо-проекты, не unit-тесты; в `CLAUDE.md` прямо сказано «No tests are used at the moment» |
| Лицензия | отдельного LICENSE-файла нет; условия — в `README.md` (публикация кода обязательна) и в лицензиях submodules |

## 2. Точка входа и архитектура

- Основной таргет приложения: `//Telegram:Swiftgram` (`Telegram/BUILD`, `ios_application`).
- Код запуска: `submodules/TelegramUI/Sources/AppDelegate.swift`,
  `ApplicationContext.swift`, `TelegramRootController.swift`.
- Бизнес-логика — в `submodules/*` (≈300 модулей): `TelegramCore` (работа с MTProto,
  `Postbox`, аккаунты), `TelegramUI` (экраны), `SettingsUI` (настройки),
  `TelegramPresentationData` (темы, локализация), `Postbox` (локальная БД).
- Расширения: Share, NotificationService/Content, Siri Intents, Watch, Widget,
  BroadcastUpload, SGActionRequestHandler.
- Бренд-специфичные модули Swiftgram — в `Swiftgram/`: `SGSimpleSettings`
  (UserDefaults-обёртка + `SimpleSettings`), `SGSettingsUI` (готовый экран настроек
  с десятками переключателей), `SGStrings`, `SGConfig`, `SGLogging`, `SGItemListUI`.

## 3. Текущие функции базы (важно для оценки объёма)

В `SGSimpleSettings.Keys` и `SGSettingsUI` **уже реализованы** десятки настроек:
скрытие телефона в настройках, скрытие реакций, скрытие таба, компактный список чатов,
размер стикеров, «stealth mode» для Stories, быстрый перевод, выбор бэкенда перевода
и транскрипции, подтверждение звонков, качество отправляемых фото, настройки контекстного
меню, отображение DC/даты регистрации и т.п. Это значит, что часть целевого объёма
(UI Customization, часть приватности) **уже готова в базе** и переписывать её не нужно.

Чего в базе нет:

- единого экрана «Privacy Center» с классификацией функций;
- локального архива сообщений с поиском/экспортом/сроками хранения;
- собственного брендинга (`CFBundleDisplayName` жёстко задан как `Swiftgram`
  в `Telegram/BUILD`, иконки/строка версии тоже Swiftgram);
- рабочего CI под наш Bundle ID и подпись (см. п. 5).

## 4. Конфигурация Telegram API

`build-system/Make/BuildConfiguration.py` принимает JSON с ключами `bundle_id`,
`api_id`, `api_hash`, `team_id`, `app_specific_url_scheme`, `sg_config` и др.
`api_id`/`api_hash` попадают в `variables.bzl` и компилируются в бинарник —
поэтому в репозитории они должны быть только заглушками, а реальные значения
передаются из GitHub Secrets на этапе CI.

## 5. Состояние CI и найденные блокеры

Предыдущая итерация оставила неотслеживаемые файлы:

- `.github/workflows/ios-build.yml` — рабочий workflow (macos-15, Xcode из `versions.json`);
- `build-system/rufatgram-configuration.json` — конфиг с `com.rufogram.rufat` / `AAAAAAAAAA`;
- `build-system/rufatgram-codesigning/` — пустой каталог только с `.gitkeep`;
- `tools/ci/import-signing-assets.sh` — импорт сертификата/профилей из Secrets;
- правка `.gitignore` — исключение сертификатов, профилей и локального конфига.

Найдено при разборе `build-system/Make/BuildConfiguration.py`:

1. **Несборка unsigned-сборки.** Workflow в unsigned-режиме передаёт
   `--codesigningInformationPath=build-system/fake-codesigning`. Скрипт
   `copy_profiles_from_directory` отбирает профили по префиксу
   `<team_id>.<bundle_id>`, а фейковые профили выпущены на
   `C67CF9S4VU.ph.telegra.Telegraph`. Для `AAAAAAAAAA.com.rufogram.rufat` ни один
   профиль не подходит, `resolve_aps_environment_from_directory` возвращает `None`,
   и `Make.py` завершается с ошибкой ещё до вызова Bazel. Это подтверждается кодом
   `build-system/Make/Make.py:547-549`.
2. **Секреты в конфиге.** `api_id = 0` и нулевой `api_hash` захардкожены. С такими
   значениями приложение соберётся, но вход в аккаунт Telegram отклонит.
3. **Кэш Bazel вне workspace.** `BAZEL_CACHE_DIR` указывает в `${{ github.workspace }}/../bazel-cache`,
   между запусками не сохраняется (нет `actions/cache`), полная сборка каждый раз.

## 6. Локальное окружение

- 12 submodules не инициализированы, включая `rules_apple`, `rules_swift`,
  `third-party/webrtc`, `TgVoipWebrtc/tgcalls`. На Windows это не мешает чтению кода,
  но означает, что локальная сборка невозможна в принципе (нужен macOS + Xcode 16.2).
- Python 3.12 и OpenSSL 3.5 доступны — можно генерировать тестовые сертификаты
  и профили локально, что и сделано для CI.

## 7. Классификация целевых функций

Обозначения: **Supported** — реализуемо средствами клиента без нарушения правил;
**PartiallySupported** — реализуемо с ограничениями, которые нужно честно показать;
**Unsupported** — недостоверно или противоречит API/правилам.

### A. Приватность
| Функция | Статус | Комментарий |
|---|---|---|
| Скрытие телефона/DC/даты регистрации в своём профиле | Supported | уже в базе (`hidePhoneInSettings`, `showDC`) |
| Скрытие реакций, скрытие таба, компактный список | Supported | уже в базе |
| Единый Privacy Center с классификацией | Supported | новый экран, только реальные переключатели |
| «Невидимка» (сервер не видит прочтения/присутствие) | Unsupported | сервер фиксирует read receipts; клиент не может это скрыть |
| Stealth mode Stories | PartiallySupported | в базе есть, но анонимность не гарантируется — подписать в UI |

### B. Локальный архив
| Функция | Статус | Комментарий |
|---|---|---|
| Сохранение текста полученных сообщений | Supported (Partially) | только то, что клиент реально получил; шифрование на диске |
| Поиск по тексту, фильтры по чату/дате/автору | Supported | SQLite FTS |
| Лимиты и срок хранения | Supported | настройка |
| Экспорт и полное удаление | Supported | локально |
| Сохранение медиа | PartiallySupported | объём; отдельная настройка |
| Хранение самоуничтожающихся сообщений | Unsupported | нарушает правила Telegram |
| «История до установки приложения» | Unsupported | данных нет |

### C. Stories
Просмотр, навигация, сохранение своих медиа — Supported (есть в базе).
Анонимный просмотр без Premium — Unsupported: сервер регистрирует просмотр.

### D. UI Customization
Размер текста, темы, анимации, компактный режим — Supported (частично есть в базе).
Новых массовых правок компонентов не требуется.

### E. Локальные инструменты
Перевод через системный механизм, локальный поиск, диагностика с редактированием
секретов — Supported. Скрытая телеметрия — не добавляется.

## 8. План

1. ✅ Аудит (этот документ).
2. CI: генерация согласованных тестовых сертификата/профилей под наш Bundle ID,
   подстановка реальных `api_id`/`api_hash` из Secrets, кэш Bazel. → `tools/ci/`
3. Первая сборка базового IPA на macOS-runner (проверяется только в CI).
4. Модуль Privacy Center (классификация Supported/Partial/Unsupported).
5. Модуль локального архива (SQLite + поиск + экспорт/удаление) и его тесты.
6. Брендинг (имя, иконка, строка «о приложении»).
7. Подписанная сборка (signed mode) и инструкция по установке.

Статусы модулей после реализации фиксируются в `docs/STATUS.md`.
