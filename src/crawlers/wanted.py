"""
원티드 크롤러
- 원티드는 API를 사용하여 데이터를 가져옴
"""
import re
from typing import List, Optional
from datetime import datetime

from loguru import logger

from .base import BaseCrawler
from src.models import JobPosting, JobSource, ExperienceLevel


class WantedCrawler(BaseCrawler):
    """원티드 크롤러"""

    source = JobSource.WANTED
    BASE_URL = "https://www.wanted.co.kr"
    API_URL = "https://www.wanted.co.kr/api/v4/jobs"

    # 원티드 직무 카테고리 ID
    # 518: 데이터 분석가
    # 655: 데이터 사이언티스트
    # 656: 데이터 엔지니어
    # 1024: 머신러닝 엔지니어
    JOB_CATEGORY_IDS = [518, 655, 656, 1024]

    async def crawl(self) -> List[JobPosting]:
        """채용 공고 목록 크롤링"""
        all_jobs = []

        for category_id in self.JOB_CATEGORY_IDS:
            jobs = await self._fetch_jobs_by_category(category_id)
            all_jobs.extend(jobs)
            logger.info(f"[원티드] 카테고리 {category_id}: {len(jobs)}건")

        # 중복 제거
        seen_ids = set()
        unique_jobs = []
        for job in all_jobs:
            if job.source_id not in seen_ids:
                seen_ids.add(job.source_id)
                if self.matches_filter(job):
                    unique_jobs.append(job)

        logger.info(f"[원티드] 총 {len(unique_jobs)}건 수집 완료")
        return unique_jobs

    async def _fetch_jobs_by_category(self, category_id: int, limit: int = 100) -> List[JobPosting]:
        """카테고리별 채용 공고 가져오기"""
        params = {
            "country": "kr",
            "job_sort": "company.response_rate_order",
            "years": "0,1,2,3",  # 신입~3년차
            "locations": "all",
            "limit": limit,
            "offset": 0,
        }

        url = f"{self.API_URL}?tag_type_ids={category_id}"
        for key, value in params.items():
            url += f"&{key}={value}"

        data = await self.fetch_json(url)

        if not data or "data" not in data:
            return []

        return self._parse_job_list(data["data"])

    def _parse_job_list(self, jobs_data: List[dict]) -> List[JobPosting]:
        """채용 공고 목록 파싱"""
        jobs = []

        for job_data in jobs_data:
            try:
                job = self._parse_job_item(job_data)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.error(f"[원티드] 파싱 오류: {e}")
                continue

        return jobs

    def _parse_job_item(self, data: dict) -> Optional[JobPosting]:
        """채용 공고 아이템 파싱"""
        job_id = str(data.get("id", ""))
        if not job_id:
            return None

        company = data.get("company", {})
        company_name = company.get("name", "")

        title = data.get("position", "")
        if not title:
            return None

        # 링크
        source_url = f"{self.BASE_URL}/wd/{job_id}"

        # 회사 로고
        company_logo = company.get("logo_img", {}).get("origin", "")

        # 위치
        location = data.get("address", {}).get("full_location", "")
        if not location:
            location = data.get("address", {}).get("location", "")

        # 경력 조건
        years = data.get("years", 0)
        if years == 0:
            experience_level = ExperienceLevel.ENTRY
            experience_text = "신입"
        elif years == -1:
            experience_level = ExperienceLevel.ANY
            experience_text = "경력무관"
        else:
            experience_level = ExperienceLevel.JUNIOR
            experience_text = f"{years}년 이상"

        return JobPosting(
            id=self.generate_id(self.source.value, job_id),
            title=title,
            company_name=company_name,
            company_logo=company_logo,
            experience_level=experience_level,
            experience_text=experience_text,
            location=location,
            source=self.source,
            source_url=source_url,
            source_id=job_id,
            crawled_at=datetime.now(),
        )

    async def get_job_detail(self, job: JobPosting) -> JobPosting:
        """채용 공고 상세 정보 가져오기"""
        detail_url = f"{self.API_URL}/{job.source_id}"
        data = await self.fetch_json(detail_url)

        if not data or "job" not in data:
            return job

        job_data = data["job"]

        # 상세 설명
        job.description = job_data.get("detail", {}).get("intro", "")[:500]

        # 자격 요건
        requirements_text = job_data.get("detail", {}).get("requirements", "")
        if requirements_text:
            # 줄바꿈으로 분리하여 리스트로 변환
            job.requirements = [
                req.strip()
                for req in requirements_text.split("\n")
                if req.strip()
            ][:10]

        # 우대 사항
        preferred_text = job_data.get("detail", {}).get("preferred_points", "")
        if preferred_text:
            job.preferred = [
                pref.strip()
                for pref in preferred_text.split("\n")
                if pref.strip()
            ][:10]

        # 기술 스택
        skill_tags = job_data.get("skill_tags", [])
        job.tech_stack = [tag.get("title", "") for tag in skill_tags][:10]

        # 마감일 (원티드는 보통 상시채용)
        due_time = job_data.get("due_time")
        if due_time:
            try:
                job.deadline = datetime.fromisoformat(due_time.replace("Z", "+00:00"))
                job.deadline_text = job.deadline.strftime("%Y-%m-%d")
            except:
                pass

        job.updated_at = datetime.now()
        return job
