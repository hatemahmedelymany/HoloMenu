import pymysql
import sys

def setup_user():
    try:
        # Connect to MySQL as root with no password
        conn = pymysql.connect(
            host="localhost",
            port=3306,
            user="root",
            password="",
            charset="utf8mb4"
        )
        print("[+] Successfully connected to MySQL as root.")
    except Exception as e:
        print(f"[-] Failed to connect to MySQL: {e}")
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            # Check if user exists
            cur.execute("SELECT Host, User FROM mysql.user WHERE User = 'holomenu_app'")
            rows = cur.fetchall()
            
            user_exists = len(rows) > 0
            if not user_exists:
                print("[+] Creating user 'holomenu_app'@'localhost'...")
                cur.execute("CREATE USER 'holomenu_app'@'localhost' IDENTIFIED BY 'app_secure_pass_123'")
            else:
                print("[*] User 'holomenu_app'@'localhost' already exists. Updating password...")
                cur.execute("ALTER USER 'holomenu_app'@'localhost' IDENTIFIED BY 'app_secure_pass_123'")
            
            # Create database if not exists
            cur.execute("CREATE DATABASE IF NOT EXISTS holomenu_db")
            
            # Grant privileges
            print("[+] Granting privileges on holomenu_db to 'holomenu_app'@'localhost'...")
            cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER ON holomenu_db.* TO 'holomenu_app'@'localhost'")
            cur.execute("FLUSH PRIVILEGES")
            
        conn.commit()
        print("[+] Setup completed successfully.")
    except Exception as e:
        print(f"[-] Database operation failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    setup_user()
