import os
import subprocess
import pymysql
import sys

def run_command(cmd, env_update=None):
    env = os.environ.copy()
    if env_update:
        env.update(env_update)
    # Use sys.executable to run subprocess using the active virtual environment's Python
    if cmd.startswith("python "):
        cmd = cmd.replace("python ", f'"{sys.executable}" ', 1)
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    return res

def execute_sql_file(cur, filepath, target_db):
    with open(filepath, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    # Standardize database name references
    sql = sql.replace("holomenu_db", target_db)
    
    # Cleanly strip out CREATE DATABASE and USE statements by finding USE target_db;
    use_stmt = f"USE {target_db};"
    idx = sql.find(use_stmt)
    if idx != -1:
        sql = sql[idx + len(use_stmt):]
    
    # Simple query splitter (by semicolon)
    statements = sql.split(';')
    for stmt in statements:
        stmt = stmt.strip()
        if not stmt:
            continue
        safe_print = stmt[:80].replace(chr(10), ' ').encode('ascii', errors='replace').decode('ascii')
        print(f"Executing statement snippet: {safe_print}...")
        cur.execute(stmt)

def main():
    db_name_mig = "holomenu_migration_verify_db"
    db_name_boot = "holomenu_bootstrap_verify_db"

    # Connect to MySQL as root
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

    print("[+] Recreating verification databases...")
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name_mig}")
        cur.execute(f"CREATE DATABASE {db_name_mig}")
        cur.execute(f"DROP DATABASE IF EXISTS {db_name_boot}")
        cur.execute(f"CREATE DATABASE {db_name_boot}")

    # 1. Load holomenu_db.sql into bootstrap verification DB
    print(f"[+] Loading holomenu_db.sql into {db_name_boot}...")
    try:
        conn.select_db(db_name_boot)
        with conn.cursor() as cur:
            execute_sql_file(cur, "holomenu_db.sql", db_name_boot)
    except Exception as e:
        print(f"[-] Failed to load holomenu_db.sql: {e}")
        sys.exit(1)

    # 2. Run Alembic upgrade head against migration verification DB
    print(f"[+] Running Alembic migrations against {db_name_mig}...")
    res = run_command("python -m alembic upgrade head", {
        "DB_NAME": db_name_mig,
        "DB_USER": "root",
        "DB_PASSWORD": ""
    })
    if res.returncode != 0:
        print(f"[-] Alembic upgrade failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        sys.exit(1)
    print("[+] Alembic migrations completed successfully.")

    # 3. Compare schemas
    conn.select_db("information_schema")
    
    col_query = """
        SELECT table_name, column_name, data_type, is_nullable, character_maximum_length 
        FROM columns 
        WHERE table_schema = %s AND table_name != 'alembic_version'
        ORDER BY table_name, column_name
    """
    
    with conn.cursor() as cur:
        cur.execute(col_query, (db_name_mig,))
        cols_mig = cur.fetchall()
        
        cur.execute(col_query, (db_name_boot,))
        cols_boot = cur.fetchall()

    const_query = """
        SELECT table_name, constraint_name, constraint_type 
        FROM table_constraints 
        WHERE table_schema = %s AND table_name != 'alembic_version'
        ORDER BY table_name, constraint_name
    """
    with conn.cursor() as cur:
        cur.execute(const_query, (db_name_mig,))
        consts_mig = cur.fetchall()
        
        cur.execute(const_query, (db_name_boot,))
        consts_boot = cur.fetchall()

    idx_query = """
        SELECT table_name, index_name, column_name, non_unique 
        FROM statistics 
        WHERE table_schema = %s AND table_name != 'alembic_version'
        ORDER BY table_name, index_name, column_name
    """
    with conn.cursor() as cur:
        cur.execute(idx_query, (db_name_mig,))
        idx_mig = cur.fetchall()
        
        cur.execute(idx_query, (db_name_boot,))
        idx_boot = cur.fetchall()

    print("[+] Comparing columns...")
    cols_diff = set(cols_mig) ^ set(cols_boot)
    if not cols_diff:
        print("[OK] Column structures are identical.")
    else:
        print("[-] Column differences found:")
        for diff in cols_diff:
            if diff in cols_mig:
                print(f"  Only in Migrated DB: Table '{diff[0]}', Col '{diff[1]}', Type '{diff[2]}', Nullable? {diff[3]}")
            else:
                print(f"  Only in Bootstrap DB (holomenu_db.sql): Table '{diff[0]}', Col '{diff[1]}', Type '{diff[2]}', Nullable? {diff[3]}")

    print("[+] Comparing constraints...")
    consts_mig_normalized = {(row[0], row[2]) for row in consts_mig}
    consts_boot_normalized = {(row[0], row[2]) for row in consts_boot}
    consts_diff = consts_mig_normalized ^ consts_boot_normalized
    if not consts_diff:
        print("[OK] Constraints are identical.")
    else:
        print("[-] Constraint differences found:")
        for diff in consts_diff:
            if diff in consts_mig_normalized:
                print(f"  Only in Migrated DB: Table '{diff[0]}', Constraint Type '{diff[1]}'")
            else:
                print(f"  Only in Bootstrap DB: Table '{diff[0]}', Constraint Type '{diff[1]}'")

    print("[+] Comparing indexes...")
    idx_mig_normalized = {(row[0], row[2], row[3]) for row in idx_mig}
    idx_boot_normalized = {(row[0], row[2], row[3]) for row in idx_boot}
    idx_diff = idx_mig_normalized ^ idx_boot_normalized
    if not idx_diff:
        print("[OK] Indexes are identical.")
    else:
        print("[-] Index differences found:")
        for diff in idx_diff:
            if diff in idx_mig_normalized:
                print(f"  Only in Migrated DB: Table '{diff[0]}', Indexed Col '{diff[1]}', Non-unique? {diff[2]}")
            else:
                print(f"  Only in Bootstrap DB: Table '{diff[0]}', Indexed Col '{diff[1]}', Non-unique? {diff[2]}")

    print("[+] Cleaning up verification databases...")
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name_mig}")
        cur.execute(f"DROP DATABASE IF EXISTS {db_name_boot}")
    conn.close()

    if cols_diff or consts_diff or idx_diff:
        print("[-] Schema check failed. The bootstrap file and migrations are NOT in sync.")
        sys.exit(1)
    else:
        print("[SUCCESS] Schema checks passed. Alembic migrations and holomenu_db.sql are in perfect sync!")

if __name__ == "__main__":
    main()
