#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

cmd="${1:-status}"
subcmd="${2:-}"

case "$cmd" in
  start)
    case "$subcmd" in
      uat|display)
        echo "Starting UAT / Display environment..."
        docker compose --profile uat up -d backend-uat frontend-uat
        echo "UAT running at: http://localhost:12347 (API: http://localhost:12346)"
        ;;
      dev)
        echo "Starting Dev environment..."
        docker compose up -d backend frontend db
        echo "Dev running at: http://localhost:12345 (API: http://localhost:12344)"
        ;;
      all)
        echo "Starting all environments..."
        docker compose --profile uat up -d
        ;;
      *)
        echo "Usage: ./manage.sh start [uat|dev|all]"
        exit 1
        ;;
    esac
    ;;
  stop)
    case "$subcmd" in
      uat|display)
        echo "Stopping UAT / Display environment..."
        docker compose stop backend-uat frontend-uat
        ;;
      dev)
        echo "Stopping Dev environment..."
        docker compose stop backend frontend
        ;;
      all)
        echo "Stopping all environments..."
        docker compose --profile uat stop
        ;;
      *)
        echo "Usage: ./manage.sh stop [uat|dev|all]"
        exit 1
        ;;
    esac
    ;;
  seed-uat|seed-display)
    echo "Resetting and seeding UAT showcase dataset..."
    python3 tests/seed_comprehensive.py --base-url http://127.0.0.1:12346 --clean
    echo "UAT dataset refreshed. Ready to showcase at: http://localhost:12347"
    ;;
  status)
    echo "================ Budget App Environments ================"
    docker compose ps
    echo ""
    echo "Endpoints:"
    echo "  - Dev Web:     http://localhost:12345  (API: http://localhost:12344/docs)"
    echo "  - UAT Web:     http://localhost:12347  (API: http://localhost:12346/docs)"
    echo "=========================================================="
    ;;
  *)
    echo "Usage: ./manage.sh [start dev|start uat|stop dev|stop uat|seed-uat|status]"
    exit 1
    ;;
esac
