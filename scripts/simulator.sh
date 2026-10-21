#!/bin/bash
# Helper script to manage the real-time status simulator

set -e

case "${1:-}" in
  start)
    echo "Starting real-time status simulator..."
    docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py
    echo "✓ Simulator started in background"
    echo "  View logs: docker logs -f ev-backend"
    echo "  Stop: ./scripts/simulator.sh stop"
    ;;

  stop)
    echo "Stopping real-time status simulator..."
    docker exec ev-backend pkill -f simulate_realtime_status.py || true
    echo "✓ Simulator stopped"
    ;;

  status)
    if docker exec ev-backend pgrep -f simulate_realtime_status.py > /dev/null; then
      echo "✓ Simulator is running"
      docker exec ev-backend pgrep -af simulate_realtime_status.py
    else
      echo "✗ Simulator is not running"
    fi
    ;;

  logs)
    echo "Following simulator logs (Ctrl+C to stop)..."
    docker logs -f ev-backend 2>&1 | grep --line-buffered -E "Total:|Charger|Session|Simulator"
    ;;

  restart)
    echo "Restarting simulator..."
    $0 stop
    sleep 2
    $0 start
    ;;

  *)
    echo "Usage: $0 {start|stop|status|logs|restart}"
    echo ""
    echo "Commands:"
    echo "  start   - Start the simulator in background"
    echo "  stop    - Stop the simulator"
    echo "  status  - Check if simulator is running"
    echo "  logs    - Follow simulator output"
    echo "  restart - Restart the simulator"
    exit 1
    ;;
esac
