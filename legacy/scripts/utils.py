"""
Utility functions for CLI formatting and colors
"""

import os
from typing import List


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def clear_screen():
    """Clear terminal screen"""
    os.system('clear' if os.name == 'posix' else 'cls')


def print_header(title: str):
    """Print formatted header"""
    width = 60
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * width}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(width)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * width}{Colors.END}")


def print_success(message: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")


def print_error(message: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {message}{Colors.END}")


def print_warning(message: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.END}")


def print_info(message: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {message}{Colors.END}")


def progress_bar(current: int, total: int, width: int = 40) -> str:
    """Generate progress bar string"""
    if total == 0:
        return "█" * width
    
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = 100 * current / total
    return f"{bar} {pct:.1f}% ({current}/{total})"


def format_duration(seconds: float) -> str:
    """Convert seconds to human-readable format"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def table_row(cells: List[str], widths: List[int]) -> str:
    """Format table row"""
    return "  ".join(
        cell.ljust(width) for cell, width in zip(cells, widths)
    )


def format_email_log(email: str, status: str, timestamp: str, message_id: str = None) -> str:
    """Format email log entry"""
    status_color = Colors.GREEN if status == "sent" else Colors.RED
    result = f"{status_color}[{status.upper()}]{Colors.END} {email}"
    if message_id:
        result += f" (ID: {message_id[:8]}...)"
    result += f" @ {timestamp}"
    return result
