"""
LinkedIn 크롤러
- LinkedIn은 로그인이 필요하므로 공개 API/RSS를 활용
"""
import re
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote

from loguru import logger

from .base import BaseCrawler
from src.models import JobPosting, JobSource, ExperienceLevel


class LinkedInCrawler(BaseCrawler):
    """LinkedIn 크롤러"""

    source = JobSource.LINKEDIN
    BASE_URL = "https://www.linkedin.com"

    # 검색 키워드
    SEARCH_KEYWORDS = ["Data Analyst", "Data Scientist", "데이터 분석"]

    # 위치 (한국)
    LOCATION = "South Korea"
    LOCATION_ID = "105149562"  # LinkedIn의 한국 지역 ID

    async def crawl(self) -> List[JobPosting]:
        """채용 공고 목록 크롤링"""
        all_jobs = []

        for keyword in self.SEARCH_KEYWORDS:
            jobs = await self._search_jobs(keyword)
            all_jobs.extend(jobs)
            logger.info(f"[LinkedIn] '{keyword}' 검색 결과: {len(jobs)}건")

        # 중복 제거
        seen_ids = set()
        unique_jobs = []
        for job in all_jobs:
            if job.source_id not in seen_ids:
                seen_ids.add(job.source_id)
                if self.matches_filter(job):
                    unique_jobs.append(job)

        logger.info(f"[LinkedIn] 총 {len(unique_jobs)}건 수집 완료")
        return unique_jobs

    async def _search_jobs(self, keyword: str) -> List[JobPosting]:
        """키워드로 채용 공고 검색 (공개 페이지 사용)"""
        params = {
            "keywords": keyword,
            "location": self.LOCATION,
            "f_E": "1,2",  # Entry level, Associate
            "f_TPR": "r604800",  # 지난 7일
        }

        # LinkedIn 공개 채용 페이지
        url = f"{self.BASE_URL}/jobs/search?{urlencode(params)}"
        html = await self.fetch(url)

        if not html:
            return []

        return self._parse_job_list(html)

    def _parse_job_list(self, html: str) -> List[JobPosting]:
        """채용 공고 목록 파싱"""
        soup = self.parse_html(html)
        jobs = []

        # LinkedIn 채용 공고 카드 (공개 페이지 기준)
        job_cards = soup.select(".base-card, .job-search-card")

        for card in job_cards:
            try:
                job = self._parse_job_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.error(f"[LinkedIn] 파싱 오류: {e}")
                continue

        return jobs

    def _parse_job_card(self, card) -> Optional[JobPosting]:
        """채용 공고 카드 파싱"""
        # 포지션명
        title_elem = card.select_one(".base-card__title, .job-card-list__title")
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)

        # 회사명
        company_elem = card.select_one(".base-card__subtitle, .job-card-container__company-name")
        if not company_elem:
            return None
        company_name = company_elem.get_text(strip=True)

        # 링크
        link_elem = card.select_one("a.base-card__full-link, a.job-card-list__title")
        link = ""
        source_id = ""

        if link_elem:
            link = link_elem.get("href", "")
            source_id = self._extract_source_id(link)

        if not source_id:
            # data-entity-urn에서 추출 시도
            urn = card.get("data-entity-urn", "")
            match = re.search(r":(\d+)$", urn)
            if match:
                source_id = match.group(1)
                link = f"{self.BASE_URL}/jobs/view/{source_id}"

        if not source_id:
            return None

        # 위치
        location_elem = card.select_one(".job-card-container__metadata-item, .base-card__metadata")
        location = location_elem.get_text(strip=True) if location_elem else ""

        # 회사 로고
        logo_elem = card.select_one(".company-logo img, .artdeco-entity-image")
        company_logo = logo_elem.get("src") if logo_elem else None

        # 게시 시간
        posted_elem = card.select_one(".job-card-container__footer-item, time")
        posted_text = posted_elem.get_text(strip=True) if posted_elem else ""

        # 경력 레벨 (LinkedIn은 기본적으로 Entry level로 검색하므로)
        experience_level = ExperienceLevel.ENTRY
        experience_text = "Entry level"

        return JobPosting(
            id=self.generate_id(self.source.value, source_id),
            title=title,
            company_name=company_name,
            company_logo=company_logo,
            experience_level=experience_level,
            experience_text=experience_text,
            location=location,
            deadline_text=posted_text,
            source=self.source,
            source_url=link,
            source_id=source_id,
            crawled_at=datetime.now(),
        )

    def _extract_source_id(self, url: str) -> str:
        """URL에서 공고 ID 추출"""
        # /jobs/view/1234567890 형식
        match = re.search(r"/jobs/view/(\d+)", url)
        if match:
            return match.group(1)

        # ?currentJobId=1234567890 형식
        match = re.search(r"currentJobId=(\d+)", url)
        if match:
            return match.group(1)

        return ""

    async def get_job_detail(self, job: JobPosting) -> JobPosting:
        """채용 공고 상세 정보 가져오기"""
        html = await self.fetch(job.source_url)
        if not html:
            return job

        soup = self.parse_html(html)

        # 상세 설명
        desc_elem = soup.select_one(".show-more-less-html__markup, .description__text")
        if desc_elem:
            job.description = desc_elem.get_text(strip=True)[:500]

        # 고용 형태
        employment_elem = soup.select_one(".job-criteria-item:contains('Employment type')")
        if employment_elem:
            value_elem = employment_elem.select_one(".job-criteria-text")
            if value_elem:
                job.employment_type = value_elem.get_text(strip=True)

        # Seniority level
        seniority_elem = soup.select_one(".job-criteria-item:contains('Seniority level')")
        if seniority_elem:
            value_elem = seniority_elem.select_one(".job-criteria-text")
            if value_elem:
                seniority = value_elem.get_text(strip=True).lower()
                if "intern" in seniority:
                    job.experience_level = ExperienceLevel.INTERN
                    job.experience_text = "Intern"
                elif "entry" in seniority:
                    job.experience_level = ExperienceLevel.ENTRY
                    job.experience_text = "Entry level"

        job.updated_at = datetime.now()
        return job
