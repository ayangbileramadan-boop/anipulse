# AniPulse — Anime Discovery & Tracking Platform

> A modern, production-ready anime tracking platform built with Django + React. Powered by the AniList GraphQL API.

![Tech Stack](https://img.shields.io/badge/Django-5.0-092E20?logo=django)
![Tech Stack](https://img.shields.io/badge/React-18.3-61DAFB?logo=react)
![Tech Stack](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)
![Tech Stack](https://img.shields.io/badge/Redis-7.2-DC382D?logo=redis)

**Features:**
- 🔥 Trending anime discovery
- 📅 Live airing calendar
- ⭐ Personal watchlist with progress tracking
- 🎯 Content-based recommendations
- 🔍 Advanced search with filters
- 📱 Fully responsive UI
- 🚀 Production-ready architecture

---

## 📦 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- Node.js 18+ (for frontend)

### 1. Clone & Setup Backend

```bash
cd anipulse

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env with your database credentials
```

### 2. Database Setup

```bash
# Create PostgreSQL database
createdb anipulse

# Or using psql:
psql -U postgres
CREATE DATABASE anipulse;
CREATE USER anipulse WITH PASSWORD 'anipulse_password';
GRANT ALL PRIVILEGES ON DATABASE anipulse TO anipulse;
\q

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 3. Start Services

**Terminal 1 — Django Dev Server:**
```bash
python manage.py runserver
```

**Terminal 2 — Celery Worker (optional for background sync):**
```bash
celery -A config worker -l info
```

**Terminal 3 — Celery Beat (optional for scheduled tasks):**
```bash
celery -A config beat -l info
```

**Terminal 4 — Frontend Dev Server:**
```bash
cd frontend
npm install
npm run dev
```

### 4. Access the App

- **Frontend:** http://localhost:5173
- **API:** http://localhost:8000/api/v1/
- **API Docs:** http://localhost:8000/api/docs/
- **Admin:** http://localhost:8000/admin/

---

## 🏗️ Architecture Overview

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   React     │─────▶│    Django    │─────▶│  PostgreSQL │
│   (Vite)    │ HTTP │ REST API     │ ORM  │   Database  │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            ├───▶ Redis (Cache + Celery)
                            │
                            └───▶ AniList GraphQL API
```

### Backend Stack
- **Django 5.0**: Web framework
- **Django REST Framework**: API endpoints
- **PostgreSQL**: Primary database
- **Redis**: Caching + Celery broker
- **Celery**: Background tasks (sync trending, airing schedule)
- **httpx**: AniList API client

### Frontend Stack (in `/frontend`)
- **React 18**: UI library
- **Vite**: Build tool
- **React Router**: Client-side routing
- **Zustand**: State management
- **React Query**: Server state + caching
- **Tailwind CSS**: Styling

---

## 📂 Project Structure

```
anipulse/
├── config/                 # Django settings
│   ├── settings/
│   │   ├── base.py        # Shared settings
│   │   ├── development.py # Dev config
│   │   └── production.py  # Production config
│   ├── urls.py
│   ├── wsgi.py
│   └── celery.py          # Celery app
├── apps/
│   ├── core/              # Shared utilities
│   ├── anime/             # Anime models, AniList sync
│   │   ├── services/
│   │   │   ├── anilist.py # GraphQL client
│   │   │   └── sync.py    # DB sync logic
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   └── tasks.py       # Celery tasks
│   ├── users/             # Authentication
│   ├── watchlist/         # Progress tracking
│   └── recommendations/   # Recommendation engine
├── frontend/              # React SPA
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── store/         # Zustand stores
│   │   └── lib/           # API client, utils
│   ├── package.json
│   └── vite.config.js
├── requirements.txt
├── manage.py
└── README.md
```

---

## 🔌 API Endpoints

### Anime
- `GET /api/v1/anime/` — List anime (from local DB)
- `GET /api/v1/anime/{slug}/` — Anime detail
- `GET /api/v1/anime/trending/` — Live trending (AniList)
- `GET /api/v1/anime/airing-today/` — Airing in next 24h
- `GET /api/v1/anime/calendar/` — 7-day schedule
- `GET /api/v1/anime/search/` — Search with filters
- `GET /api/v1/anime/{slug}/episodes/` — Episode list

### Users
- `POST /api/v1/users/register/` — Create account
- `POST /api/v1/users/login/` — Get auth token
- `DELETE /api/v1/users/logout/` — Revoke token
- `GET /api/v1/users/me/` — Current user profile
- `PATCH /api/v1/users/me/` — Update profile
- `GET /api/v1/users/{username}/` — Public profile

### Watchlist
- `GET /api/v1/watchlist/` — User's full list
- `POST /api/v1/watchlist/` — Add anime
- `PATCH /api/v1/watchlist/{id}/` — Update entry
- `DELETE /api/v1/watchlist/{id}/` — Remove anime
- `PATCH /api/v1/watchlist/{id}/increment_episode/` — +1 episode

### Recommendations
- `GET /api/v1/recommendations/` — Personalized suggestions

---

## ⚙️ Configuration

### Environment Variables (`.env`)

```env
# Django
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=anipulse
DB_USER=anipulse
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# CORS (frontend URLs)
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Optional
SENTRY_DSN=  # For error tracking in production
```

### Celery Beat Schedule

Background tasks run automatically when Celery Beat is running:

- **sync_trending_anime**: Every 1 hour
- **sync_seasonal_anime**: Every 6 hours
- **fetch_airing_schedule**: Every 15 minutes

Configure in Django admin under `Periodic Tasks` or in `config/settings/base.py`.

---

## 🚀 Deployment

### Production Checklist

1. **Environment**
   ```bash
   export DJANGO_SETTINGS_MODULE=config.settings.production
   DEBUG=False
   SECRET_KEY=<generate-strong-key>
   ```

2. **Static Files**
   ```bash
   python manage.py collectstatic --noinput
   ```

3. **Database**
   - Use managed PostgreSQL (RDS, Cloud SQL, etc.)
   - Enable SSL connections
   - Set up read replicas for scale

4. **Redis**
   - Use managed Redis (ElastiCache, Cloud Memorystore)
   - Enable persistence

5. **Celery**
   - Run workers in separate containers/processes
   - Monitor with Flower: `celery -A config flower`

6. **Web Server**
   ```bash
   gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
   ```

7. **Reverse Proxy**
   - Nginx or Cloudflare in front
   - Serve `/static/` and `/media/` directly
   - SSL/TLS certificates

8. **Frontend Build**
   ```bash
   cd frontend
   npm run build
   # Serve dist/ via Nginx or S3+CloudFront
   ```

### Docker Deployment (Optional)

Create `docker-compose.yml`:
```yaml
version: '3.9'
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: anipulse
      POSTGRES_USER: anipulse
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

  web:
    build: .
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    env_file:
      - .env

  celery:
    build: .
    command: celery -A config worker -l info
    depends_on:
      - db
      - redis
    env_file:
      - .env

  celery-beat:
    build: .
    command: celery -A config beat -l info
    depends_on:
      - db
      - redis
    env_file:
      - .env

volumes:
  postgres_data:
```

---

## 🧪 Testing

```bash
# Run backend tests
python manage.py test

# Frontend tests
cd frontend
npm test
```

---

## 📊 Performance Optimization

### Caching Strategy
- **AniList API responses**: 1-6 hours depending on endpoint
- **Database queries**: `select_related()` and `prefetch_related()` everywhere
- **Static assets**: WhiteNoise with compression + CDN

### Database Indexes
- `trending`, `popularity`: For sorting/filtering
- `status`, `season_year`: For seasonal queries
- `(user, status)`: For watchlist filtering
- `slug`: For URL lookups

### Scaling Tips
1. Enable Django query caching via Redis
2. Add read replicas for DB
3. Use CDN for images (cover, banner)
4. Horizontal scaling with load balancer
5. Upgrade to async views (Django 5.0+ ASGI)

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📝 API Integration Notes

### AniList GraphQL API
- **Rate Limit**: 90 requests/minute
- **Cache Strategy**: All queries cached in Redis to stay under limits
- **Auth**: No API key required (public endpoints)
- **Docs**: https://anilist.gitbook.io/anilist-apiv2-docs

### Important Data Points
- `anilist_id`: Primary key for syncing
- `slug`: URL-safe unique identifier
- `nextAiringEpisode`: Contains Unix timestamp + episode number
- Adult content is filtered out by default (`isAdult: false`)

---

## 🐛 Troubleshooting

### Issue: "Connection refused" to PostgreSQL
**Fix:**
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql
sudo systemctl start postgresql

# Verify connection
psql -U anipulse -d anipulse
```

### Issue: Redis connection errors
**Fix:**
```bash
# Check Redis
redis-cli ping  # Should return "PONG"

# If not running:
sudo systemctl start redis
```

### Issue: CORS errors in frontend
**Fix:** Add frontend URL to `CORS_ORIGINS` in `.env`

### Issue: Celery tasks not running
**Fix:**
```bash
# Check if worker is running
celery -A config inspect active

# Check Beat scheduler
celery -A config beat -l debug
```

---

## 📚 Additional Resources

- **Django Docs**: https://docs.djangoproject.com/
- **DRF Docs**: https://www.django-rest-framework.org/
- **AniList API**: https://anilist.gitbook.io/anilist-apiv2-docs/
- **Celery Docs**: https://docs.celeryproject.org/
- **React Query**: https://tanstack.com/query/latest

---

## 📄 License

MIT License - feel free to use this project for learning or production.

---

## 🎉 Acknowledgments

- **AniList** for the incredible GraphQL API
- **MyAnimeList** for pioneering anime tracking
- **Anthropic** for Claude assistance in development

---

**Built with ❤️ by the anime community, for the anime community.**
