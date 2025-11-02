# Vihaa Vastra Sarees CRM (Flask + SQLite)

A lightweight CRM with Dashboard, Orders, Payments, Customers, Follow-ups, Reports, and Settings. Uses Bootstrap + Chart.js and SQLite.

## Local run (good for Amazon Linux too)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit paths if you want system-wide DB/logs
python app.py          # http://0.0.0.0:5000
```
The app seeds demo data on first run. Remove seeding after going live if you want.

## Production on Amazon Linux (EC2)
Create a directory like `/home/ec2-user/sare` and copy this project there.
Edit `.env` paths like:
```
DATABASE_URL=sqlite:////home/ec2-user/sare/saree_crm.db
LOG_FILE=/home/ec2-user/sare/crm.log
BACKUP_DIR=/home/ec2-user/sare/backups
SECRET_KEY=change-me
```

### Gunicorn (systemd)
Create `/etc/systemd/system/saree_crm.service` from `systemd/saree_crm.service` and then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable saree_crm
sudo systemctl start saree_crm
sudo journalctl -u saree_crm -f
```

### Nginx
Place the file from `nginx/saree_crm.conf` into `/etc/nginx/conf.d/`, check and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Backups
A simple cron to copy the DB:
```
0 2 * * * cp /home/ec2-user/sare/saree_crm.db /home/ec2-user/sare/backups/saree_crm-$(date +\%F).db
```

## Notes
- We keep `db.create_all()` inside `if __name__ == "__main__":` within `app.app_context()` only.
- Numeric fields like `amount` are validated & coerced on the server.
- Logs go to `crm.log` and include full tracebacks.
- CSV export available from the UI.
- Filters on Orders page for payment status and month.
