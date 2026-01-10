"""
데이터베이스 관리 모듈
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from loguru import logger

from src.models import JobPosting, JobSummary, JobSource
from config import settings

Base = declarative_base()


class JobTable(Base):
    """채용 공고 테이블"""

    __tablename__ = "jobs"

    id = Column(String(20), primary_key=True)
    title = Column(String(500), nullable=False)
    company_name = Column(String(200), nullable=False)
    company_logo = Column(String(500), nullable=True)

    experience_level = Column(String(50), nullable=True)
    experience_text = Column(String(100), nullable=True)

    deadline = Column(DateTime, nullable=True)
    deadline_text = Column(String(100), nullable=True)
    internship_period = Column(String(100), nullable=True)

    location = Column(String(200), nullable=True)
    salary = Column(String(100), nullable=True)
    employment_type = Column(String(50), nullable=True)

    requirements = Column(Text, nullable=True)  # JSON 문자열
    preferred = Column(Text, nullable=True)  # JSON 문자열
    tech_stack = Column(Text, nullable=True)  # JSON 문자열
    description = Column(Text, nullable=True)

    source = Column(String(50), nullable=False)
    source_url = Column(String(500), nullable=False)
    source_id = Column(String(100), nullable=True)

    crawled_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    is_new = Column(Boolean, default=True)


def init_db():
    """데이터베이스 초기화"""
    db_path = settings.database.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    logger.info(f"데이터베이스 초기화 완료: {db_path}")
    return engine


class Database:
    """데이터베이스 관리 클래스"""

    def __init__(self):
        self.engine = init_db()
        self.Session = sessionmaker(bind=self.engine)

    def _to_job_table(self, job: JobPosting) -> JobTable:
        """JobPosting을 JobTable로 변환"""
        return JobTable(
            id=job.id,
            title=job.title,
            company_name=job.company_name,
            company_logo=job.company_logo,
            experience_level=job.experience_level.value if job.experience_level else None,
            experience_text=job.experience_text,
            deadline=job.deadline,
            deadline_text=job.deadline_text,
            internship_period=job.internship_period,
            location=job.location,
            salary=job.salary,
            employment_type=job.employment_type,
            requirements=json.dumps(job.requirements or [], ensure_ascii=False),
            preferred=json.dumps(job.preferred or [], ensure_ascii=False),
            tech_stack=json.dumps(job.tech_stack or [], ensure_ascii=False),
            description=job.description,
            source=job.source.value if isinstance(job.source, JobSource) else job.source,
            source_url=job.source_url,
            source_id=job.source_id,
            crawled_at=job.crawled_at,
            updated_at=job.updated_at,
            is_active=job.is_active,
            is_new=job.is_new,
        )

    def _to_job_posting(self, row: JobTable) -> JobPosting:
        """JobTable을 JobPosting으로 변환"""
        return JobPosting(
            id=row.id,
            title=row.title,
            company_name=row.company_name,
            company_logo=row.company_logo,
            experience_level=row.experience_level,
            experience_text=row.experience_text,
            deadline=row.deadline,
            deadline_text=row.deadline_text,
            internship_period=row.internship_period,
            location=row.location,
            salary=row.salary,
            employment_type=row.employment_type,
            requirements=json.loads(row.requirements) if row.requirements else [],
            preferred=json.loads(row.preferred) if row.preferred else [],
            tech_stack=json.loads(row.tech_stack) if row.tech_stack else [],
            description=row.description,
            source=row.source,
            source_url=row.source_url,
            source_id=row.source_id,
            crawled_at=row.crawled_at,
            updated_at=row.updated_at,
            is_active=row.is_active,
            is_new=row.is_new,
        )

    def _to_job_summary(self, row: JobTable) -> JobSummary:
        """JobTable을 JobSummary로 변환"""
        days_until_deadline = None
        if row.deadline:
            delta = row.deadline - datetime.now()
            days_until_deadline = max(0, delta.days)

        return JobSummary(
            id=row.id,
            title=row.title,
            company_name=row.company_name,
            company_logo=row.company_logo,
            experience_text=row.experience_text,
            deadline_text=row.deadline_text,
            location=row.location,
            source=row.source,
            source_url=row.source_url,
            crawled_at=row.crawled_at,
            is_new=row.is_new,
            days_until_deadline=days_until_deadline,
        )

    def save_jobs(self, jobs: List[JobPosting]) -> int:
        """채용 공고 저장 (upsert)"""
        session = self.Session()
        saved_count = 0

        try:
            for job in jobs:
                existing = session.query(JobTable).filter_by(id=job.id).first()

                if existing:
                    # 업데이트
                    existing.title = job.title
                    existing.company_name = job.company_name
                    existing.deadline = job.deadline
                    existing.deadline_text = job.deadline_text
                    existing.updated_at = datetime.now()
                    existing.is_new = False
                else:
                    # 새 공고 추가
                    job_table = self._to_job_table(job)
                    job_table.is_new = True
                    session.add(job_table)
                    saved_count += 1

            session.commit()
            logger.info(f"저장 완료: 신규 {saved_count}건")
            return saved_count

        except Exception as e:
            session.rollback()
            logger.error(f"저장 오류: {e}")
            raise
        finally:
            session.close()

    def get_all_jobs(self, active_only: bool = True) -> List[JobSummary]:
        """모든 채용 공고 조회"""
        session = self.Session()

        try:
            query = session.query(JobTable)

            if active_only:
                query = query.filter(JobTable.is_active == True)

            # 마감일 임박 순으로 정렬
            rows = query.order_by(JobTable.deadline.asc().nulls_last()).all()

            return [self._to_job_summary(row) for row in rows]

        finally:
            session.close()

    def get_job_by_id(self, job_id: str) -> Optional[JobPosting]:
        """ID로 채용 공고 조회"""
        session = self.Session()

        try:
            row = session.query(JobTable).filter_by(id=job_id).first()
            return self._to_job_posting(row) if row else None

        finally:
            session.close()

    def get_jobs_by_source(self, source: str) -> List[JobSummary]:
        """소스별 채용 공고 조회"""
        session = self.Session()

        try:
            rows = (
                session.query(JobTable)
                .filter(JobTable.source == source, JobTable.is_active == True)
                .order_by(JobTable.deadline.asc().nulls_last())
                .all()
            )

            return [self._to_job_summary(row) for row in rows]

        finally:
            session.close()

    def get_new_jobs(self) -> List[JobSummary]:
        """새 채용 공고 조회"""
        session = self.Session()

        try:
            rows = (
                session.query(JobTable)
                .filter(JobTable.is_new == True, JobTable.is_active == True)
                .order_by(JobTable.crawled_at.desc())
                .all()
            )

            return [self._to_job_summary(row) for row in rows]

        finally:
            session.close()

    def get_expiring_jobs(self, days: int = 7) -> List[JobSummary]:
        """마감 임박 채용 공고 조회"""
        session = self.Session()

        try:
            deadline_threshold = datetime.now() + timedelta(days=days)

            rows = (
                session.query(JobTable)
                .filter(
                    JobTable.deadline != None,
                    JobTable.deadline <= deadline_threshold,
                    JobTable.deadline >= datetime.now(),
                    JobTable.is_active == True,
                )
                .order_by(JobTable.deadline.asc())
                .all()
            )

            return [self._to_job_summary(row) for row in rows]

        finally:
            session.close()

    def mark_as_read(self, job_id: str):
        """채용 공고를 읽음 처리"""
        session = self.Session()

        try:
            job = session.query(JobTable).filter_by(id=job_id).first()
            if job:
                job.is_new = False
                session.commit()

        finally:
            session.close()

    def mark_expired_jobs(self):
        """마감된 공고 비활성화"""
        session = self.Session()

        try:
            expired = (
                session.query(JobTable)
                .filter(
                    JobTable.deadline != None,
                    JobTable.deadline < datetime.now(),
                    JobTable.is_active == True,
                )
                .all()
            )

            for job in expired:
                job.is_active = False

            session.commit()
            logger.info(f"마감 처리: {len(expired)}건")

        finally:
            session.close()

    def get_statistics(self) -> dict:
        """통계 정보 조회"""
        session = self.Session()

        try:
            total = session.query(JobTable).filter(JobTable.is_active == True).count()
            new_count = session.query(JobTable).filter(JobTable.is_new == True, JobTable.is_active == True).count()

            # 소스별 통계
            source_stats = {}
            for source in JobSource:
                count = (
                    session.query(JobTable)
                    .filter(JobTable.source == source.value, JobTable.is_active == True)
                    .count()
                )
                source_stats[source.value] = count

            # 마감 임박
            deadline_threshold = datetime.now() + timedelta(days=7)
            expiring = (
                session.query(JobTable)
                .filter(
                    JobTable.deadline != None,
                    JobTable.deadline <= deadline_threshold,
                    JobTable.deadline >= datetime.now(),
                    JobTable.is_active == True,
                )
                .count()
            )

            return {
                "total": total,
                "new": new_count,
                "expiring_7days": expiring,
                "by_source": source_stats,
            }

        finally:
            session.close()
