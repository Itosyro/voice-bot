# DVIZH Hermes control v1

Безопасный read-only слой между Hermes и продакшен-сервером ДВИЖа.

## Что устанавливается

- `/usr/local/bin/dvizhctl` — ограниченный CLI для диагностики;
- `~/.hermes/skills/dvizh/dvizh-server/SKILL.md` — Hermes skill, который направляет диагностику через `dvizhctl`.

## Разрешено

- `dvizhctl status`
- `dvizhctl doctor`
- `dvizhctl logs <service> [1..300]`
- `dvizhctl paths`
- `dvizhctl version`

## Запрещено в v1

Restart, deploy, rollback, изменение БД/конфигурации, установка пакетов и чтение credential-файлов. Логи проходят автоматическую базовую редакцию распространённых токенов/ключей/паролей.

## Установка

Использовать locked installer `install-dvizh-hermes-control.sh` с конкретного протестированного commit SHA.
