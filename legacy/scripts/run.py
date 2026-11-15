#!/usr/bin/env python3
"""
AutoReach - Main entry point
Run the web dashboard or CLI
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def main():
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    else:
        mode = "cli"
    
    if mode in ["web", "dashboard", "--web", "-w"]:
        # Start Flask web dashboard
        print("\n🚀 Starting AutoReach Web Dashboard...")
        print("   Open http://localhost:8080 in your browser\n")
        subprocess.run([str(VENV_PYTHON), "-m", "flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "8080"])
    
    elif mode in ["cli", "--cli", "-c"]:
        # Start Rich CLI
        subprocess.run([str(VENV_PYTHON), str(PROJECT_ROOT / "cli_pro.py")])
    
    elif mode in ["status", "--status", "-s"]:
        # Quick status
        subprocess.run([str(VENV_PYTHON), str(PROJECT_ROOT / "cli_pro.py"), "--status"])
    
    elif mode in ["start", "--start"]:
        subprocess.run([str(VENV_PYTHON), str(PROJECT_ROOT / "cli_pro.py"), "--start"])
    
    elif mode in ["stop", "--stop"]:
        subprocess.run([str(VENV_PYTHON), str(PROJECT_ROOT / "cli_pro.py"), "--stop"])
    
    else:
        print("""
🚀 AutoReach - Professional Email Campaign Manager

Usage:
  python run.py [command]

Commands:
  cli         Start interactive terminal UI (default)
  web         Start web dashboard at http://localhost:5000
  status      Quick status check
  start       Start/resume campaign
  stop        Stop running campaign

Examples:
  python run.py web      # Launch web dashboard
  python run.py cli      # Launch terminal UI
  python run.py status   # Check campaign status
        """)


if __name__ == "__main__":
    main()
