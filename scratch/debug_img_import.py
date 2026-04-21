
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("DEBUG: Importing fetch_images_for_processed...")
from STEP1.processor import fetch_images_for_processed
print("DEBUG: Import SUCCESS!")
