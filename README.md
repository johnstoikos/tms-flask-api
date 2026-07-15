# Terminal Management System (TMS) API

Ένα ολοκληρωμένο και ανθεκτικό σύστημα διαχείρισης τερματικών POS, βασισμένο σε **Flask**, **MySQL**, **Redis** και **Pandas**.

Η εφαρμογή είναι πλήρως containerized με **Docker Compose** και περιλαμβάνει προηγμένες δυνατότητες, όπως:

* Caching με το **cache-aside pattern**
* Αυτόματο cache invalidation
* Αυτοματοποιημένο cleanup μέσω background cron container
* Πλήρες unit testing suite

---

## Αρχιτεκτονική και Τεχνολογίες

* **Backend Framework:** Flask με Python 3.12
* **Βάση Δεδομένων:** MySQL 8.0

  * Σχεσιακό schema
  * Υποστήριξη συναλλαγών
* **Caching Layer:** Redis

  * Cache-aside pattern
  * Αυτόματο invalidation κατά τις μεταβολές δεδομένων
* **Data Analysis:** Pandas

  * Υπολογισμός στατιστικών
  * Εξαγωγή αναφορών CSV
* **Background Jobs:** Αυτόνομο cron container

  * Εκτέλεση περιοδικών cleanup διεργασιών
* **Testing:** Pytest

  * 22 unit tests για pure helper functions

---

## Οδηγίες Εκκίνησης

### 1. Προαπαιτούμενα

Βεβαιωθείτε ότι έχετε εγκατεστημένα στο σύστημά σας:

* **Docker**
* **Docker Compose**

### 2. Ρύθμιση του αρχείου `.env`

Δημιουργήστε ένα αρχείο με όνομα `.env` στη ρίζα του project και προσθέστε τις παρακάτω ρυθμίσεις:

```env
MYSQL_ROOT_PASSWORD=tms_root_password
MYSQL_DATABASE=tms_db
MYSQL_USER=tms_user
MYSQL_PASSWORD=tms_password
MYSQL_PORT=3306
MYSQL_HOST=mysql

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

FLASK_PORT=5001
FLASK_HOST=0.0.0.0
```

### 3. Εκκίνηση των Containers

Εκτελέστε την ακόλουθη εντολή στο τερματικό, από τη ρίζα του project, για να δημιουργήσετε και να ξεκινήσετε όλες τις υπηρεσίες στο background:

```bash
docker compose up --build -d
```

Η εντολή θα θέσει σε λειτουργία τις παρακάτω υπηρεσίες:

* **`tms-api`**: Το Flask Web API στη θύρα `5001`
* **`mysql`**: Η βάση δεδομένων στη θύρα `3306`
* **`redis`**: Το caching layer στη θύρα `6379`
* **`tms-cron-cleanup`**: Το background cron container για την αυτόματη εκκαθάριση

---

## Εκτέλεση Tests

### Unit Tests με Pytest

Το project περιλαμβάνει 22 unit tests, τα οποία καλύπτουν:

* Edge cases
* Boundary conditions
* Εξαιρέσεις των βοηθητικών συναρτήσεων
* Επικύρωση παραμέτρων εισόδου

Για να εκτελέσετε τα tests μέσα από το container, χρησιμοποιήστε:

```bash
docker compose exec tms-api pytest -v
```

---

## Λίστα API Endpoints

### Health Check

#### `GET /health`

Ελέγχει ξεχωριστά τη διαθεσιμότητα της MySQL και της Redis.

Επιστρέφει:

* `200 OK`, όταν όλες οι υπηρεσίες λειτουργούν σωστά
* `503 Service Unavailable`, όταν κάποια υπηρεσία είναι εκτός λειτουργίας

---

## Διαχείριση Τερματικών

### `GET /terminals`

Επιστρέφει τη λίστα όλων των τερματικών.

Υποστηρίζει:

* Φιλτράρισμα μέσω του query parameter `enabled`
* Τιμές `true` ή `false`
* Caching στη Redis με TTL 30 δευτερολέπτων

Παράδειγμα:

```http
GET /terminals?enabled=true
```

### `GET /terminals/<tid>`

Επιστρέφει τις αναλυτικές πληροφορίες ενός συγκεκριμένου τερματικού, βάσει του TID του.

### `POST /terminals/<tid>/flag`

Σημαίνει ένα τερματικό, εισάγοντας έναν κωδικό σεναρίου μέσω του πεδίου `scenario_number`.

Η λειτουργία:

* Ενημερώνει το τερματικό
* Καταγράφει τη μετάβαση στα logs
* Κάνει invalidation την cache της Redis

### `POST /terminals/<tid>/unflag`

Αφαιρεί τη σήμανση από ένα τερματικό, θέτοντας τον αριθμό σεναρίου σε `0`.

Η λειτουργία:

* Ενημερώνει το τερματικό
* Καταγράφει τη μετάβαση στα logs
* Κάνει invalidation την cache της Redis

### `POST /terminals/<tid>/decommission`

Θέτει ένα τερματικό σε κατάσταση απενεργοποίησης, ορίζοντας:

```text
enabled = 0
```

Στη συνέχεια, το εισάγει στην ουρά διαγραφής με περίοδο χάριτος τριών ημερών.

### `GET /terminals/decommissioned`

Επιστρέφει τη λίστα των τερματικών που βρίσκονται στην ουρά διαγραφής.

Για κάθε τερματικό υπολογίζεται δυναμικά το πεδίο:

```text
days_remaining
```

Το πεδίο αυτό δείχνει πόσες ημέρες απομένουν μέχρι την οριστική διαγραφή.

### `GET /terminals/csv`

Παράγει και εξάγει ένα αρχείο CSV με τα βασικά στοιχεία των τερματικών, χρησιμοποιώντας τη βιβλιοθήκη Pandas.

---

## Πρότυπα Τερματικών

### `GET /templates`

Επιστρέφει τη λίστα με όλα τα διαθέσιμα πρότυπα τερματικών.

### `POST /terminals/from-template`

Δημιουργεί ένα νέο ενεργό τερματικό με βάση ένα υπάρχον template.

Η λειτουργία παράγει αυτόματα το επόμενο διαθέσιμο TID, βάσει του MID του εμπόρου.

Παράδειγμα παραγόμενου TID:

```text
T0101008
```

---

## Στατιστικά Στοιχεία

Όλα τα στατιστικά:

* Υπολογίζονται με Pandas
* Αποθηκεύονται στη Redis
* Έχουν TTL 60 δευτερολέπτων

### `GET /statistics/by-hardware`

Επιστρέφει το πλήθος των τερματικών ανά μοντέλο υλικού.

Το grouping πραγματοποιείται βάσει του πεδίου:

```text
hardware_model
```

### `GET /statistics/by-hardware-family`

Επιστρέφει το πλήθος των τερματικών ανά οικογένεια υλικού.

Το grouping πραγματοποιείται βάσει του πεδίου:

```text
hardware_family
```

### `GET /statistics/by-state`

Επιστρέφει το πλήθος των:

* Ενεργών τερματικών
* Ανενεργών τερματικών
* Συνολικών τερματικών

### `GET /statistics/idle-distribution`

Επιστρέφει την κατανομή των τερματικών ανάλογα με τις ημέρες αδράνειας από την τελευταία τους κλήση.

Η κατανομή χωρίζεται στα παρακάτω πέντε buckets:

1. **Σήμερα**
2. **1–7 μέρες**
3. **8–30 μέρες**
4. **31–90 μέρες**
5. **90+ μέρες**

---

## Bonus Χαρακτηριστικά

### Background Decommission Cleanup Container

Υλοποιήθηκε ένα ξεχωριστό, lightweight Docker container, το οποίο εκτελεί περιοδικά ένα Python script.

Το script:

* Εντοπίζει τα τερματικά των οποίων η περίοδος χάριτος έχει λήξει
* Διαγράφει οριστικά τα αντίστοιχα δεδομένα
* Εκτελεί τις διαγραφές με τη σωστή σειρά:

```text
Child Table → Parent Table
```

* Χρησιμοποιεί ασφαλείς SQL transactions
* Εκτελεί rollback σε περίπτωση αποτυχίας

### Pandas Integration

Η βιβλιοθήκη Pandas χρησιμοποιείται για:

* Τον υπολογισμό στατιστικών
* Την ομαδοποίηση δεδομένων
* Τη διαχείριση κενών τιμών με την κατηγορία `Unknown`
* Τη δυναμική παραγωγή του CSV export

### Redis Cache-Aside και Invalidation

Υλοποιήθηκε το cache-aside pattern με διαφορετικά TTLs ανά κατηγορία δεδομένων.

Πραγματοποιείται καθολικό invalidation μέσω:

```text
FLUSHDB
```

Το invalidation εκτελείται κατά:

* Τη δημιουργία τερματικών
* Την τροποποίηση τερματικών
* Τη σήμανση ή αφαίρεση σήμανσης
* Την απενεργοποίηση τερματικών

Με αυτόν τον τρόπο αποφεύγεται η εμφάνιση παρωχημένων δεδομένων.

### Unit Testing με Pytest

Το project περιλαμβάνει 22 πλήρως παραμετροποιημένα unit tests.

Τα tests επαληθεύουν:

* Την ορθή λειτουργία των helper functions
* Τα όρια των ημερομηνιών
* Τα edge cases
* Τις αναμενόμενες εξαιρέσεις
* Την επικύρωση των παραμέτρων εισόδου
