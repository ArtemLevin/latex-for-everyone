#!/bin/bash
# scripts/setup.sh

set -e

echo "🚀 Setting up Latexed Backend..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "📦 Python version: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env if not exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please update .env with your settings"
fi

# Initialize database
echo "🗄️  Initializing database..."
alembic upgrade head

# Create directories
echo "📁 Creating directories..."
mkdir -p /tmp/latexed_compiles
mkdir -p /tmp/latexed_uploads/exports

# Check if pdflatex is available
if command -v pdflatex &> /dev/null; then
    echo "✅ pdflatex found: $(which pdflatex)"
    pdflatex --version | head -1
else
    echo "⚠️  pdflatex not found! Install texlive:"
    echo "   Ubuntu/Debian: sudo apt-get install texlive-latex-base texlive-latex-extra texlive-lang-cyrillic"
    echo "   macOS: brew install --cask mactex"
fi

echo ""
echo "✅ Setup complete!"
echo "🏃 Start server: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo "📖 API Docs: http://localhost:8000/api/docs"
