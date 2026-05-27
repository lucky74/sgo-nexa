import sys
import os

# Add the parent directory to sys.path to allow importing main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

# Vercel entry point
# No additional handler needed if using vercel.json rewrites to main:app
