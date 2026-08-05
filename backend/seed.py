import os
import subprocess

with open(".env", "r") as f:
    lines = f.readlines()

db_url = None
for line in lines:
    if line.startswith("External_Database_URL="):
        db_url = line.split("=", 1)[1].strip()
        break

if db_url:
    print(f"Found External_Database_URL")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    cmd = f'docker-compose run --rm -v "%cd%:/app" -e DATABASE_URL="{db_url}" -e PYTHONPATH=/app -e SEED_ADMIN_EMAIL="gupta.yash0702@gmail.com" -e SEED_ADMIN_PASSWORD="password123" api python -m scripts.seed_super_admin'
    print("Running:", cmd)
    subprocess.run(cmd, shell=True)
else:
    print("External_Database_URL not found in .env")
