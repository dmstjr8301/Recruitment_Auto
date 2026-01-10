"""
잡코리아 크롤러
"""
import re
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode

from loguru import logger

from .base import BaseCrawler
from src.models import JobPosting, JobSource, ExperienceLevel


class JobKoreaCrawler(BaseCrawler):
    """잡코리아 크롤러"""

    source = JobSource.JOBKOREA
    BASE_URL = "https://www.jobkorea.co.kr"

    SEARCH_KEYWORDS = ["데이터분석", "DataAnalyst", "데이터사이언티스트"]

    async def crawl(self) -> List[JobPosting]:
        """채용 공고 목록 크롤링"""
        all_jobs = []

        for keyword in self.SEARCH_KEYWORDS:
            jobs = await self._search_jobs(keyword)
            all_jobs.extend(jobs)
            logger.info(f"[잡코리아] '{keyword}' 검색 결과: {len(jobs)}건")

        # 중복 제거
        seen_ids = set()
        unique_jobs = []
        for job in all_jobs:
            if job.source_id not in seen_ids:
                seen_ids.add(job.source_id)
                if self.matches_filter(job):
                    unique_jobs.append(job)

        logger.info(f"[잡코리아] 총 {len(unique_jobs)}건 수집 완료")
        return unique_jobs

    async def _search_jobs(self, keyword: str, page: int = 1) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        params = {
            "stext": keyword,
            "tabType": "recruit",
            "Page_No": page,
            "careerType": "1,3",  # 1: 신입, 3: 경력무관
        }

        url = f"{self.BASE_URL}/Search/?{urlencode(params)}"
        html = await self.fetch(url)

        if not html:
            return []

        return self._parse_job_list(html)

    def _parse_job_list(self, html: str) -> List[JobPosting]:
        """채용 공고 목록 파싱"""
        soup = self.parse_html(html)
        jobs = []

        # 채용 공고 아이템 찾기
        job_items = soup.select(".list-default .list-post")

        for item in job_items:
            try:
                job = self._parse_job_item(item)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.error(f"[잡코리아] 파싱 오류: {e}")
                continue

        return jobs

    def _parse_job_item(self, item) -> Optional[JobPosting]:
        """채용 공고 아이템 파싱"""
        # 회사명
        company_elem = item.select_one(".post-list-corp a")
        if not company_elem:
            return None
        company_name = company_elem.get_text(strip=True)

        # 포지션명
        title_elem = item.select_one(".post-list-info a.title")
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)

        # 링크
        link = title_elem.get("href", "")
        if link.startswith("/"):
            link = f"{self.BASE_URL}{link}"

        # 공고 ID
        source_id = self._extract_source_id(link)

        # 조건 정보
        option_elem = item.select_one(".post-list-info .option")
        option_text = option_elem.get_text(strip=True) if option_elem else ""

        # 경력 조건
        experience_text = ""
        experience_level = ExperienceLevel.ANY

        if "신입" in option_text:
            experience_text = "신입"
            experience_level = ExperienceLevel.ENTRY
        elif "경력무관" in option_text:
            experience_text = "경력무관"
            experience_level = ExperienceLevel.ANY
        elif "인턴" in option_text:
            experience_text = "인턴"
            experience_level = ExperienceLevel.INTERN

        # 위치
        location = ""
        loc_match = re.search(r"(서울|경기|부산|대전|대구|인천|광주|세종|울산|강원|충북|충남|전북|전남|경북|경남|제주)[^\s,]*", option_text)
        if loc_match:
            location = loc_match.group(0)

        # 마감일
        date_elem = item.select_one(".post-list-info .date")
        deadline_text = date_elem.get_text(strip=True) if date_elem else ""
        deadline = self._parse_deadline(deadline_text)

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
        match = re.search(r"/Recruit/GI_Read/(\d+)", url)
        if match:
            return match.group(1)
        return url.split("/")[-1]

    def _parse_deadline(self, text: str) -> Optional[datetime]:
        """마감일 파싱"""
        if not text:
            return None

        today = datetime.now()

        # ~01/15(수) 형식
        match = re.search(r"~\s*(\d{1,2})/(\d{1,2})", text)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            year = today.year
            deadline = datetime(year, month, day)
            if deadline < today:
                deadline = datetime(year + 1, month, day)
            return deadline

        # 내일마감, 오늘마감
        if "오늘" in text:
            return today
        if "내일" in text:
            return today + timedelta(days=1)

        return None

    async def get_job_detail(self, job: JobPosting) -> JobPosting:
        """채용 공고 상세 정보 가져오기"""
        html = await self.fetch(job.source_url)
        if not html:
            return job

        soup = self.parse_html(html)

        # 상세 설명
        desc_elem = soup.select_one(".view-detail-content")
        if desc_elem:
            job.description = desc_elem.get_text(strip=True)[:500]

        # 자격 요건
        requirements = []
        req_section = soup.select(".tbRow .cell")
        for cell in req_section:
            label = cell.select_one(".tit")
            if label and "자격요건" in label.get_text():
                content = cell.select_one(".cont")
                if content:
                    requirements = [li.get_text(strip=True) for li in content.select("li")]
        job.requirements = requirements[:10]

        # 실습 기간
        for row in req_section:
            label = row.select_one(".tit")
            if label and any(k in label.get_text() for k in ["수습", "실습", "기간"]):
                content = row.select_one(".cont")
                if content:
                    job.internship_period = content.get_text(strip=True)

        job.updated_at = datetime.now()
        return job
