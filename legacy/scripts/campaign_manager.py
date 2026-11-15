"""
Campaign Manager - Handle campaign state, progress tracking, and process management
"""

import yaml
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import re


class CampaignManager:
    """Manage email campaigns, track progress, handle resuming"""
    
    def __init__(self, campaigns_dir: str = "campaigns"):
        self.campaigns_dir = Path(campaigns_dir)
        self.campaigns_dir.mkdir(exist_ok=True)
        self.default_config_path = self.campaigns_dir / "default.yaml"
    
    def load_campaign(self, campaign_name: str = "default") -> Dict:
        """Load campaign configuration"""
        config_path = self.campaigns_dir / f"{campaign_name}.yaml"
        
        if not config_path.exists():
            # Return empty config if doesn't exist
            return self.get_default_config()
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config if config else self.get_default_config()
        except Exception as e:
            print(f"Error loading campaign: {e}")
            return self.get_default_config()
    
    def save_campaign(self, config: Dict, campaign_name: str = "default"):
        """Save campaign configuration"""
        config_path = self.campaigns_dir / f"{campaign_name}.yaml"
        
        try:
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            print(f"Error saving campaign: {e}")
    
    def get_default_config(self) -> Dict:
        """Return default campaign configuration"""
        return {
            "name": "Default Campaign",
            "status": "pending",  # pending, in_progress, paused, completed, failed
            "email_settings": {
                "template_text": "templates/application_inquiry_v2.txt.j2",
                "template_html": "templates/application_inquiry.html.j2",
                "subject": "VIT B.Tech 2026 Fresher | Backend Engineer for {{ company }} – Tarandeep Singh Juneja",
                "from_name": "Tarandeep Singh Juneja",
                "attachment": "CV_backend_Tarandeep_Singh_Juneja (1).pdf"
            },
            "data": {
                "source": "out/hr_contacts_cleaned.csv",
                "total_contacts": 0,
                "emails_sent": 0,
                "emails_failed": 0,
                "resume_point": 0
            },
            "sending_params": {
                "batch_size": 450,
                "sleep_min": 90,
                "sleep_max": 150,
                "daily_limit": 500,
                "limit": None
            },
            "timeline": {
                "created": datetime.now().isoformat(),
                "started": None,
                "paused": None,
                "resumed": None,
                "completed": None,
                "estimated_completion": None
            },
            "logs": {
                "process_id": None,
                "nohup_file": None,
                "last_checked": None,
                "error_count": 0
            }
        }
    
    def get_campaign_status(self, campaign_name: str = "default") -> Dict:
        """Get current campaign status with progress info"""
        config = self.load_campaign(campaign_name)
        
        total = config["data"]["total_contacts"]
        sent = config["data"]["emails_sent"]
        failed = config["data"]["emails_failed"]
        
        # Calculate progress
        progress_pct = 0 if total == 0 else (sent / total) * 100
        remaining = total - sent - failed
        
        # Read process logs to verify actual sent count
        actual_sent = self._count_emails_sent()
        
        status = {
            "campaign_name": config["name"],
            "status": config["status"],
            "total_contacts": total,
            "emails_sent": sent,
            "actual_sent_from_logs": actual_sent,
            "emails_failed": failed,
            "remaining": remaining,
            "progress_pct": progress_pct,
            "resume_point": config["data"]["resume_point"],
            "batch_size": config["sending_params"]["batch_size"],
            "process_running": self.is_process_running(),
            "created": config["timeline"]["created"],
            "started": config["timeline"]["started"],
            "estimated_completion": config["timeline"]["estimated_completion"]
        }
        
        return status
    
    def start_campaign(self, total_contacts: int, campaign_name: str = "default"):
        """Initialize new campaign"""
        config = self.load_campaign(campaign_name)
        
        config["data"]["total_contacts"] = total_contacts
        config["data"]["emails_sent"] = 0
        config["data"]["emails_failed"] = 0
        config["data"]["resume_point"] = 0
        config["status"] = "in_progress"
        config["timeline"]["started"] = datetime.now().isoformat()
        config["timeline"]["resumed"] = None
        
        # Calculate estimated completion
        batch_size = config["sending_params"]["batch_size"]
        batches_needed = (total_contacts + batch_size - 1) // batch_size
        est_days = batches_needed  # 1 batch per day due to rate limit
        completion = datetime.now() + timedelta(days=est_days)
        config["timeline"]["estimated_completion"] = completion.isoformat()
        
        self.save_campaign(config, campaign_name)
        return config
    
    def resume_campaign(self, emails_sent: int, campaign_name: str = "default"):
        """Resume campaign after pause"""
        config = self.load_campaign(campaign_name)
        
        config["status"] = "in_progress"
        config["data"]["emails_sent"] = emails_sent
        config["data"]["resume_point"] = emails_sent
        config["timeline"]["resumed"] = datetime.now().isoformat()
        
        self.save_campaign(config, campaign_name)
        return config
    
    def pause_campaign(self, campaign_name: str = "default"):
        """Pause running campaign"""
        config = self.load_campaign(campaign_name)
        config["status"] = "paused"
        config["timeline"]["paused"] = datetime.now().isoformat()
        self.save_campaign(config, campaign_name)
    
    def complete_campaign(self, campaign_name: str = "default"):
        """Mark campaign as completed"""
        config = self.load_campaign(campaign_name)
        config["status"] = "completed"
        config["timeline"]["completed"] = datetime.now().isoformat()
        self.save_campaign(config, campaign_name)
    
    def get_campaign_history(self) -> List[Dict]:
        """Get list of all campaigns"""
        campaigns = []
        
        for config_file in self.campaigns_dir.glob("*.yaml"):
            try:
                with open(config_file, 'r') as f:
                    config = yaml.safe_load(f)
                    if config:
                        campaigns.append({
                            "name": config.get("name", "Unknown"),
                            "status": config.get("status", "unknown"),
                            "sent": config["data"]["emails_sent"],
                            "total": config["data"]["total_contacts"],
                            "created": config["timeline"]["created"],
                            "file": config_file.name
                        })
            except Exception as e:
                print(f"Error reading campaign {config_file}: {e}")
        
        return sorted(campaigns, key=lambda x: x["created"], reverse=True)
    
    def is_process_running(self, campaign_name: str = "default") -> bool:
        """Check if background process is running"""
        try:
            # Check for any bulk_mail process
            result = subprocess.run(
                ["pgrep", "-f", "bulk_mail_with_attachment"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_recent_logs(self, campaign_name: str = "default", lines: int = 20) -> List[str]:
        """Get recent log entries"""
        nohup_files = list(Path(".").glob("nohup*.out"))
        all_lines = []
        
        try:
            for log_file in sorted(nohup_files, key=lambda x: x.stat().st_mtime, reverse=True):
                with open(log_file, 'r') as f:
                    all_lines.extend(f.readlines())
        except Exception as e:
            return [f"Error reading logs: {e}"]
        
        # Return last N lines
        return all_lines[-lines:] if all_lines else ["No logs found"]
    
    def get_email_log_summary(self) -> Dict:
        """Parse logs and return summary of sent emails"""
        sent_count = 0
        failed_count = 0
        last_email = None
        last_timestamp = None
        
        nohup_files = list(Path(".").glob("nohup*.out"))
        
        try:
            for log_file in nohup_files:
                with open(log_file, 'r') as f:
                    for line in f:
                        if "Sent to" in line and "@" in line:
                            sent_count += 1
                            # Extract email if possible
                            match = re.search(r'(\S+@\S+)', line)
                            if match:
                                last_email = match.group(1)
                            last_timestamp = line.split()[0] if line.split() else None
                        elif "Failed to send" in line or "Error" in line:
                            failed_count += 1
        except Exception as e:
            print(f"Error parsing logs: {e}")
        
        return {
            "sent": sent_count,
            "failed": failed_count,
            "last_email": last_email,
            "last_timestamp": last_timestamp
        }
    
    def _count_emails_sent(self) -> int:
        """Count emails sent from log files"""
        count = 0
        nohup_files = list(Path(".").glob("nohup*.out"))
        
        try:
            for log_file in nohup_files:
                with open(log_file, 'r') as f:
                    for line in f:
                        if "Sent to" in line and "@" in line:
                            count += 1
        except Exception:
            pass
        
        return count
    
    def calculate_resume_point(self) -> Tuple[int, int]:
        """Calculate next resume point from logs (return processed_count, sent_count)"""
        processed = 0
        sent = 0
        
        nohup_files = list(Path(".").glob("nohup*.out"))
        
        try:
            for log_file in sorted(nohup_files):
                with open(log_file, 'r') as f:
                    for line in f:
                        # Look for "Processed X rows" messages
                        match = re.search(r'Processed (\d+) rows', line)
                        if match:
                            processed = int(match.group(1))
                        
                        # Count actual sent emails
                        if "Sent to" in line and "@" in line:
                            sent += 1
        except Exception:
            pass
        
        return processed, sent
    
    def clear_logs(self, campaign_name: str = "default"):
        """Clear old log files"""
        nohup_files = list(Path(".").glob("nohup*.out"))
        
        cleared = 0
        try:
            for log_file in nohup_files:
                log_file.unlink()
                cleared += 1
        except Exception as e:
            print(f"Error clearing logs: {e}")
        
        return cleared
    
    def get_next_skip_value(self) -> int:
        """Get the --skip value for next resume"""
        processed, sent = self.calculate_resume_point()
        # Skip value should be the number of already processed rows
        return processed
