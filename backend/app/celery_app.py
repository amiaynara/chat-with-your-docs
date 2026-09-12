from celery import Celery

from app.config import settings

celery_app = Celery("chat_with_your_docs", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)

celery_app.autodiscover_tasks(["app"])
