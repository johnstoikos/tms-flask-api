import os
import sys
import pymysql

def main():
    # Λήψη των ρυθμίσεων σύνδεσης από τις μεταβλητές περιβάλλοντος του Cron container
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
            # Ανάκτηση των TIDs που έχουν ξεπεράσει την ημερομηνία διαγραφής (delete_after < NOW())
            cursor.execute(
                "SELECT tid FROM decommission_queue WHERE delete_after < NOW()"
            )
            expired_records = cursor.fetchall()

            if not expired_records:
                print("Cron Job: No expired decommissioned terminals found to delete.", flush=True)
                return

            expired_tids = [row["tid"] for row in expired_records]
            print(f"Cron Job: Found {len(expired_tids)} expired terminals: {expired_tids}", flush=True)

            # Έναρξη χειροκίνητης συναλλαγής (Transaction) για εγγύηση της ατομικότητας (All-or-Nothing execution)
            connection.begin()

            # Δυναμικό χτίσιμο των safe query placeholders (%s, %s, ...) για την αποφυγή SQL Injection
            format_strings = ','.join(['%s'] * len(expired_tids))
            
            # Βήμα 1: Απαλοιφή των εγγραφών από το decommission_queue (Child Table) 
            # για την αποφυγή Foreign Key constraint violation κατά τη διαγραφή
            cursor.execute(
                f"DELETE FROM decommission_queue WHERE tid IN ({format_strings})",
                tuple(expired_tids)
            )

            # Βήμα 2: Οριστική διαγραφή από τον πίνακα terminals (Parent Table)
            cursor.execute(
                f"DELETE FROM terminals WHERE tid IN ({format_strings})",
                tuple(expired_tids)
            )

            # Οριστικοποίηση των αλλαγών στη βάση
            connection.commit()
            print(f"Cron Job SUCCESS: Deleted {len(expired_tids)} terminals from queue and terminals table.", flush=True)

    except Exception as e:
        # Αν προκύψει οποιοδήποτε σφάλμα, ακυρώνονται όλες οι ενδιάμεσες αλλαγές για την προστασία της ακεραιότητας των δεδομένων
        connection.rollback()
        print(f"Cron Job TRANSACTION FAILED: Rolling back. Error: {e}", file=sys.stderr, flush=True)
    finally:
        connection.close()

if __name__ == "__main__":
    main()