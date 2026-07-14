import logging
import sys
from dotenv import load_dotenv

# Φόρτωση των μεταβλητών περιβάλλοντος από το αρχείο .env
load_dotenv()

# Κεντρική ρύθμιση του logging για όλο το project (έξοδος στο stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)

# Export του logger για να τον κάνουν import τα υπόλοιπα αρχεία
logger = logging.getLogger("tms_api")