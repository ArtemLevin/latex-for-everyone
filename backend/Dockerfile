FROM python:3.12-slim

# Install TeX Live (minimal) and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-bibtex-extra \
    texlive-lang-cyrillic \
    texlive-science \
    latexmk \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create necessary directories
RUN mkdir -p /tmp/latexed_compiles /tmp/latexed_uploads

# Run migrations and start
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"]
