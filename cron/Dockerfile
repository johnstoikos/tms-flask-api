FROM python:3.12-slim

WORKDIR /app

# Εγκαθιστούμε μόνο το PyMySQL driver για lightweight container
RUN pip install --no-cache-dir pymysql

COPY cleanup.py .

# Εκτέλεση του cleanup script κατά την εκκίνηση του container
CMD ["python", "cleanup.py"]