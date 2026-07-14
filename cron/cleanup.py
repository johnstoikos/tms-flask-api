import os
import sys
import pymysql

def main():
    # Λήψη ρυθμίσεων σύνδεσης από το περιβάλλον
    host = os.getenv("MYSQL_HOST", "mysql")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "tms_user")
    password = os.getenv("MYSQL_PASSWORD", "tms_password")
    database = os.getenv("MYSQL_DATABASE", "tms_db")

    print("Cron Job: Starting decommission cleanup...", flush=True)

    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"Cron Job Error: Could not connect to database. Details: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        with connection.cursor() as cursor:
            # 1. Εύρεση των TIDs που έχουν λήξει (delete_after < NOW())
            cursor.execute(
                "SELECT tid FROM decommission_queue WHERE delete_after < NOW()"
            )
            expired_records = cursor.fetchall()

            if not expired_records:
                print("Cron Job: No expired decommissioned terminals found to delete.", flush=True)
                return

            expired_tids = [row["tid"] for row in expired_records]
            print(f"Cron Job: Found {len(expired_tids)} expired terminals: {expired_tids}", flush=True)

            # Ξεκινάμε transaction
            connection.begin()

            # 2. Διαγραφή ΠΡΩΤΑ από το decommission_queue για αποφυγή FK constraint error
            format_strings = ','.join(['%s'] * len(expired_tids))
            cursor.execute(
                f"DELETE FROM decommission_queue WHERE tid IN ({format_strings})",
                tuple(expired_tids)
            )

            # 3. Διαγραφή ΜΕΤΑ από τον πίνακα terminals
            cursor.execute(
                f"DELETE FROM terminals WHERE tid IN ({format_strings})",
                tuple(expired_tids)
            )

            # Commit της συναλλαγής
            connection.commit()
            print(f"Cron Job SUCCESS: Deleted {len(expired_tids)} terminals from queue and terminals table.", flush=True)

    except Exception as e:
        connection.rollback()
        print(f"Cron Job TRANSACTION FAILED: Rolling back. Error: {e}", file=sys.stderr, flush=True)
    finally:
        connection.close()

if __name__ == "__main__":
    main()