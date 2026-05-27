import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def start_scheduler(job_func, run_time: str = "08:30"):
    """Start APScheduler to run the job daily at specified time."""
    hour, minute = map(int, run_time.split(":"))
    scheduler = AsyncIOScheduler()

    async def wrapper():
        await job_func()

    scheduler.add_job(wrapper, "cron", hour=hour, minute=minute, id="daily_news")
    scheduler.start()
    print(f"调度器已启动，每日 {run_time} 执行新闻抓取")
    return scheduler
