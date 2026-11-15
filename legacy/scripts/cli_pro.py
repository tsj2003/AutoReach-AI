#!/usr/bin/env python3
"""
AutoReach Pro CLI - Beautiful terminal interface using Rich
Professional command-line experience with live updates
"""

import os
import sys
import time
import yaml
import subprocess
from pathlib import Path
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich.markdown import Markdown
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Installing rich library for beautiful UI...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'rich'], check=True)
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich import box


console = Console()

# Project paths
PROJECT_ROOT = Path(__file__).parent
CAMPAIGNS_DIR = PROJECT_ROOT / "campaigns"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def load_campaign_config() -> dict:
    """Load campaign configuration"""
    config_path = CAMPAIGNS_DIR / "default.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_campaign_config(config: dict):
    """Save campaign configuration"""
    config_path = CAMPAIGNS_DIR / "default.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)


def count_emails_sent() -> int:
    """Count emails from log files"""
    count = 0
    for log_file in PROJECT_ROOT.glob('nohup*.out'):
        try:
            with open(log_file) as f:
                for line in f:
                    if 'Sent to' in line and '@' in line:
                        count += 1
        except:
            pass
    return count


def is_process_running() -> bool:
    """Check if email process is running"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'bulk_mail_with_attachment'],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False


def get_recent_logs(lines: int = 20) -> list:
    """Get recent log entries"""
    all_lines = []
    for log_file in sorted(PROJECT_ROOT.glob('nohup*.out'), 
                          key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(log_file) as f:
                all_lines.extend(f.readlines())
        except:
            pass
    return all_lines[-lines:] if all_lines else []


def create_header() -> Panel:
    """Create header panel"""
    return Panel(
        Text("AutoReach Pro", style="bold white", justify="center"),
        subtitle="Email Campaign Manager",
        style="bold blue",
        box=box.DOUBLE
    )


def create_status_table(config: dict) -> Table:
    """Create status table"""
    table = Table(title="📊 Campaign Status", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    
    actual_sent = count_emails_sent()
    total = config.get('data', {}).get('total_contacts', 0)
    sent = config.get('data', {}).get('emails_sent', 0)
    remaining = total - sent
    progress = (sent / total * 100) if total > 0 else 0
    
    running = is_process_running()
    status_text = "[green]● Running[/green]" if running else "[red]● Stopped[/red]"
    
    table.add_row("Campaign", config.get('name', 'N/A'))
    table.add_row("Status", status_text)
    table.add_row("", "")
    table.add_row("Total Contacts", f"{total:,}")
    table.add_row("Emails Sent", f"[green]{sent:,}[/green]")
    table.add_row("Remaining", f"[yellow]{remaining:,}[/yellow]")
    table.add_row("Progress", f"[bold]{progress:.1f}%[/bold]")
    table.add_row("", "")
    table.add_row("Resume Point", f"--skip {config.get('data', {}).get('resume_point', 0)}")
    table.add_row("Batch Size", f"{config.get('sending_params', {}).get('batch_size', 450)}/day")
    table.add_row("Delay", f"{config.get('sending_params', {}).get('sleep_min', 90)}-{config.get('sending_params', {}).get('sleep_max', 150)} sec")
    
    return table


def show_dashboard():
    """Show main dashboard"""
    console.clear()
    console.print(create_header())
    
    config = load_campaign_config()
    
    # Status table
    console.print(create_status_table(config))
    console.print()
    
    # Progress bar
    total = config.get('data', {}).get('total_contacts', 0)
    sent = config.get('data', {}).get('emails_sent', 0)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(complete_style="green", finished_style="green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Campaign Progress", total=total if total > 0 else 100)
        progress.update(task, completed=sent)
        time.sleep(0.1)  # Let it render
    
    console.print()


def show_menu():
    """Show main menu"""
    menu = Table(title="🎯 Main Menu", box=box.ROUNDED, show_header=False)
    menu.add_column("Option", style="cyan", width=4)
    menu.add_column("Action", style="white")
    
    menu.add_row("1", "📊 View Dashboard")
    menu.add_row("2", "▶️  Start/Resume Campaign")
    menu.add_row("3", "⏹️  Stop Campaign")
    menu.add_row("4", "📋 View Logs")
    menu.add_row("5", "⚙️  Settings")
    menu.add_row("6", "🔄 Sync from Logs")
    menu.add_row("7", "🌐 Start Web Dashboard")
    menu.add_row("8", "❌ Exit")
    
    console.print(menu)


def start_campaign():
    """Start or resume the campaign"""
    config = load_campaign_config()
    
    if is_process_running():
        console.print("[yellow]⚠ Campaign is already running![/yellow]")
        return
    
    skip = config.get('data', {}).get('resume_point', 0)
    limit = config.get('sending_params', {}).get('limit')
    sleep_min = config.get('sending_params', {}).get('sleep_min', 90)
    sleep_max = config.get('sending_params', {}).get('sleep_max', 150)
    csv_file = config.get('data', {}).get('source', 'out/hr_contacts_cleaned.csv')
    attachment = config.get('email_settings', {}).get('attachment', '')
    text_template = config.get('email_settings', {}).get('template_text', 'templates/application_inquiry_v2.txt.j2')
    html_template = config.get('email_settings', {}).get('template_html', 'templates/application_inquiry.html.j2')
    subject = config.get('email_settings', {}).get('subject', 'VIT B.Tech 2026 Fresher | Backend Engineer for {{ company }} – Tarandeep Singh Juneja')
    
    console.print("\n[bold]Starting campaign with:[/bold]")
    console.print(f"  CSV: {csv_file}")
    console.print(f"  Subject: {subject}")
    console.print(f"  Skip: {skip} rows")
    limit_display = f"{limit} emails" if limit and limit > 0 else "unlimited"
    console.print(f"  Limit: {limit_display}")
    console.print(f"  Delay: {sleep_min}-{sleep_max} seconds")
    console.print(f"  Attachment: {attachment}")
    
    if not Confirm.ask("\nProceed?"):
        return
    
    limit_arg = f" --limit {limit}" if limit and limit > 0 else ""
    cmd = (
        f"cd {PROJECT_ROOT} && nohup {VENV_PYTHON} bulk_mail_with_attachment.py "
        f"--csv {csv_file} --text-template {text_template} --html-template {html_template} "
        f"--subject \"{subject}\" --attachment \"{attachment}\" --skip {skip}{limit_arg} "
        f"--sleep-min {sleep_min} --sleep-max {sleep_max} > nohup_send.out 2>&1 &"
    )
    
    with console.status("[bold green]Starting campaign..."):
        subprocess.Popen(cmd, shell=True, cwd=str(PROJECT_ROOT))
        time.sleep(2)
    
    if is_process_running():
        console.print("[green]✓ Campaign started successfully![/green]")
        config['status'] = 'in_progress'
        config['timeline']['resumed'] = datetime.now().isoformat()
        save_campaign_config(config)
    else:
        console.print("[red]✗ Failed to start campaign[/red]")


def stop_campaign():
    """Stop the running campaign"""
    if not is_process_running():
        console.print("[yellow]⚠ No campaign is running[/yellow]")
        return
    
    if not Confirm.ask("Stop the running campaign?"):
        return
    
    with console.status("[bold red]Stopping campaign..."):
        subprocess.run(['pkill', '-f', 'bulk_mail_with_attachment'], check=False)
        time.sleep(1)
    
    if not is_process_running():
        console.print("[green]✓ Campaign stopped[/green]")
        
        # Update config
        config = load_campaign_config()
        config['status'] = 'paused'
        config['data']['emails_sent'] = count_emails_sent()
        config['data']['resume_point'] = config['data']['emails_sent']
        save_campaign_config(config)
    else:
        console.print("[red]✗ Failed to stop campaign[/red]")


def view_logs():
    """View recent logs"""
    console.clear()
    console.print(Panel("📋 Recent Logs", style="bold blue"))
    
    logs = get_recent_logs(30)
    
    for line in logs:
        line = line.strip()
        if 'Sent to' in line:
            console.print(f"[green]{line}[/green]")
        elif 'Error' in line or 'Failed' in line:
            console.print(f"[red]{line}[/red]")
        elif 'WARNING' in line or 'rate limit' in line.lower():
            console.print(f"[yellow]{line}[/yellow]")
        else:
            console.print(f"[dim]{line}[/dim]")
    
    console.print()
    Prompt.ask("Press Enter to continue")


def settings_menu():
    """Settings menu"""
    config = load_campaign_config()
    
    console.clear()
    console.print(Panel("⚙️ Settings", style="bold blue"))
    
    current = Table(title="Current Settings", box=box.ROUNDED)
    current.add_column("Setting", style="cyan")
    current.add_column("Value", style="white")
    
    current.add_row("Batch Size", str(config.get('sending_params', {}).get('batch_size', 450)))
    current.add_row("Min Delay", str(config.get('sending_params', {}).get('sleep_min', 90)))
    current.add_row("Max Delay", str(config.get('sending_params', {}).get('sleep_max', 150)))
    current.add_row("Resume Point", str(config.get('data', {}).get('resume_point', 0)))
    
    console.print(current)
    console.print()
    
    if Confirm.ask("Update settings?"):
        batch = Prompt.ask("Batch size", default=str(config.get('sending_params', {}).get('batch_size', 450)))
        sleep_min = Prompt.ask("Min delay (sec)", default=str(config.get('sending_params', {}).get('sleep_min', 90)))
        sleep_max = Prompt.ask("Max delay (sec)", default=str(config.get('sending_params', {}).get('sleep_max', 150)))
        resume = Prompt.ask("Resume point", default=str(config.get('data', {}).get('resume_point', 0)))
        
        config['sending_params']['batch_size'] = int(batch)
        config['sending_params']['sleep_min'] = int(sleep_min)
        config['sending_params']['sleep_max'] = int(sleep_max)
        config['data']['resume_point'] = int(resume)
        
        save_campaign_config(config)
        console.print("[green]✓ Settings saved![/green]")
    
    Prompt.ask("Press Enter to continue")


def sync_from_logs():
    """Sync resume point from logs"""
    actual_sent = count_emails_sent()
    
    config = load_campaign_config()
    config['data']['emails_sent'] = actual_sent
    config['data']['resume_point'] = actual_sent
    save_campaign_config(config)
    
    console.print(f"[green]✓ Synced: {actual_sent} emails sent, resume point updated[/green]")
    time.sleep(1)


def start_web_dashboard():
    """Start the web dashboard"""
    console.print("\n[bold]Starting web dashboard...[/bold]")
    console.print("[dim]Open http://localhost:5000 in your browser[/dim]\n")
    
    # Run Flask
    os.chdir(PROJECT_ROOT)
    subprocess.run([str(VENV_PYTHON), '-m', 'flask', '--app', 'app', 'run', '--host', '0.0.0.0', '--port', '5000'])


def main():
    """Main entry point"""
    # Handle command-line arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ['--status', '-s', 'status']:
            show_dashboard()
            return
        elif arg in ['--start', 'start']:
            start_campaign()
            return
        elif arg in ['--stop', 'stop']:
            stop_campaign()
            return
        elif arg in ['--web', 'web', 'dashboard']:
            start_web_dashboard()
            return
        elif arg in ['--help', '-h', 'help']:
            console.print("""
[bold]AutoReach Pro CLI[/bold]

[cyan]Usage:[/cyan]
  python cli_pro.py [command]

[cyan]Commands:[/cyan]
  (none)      Interactive menu
  --status    Show campaign status
  --start     Start/resume campaign
  --stop      Stop running campaign
  --web       Start web dashboard
  --help      Show this help
            """)
            return
    
    # Interactive mode
    while True:
        show_dashboard()
        show_menu()
        
        choice = Prompt.ask("\n[bold cyan]Select option[/bold cyan]", choices=["1", "2", "3", "4", "5", "6", "7", "8"])
        
        if choice == "1":
            show_dashboard()
            Prompt.ask("Press Enter to continue")
        elif choice == "2":
            start_campaign()
            time.sleep(1)
        elif choice == "3":
            stop_campaign()
            time.sleep(1)
        elif choice == "4":
            view_logs()
        elif choice == "5":
            settings_menu()
        elif choice == "6":
            sync_from_logs()
        elif choice == "7":
            start_web_dashboard()
        elif choice == "8":
            console.print("\n[bold green]Goodbye! 👋[/bold green]\n")
            break


if __name__ == "__main__":
    main()
