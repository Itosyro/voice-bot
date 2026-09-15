# DVIZH: перенос сервера и продолжение разработки

Подготовлено 2026-09-15. ПЕРЕНОС ЕЩЁ НЕ ВЫПОЛНЕН. В этой папке только read-only inventory и handoff, не backup и не restore installer.

## Цель владельца

У сервера заканчивается trial; нужен перенос всего рабочего окружения на новый сервер с минимальным ручным участием. После этого разработка продолжится в Claude Code. Не начинать redesign, новый проект или очередную переработку Autopilot. Желаемый интерфейс: подготовка на старом сервере и одна команда восстановления на новом. Сначала выяснить целевой провайдер, ОС, архитектуру, объём диска и разрешённый доступ.

## Известное состояние

- Repo: Itosyro/voice-bot. Здесь ДВА разных проекта. Корневые CLAUDE.md, src/**, migrations/**, tests/test_*.py, Dockerfile, compose-файлы, pyproject.toml, Makefile, README.md относятся прежде всего к Voice Polisher (проект друга). Не применять его /migrate вместо переноса планировщика.
- Старый сервер: rikarishi-dvizh на exe.dev, пользователь exedev (по терминалу владельца). Полная карта live state и ОС ещё не получены.
- Владелец прислал успешный production-отчёт от 2026-09-14 для frontend commit f6b8959c7d05eea434fbe25937b6428b70ed1716. Backup из отчёта: /var/lib/dvizh-release-gate/backups/autopilot.nc8ze2zo. Это backup пяти frontend-файлов, НЕ всей VM. Нынешнее существование backup самостоятельно не проверено.
- Ветка chatgpt/dvizh-daily-stability-2026-09-14 на проверке GitHub 2026-09-15 указывала на этот SHA. Payload: minimal-ui-v1/health-recovery-v1/daily-stability/release-payload/.
- Установлены исправления sync/сохранения задач/AI-черновиков. Реальный Android end-to-end после релиза ещё не подтверждён. Не повторять слова старых handoffs как live proof.
- Foundation dd0c856ddd491beaad10568861fe760d12148835 НЕ устанавливать попутно. Не менять reviewed candidate, права Hermes, sudoers или auth ради обхода ограничений.

## Что действительно сохранить

Исследовать реальные пути, а не считать список исчерпывающим:

1. Все live /opt/dvizh*, static/backend/служебные модули и /var/lib/dvizh* с пользовательскими данными, SQLite/WAL, историей, очередями/подтверждениями и backups; /etc/dvizh и env-файлы. Переносить фактическую установленную версию, а не заново запускать старый installer или git pull main.
2. /home/exedev/.hermes целиком: память, история, настройки, skills, state, рабочие папки, незапушенные изменения. Найти также Hermes runtime, venv и интерпретаторы вне .hermes. Учесть пользовательский hermes-gateway.service и его linger.
3. System/user services, drop-ins, timers, cron, реальные writers вне systemd, UID/GID/группы/permissions. По старому installer могли присутствовать dvizh-auth, dvizh-telegram, dvizh-bridge, dvizh-web-week, dvizh-web-editor, dvizh-training, dvizh-jump, dvizh-social, dvizh-ai-approval и dvizh-ai-home. Проверить все, не ограничиваться тремя active-сервисами из прошлого скриншота.
4. /usr/local/bin/dvizhautopilot, /usr/local/sbin/dvizhgitpush, /usr/local/sbin/dvizhrelease и root-owned configuration/state. Не удалять pending journal, не расширять привилегии и не переиздавать approvals автоматически.
5. Другие проекты сервера, включая проект друга, если он реально размещён здесь: сохранять код, локальные незакоммиченные изменения, env и данные без изменения логики. Обслуживание/остановку согласовать.
6. Docker containers, named/anonymous volumes, bind mounts, внешние диски, custom Docker root/driver; rootless engines и detached volumes отдельно. Docker export не включает volumes; живая копия /var/lib/docker не гарантирует переносимость.
7. Пользовательские настройки GitHub/Claude/Codex и планы вне repo приватно. OAuth может потребовать повторного входа. Копирование credentials не продлевает подписки.

## Особенность exe.dev

HTTPS, *.exe.xyz, /__exe.dev/login, identity headers X-ExeDev-*, SSH gateway и *.int.exe.xyz integrations принадлежат инфраструктуре провайдера. На другом VPS они не появляются от tar/rsync. Выяснить реальный auth contract. Не открывать backend напрямую в Интернет и не подставлять фиксированный user-id в общедоступный proxy. Сохранить привязку владельца к его данным, иначе получится пустой профиль или раскрытие чужих данных. Новый домен/HTTPS/вход согласовать до запуска.

Browser localStorage/sessionStorage остаются на старом origin и не входят в backup VM. Владелец должен синхронизировать настоящие изменения до переключения. Не советовать очищать данные браузера; AI-черновик не является постоянной серверной записью.

## Как завершить перенос

- Запустить inventory.py на старом сервере через разрешённую owner sudo-сессию. Он не выводит содержимое БД, env, ключей, переписок и не меняет службы. Это ограниченное обследование: проверить дополнительно user services, cron, внешние/отключённые volumes, прочие writers и интеграции.
- Получить параметры нового сервера. Обеспечить совместимость ОС/архитектуры/runtime и место. Не перезаписывать сетевые настройки, SSH host keys, machine-id, fstab и весь /etc нового провайдера.
- Создать и проверить зашифрованный backup ВНЕ исходной VM; ключ расшифровки только у владельца. Не публиковать нешифрованные архивы, env или credentials через HTTP/GitHub/чат.
- Bulk copy, затем короткое согласованное окно финальной остановки ВСЕХ writers и финальный snapshot. SQLite: Online Backup API либо корректно остановленные приложения с WAL. Отдельные live snapshots разных БД не дают общей транзакционной согласованности.
- Фиксировать состояния служб до остановки. При неудаче до cutover вернуть только ранее работавшие сервисы. На новом сервере workers/боты/cron остаются OFF, пока не доказана остановка старых. Не запускать два polling-бота/Hermes gateway с одинаковыми credentials.
- Restore в приватный staging, проверка целостности, владельцев/режимов, БД и manifests. На новом сервере не ослаблять защиту под предлогом миграции. Использовать существующие approval boundaries.
- Cutover с сохранением user identity, HTTPS/auth; read-only /api/health обязан вернуть JSON с ok=true и app=dvizh. HTML с HTTP 200 не подходит. Проверить HTTP bytes и ВСЕ сервисы, затем пользователь проверяет реальные данные и сценарии. Не создавать синтетических задач в его БД.
- Старый сервер и независимый backup не удалять до подтверждённого восстановления. После новых записей на target rollback требует согласования данных, а не простого включения старой копии.

## Acceptance

Не смешивать: обнаружено / скопировано / восстановлено / запущено / проверено. Отчёт должен назвать реальные snapshot/backup path, результат проверки восстановления, exact fingerprints, сервисы и volumes, состояние writers на обеих машинах, HTTPS/auth и подтверждение владельца на телефоне. Пока это не выполнено, нельзя писать «всё перенесено».

После миграции — вернуться к задачам, AI Home (текст/голос/озвучка), AI↔Manual, здоровью/тренировкам. Дизайн сохранять. Исправлять подтверждённые блокеры, не развивать инфраструктуру ради инфраструктуры.

## Источники

- https://github.com/Itosyro/voice-bot/tree/f6b8959c7d05eea434fbe25937b6428b70ed1716/minimal-ui-v1/health-recovery-v1/daily-stability
- https://github.com/Itosyro/voice-bot/blob/f6b8959c7d05eea434fbe25937b6428b70ed1716/install-dvizh-ai-home.sh
- https://exe.dev/docs/proxy
- https://exe.dev/docs/login-with-exe
- https://exe.dev/docs/faq/copy-files
- https://www.sqlite.org/backup.html
- https://docs.docker.com/engine/storage/volumes/
