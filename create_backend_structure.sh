#!/usr/bin/env bash

# Останавливаем скрипт при любой ошибке
set -e

# Корневая папка проекта
ROOT_DIR="backend"

# Создаём папки
mkdir -p "$ROOT_DIR/app/routers"
mkdir -p "$ROOT_DIR/app/services"
mkdir -p "$ROOT_DIR/alembic/versions"
mkdir -p "$ROOT_DIR/nginx"
mkdir -p "$ROOT_DIR/scripts"

# Создаём файлы в app
touch "$ROOT_DIR/app/__init__.py"
touch "$ROOT_DIR/app/main.py"
touch "$ROOT_DIR/app/config.py"
touch "$ROOT_DIR/app/database.py"
touch "$ROOT_DIR/app/models.py"
touch "$ROOT_DIR/app/schemas.py"
touch "$ROOT_DIR/app/dependencies.py"

# Создаём файлы в routers
touch "$ROOT_DIR/app/routers/__init__.py"
touch "$ROOT_DIR/app/routers/files.py"
touch "$ROOT_DIR/app/routers/compile.py"
touch "$ROOT_DIR/app/routers/export.py"
touch "$ROOT_DIR/app/routers/templates.py"
touch "$ROOT_DIR/app/routers/projects.py"

# Создаём файлы в services
touch "$ROOT_DIR/app/services/__init__.py"
touch "$ROOT_DIR/app/services/latex_compiler.py"
touch "$ROOT_DIR/app/services/pdf_generator.py"

# Создаём файлы Alembic
touch "$ROOT_DIR/alembic/env.py"
touch "$ROOT_DIR/alembic/script.py.mako"

# Создаём файлы в корне backend
touch "$ROOT_DIR/alembic.ini"
touch "$ROOT_DIR/Dockerfile"
touch "$ROOT_DIR/docker-compose.yml"
touch "$ROOT_DIR/docker-compose.prod.yml"
touch "$ROOT_DIR/requirements.txt"
touch "$ROOT_DIR/.env.example"

# Создаём nginx config
touch "$ROOT_DIR/nginx/nginx.conf"

# Создаём scripts
touch "$ROOT_DIR/scripts/setup.sh"
touch "$ROOT_DIR/scripts/deploy.sh"

# Делаем shell-скрипты исполняемыми
chmod +x "$ROOT_DIR/scripts/setup.sh"
chmod +x "$ROOT_DIR/scripts/deploy.sh"

echo "Структура backend успешно создана."