"""
Task Scheduler: Manage scheduled reminders and task tracking.
Automatic proactive reminders based on extracted tasks and deadlines.
"""

import logging
import json
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

class TaskScheduler:
    """
    Manages scheduled tasks and reminders.
    Extracts deadlines and task mentions from conversations.
    Proactively reminds user when relevant.
    """
    
    def __init__(self, db_path: str = "./persistent_state"):
        """
        Initialize task scheduler.
        
        Args:
            db_path: Path to directory for persistence
        """
        self.db_path = db_path
        self.tasks_path = os.path.join(db_path, "tasks.json")
        
        # Load or create tasks
        self.tasks = self._load_tasks()
        self.completed_tasks = self._load_completed_tasks()
    
    def add_task(
        self,
        title: str,
        due_date: Optional[datetime] = None,
        priority: str = "normal",
        metadata: Dict = None
    ) -> str:
        """
        Add a task to the scheduler.
        
        Args:
            title: Task title
            due_date: Optional due date/time
            priority: "low", "normal", "high"
            metadata: Additional metadata
        
        Returns:
            Task ID
        """
        if not title or not isinstance(title, str):
            return None
        
        title = title.strip()
        if not title:
            return None
        
        # Generate task ID
        task_id = f"task_{len(self.tasks)}_{int(datetime.now().timestamp())}"
        
        task = {
            "id": task_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "due_date": due_date.isoformat() if due_date else None,
            "priority": priority if priority in ["low", "normal", "high"] else "normal",
            "completed": False,
            "metadata": metadata or {},
            "last_check": datetime.now().isoformat(),
            "next_check_time": datetime.now().isoformat(),  # Check immediately on next scan
            "reminder_sent": False
        }
        
        self.tasks[task_id] = task
        self._calculate_next_check(task_id)
        self._save_tasks()
        
        logger.info(f"Added task: {title} (due: {due_date})")
        return task_id
    
    def extract_tasks_from_text(self, text: str) -> List[Dict]:
        """
        Extract task mentions and deadlines from text.
        Uses pattern matching to identify tasks and dates.
        
        Returns:
            List of extracted tasks
        """
        tasks = []
        
        # Pattern 1: "remind me to ....[by/on/next] [date]"
        pattern1 = r"remind\s+me\s+to\s+(.+?)\s+(?:by|on|at|next)\s+(.+?)(?:\.|$)"
        matches = re.finditer(pattern1, text.lower())
        for match in matches:
            task_title = match.group(1).strip()
            date_str = match.group(2).strip()
            
            due_date = self._parse_date(date_str)
            tasks.append({
                "title": task_title,
                "due_date": due_date,
                "priority": "normal",
                "source": "extraction"
            })
        
        # Pattern 2: "I need to/I should ... by [date]"
        pattern2 = r"(?:I need to|I should|I have to|I must)\s+(.+?)\s+by\s+(.+?)(?:\.|,|$)"
        matches = re.finditer(pattern2, text.lower())
        for match in matches:
            task_title = match.group(1).strip()
            date_str = match.group(2).strip()
            
            due_date = self._parse_date(date_str)
            tasks.append({
                "title": task_title,
                "due_date": due_date,
                "priority": "normal",
                "source": "extraction"
            })
        
        # Pattern 3: "I have a [deadline/task] to ... on [date]"
        pattern3 = r"(?:i have (?:a )?)(?:deadline|task|commitment|goal)\s+(?:to\s+)?(.+?)\s+on\s+(.+?)(?:\.|,|$)"
        matches = re.finditer(pattern3, text.lower())
        for match in matches:
            task_title = match.group(1).strip()
            date_str = match.group(2).strip()
            
            due_date = self._parse_date(date_str)
            tasks.append({
                "title": task_title,
                "due_date": due_date,
                "priority": "high",
                "source": "extraction"
            })
        
        return tasks
    
    def get_due_soon(self, hours: int = 24) -> List[Dict]:
        """
        Get tasks due within next N hours.
        
        Args:
            hours: Lookback window in hours
        
        Returns:
            List of upcoming tasks
        """
        now = datetime.now()
        cutoff = now + timedelta(hours=hours)
        
        due_tasks = []
        
        for task in self.tasks.values():
            if task["completed"]:
                continue
            
            if not task["due_date"]:
                continue
            
            try:
                due_date = datetime.fromisoformat(task["due_date"])
                if now <= due_date <= cutoff:
                    due_tasks.append(task)
            except:
                continue
        
        # Sort by due date
        due_tasks.sort(key=lambda t: t["due_date"])
        return due_tasks
    
    def get_overdue(self) -> List[Dict]:
        """Get overdue tasks."""
        now = datetime.now()
        overdue = []
        
        for task in self.tasks.values():
            if task["completed"]:
                continue
            
            if not task["due_date"]:
                continue
            
            try:
                due_date = datetime.fromisoformat(task["due_date"])
                if due_date < now:
                    overdue.append(task)
            except:
                continue
        
        return overdue
    
    def complete_task(self, task_id: str) -> bool:
        """Mark task as completed."""
        if task_id not in self.tasks:
            return False
        
        self.tasks[task_id]["completed"] = True
        self.tasks[task_id]["completed_at"] = datetime.now().isoformat()
        
        # Move to completed
        self.completed_tasks[task_id] = self.tasks.pop(task_id)
        
        self._save_tasks()
        logger.info(f"Completed task: {task_id}")
        return True
    
    def get_all_tasks(self, include_completed: bool = False) -> List[Dict]:
        """Get all tasks."""
        tasks = list(self.tasks.values())
        
        if include_completed:
            tasks.extend(self.completed_tasks.values())
        
        # Sort by due date (null last)
        tasks.sort(key=lambda t: (t["due_date"] is None, t["due_date"]))
        return tasks
    
    def get_proactive_reminders(self) -> List[str]:
        """
        Get proactive reminders to inject into UI/chat.
        Checks for:
        - Overdue tasks
        - Tasks due today
        - High priority tasks
        
        Returns:
            List of reminder messages
        """
        reminders = []
        
        # Check overdue
        overdue = self.get_overdue()
        if overdue:
            for task in overdue[:3]:  # Max 3 reminders
                days_overdue = (datetime.now() - datetime.fromisoformat(task["due_date"])).days
                reminders.append(f"⚠️ Overdue: {task['title']} (by {task['due_date']})")
        
        # Check due today
        today = datetime.now().date()
        for task in self.tasks.values():
            if task["completed"]:
                continue
            
            if not task["due_date"]:
                continue
            
            try:
                due_date = datetime.fromisoformat(task["due_date"]).date()
                if due_date == today:
                    reminders.append(f"📌 Due today: {task['title']}")
            except:
                continue
        
        # Check high priority
        high_priority = [t for t in self.tasks.values() if t["priority"] == "high" and not t["completed"]]
        if high_priority and not reminders:  # Only show if no urgent reminders
            reminders.append(f"⭐ High priority: {high_priority[0]['title']}")
        
        return reminders[:3]  # Max 3 reminders
    
    def _calculate_next_check(self, task_id: str) -> None:
        """
        Calculate the optimal next check time for a task based on time-to-due.
        
        Strategy:
        - > 24 hours away: Don't check until next app startup (skip_until_startup=True)
        - 1-24 hours away: Check every 30 minutes
        - < 1 hour away: Check every minute
        - Overdue: Check every minute
        
        Handles app restarts gracefully - times are absolute, not relative.
        """
        task = self.tasks.get(task_id)
        if not task or not task["due_date"] or task["completed"]:
            return
        
        try:
            due_date = datetime.fromisoformat(task["due_date"])
            now = datetime.now()
            time_until_due = due_date - now
            
            if time_until_due.total_seconds() < 0:
                # Overdue - check every minute
                next_check = now + timedelta(minutes=1)
            elif time_until_due.total_seconds() < 3600:  # < 1 hour
                # Check every minute
                next_check = now + timedelta(minutes=1)
            elif time_until_due.total_seconds() < 86400:  # < 24 hours
                # Check every 30 minutes
                next_check = now + timedelta(minutes=30)
            else:
                # > 24 hours away - skip until next startup
                # Set to a very distant time so it's only checked on app restart
                next_check = due_date - timedelta(hours=24)
            
            task["next_check_time"] = next_check.isoformat()
            task["last_check"] = now.isoformat()
            
        except Exception as e:
            logger.error(f"Failed to calculate next check time for {task_id}: {e}")
    
    def get_tasks_needing_check(self) -> List[Dict]:
        """
        Get tasks that need to be checked now based on their next_check_time.
        This is the main method for the background monitor.
        
        Returns:
            List of tasks ready for checking
        """
        tasks_to_check = []
        now = datetime.now()
        
        for task_id, task in self.tasks.items():
            if task["completed"]:
                continue
            
            if not task["due_date"]:
                continue
            
            try:
                # Ensure new fields exist (for upgrading old tasks.json)
                if "next_check_time" not in task:
                    task["next_check_time"] = now.isoformat()
                if "reminder_sent" not in task:
                    task["reminder_sent"] = False
                
                next_check = datetime.fromisoformat(task["next_check_time"])
                
                # If current time >= next_check_time, this task needs checking
                if now >= next_check:
                    tasks_to_check.append(task)
                    
            except Exception as e:
                logger.warning(f"Error checking task {task_id}: {e}")
        
        return tasks_to_check
    
    def mark_reminder_sent(self, task_id: str) -> None:
        """Mark that a reminder has been sent for this task."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task["reminder_sent"] = True
            self._calculate_next_check(task_id)  # Recalculate for next check
            self._save_tasks()
    
    def reset_tasks_on_startup(self) -> None:
        """
        Called on app startup to recalculate check times for all tasks.
        Ensures that tasks >24h away get checked immediately, then adjusted accordingly.
        Handles the case of app being closed for extended periods.
        """
        now = datetime.now()
        updated_count = 0
        
        for task_id in self.tasks.keys():
            task = self.tasks[task_id]
            
            # Ensure new fields exist (upgrade old tasks.json)
            if "next_check_time" not in task:
                task["next_check_time"] = now.isoformat()
            if "reminder_sent" not in task:
                task["reminder_sent"] = False
            
            # Recalculate for this task
            self._calculate_next_check(task_id)
            updated_count += 1
        
        if updated_count > 0:
            self._save_tasks()
            logger.info(f"Reset {updated_count} task check times on startup")
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """
        Try to parse date string.
        Supports: "tomorrow", "next friday", "in 3 days", "2024-02-15", "february 15", etc.
        
        Returns:
            ISO format date string or None
        """
        if not date_str:
            return None
        
        date_str = date_str.lower().strip()
        
        # Special cases
        if date_str == "tomorrow":
            due = datetime.now() + timedelta(days=1)
            return due.isoformat()
        
        if date_str == "today":
            return datetime.now().isoformat()
        
        if "in " in date_str and " day" in date_str:
            match = re.search(r"in\s+(\d+)\s+days?", date_str)
            if match:
                days = int(match.group(1))
                due = datetime.now() + timedelta(days=days)
                return due.isoformat()
        
        # Try common date formats
        formats = [
            "%B %d, %Y",
            "%B %d",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d"
        ]
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If year not specified, assume current/next year
                if "%Y" not in fmt:
                    if parsed.month < datetime.now().month:
                        parsed = parsed.replace(year=datetime.now().year + 1)
                    else:
                        parsed = parsed.replace(year=datetime.now().year)
                return parsed.isoformat()
            except:
                continue
        
        # If parsing fails, assume 1 week from now
        logger.debug(f"Could not parse date: {date_str}. Defaulting to 1 week from now.")
        due = datetime.now() + timedelta(days=7)
        return due.isoformat()
    
    def _load_tasks(self) -> Dict:
        """Load tasks from disk."""
        if os.path.exists(self.tasks_path):
            try:
                with open(self.tasks_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("active", {})
            except Exception as e:
                logger.warning(f"Failed to load tasks: {e}")
        
        return {}
    
    def _load_completed_tasks(self) -> Dict:
        """Load completed tasks from disk."""
        if os.path.exists(self.tasks_path):
            try:
                with open(self.tasks_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("completed", {})
            except Exception as e:
                logger.warning(f"Failed to load completed tasks: {e}")
        
        return {}
    
    def _save_tasks(self):
        """Save tasks to disk."""
        try:
            with open(self.tasks_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "active": self.tasks,
                    "completed": self.completed_tasks,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")
    
    def get_stats(self) -> Dict:
        """Get task statistics."""
        return {
            "total_active": len(self.tasks),
            "total_completed": len(self.completed_tasks),
            "overdue_count": len(self.get_overdue()),
            "due_soon_count": len(self.get_due_soon(hours=24))
        }
