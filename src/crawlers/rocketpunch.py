"""
로켓펀치 크롤러
"""
import re
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode

from loguru import logger

from .base import BaseCrawler
from src.models import JobPosting, JobSource, ExperienceLevel


class RocketPunchCrawler(BaseCrawler):
    """로켓펀치 크롤러"""

    source = JobSource.ROCKETPUNCH
    BASE_URL = "https://www.rocketpunch.com"
    API_URL = "https://www.rocketpunch.com/api/jobs"

    # 검색 키워드 및 카테고리
    SEARCH_KEYWORDS = ["데이터 분석", "데이터 사이언스", "Data Analyst"]

    async def crawl(self) -> List[JobPosting]:
        """채용 공고 목록 크롤링"""
        all_jobs = []

        for keyword in self.SEARCH_KEYWORDS:
            jobs = await self._search_jobs(keyword)
            all_jobs.extend(jobs)
            logger.info(f"[로켓펀치] '{keyword}' 검색 결과: {len(jobs)}건")

        # 중복 제거
        seen_ids = set()
        unique_jobs = []
        for job in all_jobs:
            if job.source_id not in seen_ids:
                seen_ids.add(job.source_id)
                if self.matches_filter(job):
                    unique_jobs.append(job)

        logger.info(f"[로켓펀치] 총 {len(unique_jobs)}건 수집 완료")
        return unique_jobs

    async def _search_jobs(self, keyword: str) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        params = {
            "keywords": keyword,
            "career": "entry",  # entry: 신입, any: 경력무관
        }

        url = f"{self.BASE_URL}/jobs?{urlencode(params)}"
        html = await self.fetch(url)

        if not html:
            return []

        return self._parse_job_list(html)

    def _parse_job_list(self, html: str) -> List[JobPosting]:
        """채용 공고 목록 파싱"""
        soup = self.parse_html(html)
        jobs = []

        # 채용 공고 카드 찾기
        job_cards = soup.select(".job-card")

        for card in job_cards:
            try:
                job = self._parse_job_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.error(f"[로켓펀치] 파싱 오류: {e}")
                continue

        return jobs

    def _parse_job_card(self, card) -> Optional[JobPosting]:
        """채용 공고 카드 파싱"""
        # 회사명
        company_elem = card.select_one(".company-name")
        if not company_elem:
            return None
        company_name = company_elem.get_text(strip=True)

        # 포지션명
        title_elem = card.select_one(".job-title")
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)

        # 링크
        link_elem = card.select_one("a[href*='/jobs/']")
        link = ""
        source_id = ""
        if link_elem:
            link = link_elem.get("href", "")
            if link.startswith("/"):
                link = f"{self.BASE_URL}{link}"
            source_id = self._extract_source_id(link)

        if not source_id:
            return None

        # 회사 로고
        logo_elem = card.select_one(".company-logo img")
        company_logo = logo_elem.get("src") if logo_elem else None

        # 태그 정보 (경력, 위치 등)
        tags = card.select(".job-stat-info span, .job-tags span")
        experience_text = ""
        location = ""

        for tag in tags:
            text = tag.get_text(strip=True)
            if any(exp in text for exp in ["신입", "경력", "무관", "인턴"]):
                experience_text = text
            elif any(loc in text for loc in ["서울", "경기", "부산", "대전"]):
                location = text

        experience_level = self._determine_experience_level(experience_text)

        # 마감일
        deadline_elem = card.select_one(".deadline, .job-deadline")
        deadline_text = deadline_elem.get_text(strip=True) if deadline_elem else ""
        deadline = self._parse_deadline(deadline_text)

        return JobPosting(
            id=self.generate_id(self.source.value, source_id),
            title=title,
            company_name=company_name,
            company_logo=company_logo,
            experience_level=experience_level,
            experience_text=experience_text,
            deadline=deadline,
            deadline_text=deadline_text,
            location=location,
            source=self.source,
            source_url=link,
            source_id=source_id,
            crawled_at=datetime.now(),
        )

    def _extract_source_id(self, url: str) -> str:
        """URL에서 공고 ID 추출"""
        match = re.search(r"/jobs/(\d+)", url)
        if match:
            return match.group(1)
        return ""

    def _determine_experience_level(self, text: str) -> ExperienceLevel:
        """경력 레벨 결정"""
        text = text.lower()
        if "인턴" in text:
            return ExperienceLevel.INTERN
        if "경력무관" in text or "경력 무관" in text:
            return ExperienceLevel.ANY
        if "신입" in text:
            return ExperienceLevel.ENTRY
        return ExperienceLevel.EXPERIENCED

    def _parse_deadline(self, text: str) -> Optional[datetime]:
        """마감일 파싱"""
        if not text:
            return None

        today = datetime.now()

        # D-7 형식
        match = re.search(r"D-(\d+)", text)
        if match:
            days = int(match.group(1))
            return today + timedelta(days=days)

        # YYYY.MM.DD 형식
        match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)
        if match:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return datetime(year, month, day)

        return None

    async def get_job_detail(self, job: JobPosting) -> JobPosting:
        """채용 공고 상세 정보 가져오기"""
        html = await self.fetch(job.source_url)
        if not html:
            return job

        soup = self.parse_html(html)

        # 상세 설명
        desc_elem = soup.select_one(".job-description, .content-body")
        if desc_elem:
            job.description = desc_elem.get_text(strip=True)[:500]

        # 기술 스택
        tech_elems = soup.select(".job-skill-tags span, .tech-stack span")
        job.tech_stack = [elem.get_text(strip=True) for elem in tech_elems][:10]

        # 자격 요건
        requirements = []
        req_section = soup.select_one(".requirements, .qualifications")
        if req_section:
            for li in req_section.select("li"):
                requirements.append(li.get_text(strip=True))
        job.requirements = requirements[:10]

        job.updated_at = datetime.now()
        return job
