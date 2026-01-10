"""
FastAPI 웹 애플리케이션
"""
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from src.storage import Database
from src.models import JobSource
from config import settings


def create_app() -> FastAPI:
    """FastAPI 앱 생성"""
    app = FastAPI(
        title="채용 정보 대시보드",
        description="데이터 분석 관련 채용 정보를 모아보는 대시보드",
        version="1.0.0",
    )

    # 템플릿 설정
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)
    templates = Jinja2Templates(directory=str(templates_dir))

    # 정적 파일 설정
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 데이터베이스
    db = Database()

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        source: Optional[str] = Query(None, description="소스 필터"),
        view: Optional[str] = Query("all", description="뷰 타입"),
    ):
        """메인 대시보드"""
        # 통계
        stats = db.get_statistics()

        # 채용 공고 목록
        if view == "new":
            jobs = db.get_new_jobs()
        elif view == "expiring":
            jobs = db.get_expiring_jobs(days=7)
        elif source:
            jobs = db.get_jobs_by_source(source)
        else:
            jobs = db.get_all_jobs()

        # 소스 목록
        sources = [
            {"value": s.value, "label": s.value.upper()}
            for s in JobSource
        ]

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "jobs": jobs,
                "stats": stats,
                "sources": sources,
                "current_source": source,
                "current_view": view,
            },
        )

    @app.get("/job/{job_id}", response_class=HTMLResponse)
    async def job_detail(request: Request, job_id: str):
        """채용 공고 상세"""
        job = db.get_job_by_id(job_id)

        if not job:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "message": "공고를 찾을 수 없습니다."},
                status_code=404,
            )

        # 읽음 처리
        db.mark_as_read(job_id)

        return templates.TemplateResponse(
            "detail.html",
            {"request": request, "job": job},
        )

    @app.get("/api/jobs")
    async def api_jobs(
        source: Optional[str] = None,
        view: Optional[str] = "all",
    ):
        """API: 채용 공고 목록"""
        if view == "new":
            jobs = db.get_new_jobs()
        elif view == "expiring":
            jobs = db.get_expiring_jobs(days=7)
        elif source:
            jobs = db.get_jobs_by_source(source)
        else:
            jobs = db.get_all_jobs()

        return {"jobs": [job.model_dump() for job in jobs]}

    @app.get("/api/stats")
    async def api_stats():
        """API: 통계"""
        return db.get_statistics()

    @app.post("/api/mark-read/{job_id}")
    async def api_mark_read(job_id: str):
        """API: 읽음 처리"""
        db.mark_as_read(job_id)
        return {"success": True}

    return app


# 앱 인스턴스
app = create_app()
