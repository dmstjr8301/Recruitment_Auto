#!/bin/bash
# 채용 정보 자동 수집 에이전트 실행 스크립트 (Linux/Mac)

case "$1" in
  install)
    echo "의존성을 설치합니다..."
    python -m pip install -r requirements.txt
    ;;
  crawl)
    echo "채용 공고를 수집합니다..."
    python -m src.main crawl
    ;;
  serve)
    echo "웹 대시보드를 시작합니다..."
    echo "http://localhost:8000 에서 확인하세요."
    python -m src.main serve
    ;;
  schedule)
    echo "스케줄러 모드로 시작합니다..."
    python -m src.main schedule
    ;;
  stats)
    python -m src.main stats
    ;;
  list)
    python -m src.main list-jobs
    ;;
  *)
    echo ""
    echo "채용 정보 자동 수집 에이전트"
    echo "============================="
    echo ""
    echo "사용법: ./run.sh [명령]"
    echo ""
    echo "명령:"
    echo "  install   - 의존성 설치"
    echo "  crawl     - 채용 공고 수집 실행"
    echo "  serve     - 웹 대시보드 실행"
    echo "  schedule  - 스케줄러 + 웹 서버 실행"
    echo "  stats     - 수집 통계 확인"
    echo "  list      - 채용 공고 목록 출력"
    echo ""
    ;;
esac
