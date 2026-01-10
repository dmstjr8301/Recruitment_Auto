"""
인디스워크(inthiswork.com) 크롤러 - 데이터 분석 채용 전문
"""
import re
from typing import List, Optional
from datetime import datetime, timedelta

from loguru import logger

from .base import BaseCrawler
from src.models import JobPosting, JobSource, ExperienceLevel


class InthisworkCrawler(BaseCrawler):
    """인디스워크 크롤러"""

    source = JobSource.INTHISWORK
    BASE_URL = "https://inthiswork.com"

    async def crawl(self) -> List[JobPosting]:
        """채용 공고 목록 크롤링"""
        url = f"{self.BASE_URL}/data"
        html = await self.fetch(url)

        if not html:
            logger.error("[인디스워크] 페이지 로드 실패")
            return []

        jobs = self._parse_job_list(html)

        # 필터 적용
        filtered_jobs = []
        for job in jobs:
            if self.matches_filter(job):
                filtered_jobs.append(job)

        logger.info(f"[인디스워크] 총 {len(filtered_jobs)}건 수집 완료 (필터 전: {len(jobs)}건)")
        return filtered_jobs

    def _parse_job_list(self, html: str) -> List[JobPosting]:
        """채용 공고 목록 파싱"""
        soup = self.parse_html(html)
        jobs = []

        # archives 링크에서 채용 공고 추출 (회사명｜포지션 형식)
        archive_links = soup.select('a[href*="/archives/"]')
        logger.info(f"[인디스워크] {len(archive_links)}개 링크 발견")

        # 중복 제거를 위한 딕셔너리
        unique_jobs = {}
        for link in archive_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)

            # comment 링크는 기본 URL로 정리
            if '#comment' in href or '/comment-page' in href:
                base_href = href.split('#')[0].split('/comment-page')[0]
            else:
                base_href = href

            # "회사명｜포지션" 형식인 경우만 처리
            if base_href and '｜' in text and base_href not in unique_jobs:
                unique_jobs[base_href] = text

        logger.info(f"[인디스워크] {len(unique_jobs)}개 유니크 공고 발견")

        for url, title_text in unique_jobs.items():
            try:
                job = self._parse_job_from_link(url, title_text)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"[인디스워크] 파싱 오류: {e}")
                continue

        return jobs

    def _parse_job_from_link(self, url: str, title_text: str) -> Optional[JobPosting]:
        """링크에서 채용 공고 정보 추출"""
        # "회사명｜포지션" 형식 파싱
        parts = title_text.split('｜')
        if len(parts) < 2:
            return None

        company_name = parts[0].strip()
        title = parts[1].strip()

        if not company_name or not title:
            return None

        # 공고 ID 추출 (URL에서 숫자 추출)
        source_id = self._extract_source_id(url)

        # 제목에서 경력 조건 추출
        experience_text = ""
        exp_patterns = [
            (r'인턴', '인턴'),
            (r'신입', '신입'),
            (r'경력\s*무관', '경력무관'),
            (r'(\d+)년\s*이상', None),
            (r'(\d+)\s*~\s*(\d+)년', None),
        ]
        for pattern, default_text in exp_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                experience_text = default_text or match.group(0)
                break

        experience_level = self._determine_experience_level(experience_text or title)

        return JobPosting(
            id=self.generate_id(self.source.value, source_id),
            title=title,
            company_name=company_name,
            experience_level=experience_level,
            experience_text=experience_text,
            deadline=None,
            deadline_text="",
            location="",
            source=self.source,
            source_url=url,
            source_id=source_id,
            crawled_at=datetime.now(),
        )

    def _extract_source_id(self, url: str) -> str:
        """URL에서 공고 ID 추출"""
        if not url:
            return ""
        # /archives/12345 형식
        match = re.search(r'/archives/(\d+)', url)
        if match:
            return match.group(1)
        # URL의 마지막 경로를 ID로 사용
        return url.rstrip('/').split('/')[-1][:20]

    def _determine_experience_level(self, text: str) -> ExperienceLevel:
        """경력 레벨 결정"""
        if not text:
            return ExperienceLevel.ANY
        text = text.lower()
        if "인턴" in text or "intern" in text:
            return ExperienceLevel.INTERN
        if "경력무관" in text or "경력 무관" in text:
            return ExperienceLevel.ANY
        if "신입" in text or "entry" in text or "junior" in text:
            return ExperienceLevel.ENTRY
        if any(x in text for x in ["경력", "시니어", "senior"]):
            return ExperienceLevel.EXPERIENCED
        return ExperienceLevel.ANY

    def _parse_deadline(self, text: str) -> Optional[datetime]:
        """마감일 파싱"""
        if not text:
            return None

        today = datetime.now()

        # D-7 형식
        match = re.search(r'D-(\d+)', text, re.IGNORECASE)
        if match:
            days = int(match.group(1))
            return today + timedelta(days=days)

        # YYYY-MM-DD 형식
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
        if match:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return datetime(year, month, day)

        # YYYY.MM.DD 형식
        match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', text)
        if match:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return datetime(year, month, day)

        # MM/DD 또는 MM.DD 형식
        match = re.search(r'(\d{1,2})[/.](\d{1,2})', text)
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

        # 인디스워크 상세 페이지 구조에 맞게 파싱
        # entry-content 클래스에서 내용 추출
        content_elem = soup.select_one('.entry-content, .post-content, article')
        if content_elem:
            job.description = content_elem.get_text(strip=True)[:500]

        job.updated_at = datetime.now()
        return job
