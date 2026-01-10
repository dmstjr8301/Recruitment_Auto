"""
잡알리오 (공공기관 채용) 크롤러
"""
import re
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode

from loguru import logger

from .base import BaseCrawler
from src.models import JobPosting, JobSource, ExperienceLevel


class JobTalioCrawler(BaseCrawler):
    """잡알리오 크롤러 - 공공기관 채용 정보"""

    source = JobSource.JOBTALIO
    BASE_URL = "https://www.job.go.kr"

    # 검색 키워드
    SEARCH_KEYWORDS = ["데이터", "분석", "빅데이터"]

    async def crawl(self) -> List[JobPosting]:
        """채용 공고 목록 크롤링"""
        all_jobs = []

        for keyword in self.SEARCH_KEYWORDS:
            jobs = await self._search_jobs(keyword)
            all_jobs.extend(jobs)
            logger.info(f"[잡알리오] '{keyword}' 검색 결과: {len(jobs)}건")

        # 중복 제거
        seen_ids = set()
        unique_jobs = []
        for job in all_jobs:
            if job.source_id not in seen_ids:
                seen_ids.add(job.source_id)
                if self.matches_filter(job):
                    unique_jobs.append(job)

        logger.info(f"[잡알리오] 총 {len(unique_jobs)}건 수집 완료")
        return unique_jobs

    async def _search_jobs(self, keyword: str) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        params = {
            "searchWord": keyword,
            "searchType": "1",
            "careerGbn": "N",  # N: 신입, A: 전체
            "pageNo": 1,
            "pageSize": 50,
        }

        # 잡알리오 공고 검색 페이지
        url = f"{self.BASE_URL}/esroom/servlet/sbsrc/list"

        # POST 요청이 필요할 수 있으므로 GET으로 시도
        search_url = f"{self.BASE_URL}/esroom/servlet/sbsrc/list?{urlencode(params)}"
        html = await self.fetch(search_url)

        if not html:
            # 대체 URL 시도
            alt_url = f"{self.BASE_URL}/jobList/jobListSearch.do?{urlencode(params)}"
            html = await self.fetch(alt_url)

        if not html:
            return []

        return self._parse_job_list(html)

    def _parse_job_list(self, html: str) -> List[JobPosting]:
        """채용 공고 목록 파싱"""
        soup = self.parse_html(html)
        jobs = []

        # 공공기관 채용 공고 테이블/리스트
        job_items = soup.select(".job-list tr, .recruit-list li, .tb-list tr")

        for item in job_items:
            try:
                job = self._parse_job_item(item)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.error(f"[잡알리오] 파싱 오류: {e}")
                continue

        return jobs

    def _parse_job_item(self, item) -> Optional[JobPosting]:
        """채용 공고 아이템 파싱"""
        # 기관명
        company_elem = item.select_one(".corp-name, .company, td:nth-child(1)")
        if not company_elem:
            return None
        company_name = company_elem.get_text(strip=True)

        # 포지션명
        title_elem = item.select_one(".job-title, .title, td:nth-child(2) a")
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)

        # 링크
        link_elem = item.select_one("a[href]")
        link = ""
        source_id = ""

        if link_elem:
            link = link_elem.get("href", "")
            if link.startswith("/"):
                link = f"{self.BASE_URL}{link}"
            source_id = self._extract_source_id(link)

        if not source_id:
            # 임시 ID 생성
            source_id = f"{company_name}_{title}"[:50]

        # 마감일
        deadline_elem = item.select_one(".deadline, .end-date, td:nth-child(4)")
        deadline_text = deadline_elem.get_text(strip=True) if deadline_elem else ""
        deadline = self._parse_deadline(deadline_text)

        # 경력 조건
        career_elem = item.select_one(".career, td:nth-child(3)")
        experience_text = career_elem.get_text(strip=True) if career_elem else ""
        experience_level = self._determine_experience_level(experience_text)

        # 위치
        location_elem = item.select_one(".location, .region, td:nth-child(5)")
        location = location_elem.get_text(strip=True) if location_elem else ""

        return JobPosting(
            id=self.generate_id(self.source.value, source_id),
            title=title,
            company_name=company_name,
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
        # seq=12345 형식
        match = re.search(r"seq=(\d+)", url)
        if match:
            return match.group(1)

        # /detail/12345 형식
        match = re.search(r"/detail/(\d+)", url)
        if match:
            return match.group(1)

        return ""

    def _determine_experience_level(self, text: str) -> ExperienceLevel:
        """경력 레벨 결정"""
        text = text.lower()
        if "인턴" in text:
            return ExperienceLevel.INTERN
        if "경력무관" in text or "무관" in text:
            return ExperienceLevel.ANY
        if "신입" in text:
            return ExperienceLevel.ENTRY
        return ExperienceLevel.ANY  # 공공기관은 기본적으로 경력무관이 많음

    def _parse_deadline(self, text: str) -> Optional[datetime]:
        """마감일 파싱"""
        if not text:
            return None

        today = datetime.now()

        # YYYY.MM.DD 형식
        match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)
        if match:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return datetime(year, month, day)

        # YYYY-MM-DD 형식
        match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if match:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return datetime(year, month, day)

        # MM/DD 형식
        match = re.search(r"(\d{1,2})/(\d{1,2})", text)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            year = today.year
            deadline = datetime(year, month, day)
            if deadline < today:
                deadline = datetime(year + 1, month, day)
            return deadline

        return None

    async def get_job_detail(self, job: JobPosting) -> JobPosting:
        """채용 공고 상세 정보 가져오기"""
        if not job.source_url:
            return job

        html = await self.fetch(job.source_url)
        if not html:
            return job

        soup = self.parse_html(html)

        # 상세 설명
        desc_elem = soup.select_one(".job-detail, .content, .detail-content")
        if desc_elem:
            job.description = desc_elem.get_text(strip=True)[:500]

        # 자격 요건
        requirements = []
        req_section = soup.select(".qualification li, .requirements li")
        for li in req_section:
            requirements.append(li.get_text(strip=True))
        job.requirements = requirements[:10]

        # 실습/수습 기간 (공공기관 인턴의 경우)
        period_elem = soup.find(string=re.compile(r"(근무|실습|수습)\s*기간"))
        if period_elem:
            parent = period_elem.find_parent()
            if parent:
                # 다음 형제 요소에서 기간 정보 추출
                next_elem = parent.find_next_sibling()
                if next_elem:
                    job.internship_period = next_elem.get_text(strip=True)

        job.updated_at = datetime.now()
        return job
