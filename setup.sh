#!/bin/bash

# AniPulse Quick Setup Script

echo "🎌 AniPulse Setup Script"
echo "========================"
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version
if [ $? -ne 0 ]; then
    echo "❌ Python 3 not found. Please install Python 3.11+"
    exit 1
fi

# Check PostgreSQL
echo "Checking PostgreSQL..."
psql --version
if [ $? -ne 0 ]; then
    echo "⚠️  PostgreSQL not found. You'll need to install it."
fi

# Check Redis
echo "Checking Redis..."
redis-cli --version
if [ $? -ne 0 ]; then
    echo "⚠️  Redis not found. You'll need to install it."
fi

echo ""
echo "Step 1: Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo ""
echo "Step 2: Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Step 3: Setting up environment file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env file. Please edit it with your database credentials."
else
    echo "ℹ️  .env file already exists."
fi

echo ""
echo "Step 4: Database setup..."
read -p "Have you created the PostgreSQL database 'anipulse'? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Running migrations..."
    python manage.py migrate
    
    echo ""
    echo "Creating superuser..."
    python manage.py createsuperuser
else
    echo "Please create the database first:"
    echo "  createdb anipulse"
    echo "  # OR"
    echo "  psql -U postgres -c 'CREATE DATABASE anipulse;'"
fi

echo ""
echo "Step 5: Frontend setup..."
if [ -d "frontend" ]; then
    cd frontend
    if command -v npm &> /dev/null; then
        echo "Installing frontend dependencies..."
        npm install
        cd ..
    else
        echo "⚠️  npm not found. Please install Node.js 18+ to build frontend."
        cd ..
    fi
else
    echo "Frontend directory not found."
fi

echo ""
echo "=========================================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your database credentials"
echo "  2. Run migrations: python manage.py migrate"
echo "  3. Create superuser: python manage.py createsuperuser"
echo "  4. Start Django: python manage.py runserver"
echo "  5. Start frontend: cd frontend && npm run dev"
echo "  6. (Optional) Start Celery: celery -A config worker -l info"
echo ""
echo "Access points:"
echo "  - Frontend: http://localhost:5173"
echo "  - API: http://localhost:8000/api/v1/"
echo "  - Admin: http://localhost:8000/admin/"
echo "  - API Docs: http://localhost:8000/api/docs/"
echo ""
echo "Happy tracking! 🎌"
