# Pulse - FastAPI Deployment Guide

This guide covers deploying the Pulse FastAPI application on AWS EC2 with Nginx reverse proxy and SSL certificate using Let's Encrypt.

## 🏗️ Architecture Overview

```
Internet → Cloudflare → Nginx (Port 80/443) → Gunicorn (127.0.0.1:8000) → FastAPI App
```

## 📋 Prerequisites

- AWS EC2 instance (Ubuntu 20.04/22.04)
- Domain/subdomain pointing to EC2 public IP
- Git repository with Pulse FastAPI application
- SSH access to EC2 instance

## 🚀 Initial Deployment

### 1. Server Setup

Connect to your EC2 instance:

```bash
ssh -i your-key.pem ubuntu@ec2-34-201-101-18.compute-1.amazonaws.com
```

Update system and install dependencies:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv nginx git certbot python3-certbot-nginx -y
```

### 2. Clone Repository

```bash
cd /home/ubuntu
git clone https://PulseInsights-Org:PAT@github.com/PulseInsights-Org/pulse-application-layer.git
cd pulse-application-layer
```

### 3. Python Environment Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Environment Configuration

Create `.env` file:

```bash
nano .env
```

Add your environment variables:

```env
SUPABASE_URL=https://qiafwyuzcmqoqxhzqcjq.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFpYWZ3eXV6Y21xb3F4aHpxY2pxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NzgxOTYxNywiZXhwIjoyMDYzMzk1NjE3fQ.XialwEMq5360kdPClHdVWlniXYy94qXxJRg-rtzPhcg
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFpYWZ3eXV6Y21xb3F4aHpxY2pxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDc4MTk2MTcsImV4cCI6MjA2MzM5NTYxN30.Htl8pvbB21SLNDIl9W6h7yAbGpZPAu1nRlK5no3uBYY
```

**Security Note**: Never commit `.env` to version control. Add it to `.gitignore`.

### 5. Test Application

```bash
# Test locally first
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Visit http://your-ec2-ip:8000 to verify it works
# Press Ctrl+C to stop
```

### 6. Gunicorn Configuration

Create `gunicorn.conf.py`:

```bash
nano gunicorn.conf.py
```

```python
# Gunicorn configuration
bind = "127.0.0.1:8000"
workers = 2
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 5
preload_app = True

# Logging
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"
```

Create log directory:

```bash
sudo mkdir -p /var/log/gunicorn
sudo chown ubuntu:ubuntu /var/log/gunicorn
```

### 7. Systemd Service

Create service file:

```bash
sudo nano /etc/systemd/system/pulse-application-layer.service
```

```ini
[Unit]
Description=Pulse Core Application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/pulse-application-layer
Environment="PATH=/home/ubuntu/pulse-application-layer/venv/bin"
EnvironmentFile=/home/ubuntu/pulse-application-layer/.env
ExecStart=/home/ubuntu/pulse-application-layer/venv/bin/gunicorn -c gunicorn.conf.py app.main:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pulse-application-layer
sudo systemctl start pulse-application-layer
sudo systemctl status pulse-application-layer
```

### 8. Nginx Configuration

Create Nginx config:

```bash
sudo nano /etc/nginx/sites-available/pulse-application-layer
```

```nginx
server {
    listen 80;
    server_name dev.pulse-api.getpulseinsights.ai;
    client_max_body_size 50M;

    # For Let's Encrypt challenges
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;

        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/pulse-application-layer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 9. SSL Certificate

Install SSL certificate with Let's Encrypt:

```bash
sudo certbot --nginx -d dev.pulse-api.getpulseinsights.ai
```
