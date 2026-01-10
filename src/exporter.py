"""
JSON 내보내기 및 정적 사이트 생성 모듈
"""
import json
from datetime import datetime
from pathlib import Path
from typing import List

from loguru import logger

from src.models import JobPosting, JobSource
from config import settings


class JSONExporter:
    """JSON 파일 내보내기"""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or settings.base_dir / "data"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_jobs(self, jobs: List[JobPosting]) -> Path:
        """채용 공고를 JSON 파일로 내보내기"""
        output_file = self.output_dir / "jobs.json"

        # 기존 데이터 로드
        existing_jobs = {}
        if output_file.exists():
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    existing_jobs = {job["id"]: job for job in data.get("jobs", [])}
            except:
                pass

        # 새 데이터 병합 (first_seen_at 기반 is_new 판별)
        now = datetime.now()
        new_threshold_hours = 48  # 48시간 이내 발견된 공고를 "새 공고"로 표시
        new_count = 0

        for job in jobs:
            job_dict = self._job_to_dict(job)
            if job.id not in existing_jobs:
                # 처음 발견된 공고: first_seen_at 기록
                job_dict["first_seen_at"] = now.isoformat()
                job_dict["is_new"] = True
                new_count += 1
            else:
                # 기존 공고: first_seen_at 유지, is_new는 시간 기반으로 판별
                existing_job = existing_jobs[job.id]
                job_dict["first_seen_at"] = existing_job.get("first_seen_at", now.isoformat())

                # first_seen_at으로부터 48시간 이내면 여전히 "새 공고"
                try:
                    first_seen = datetime.fromisoformat(job_dict["first_seen_at"])
                    hours_since_first_seen = (now - first_seen).total_seconds() / 3600
                    job_dict["is_new"] = hours_since_first_seen <= new_threshold_hours
                    if job_dict["is_new"]:
                        new_count += 1
                except:
                    job_dict["is_new"] = False

            existing_jobs[job.id] = job_dict

        # 마감된 공고 필터링
        now = datetime.now()
        active_jobs = []
        for job in existing_jobs.values():
            if job.get("deadline"):
                try:
                    deadline = datetime.fromisoformat(job["deadline"])
                    if deadline < now:
                        continue  # 마감된 공고 제외
                except:
                    pass
            active_jobs.append(job)

        # 마감일 기준 정렬
        active_jobs.sort(
            key=lambda x: (
                x.get("deadline") or "9999-99-99",
                x.get("crawled_at") or ""
            )
        )

        # 통계 계산
        stats = self._calculate_stats(active_jobs)

        # 저장
        output_data = {
            "updated_at": datetime.now().isoformat(),
            "stats": stats,
            "jobs": active_jobs,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON 저장 완료: {output_file} ({len(active_jobs)}건, 신규 {new_count}건)")
        return output_file

    def _job_to_dict(self, job: JobPosting) -> dict:
        """JobPosting을 dict로 변환"""
        return {
            "id": job.id,
            "title": job.title,
            "company_name": job.company_name,
            "company_logo": job.company_logo,
            "experience_level": job.experience_level.value if hasattr(job.experience_level, 'value') else job.experience_level,
            "experience_text": job.experience_text,
            "deadline": job.deadline.isoformat() if job.deadline else None,
            "deadline_text": job.deadline_text,
            "internship_period": job.internship_period,
            "location": job.location,
            "salary": job.salary,
            "employment_type": job.employment_type,
            "requirements": job.requirements or [],
            "preferred": job.preferred or [],
            "tech_stack": job.tech_stack or [],
            "description": job.description,
            "source": job.source.value if hasattr(job.source, 'value') else job.source,
            "source_url": job.source_url,
            "crawled_at": job.crawled_at.isoformat() if job.crawled_at else None,
            "is_new": job.is_new,
        }

    def _calculate_stats(self, jobs: List[dict]) -> dict:
        """통계 계산"""
        now = datetime.now()

        total = len(jobs)
        new_count = sum(1 for j in jobs if j.get("is_new"))

        # 7일 내 마감
        expiring = 0
        for job in jobs:
            if job.get("deadline"):
                try:
                    deadline = datetime.fromisoformat(job["deadline"])
                    days_left = (deadline - now).days
                    if 0 <= days_left <= 7:
                        expiring += 1
                except:
                    pass

        # 소스별 통계
        by_source = {}
        for source in JobSource:
            count = sum(1 for j in jobs if j.get("source") == source.value)
            by_source[source.value] = count

        return {
            "total": total,
            "new": new_count,
            "expiring_7days": expiring,
            "by_source": by_source,
        }


class StaticSiteBuilder:
    """정적 사이트 빌더"""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or settings.base_dir / "docs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = settings.base_dir / "data"

    def build(self):
        """정적 사이트 생성"""
        # jobs.json 복사
        jobs_file = self.data_dir / "jobs.json"
        if jobs_file.exists():
            import shutil
            shutil.copy(jobs_file, self.output_dir / "jobs.json")

        # index.html 생성
        self._create_index_html()

        logger.info(f"정적 사이트 생성 완료: {self.output_dir}")

    def _create_index_html(self):
        """index.html 생성"""
        html = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>채용 정보 대시보드 - 데이터 분석</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .new-badge { animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
        .card-hover:hover { transform: translateY(-2px); box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1); }
        .source-saramin { border-left-color: #0066cc; }
        .source-jobkorea { border-left-color: #ff6600; }
        .source-wanted { border-left-color: #3366ff; }
        .source-rocketpunch { border-left-color: #6366f1; }
        .source-linkedin { border-left-color: #0077b5; }
        .source-jobtalio { border-left-color: #22c55e; }
        .loading { display: flex; justify-content: center; align-items: center; height: 200px; }
        .spinner { width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <nav class="bg-white shadow-sm border-b sticky top-0 z-10">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex items-center justify-between">
                <h1 class="text-xl font-bold text-gray-800">채용 정보 대시보드</h1>
                <div class="text-sm text-gray-500">
                    <span id="update-time">업데이트: -</span>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-4 py-6">
        <!-- 통계 -->
        <div id="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div class="bg-white rounded-lg shadow p-4">
                <div id="stat-total" class="text-3xl font-bold text-blue-600">-</div>
                <div class="text-gray-500 text-sm">전체 공고</div>
            </div>
            <div class="bg-white rounded-lg shadow p-4">
                <div id="stat-new" class="text-3xl font-bold text-green-600">-</div>
                <div class="text-gray-500 text-sm">새 공고</div>
            </div>
            <div class="bg-white rounded-lg shadow p-4">
                <div id="stat-expiring" class="text-3xl font-bold text-orange-600">-</div>
                <div class="text-gray-500 text-sm">7일 내 마감</div>
            </div>
            <div class="bg-white rounded-lg shadow p-4">
                <div id="stat-sources" class="text-3xl font-bold text-purple-600">2</div>
                <div class="text-gray-500 text-sm">수집 사이트</div>
            </div>
        </div>

        <!-- 필터 -->
        <div class="bg-white rounded-lg shadow p-4 mb-6">
            <div class="flex flex-wrap gap-2" id="filters">
                <button onclick="filterJobs('all')" class="filter-btn active px-4 py-2 rounded-full text-sm font-medium bg-blue-600 text-white" data-filter="all">전체</button>
                <button onclick="filterJobs('new')" class="filter-btn px-4 py-2 rounded-full text-sm font-medium bg-gray-100 text-gray-700 hover:bg-gray-200" data-filter="new">새 공고</button>
                <button onclick="filterJobs('expiring')" class="filter-btn px-4 py-2 rounded-full text-sm font-medium bg-gray-100 text-gray-700 hover:bg-gray-200" data-filter="expiring">마감 임박</button>
            </div>
        </div>

        <!-- 채용 공고 목록 -->
        <div id="jobs-container">
            <div class="loading">
                <div class="spinner"></div>
            </div>
        </div>
    </main>

    <footer class="bg-white border-t mt-8 py-4">
        <div class="max-w-7xl mx-auto px-4 text-center text-gray-500 text-sm">
            Recruitment Auto - 채용 정보 자동 수집 에이전트
            <br>
            <a href="https://github.com" class="text-blue-500 hover:underline">GitHub</a>에서 자동 업데이트
        </div>
    </footer>

    <script>
        let allJobs = [];
        let currentFilter = 'all';

        async function loadJobs() {
            try {
                const response = await fetch('jobs.json');
                const data = await response.json();

                allJobs = data.jobs || [];
                updateStats(data.stats);
                updateTime(data.updated_at);
                renderJobs(allJobs);
            } catch (error) {
                console.error('Error loading jobs:', error);
                document.getElementById('jobs-container').innerHTML = `
                    <div class="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                        <p>데이터를 불러올 수 없습니다.</p>
                        <p class="text-sm mt-2">잠시 후 다시 시도해주세요.</p>
                    </div>
                `;
            }
        }

        function updateStats(stats) {
            if (!stats) return;
            document.getElementById('stat-total').textContent = stats.total || 0;
            document.getElementById('stat-new').textContent = stats.new || 0;
            document.getElementById('stat-expiring').textContent = stats.expiring_7days || 0;
        }

        function updateTime(isoString) {
            if (!isoString) return;
            const date = new Date(isoString);
            document.getElementById('update-time').textContent =
                `업데이트: ${date.toLocaleDateString('ko-KR')} ${date.toLocaleTimeString('ko-KR', {hour: '2-digit', minute: '2-digit'})}`;
        }

        function filterJobs(filter) {
            currentFilter = filter;

            // 버튼 스타일 업데이트
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('bg-blue-600', 'text-white');
                btn.classList.add('bg-gray-100', 'text-gray-700');
            });
            document.querySelector(`[data-filter="${filter}"]`).classList.remove('bg-gray-100', 'text-gray-700');
            document.querySelector(`[data-filter="${filter}"]`).classList.add('bg-blue-600', 'text-white');

            let filtered = allJobs;
            if (filter === 'new') {
                filtered = allJobs.filter(job => job.is_new);
            } else if (filter === 'expiring') {
                const now = new Date();
                const weekLater = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
                filtered = allJobs.filter(job => {
                    if (!job.deadline) return false;
                    const deadline = new Date(job.deadline);
                    return deadline >= now && deadline <= weekLater;
                });
            }

            renderJobs(filtered);
        }

        function renderJobs(jobs) {
            const container = document.getElementById('jobs-container');

            if (jobs.length === 0) {
                container.innerHTML = `
                    <div class="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                        <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <p>조건에 맞는 채용 공고가 없습니다.</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = jobs.map(job => {
                const daysLeft = job.deadline ? getDaysUntilDeadline(job.deadline) : null;

                return `
                    <a href="${job.source_url}" target="_blank" rel="noopener noreferrer" class="block mb-4">
                        <div class="bg-white rounded-lg shadow p-4 border-l-4 source-${job.source} card-hover transition duration-200">
                            <div class="flex items-start justify-between">
                                <div class="flex-1">
                                    <div class="flex items-center gap-2 mb-1">
                                        ${job.is_new ? '<span class="new-badge bg-green-500 text-white text-xs px-2 py-0.5 rounded-full">NEW</span>' : ''}
                                        ${daysLeft !== null && daysLeft <= 7 ? `<span class="bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">D-${daysLeft}</span>` : ''}
                                        <span class="text-xs text-gray-500 uppercase">${job.source}</span>
                                    </div>
                                    <h3 class="text-lg font-semibold text-gray-800 mb-1">${escapeHtml(job.title)}</h3>
                                    <div class="flex items-center gap-3 text-sm text-gray-600">
                                        <span class="font-medium">${escapeHtml(job.company_name)}</span>
                                        ${job.location ? `<span>${escapeHtml(job.location)}</span>` : ''}
                                        ${job.experience_text ? `<span class="text-blue-600">${escapeHtml(job.experience_text)}</span>` : ''}
                                    </div>
                                </div>
                                <div class="text-right text-sm">
                                    ${job.deadline_text ? `<div class="text-gray-500">마감: ${escapeHtml(job.deadline_text)}</div>` : ''}
                                    <div class="text-gray-400 text-xs mt-1">${formatDate(job.crawled_at)}</div>
                                </div>
                            </div>
                        </div>
                    </a>
                `;
            }).join('');
        }

        function getDaysUntilDeadline(deadline) {
            const now = new Date();
            const deadlineDate = new Date(deadline);
            const diff = deadlineDate - now;
            return Math.max(0, Math.floor(diff / (1000 * 60 * 60 * 24)));
        }

        function formatDate(isoString) {
            if (!isoString) return '';
            const date = new Date(isoString);
            return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // 초기 로드
        loadJobs();

        // 5분마다 새로고침
        setInterval(loadJobs, 5 * 60 * 1000);
    </script>
</body>
</html>'''

        output_file = self.output_dir / "index.html"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"index.html 생성 완료: {output_file}")
