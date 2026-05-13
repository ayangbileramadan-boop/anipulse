# Deployment Guide — AniPulse

This guide covers deploying AniPulse to production environments.

## Table of Contents
- [Quick Deploy with Docker](#quick-deploy-with-docker)
- [Manual Deployment](#manual-deployment)
- [Platform-Specific Guides](#platform-specific-guides)
- [Post-Deployment](#post-deployment)

---

## Quick Deploy with Docker

### Prerequisites
- Docker & Docker Compose installed
- Domain name (optional)

### Steps

1. **Clone & Configure**
   ```bash
   git clone <your-repo>
   cd anipulse
   cp .env.example .env
   # Edit .env with production values
   ```

2. **Update `.env` for Production**
   ```env
   DEBUG=False
   SECRET_KEY=<generate-strong-random-key>
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   
   DB_NAME=anipulse
   DB_USER=anipulse
   DB_PASSWORD=<strong-password>
   DB_HOST=db
   DB_PORT=5432
   
   REDIS_URL=redis://redis:6379/0
   CORS_ORIGINS=https://yourdomain.com
   ```

3. **Build & Run**
   ```bash
   docker-compose up -d --build
   ```

4. **Initialize Database**
   ```bash
   docker-compose exec web python manage.py migrate
   docker-compose exec web python manage.py createsuperuser
   docker-compose exec web python manage.py collectstatic --noinput
   ```

5. **Set Up Periodic Tasks**
   ```bash
   docker-compose exec web python manage.py shell
   ```
   ```python
   from django_celery_beat.models import PeriodicTask, IntervalSchedule
   
   # Create schedules
   hourly = IntervalSchedule.objects.create(every=1, period='hours')
   every_6h = IntervalSchedule.objects.create(every=6, period='hours')
   every_15m = IntervalSchedule.objects.create(every=15, period='minutes')
   
   # Sync trending every hour
   PeriodicTask.objects.create(
       interval=hourly,
       name='Sync trending anime',
       task='anime.sync_trending',
   )
   
   # Sync seasonal every 6 hours
   PeriodicTask.objects.create(
       interval=every_6h,
       name='Sync seasonal anime',
       task='anime.sync_seasonal',
   )
   
   # Fetch airing schedule every 15 minutes
   PeriodicTask.objects.create(
       interval=every_15m,
       name='Fetch airing schedule',
       task='anime.fetch_airing_schedule',
   )
   ```

6. **Access**
   - App: http://localhost
   - Admin: http://localhost/admin/

---

## Manual Deployment

### On Ubuntu/Debian VPS

#### 1. Install Dependencies
```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql redis-server nginx
```

#### 2. Set Up PostgreSQL
```bash
sudo -u postgres psql
CREATE DATABASE anipulse;
CREATE USER anipulse WITH PASSWORD 'strong_password';
GRANT ALL PRIVILEGES ON DATABASE anipulse TO anipulse;
\q
```

#### 3. Clone & Set Up App
```bash
cd /var/www
sudo git clone <your-repo> anipulse
cd anipulse
sudo chown -R $USER:$USER .

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

#### 4. Configure Environment
```bash
cp .env.example .env
nano .env  # Edit with production settings
```

#### 5. Run Migrations
```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

#### 6. Set Up Gunicorn Service
Create `/etc/systemd/system/anipulse.service`:
```ini
[Unit]
Description=AniPulse Gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/anipulse
Environment="PATH=/var/www/anipulse/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
EnvironmentFile=/var/www/anipulse/.env
ExecStart=/var/www/anipulse/venv/bin/gunicorn config.wsgi:application \
    --workers 4 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile /var/log/anipulse/access.log \
    --error-logfile /var/log/anipulse/error.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir /var/log/anipulse
sudo chown www-data:www-data /var/log/anipulse
sudo systemctl enable anipulse
sudo systemctl start anipulse
```

#### 7. Set Up Celery Services

Create `/etc/systemd/system/celery.service`:
```ini
[Unit]
Description=Celery Worker
After=network.target

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/var/www/anipulse
Environment="PATH=/var/www/anipulse/venv/bin"
EnvironmentFile=/var/www/anipulse/.env
ExecStart=/var/www/anipulse/venv/bin/celery -A config worker -l info --detach

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/celery-beat.service`:
```ini
[Unit]
Description=Celery Beat Scheduler
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/anipulse
Environment="PATH=/var/www/anipulse/venv/bin"
EnvironmentFile=/var/www/anipulse/.env
ExecStart=/var/www/anipulse/venv/bin/celery -A config beat -l info

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable celery celery-beat
sudo systemctl start celery celery-beat
```

#### 8. Configure Nginx
Create `/etc/nginx/sites-available/anipulse`:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    client_max_body_size 20M;

    location /static/ {
        alias /var/www/anipulse/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /var/www/anipulse/media/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/anipulse /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 9. SSL with Let's Encrypt
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

---

## Platform-Specific Guides

### Railway
1. Create new project
2. Add PostgreSQL & Redis services
3. Connect GitHub repo
4. Set environment variables
5. Deploy

### Heroku
```bash
heroku create anipulse
heroku addons:create heroku-postgresql:mini
heroku addons:create heroku-redis:mini
heroku config:set DJANGO_SETTINGS_MODULE=config.settings.production
git push heroku main
heroku run python manage.py migrate
```

### AWS (Elastic Beanstalk)
1. Install EB CLI: `pip install awsebcli`
2. Initialize: `eb init -p python-3.11 anipulse`
3. Create environment: `eb create anipulse-env`
4. Add RDS PostgreSQL & ElastiCache Redis
5. Deploy: `eb deploy`

### DigitalOcean App Platform
1. Create new app from GitHub
2. Add managed PostgreSQL & Redis
3. Set build/run commands
4. Deploy

---

## Post-Deployment

### 1. Monitor Services
```bash
# Check Django
sudo systemctl status anipulse

# Check Celery
sudo systemctl status celery celery-beat

# View logs
sudo journalctl -u anipulse -f
sudo tail -f /var/log/anipulse/error.log
```

### 2. Set Up Monitoring
- **Sentry**: Add `SENTRY_DSN` to `.env`
- **Uptime**: Use UptimeRobot or similar
- **Performance**: New Relic, Datadog, or Grafana

### 3. Backups
```bash
# Database backup script
#!/bin/bash
pg_dump -U anipulse anipulse | gzip > backup-$(date +%Y%m%d).sql.gz
```

Add to crontab: `0 2 * * * /path/to/backup.sh`

### 4. Security Checklist
- [x] `DEBUG=False` in production
- [x] Strong `SECRET_KEY`
- [x] HTTPS enabled
- [x] `ALLOWED_HOSTS` configured
- [x] Database password is strong
- [x] Firewall configured (only 80, 443, SSH open)
- [x] Regular security updates: `sudo apt update && sudo apt upgrade`

---

## Troubleshooting

### Issue: 502 Bad Gateway
**Check:** Is Gunicorn running?
```bash
sudo systemctl status anipulse
sudo journalctl -u anipulse -n 50
```

### Issue: Static files not loading
**Fix:**
```bash
python manage.py collectstatic --noinput
sudo systemctl restart nginx
```

### Issue: Celery tasks not executing
**Check:**
```bash
sudo systemctl status celery celery-beat
celery -A config inspect active
```

### Issue: Database connection errors
**Check:** PostgreSQL is running and credentials are correct
```bash
sudo systemctl status postgresql
psql -U anipulse -d anipulse  # Test connection
```

---

## Scaling Tips

### Horizontal Scaling
- Use load balancer (AWS ELB, nginx upstream)
- Run multiple Gunicorn instances
- Scale Celery workers independently

### Database Optimization
- Enable read replicas
- Use PgBouncer for connection pooling
- Regular VACUUM and ANALYZE

### Caching
- Use CDN (CloudFront, Cloudflare) for static assets
- Enable Redis cache for expensive queries
- Cache AniList API responses aggressively

---

**Need help?** Open an issue on GitHub or check the main README.
