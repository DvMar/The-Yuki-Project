"""
Background utility tasks:
- extract_recurring_themes  : keyword frequency across episodic memory
- store_wrapper_memory_candidates : persist SubconsciousWrapper candidates
- task_monitor_loop         : poll scheduled tasks and fire reminders
"""
import asyncio
import logging
import time
from datetime import datetime

import api.context as ctx
from cognition.reactive_core import MemoryCandidate
from utils.logging import log_structured

logger = logging.getLogger(__name__)


async def extract_recurring_themes() -> None:
    """
    Scan the last 15 episodic summaries for keyword frequency.
    Any keyword appearing 3+ times is registered as a recurring theme.
    """
    try:
        episodic_data = ctx.memory.episodic_memory.get()
        if not episodic_data or not episodic_data.get("documents"):
            return

        recent_episodes = episodic_data["documents"][-15:]

        theme_keywords = [
            "architecture", "system", "design", "learning", "evolution",
            "memory", "personality", "growth", "interaction", "development",
            "reasoning", "structure", "pattern", "philosophy", "nature",
        ]

        keyword_freq: dict[str, int] = {}
        for episode in recent_episodes:
            if not episode:
                continue
            text = episode.lower()
            for keyword in theme_keywords:
                if keyword in text:
                    keyword_freq[keyword] = keyword_freq.get(keyword, 0) + 1

        for keyword, freq in keyword_freq.items():
            if freq >= 3:
                ctx.memory.add_recurring_theme(keyword)

        if keyword_freq:
            logger.debug(f"Theme frequency: {keyword_freq}")

    except Exception as e:
        logger.warning(f"Theme extraction error: {e}")


async def store_wrapper_memory_candidates(
    candidates: list[MemoryCandidate], user_msg: str
) -> None:
    """Persist SubconsciousWrapper-selected memory candidates via MemoryEngine."""
    if not candidates:
        return

    for candidate in candidates:
        try:
            if candidate.memory_type == "semantic":
                ctx.memory.add_user_fact_deduplicated(
                    candidate.content, original_user_message=user_msg
                )
            elif candidate.memory_type == "episodic":
                ctx.memory.add_episodic_summary(candidate.content)
        except Exception as e:
            logger.debug(f"Wrapper memory candidate store skipped: {e}")


async def task_monitor_loop() -> None:
    """
    Adaptive background monitor for scheduled task reminders.

    Check frequency adapts to proximity of the nearest due date:
      - >24 h  : only checked on startup
      -  1–24 h: every 30 minutes
      -   <1 h : every minute
    """
    loop_start = time.perf_counter()
    logger.info("Adaptive task monitor started")
    log_structured("async_task_start", task="task_monitor_loop")

    while True:
        try:
            await asyncio.sleep(300)  # baseline: check every 5 minutes

            tasks_to_check = ctx.memory.task_scheduler.get_tasks_needing_check()
            if not tasks_to_check:
                continue

            logger.debug(f"Checking {len(tasks_to_check)} task(s)...")

            for task in tasks_to_check:
                task_id = task["id"]
                task_title = task["title"]

                try:
                    due_date = datetime.fromisoformat(task["due_date"])
                    now = datetime.now()
                    time_until = due_date - now

                    should_remind = False
                    reminder_msg = ""

                    if time_until.total_seconds() < 0:
                        should_remind = True
                        days_ago = abs(time_until.days)
                        reminder_msg = (
                            f"⚠️ **OVERDUE REMINDER:** Your task '{task_title}' "
                            f"was due {days_ago} days ago! Please complete it as soon as possible."
                        )

                    elif time_until.total_seconds() < 3600:
                        should_remind = True
                        minutes_left = int(time_until.total_seconds() / 60)
                        reminder_msg = (
                            f"🔴 **TIME-SENSITIVE:** Your task '{task_title}' "
                            f"is due in {minutes_left} minutes!"
                        )

                    elif time_until.total_seconds() < 86400:
                        if not task.get("reminder_sent", False):
                            should_remind = True
                            hours_left = int(time_until.total_seconds() / 3600)
                            reminder_msg = (
                                f"🟡 **UPCOMING:** Your task '{task_title}' "
                                f"is due in {hours_left} hours."
                            )

                    if should_remind:
                        await ctx.memory.add_user_fact_with_salience(
                            fact=reminder_msg,
                            context=f"Task reminder for: {task_title}",
                            llm_check=False,
                        )
                        ctx.memory.task_scheduler.mark_reminder_sent(task_id)
                        logger.info(f"Sent reminder for: {task_title}")

                except Exception as e:
                    logger.warning(f"Error processing task {task_id}: {e}")

        except Exception as e:
            logger.warning(f"Task monitor loop error: {e}")
            await asyncio.sleep(60)
            log_structured(
                "async_task_end",
                task="task_monitor_loop_iteration",
                duration_ms=round((time.perf_counter() - loop_start) * 1000, 2),
                status="error",
            )
