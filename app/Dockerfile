FROM python:3.12-slim

WORKDIR /app

# Εγκατάσταση απαραίτητων συστημικών βιβλιοθηκών για C extensions (π.χ. Pandas/PyMySQL αν χρειαστεί)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

# Αντιγραφή και εγκατάσταση των dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Αντιγραφή όλου του κώδικα της εφαρμογής
COPY . .

EXPOSE 5000

CMD ["python", "main.py"]