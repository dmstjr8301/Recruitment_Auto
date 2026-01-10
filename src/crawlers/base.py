"""
크롤러 기본 클래스
"""
import asyncio
import hashlib
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger

from src.models import JobPosting, JobSource
from config import settings


class BaseCrawler(ABC):
    """크롤러 기본 클래스"""

    source: JobSource

    def __init__(self):
        self.settings = settings.crawler
        self.filter_settings = settings.filter
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": self.settings.user_agent},
            timeout=aiohttp.ClientTimeout(total=self.settings.request_timeout),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch(self, url: str) -> Optional[str]:
        """URL에서 HTML 가져오기"""
        try:
            await asyncio.sleep(self.settings.request_delay_seconds)
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                logger.warning(f"Failed to fetch {url}: status {response.status}")
                return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    async def fetch_json(self, url: str, **kwargs) -> Optional[dict]:
        """URL에서 JSON 가져오기"""
        try:
            await asyncio.sleep(self.settings.request_delay_seconds)
            async with self.session.get(url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                logger.warning(f"Failed to fetch {url}: status {response.status}")
                return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def parse_html(self, html: str) -> BeautifulSoup:
        """HTML 파싱"""
        return BeautifulSoup(html, "html.parser")

    def generate_id(self, source: str, source_id: str) -> str:
        """고유 ID 생성"""
        unique_str = f"{source}_{source_id}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:12]

    def matches_filter(self, job: JobPosting) -> bool:
        """필터 조건에 맞는지 확인"""
        # 제외 키워드 체크
        title_lower = job.title.lower()
        for exclude in self.filter_settings.exclude_keywords:
            if exclude.lower() in title_lower:
                return False

        # 직무 키워드 체크 (OR 조건)
        job_match = False
        search_text = f"{job.title} {job.description or ''}".lower()
        for keyword in self.filter_settings.job_keywords:
            if keyword.lower() in search_text:
                job_match = True
                break

        if not job_match:
            return False

        # 경력 조건 체크 (OR 조건)
        exp_text = (job.experience_text or "").lower()
        for exp_keyword in self.filter_settings.experience_keywords:
            if exp_keyword.lower() in exp_text:
                return True

        # 기본적으로 경력 조건이 없으면 포함
        return not job.experience_text

    @abstractmethod
    async def crawl(self) -> List[JobPosting]:
        """채용 공고 크롤링 (구현 필요)"""
        pass

    @abstractmethod
    async def get_job_detail(self, job: JobPosting) -> JobPosting:
        """채용 공고 상세 정보 가져오기 (구현 필요)"""
        pass
