"""
채용 정보 자동 수집 에이전트 - 메인 진입점
"""
import asyncio
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.crawlers import (
    SaraminCrawler,
    JobKoreaCrawler,
    WantedCrawler,
    RocketPunchCrawler,
    LinkedInCrawler,
    JobTalioCrawler,
)
from src.storage import Database
from src.exporter import JSONExporter, StaticSiteBuilder
from config import settings

app = typer.Typer(help="채용 정보 자동 수집 에이전트")
console = Console()


# 크롤러 목록
CRAWLERS = [
    SaraminCrawler,
    JobKoreaCrawler,
    WantedCrawler,
    RocketPunchCrawler,
    LinkedInCrawler,
    JobTalioCrawler,
]


async def run_crawlers():
    """모든 크롤러 실행"""
    db = Database()
    total_jobs = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for CrawlerClass in CRAWLERS:
            crawler_name = CrawlerClass.__name__
            task = progress.add_task(f"[cyan]{crawler_name} 수집 중...", total=None)

            try:
                async with CrawlerClass() as crawler:
                    jobs = await crawler.crawl()
                    total_jobs.extend(jobs)

                    # 상세 정보 가져오기 (처음 10개만)
                    for job in jobs[:10]:
                        try:
                            await crawler.get_job_detail(job)
                        except Exception as e:
                            logger.error(f"상세 정보 오류: {e}")

                progress.update(task, description=f"[green]{crawler_name}: {len(jobs)}건 완료")

            except Exception as e:
                logger.error(f"{crawler_name} 오류: {e}")
                progress.update(task, description=f"[red]{crawler_name}: 오류 발생")

    # 저장
    if total_jobs:
        saved = db.save_jobs(total_jobs)
        console.print(f"\n[bold green]수집 완료![/] 총 {len(total_jobs)}건 수집, {saved}건 신규 저장")

    # 마감된 공고 처리
    db.mark_expired_jobs()

    return total_jobs


@app.command()
def crawl():
    """채용 공고 크롤링 실행 (DB 저장)"""
    console.print("[bold blue]채용 정보 수집을 시작합니다...[/]")
    asyncio.run(run_crawlers())


@app.command("crawl-to-json")
def crawl_to_json():
    """채용 공고 크롤링 후 JSON으로 저장 (GitHub Actions용)"""
    console.print("[bold blue]채용 정보 수집을 시작합니다 (JSON 모드)...[/]")

    async def run():
        total_jobs = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            for CrawlerClass in CRAWLERS:
                crawler_name = CrawlerClass.__name__
                task = progress.add_task(f"[cyan]{crawler_name} 수집 중...", total=None)

                try:
                    async with CrawlerClass() as crawler:
                        jobs = await crawler.crawl()
                        total_jobs.extend(jobs)

                        # 상세 정보 가져오기 (처음 5개만 - API 제한 고려)
                        for job in jobs[:5]:
                            try:
                                await crawler.get_job_detail(job)
                            except Exception as e:
                                logger.error(f"상세 정보 오류: {e}")

                    progress.update(task, description=f"[green]{crawler_name}: {len(jobs)}건 완료")

                except Exception as e:
                    logger.error(f"{crawler_name} 오류: {e}")
                    progress.update(task, description=f"[red]{crawler_name}: 오류 발생")

        # JSON으로 저장
        if total_jobs:
            exporter = JSONExporter()
            exporter.export_jobs(total_jobs)
            console.print(f"\n[bold green]수집 완료![/] 총 {len(total_jobs)}건")

        return total_jobs

    asyncio.run(run())


@app.command("build-static")
def build_static():
    """정적 사이트 생성 (GitHub Pages용)"""
    console.print("[bold blue]정적 사이트를 생성합니다...[/]")
    builder = StaticSiteBuilder()
    builder.build()
    console.print("[bold green]완료![/] docs/ 폴더에 생성됨")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="서버 호스트"),
    port: int = typer.Option(8000, help="서버 포트"),
    reload: bool = typer.Option(False, help="자동 리로드"),
):
    """웹 대시보드 서버 실행"""
    console.print(f"[bold blue]웹 대시보드를 시작합니다...[/]")
    console.print(f"[green]http://localhost:{port}[/]")

    uvicorn.run(
        "src.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def schedule(
    interval: int = typer.Option(60, help="크롤링 간격 (분)"),
):
    """스케줄러와 함께 웹 서버 실행"""
    console.print(f"[bold blue]스케줄러 모드로 시작합니다...[/]")
    console.print(f"크롤링 간격: {interval}분")

    async def main():
        # 스케줄러 설정
        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_crawlers, "interval", minutes=interval)

        # 즉시 한 번 실행
        await run_crawlers()

        # 스케줄러 시작
        scheduler.start()

        # 웹 서버 실행
        config = uvicorn.Config(
            "src.web.app:app",
            host="0.0.0.0",
            port=8000,
            loop="asyncio",
        )
        server = uvicorn.Server(config)
        await server.serve()

    asyncio.run(main())


@app.command()
def stats():
    """수집된 데이터 통계 출력"""
    db = Database()
    stats = db.get_statistics()

    console.print("\n[bold]채용 공고 통계[/]")
    console.print("-" * 40)

    table = Table(show_header=True, header_style="bold")
    table.add_column("항목", style="cyan")
    table.add_column("수량", justify="right", style="green")

    table.add_row("전체 공고", str(stats["total"]))
    table.add_row("새 공고", str(stats["new"]))
    table.add_row("7일 내 마감", str(stats["expiring_7days"]))

    console.print(table)

    console.print("\n[bold]사이트별 통계[/]")
    source_table = Table(show_header=True, header_style="bold")
    source_table.add_column("사이트", style="cyan")
    source_table.add_column("수량", justify="right", style="green")

    for source, count in stats["by_source"].items():
        source_table.add_row(source.upper(), str(count))

    console.print(source_table)


@app.command()
def list_jobs(
    limit: int = typer.Option(20, help="출력할 공고 수"),
    source: Optional[str] = typer.Option(None, help="필터할 소스"),
):
    """수집된 채용 공고 목록 출력"""
    db = Database()

    if source:
        jobs = db.get_jobs_by_source(source)
    else:
        jobs = db.get_all_jobs()

    jobs = jobs[:limit]

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("회사", style="cyan", width=20)
    table.add_column("포지션", width=35)
    table.add_column("경력", width=10)
    table.add_column("마감", width=12)
    table.add_column("소스", width=10)

    for job in jobs:
        new_marker = "[green]★[/]" if job.is_new else ""
        table.add_row(
            f"{new_marker} {job.company_name[:18]}",
            job.title[:33],
            job.experience_text or "-",
            job.deadline_text or "상시",
            job.source.upper(),
        )

    console.print(table)
    console.print(f"\n총 {len(jobs)}건 표시")


if __name__ == "__main__":
    app()
