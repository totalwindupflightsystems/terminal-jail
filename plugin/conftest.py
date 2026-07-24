"""pytest configuration for terminal-jail tests."""
import sys
from pathlib import Path

# Add plugin directory to sys.path so tests can import terminal_jail
sys.path.insert(0, str(Path(__file__).parent))
