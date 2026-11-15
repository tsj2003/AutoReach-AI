#!/usr/bin/env python3
"""
AutoReach Quick CLI - Short commands for campaign control
Compact one-line logging, error handling, and auto-resume
"""

import os
import sys
import time
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Dict

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'rich'], check=True)
    from rich.console import Console
    from rich.table import Table
    from rich import box

console = Console()

PROJECT_ROOT = Path(__file__).parent
LOG_FILE = PROJECT_ROOT / "campaign.log"
STATE_FILE = PROJECT_ROOT / ".campaign_state.json"


class CompactLogger:
    """One-line compact logging format"""
    
    @staticmethod
    def log(status: str, email: str = "", details: str = "", msg_id: str = ""):
        """Log in compact one-line format"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Build one-line log entry
        if status == "SENT":
            line = f"[{timestamp}] ✓ SENT {email[:35]:35} {details[:20]:20}"
        elif status == "SKIP":
            line = f"[{timestamp}] ⊘ SKIP {email[:35]:35} (already sent)"
        elif status == "ERROR":
            line = f"[{timestamp}] ✗ ERROR {email[:35]:35} {details[:30]:30}"
        elif status == "RATE_LIMIT":
            line = f"[{timestamp}] ⏸ RATE_LIMIT - resuming in {details}"
        elif status == "START":
            line = f"[{timestamp}] ▶ START {details}"
        elif status == "STOP":
            line = f"[{timestamp}] ⏹ STOP {details}"
        elif status == "RESUME":
            line = f"[{timestamp}] ⤴ RESUME from point {details}"
        elif status == "COMPLETE":
            line = f"[{timestamp}] ✓ COMPLETE {details}"
        else:
            line = f"[{timestamp}] ℹ {status} {details}"
        
        # Print to console
        console.print(line)
        
        # Append to file
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    
    @staticmethod
    def show_tail(num_lines: int = 15):
        """Show last N lines of log"""
        if not LOG_FILE.exists():
            console.print("[yellow]No logs yet[/yellow]")
            return
        
        with open(LOG_FILE) as f:
            lines = f.readlines()
        
        console.print(f"\n[bold]Last {min(num_lines, len(lines))} log entries:[/bold]")
        for line in lines[-num_lines:]:
            console.print(line.rstrip())


class CampaignState:
    """Manage campaign state and auto-resume logic"""
    
    @staticmethod
    def save(state: Dict):
        """Save campaign state"""
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    
    @staticmethod
    def load() -> Dict:
        """Load campaign state"""
        if not STATE_FILE.exists():
            return {
                "status": "idle",
                "total": 0,
                "sent": 0,
                "failed": 0,
                "last_error": None,
                "error_time": None,
                "retry_after": None,
                "process_id": None
            }
        
        with open(STATE_FILE) as f:
            return json.load(f)
    
    @staticmethod
    def is_rate_limited() -> bool:
        """Check if in rate limit retry window"""
        state = CampaignState.load()
        if not state.get("retry_after"):
            return False
        
        retry_time = datetime.fromisoformat(state["retry_after"])
        return datetime.now() < retry_time
    
    @staticmethod
    def get_resume_wait_time() -> int:
        """Get seconds to wait before resume"""
        state = CampaignState.load()
        if not state.get("retry_after"):
            return 0
        
        retry_time = datetime.fromisoformat(state["retry_after"])
        wait_secs = int((retry_time - datetime.now()).total_seconds())
        return max(0, wait_secs)


def start_campaign(csv_file: str, from_email: str, batch_size: int = 450):
    """Start campaign (s)"""
    if is_process_running():
        console.print("[yellow]✗ Campaign already running![/yellow]")
        return
    
    state = CampaignState.load()
    resume_point = state.get("sent", 0)
    
    console.print(f"[green]▶ Starting campaign...{' (resuming)' if resume_point > 0 else ''}[/green]")
    
    # Find CV file
    cv_file = None
    for candidate in ["Tarandeep_Singh_Juneja_SDE.pdf", "CV_backend_Tarandeep_Singh_Juneja.pdf", "CV_backend_Tarandeep_Singh_Juneja (1).pdf", "CV_Tarandeep_Singh_Juneja (1).pdf"]:
        if (PROJECT_ROOT / candidate).exists():
            cv_file = candidate
            break
    
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "bulk_mail_with_attachment.py"),
        "--csv", csv_file,
        "--from", from_email,
        "--html-template", "templates/tsj_outreach.html.j2",
        "--text-template", "templates/tsj_outreach.txt.j2",
        "--subject", "Top 0.5% globally — here's proof I can ship code (IIT Bombay Intern)",
        "--skip", str(resume_point),
        "--batch-size", str(batch_size),
        "--sleep-min", "90",
        "--sleep-max", "150",
        "--auto-resume"  # Enable auto-resume on rate limit
    ]
    
    # Add attachment if found
    if cv_file:
        cmd.extend(["--attachment", cv_file])
    
    try:
        # Start in background with nohup
        nohup_file = PROJECT_ROOT / f"nohup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.out"
        with open(nohup_file, "w") as f:
            proc = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
        
        state["status"] = "running"
        state["process_id"] = proc.pid
        state["start_time"] = datetime.now().isoformat()
        CampaignState.save(state)
        
        CompactLogger.log("START", details=f"{csv_file} | from: {resume_point}")
        console.print(f"[green]✓ Campaign started (PID: {proc.pid})[/green]")
        console.print(f"[dim]Logs: {nohup_file}[/dim]")
        
    except Exception as e:
        console.print(f"[red]✗ Failed to start: {e}[/red]")


def stop_campaign():
    """Stop campaign (x)"""
    if not is_process_running():
        console.print("[yellow]✗ No campaign running[/yellow]")
        return
    
    try:
        # Find and kill process
        result = subprocess.run(
            ['pgrep', '-f', 'bulk_mail_with_attachment'],
            capture_output=True, text=True
        )
        
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                os.kill(int(pid), 15)  # SIGTERM
            
            state = CampaignState.load()
            state["status"] = "paused"
            state["paused_time"] = datetime.now().isoformat()
            CampaignState.save(state)
            
            CompactLogger.log("STOP", details=f"Stopped {len(pids)} process(es)")
            console.print("[green]✓ Campaign stopped[/green]")
    except Exception as e:
        console.print(f"[red]✗ Error stopping: {e}[/red]")


def show_status():
    """Show status (t)"""
    state = CampaignState.load()
    running = is_process_running()
    rate_limited = CampaignState.is_rate_limited()
    
    table = Table(title="📊 Status", box=box.ROUNDED, show_header=False)
    table.add_column("Key", style="cyan", width=20)
    table.add_column("Value", style="white")
    
    status_icon = "🟢 Running" if running else "🔴 Stopped"
    if rate_limited:
        wait_secs = CampaignState.get_resume_wait_time()
        status_icon = f"⏸ Rate Limited ({wait_secs}s)"
    
    table.add_row("Status", status_icon)
    table.add_row("Total", str(state.get("total", 0)))
    table.add_row("Sent", f"[green]{state.get('sent', 0)}[/green]")
    table.add_row("Failed", f"[red]{state.get('failed', 0)}[/red]" if state.get('failed', 0) > 0 else "0")
    
    if state.get("last_error"):
        table.add_row("Last Error", f"[red]{state['last_error'][:40]}[/red]")
    
    console.print(table)


def show_logs(lines: int = 20):
    """Show logs (l)"""
    CompactLogger.show_tail(lines)


def help_menu():
    """Show help (?)"""
    table = Table(title="🎯 Quick Commands", box=box.ROUNDED)
    table.add_column("Command", style="cyan", width=10)
    table.add_column("Description", style="white")
    table.add_column("Example", style="dim")
    
    table.add_row("s", "Start/resume campaign", "python quick_cli.py s emails.csv myemail@gmail.com")
    table.add_row("x", "Stop campaign", "python quick_cli.py x")
    table.add_row("t", "Show status", "python quick_cli.py t")
    table.add_row("l", "Show logs", "python quick_cli.py l [lines]")
    table.add_row("c", "Clear logs", "python quick_cli.py c")
    table.add_row("r", "Resume (if paused)", "python quick_cli.py r")
    table.add_row("?", "Show this help", "python quick_cli.py ?")
    
    console.print(table)
    
    console.print("\n[bold]Features:[/bold]")
    console.print("  • Auto-stop on error")
    console.print("  • Auto-resume when rate limit resets")
    console.print("  • One-line compact logging")
    console.print("  • Fast status checks")


def is_process_running() -> bool:
    """Check if campaign is running"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'bulk_mail_with_attachment'],
            capture_output=True
        )
        return result.returncode == 0
    except:
        return False


def clear_logs():
    """Clear logs (c)"""
    if LOG_FILE.exists():
        LOG_FILE.unlink()
        STATE_FILE.unlink() if STATE_FILE.exists() else None
        console.print("[green]✓ Logs cleared[/green]")


def resume_campaign(csv_file: str, from_email: str):
    """Resume paused campaign (r)"""
    state = CampaignState.load()
    
    if state.get("status") == "running":
        console.print("[yellow]✗ Campaign already running[/yellow]")
        return
    
    if CampaignState.is_rate_limited():
        wait_secs = CampaignState.get_resume_wait_time()
        hours = wait_secs // 3600
        mins = (wait_secs % 3600) // 60
        console.print(f"[yellow]⏸ Rate limited. Resume in {hours}h {mins}m[/yellow]")
        
        # Auto-resume after wait period
        console.print("[dim]Waiting for quota reset...[/dim]")
        while CampaignState.is_rate_limited():
            time.sleep(30)
        
        console.print("[green]✓ Quota reset, resuming...[/green]")
    
    CompactLogger.log("RESUME", details=str(state.get("sent", 0)))
    start_campaign(csv_file, from_email)


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        help_menu()
        return
    
    cmd = sys.argv[1].lower()
    
    if cmd == "s" and len(sys.argv) >= 4:
        # s emails.csv from@email.com [batch_size]
        csv_file = sys.argv[2]
        from_email = sys.argv[3]
        batch_size = int(sys.argv[4]) if len(sys.argv) > 4 else 450
        start_campaign(csv_file, from_email, batch_size)
    
    elif cmd == "x":
        stop_campaign()
    
    elif cmd == "t":
        show_status()
    
    elif cmd == "l":
        lines = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        show_logs(lines)
    
    elif cmd == "c":
        clear_logs()
    
    elif cmd == "r" and len(sys.argv) >= 4:
        # r emails.csv from@email.com
        resume_campaign(sys.argv[2], sys.argv[3])
    
    elif cmd in ["?", "help", "-h", "--help"]:
        help_menu()
    
    else:
        console.print("[red]Unknown command[/red]")
        help_menu()


if __name__ == "__main__":
    main()
