@echo off
REM 채용 정보 자동 수집 에이전트 실행 스크립트 (Windows)

if "%1"=="" goto help
if "%1"=="install" goto install
if "%1"=="crawl" goto crawl
if "%1"=="serve" goto serve
if "%1"=="schedule" goto schedule
if "%1"=="stats" goto stats
if "%1"=="list" goto list

:help
echo.
echo 채용 정보 자동 수집 에이전트
echo =============================
echo.
echo 사용법: run.bat [명령]
echo.
echo 명령:
echo   install   - 의존성 설치
echo   crawl     - 채용 공고 수집 실행
echo   serve     - 웹 대시보드 실행
echo   schedule  - 스케줄러 + 웹 서버 실행
echo   stats     - 수집 통계 확인
echo   list      - 채용 공고 목록 출력
echo.
goto end

:install
echo 의존성을 설치합니다...
python -m pip install -r requirements.txt
goto end

:crawl
echo 채용 공고를 수집합니다...
python -m src.main crawl
goto end

:serve
echo 웹 대시보드를 시작합니다...
echo http://localhost:8000 에서 확인하세요.
python -m src.main serve
goto end

:schedule
echo 스케줄러 모드로 시작합니다...
python -m src.main schedule
goto end

:stats
python -m src.main stats
goto end

:list
python -m src.main list-jobs
goto end

:end
