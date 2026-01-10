"""
채용 정보 수집 에이전트 설정
"""
from pathlib import Path
from typing import List
from pydantic import BaseModel


class FilterSettings(BaseModel):
    """필터링 설정"""
    # 직무 키워드 (OR 조건)
    job_keywords: List[str] = [
        "데이터 분석",
        "데이터분석",
        "Data Analyst",
        "Data Analysis",
        "데이터 사이언티스트",
        "Data Scientist",
        "BI 분석",
        "비즈니스 분석",
        "데이터 엔지니어",
        "Data Engineer",
        "머신러닝",
        "ML Engineer",
    ]

    # 경력 조건 (OR 조건)
    experience_keywords: List[str] = [
        "신입",
        "경력무관",
        "경력 무관",
        "인턴",
        "Intern",
        "Junior",
        "Entry",
        "0년",
        "1년",
        "2년",
        "3년",
    ]

    # 제외 키워드 (이 키워드가 포함되면 제외)
    exclude_keywords: List[str] = [
        "시니어",
        "Senior",
        "팀장",
        "리드",
        "Lead",
        "10년 이상",
    ]


class CrawlerSettings(BaseModel):
    """크롤러 설정"""
    # 크롤링 간격 (분)
    crawl_interval_minutes: int = 60

    # 요청 간 대기 시간 (초)
    request_delay_seconds: float = 2.0

    # 타임아웃 (초)
    request_timeout: int = 30

    # User-Agent
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )


class DatabaseSettings(BaseModel):
    """데이터베이스 설정"""
    db_path: Path = Path("data/jobs.db")


class WebSettings(BaseModel):
    """웹 서버 설정"""
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True


class Settings(BaseModel):
    """전체 설정"""
    filter: FilterSettings = FilterSettings()
    crawler: CrawlerSettings = CrawlerSettings()
    database: DatabaseSettings = DatabaseSettings()
    web: WebSettings = WebSettings()

    # 프로젝트 루트 경로
    base_dir: Path = Path(__file__).parent.parent


# 전역 설정 인스턴스
settings = Settings()
