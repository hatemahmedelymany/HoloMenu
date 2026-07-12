import os
import subprocess
import pymysql
import sys
import re

def run_command(cmd, env_update=None):
    env = os.environ.copy()
    if env_update:
        env.update(env_update)
    if cmd.startswith("python "):
        cmd = cmd.replace("python ", f'"{sys.executable}" ', 1)
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    return res

def main():
    db_name = "holomenu_migration_verify_db"
    
    # 1. Connect to MySQL as root
    try:
        conn = pymysql.connect(
            host="localhost",
            port=3306,
            user="root",
            password="",
            charset="utf8mb4"
        )
        conn.autocommit = True
    except Exception as e:
        print(f"[-] Cannot connect to MySQL: {e}")
        sys.exit(1)

    print("[+] Recreating database to extract clean schema...")
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
        cur.execute(f"CREATE DATABASE {db_name}")

    # 2. Run migrations
    print("[+] Running Alembic migrations...")
    res = run_command("python -m alembic upgrade head", {
        "DB_NAME": db_name,
        "DB_USER": "root",
        "DB_PASSWORD": ""
    })
    if res.returncode != 0:
        print(f"[-] Alembic upgrade failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        sys.exit(1)

    # Connect to the migrated DB
    conn.select_db(db_name)
    
    tables_order = [
        "tenants",
        "departments",
        "products",
        "orders",
        "kiosks",
        "order_items",
        "analytics_events",
        "admins",
        "refresh_tokens",
        "audit_logs",
        "payments",
        "websocket_sessions"
    ]
    
    schema_parts = []
    with conn.cursor() as cur:
        for t in tables_order:
            cur.execute(f"SHOW CREATE TABLE {t}")
            row = cur.fetchone()
            create_sql = row[1]
            
            # Clean up the create SQL (remove AUTO_INCREMENT=X)
            create_sql = re.sub(r'AUTO_INCREMENT=\d+\s*', '', create_sql)
            
            # format nicely
            schema_parts.append(f"-- ─── {t.upper()} ───\n{create_sql};\n")

    # Read the seed data from the existing holomenu_db.sql
    seed_data = ""
    if os.path.exists("holomenu_db.sql"):
        with open("holomenu_db.sql", "r", encoding="utf-8") as f:
            content = f.read()
        
        idx = content.find("-- ─── SEED DATA ───")
        if idx != -1:
            seed_data = content[idx:]
        else:
            # Fallback to general seed data start
            idx = content.find("INSERT INTO tenants")
            if idx != -1:
                seed_data = "-- ─── SEED DATA ───\n\n" + content[idx:]
                
    # If we couldn't find seed data, throw an error
    if not seed_data:
        print("[-] Could not find seed data section in existing holomenu_db.sql")
        sys.exit(1)

    # 3. Assemble and write the new holomenu_db.sql
    new_sql = """-- HoloMenu Database Schema
-- Synchronized with Alembic migrations at head (SaaS Readiness Baseline)
-- Run: mysql -u holomenu_app -p < holomenu_db.sql

CREATE DATABASE IF NOT EXISTS holomenu_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE holomenu_db;

"""
    for part in schema_parts:
        new_sql += part + "\n"
        
    new_sql += seed_data

    with open("holomenu_db.sql", "w", encoding="utf-8") as f:
        f.write(new_sql)
    print("[SUCCESS] holomenu_db.sql successfully rebuilt and synchronized with Alembic migrations!")

    # Clean up verification database
    conn.select_db("mysql")
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    conn.close()

if __name__ == "__main__":
    main()
