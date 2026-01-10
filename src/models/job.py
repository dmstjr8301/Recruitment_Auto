"""
채용 공고 데이터 모델
"""
from datetime import datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field


class JobSource(str, Enum):
    """채용 사이트 소스"""
    SARAMIN = "saramin"
    INTHISWORK = "inthiswork"  # 인디스워크 (데이터 분석 전문)


class ExperienceLevel(str, Enum):
    """경력 수준"""
    INTERN = "인턴"
    ENTRY = "신입"
    ANY = "경력무관"
    JUNIOR = "주니어"
    EXPERIENCED = "경력"


class JobPosting(BaseModel):
    """채용 공고 모델"""
    # 기본 정보
    id: Optional[str] = None
    title: str = Field(..., description="포지션명")
    company_name: str = Field(..., description="회사명")
    company_logo: Optional[str] = Field(None, description="회사 로고 URL")

    # 채용 조건
    experience_level: ExperienceLevel = Field(..., description="경력 수준")
    experience_text: Optional[str] = Field(None, description="경력 요건 원문")

    # 기간 정보
    deadline: Optional[datetime] = Field(None, description="마감일")
    deadline_text: Optional[str] = Field(None, description="마감일 원문 (예: '상시채용', 'D-7')")
    internship_period: Optional[str] = Field(None, description="실습/수습 기간")

    # 위치 및 조건
    location: Optional[str] = Field(None, description="근무 위치")
    salary: Optional[str] = Field(None, description="급여")
    employment_type: Optional[str] = Field(None, description="고용 형태 (정규직, 계약직 등)")

    # 상세 정보
    requirements: Optional[List[str]] = Field(default_factory=list, description="자격 요건")
    preferred: Optional[List[str]] = Field(default_factory=list, description="우대 사항")
    tech_stack: Optional[List[str]] = Field(default_factory=list, description="기술 스택")
    description: Optional[str] = Field(None, description="상세 설명")

    # 메타 정보
    source: JobSource = Field(..., description="채용 사이트 소스")
    source_url: str = Field(..., description="원본 링크")
    source_id: Optional[str] = Field(None, description="원본 사이트의 공고 ID")

    # 수집 정보
    crawled_at: datetime = Field(default_factory=datetime.now, description="수집 시간")
    updated_at: Optional[datetime] = Field(None, description="업데이트 시간")

    # 상태
    is_active: bool = Field(True, description="활성 상태")
    is_new: bool = Field(True, description="새 공고 여부")

    class Config:
        use_enum_values = True


class JobSummary(BaseModel):
    """채용 공고 요약 (대시보드용)"""
    id: str
    title: str
    company_name: str
    company_logo: Optional[str] = None
    experience_text: Optional[str] = None
    deadline_text: Optional[str] = None
    location: Optional[str] = None
    source: str
    source_url: str
    crawled_at: datetime
    is_new: bool = True
    days_until_deadline: Optional[int] = None
