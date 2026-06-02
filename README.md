# Latexed Backend

Backend API for **Latexed** — online LaTeX editor with live preview.

## Stack

- **FastAPI** — web framework
- **SQLAlchemy** — ORM
- **SQLite/PostgreSQL** — database
- **pdflatex** — LaTeX compiler
- **Celery + Redis** — async task queue (prod)
- **Docker + Nginx** — deployment

## Quick Start

### Development

```bash
# Clone and setup
git clone <repo>
cd latex-for-everyone/backend

# Run setup script
chmod +x scripts/setup.sh
./scripts/setup.sh

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/api/docs

### Docker

```bash
cd backend
docker-compose up --build
```

### Production

```bash
# Set environment variables
cp .env.example .env
# Edit .env with production values

# Deploy
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/projects/` | List projects |
| POST | `/api/projects/` | Create project |
| GET | `/api/projects/{id}` | Get project details |
| PUT | `/api/projects/{id}` | Update project |
| DELETE | `/api/projects/{id}` | Delete project |
| POST | `/api/projects/{id}/duplicate` | Duplicate project |
| GET | `/api/files/project/{id}` | List files |
| POST | `/api/files/project/{id}` | Create file |
| PUT | `/api/files/{id}` | Update file |
| DELETE | `/api/files/{id}` | Delete file |
| POST | `/api/compile/` | Compile project |
| POST | `/api/compile/raw` | Compile raw LaTeX |
| GET | `/api/compile/history/{id}` | Compile history |
| POST | `/api/export/pdf` | Export to PDF |
| POST | `/api/export/html` | Export to HTML |
| POST | `/api/export/tex` | Export to TEX (zip) |
| GET | `/api/templates/` | List templates |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./latexed.db` | Database connection string |
| `DEBUG` | `false` | Debug mode |
| `SECRET_KEY` | `change-me` | Secret key for JWT |
| `LATEX_COMPILER` | `pdflatex` | LaTeX compiler binary |
| `COMPILE_TIMEOUT` | `30` | Compilation timeout (seconds) |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |

## Testing

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

## License

MIT
