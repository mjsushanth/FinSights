#!/bin/bash
# =============================================================================
# FinSights - single-window launcher
#
# Double-click this file to run the whole application.
#
# Everything runs in THIS one terminal window. Nothing is spawned into a second
# Terminal tab (the retired start_finrag.command used osascript to open two, which
# was hard to follow and hard to shut down cleanly).
#
# There is deliberately no virtualenv or conda step. The Docker images carry the
# entire Python environment - interpreter, boto3, polars, streamlit, everything -
# so "is the environment set up?" reduces to "are the images built?", which this
# script checks and can rebuild on demand. Creating a local venv as well would
# just be a second, driftable copy of the same dependency set.
#
# Replaces: setup_finrag.command / start_finrag.command / *.ps1 / *.bat and
# serving/sh files - outdated/ (all retired 2026-07-30 - they pointed at venvs
# that no longer exist and one ran a global `pkill -9 python`).
# =============================================================================

set -uo pipefail

# Resolve the real script directory. Required: double-clicking a .command runs it
# with the working directory set to $HOME, not the file's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$SCRIPT_DIR/finrag_docker_loc_tg1"
CREDS_FILE="$SCRIPT_DIR/finrag_ml_tg1/.aws_secrets/aws_credentials.env"

BACKEND_PORT=8000
FRONTEND_PORT=8501
BACKEND_IMAGE="finrag_docker_loc_tg1-backend"
FRONTEND_IMAGE="finrag_docker_loc_tg1-frontend"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; NC=$'\033[0m'

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s  OK  %s %s\n' "$GREEN" "$NC" "$*"; }
warn() { printf '%s WARN %s %s\n' "$YELLOW" "$NC" "$*"; }
bad()  { printf '%s FAIL %s %s\n' "$RED" "$NC" "$*"; }
step() { printf '\n%s>>> %s%s\n' "$CYAN" "$*" "$NC"; }

banner() {
    # Only clear when attached to a real terminal, so piping this script for a
    # scripted status check does not emit a TERM warning.
    [ -t 1 ] && clear
    printf '%s' "$CYAN"
    say '==============================================================='
    say '  FinSights - SEC 10-K Financial RAG'
    say '  Local Docker launcher'
    printf '%s' "$NC"
    say '==============================================================='
}

# --- pre-flight ------------------------------------------------------------

port_busy() { lsof -Pi ":$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

docker_cli_present() { command -v docker >/dev/null 2>&1; }

docker_running() { docker info >/dev/null 2>&1; }

start_docker_desktop() {
    if [ ! -d /Applications/Docker.app ]; then
        bad "Docker Desktop is not installed at /Applications/Docker.app"
        say "    Install it from https://www.docker.com/products/docker-desktop/"
        return 1
    fi
    say "    Starting Docker Desktop; this usually takes 20-40 seconds..."
    open -a Docker
    local waited=0
    while [ "$waited" -lt 120 ]; do
        if docker_running; then
            ok "Docker daemon is ready (${waited}s)"
            return 0
        fi
        sleep 3
        waited=$((waited + 3))
        printf '    %s...%ss%s\r' "$DIM" "$waited" "$NC"
    done
    say ""
    bad "Docker daemon did not come up within 120s"
    say "    Open Docker Desktop manually, wait for the whale icon to settle, then retry."
    return 1
}

image_exists() { docker image inspect "$1:latest" >/dev/null 2>&1; }

# Prints a status block. Returns 0 if everything needed to start is in place.
show_status() {
    step "Environment status"
    local ready=0

    if docker_cli_present; then
        ok "docker CLI      $(docker --version 2>/dev/null | sed 's/Docker version //')"
    else
        bad "docker CLI      not found on PATH"
        ready=1
    fi

    if docker_running; then
        ok "docker daemon   running"
    else
        warn "docker daemon   not running (this script can start it)"
        ready=1
    fi

    if [ -f "$CREDS_FILE" ]; then
        # Existence only. Contents are never read or printed by this script.
        ok "AWS credentials present at finrag_ml_tg1/.aws_secrets/"
    else
        bad "AWS credentials MISSING: $CREDS_FILE"
        say "    The backend cannot reach Bedrock or S3 Vectors without it."
        ready=1
    fi

    if [ -f "$COMPOSE_DIR/docker-compose.yml" ]; then
        ok "compose file    finrag_docker_loc_tg1/docker-compose.yml"
    else
        bad "compose file    MISSING at $COMPOSE_DIR/docker-compose.yml"
        ready=1
    fi

    if docker_running; then
        # Size is deliberately read from `docker images`, not `docker image inspect`
        # - under the containerd image store the two disagree substantially.
        for pair in "backend image:$BACKEND_IMAGE" "frontend image:$FRONTEND_IMAGE"; do
            local label="${pair%%:*}" img="${pair##*:}"
            if image_exists "$img"; then
                ok "$label   built ($(docker images "$img:latest" \
                    --format '{{.Size}}' 2>/dev/null | head -1))"
            else
                warn "$label   not built yet (will build on start)"
            fi
        done
    fi

    # Our own containers holding a port is expected; anything else would collide.
    # Matched on container name rather than `compose ps`, which needs the project
    # context to resolve and misreported the owner when run from another directory.
    local running=""
    if docker_running; then
        running="$(docker ps --format '{{.Names}}' 2>/dev/null)"
    fi

    for pair in "$BACKEND_PORT:finrag-backend" "$FRONTEND_PORT:finrag-frontend"; do
        local p="${pair%%:*}" cname="${pair##*:}"
        if port_busy "$p"; then
            if printf '%s\n' "$running" | grep -qx "$cname"; then
                ok "port $p       serving $cname"
            else
                warn "port $p       in use by another process (may conflict)"
            fi
        else
            ok "port $p       free"
        fi
    done

    return $ready
}

# --- actions ---------------------------------------------------------------

ensure_docker() {
    docker_cli_present || { bad "docker CLI not found; cannot continue."; return 1; }
    docker_running && return 0
    step "Docker is not running"
    start_docker_desktop
}

wait_for_health() {
    local label="$1" url="$2" limit="${3:-150}" waited=0
    printf '    waiting for %s' "$label"
    while [ "$waited" -lt "$limit" ]; do
        if curl -fs --max-time 4 "$url" >/dev/null 2>&1; then
            printf '\n'; ok "$label is responding"
            return 0
        fi
        sleep 3
        waited=$((waited + 3))
        printf '.'
    done
    printf '\n'
    warn "$label did not respond within ${limit}s"
    return 1
}

start_stack() {
    local rebuild="${1:-no}"
    ensure_docker || return 1
    [ -f "$CREDS_FILE" ] || { bad "AWS credentials missing; aborting."; return 1; }

    cd "$COMPOSE_DIR" || { bad "Cannot enter $COMPOSE_DIR"; return 1; }

    if [ "$rebuild" = "full" ]; then
        step "Rebuilding images from scratch (no cache) - this takes several minutes"
        docker compose build --no-cache || { bad "Build failed."; return 1; }
    elif [ "$rebuild" = "yes" ]; then
        step "Rebuilding images (using cache where valid)"
        docker compose build || { bad "Build failed."; return 1; }
    fi

    step "Starting the FinSights stack"
    # --build covers the first run, when no image exists yet.
    docker compose up -d --build || { bad "Failed to start containers."; return 1; }

    step "Health checks"
    wait_for_health "backend  (:$BACKEND_PORT)"  "http://localhost:$BACKEND_PORT/health"
    wait_for_health "frontend (:$FRONTEND_PORT)" "http://localhost:$FRONTEND_PORT/_stcore/health"

    say ""
    docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null

    step "Ready"
    say "  Frontend  ${BOLD}http://localhost:$FRONTEND_PORT${NC}"
    say "  Backend   http://localhost:$BACKEND_PORT/health"
    say "  API docs  http://localhost:$BACKEND_PORT/docs"
    say ""
    say "  ${DIM}A query costs roughly \$0.02-0.03 and takes 25-50 seconds.${NC}"
    open "http://localhost:$FRONTEND_PORT" 2>/dev/null || true
}

stop_stack() {
    ensure_docker || return 1
    cd "$COMPOSE_DIR" || return 1
    step "Stopping the FinSights stack"
    # Stop our containers before anyone quits Docker Desktop. Quitting Desktop
    # with containers still running has hung the shutdown path on this machine.
    docker compose down || { warn "compose down reported an error; retrying with timeout"; \
        docker compose down -t 30; }
    ok "Containers stopped. Docker Desktop is left running on purpose."
    say "    ${DIM}To quit Docker Desktop, do it from its menu now that the stack is down.${NC}"
}

tail_logs() {
    ensure_docker || return 1
    cd "$COMPOSE_DIR" || return 1
    step "Streaming logs - press Ctrl+C to return to the menu"
    # Ctrl+C must not kill this script, only the log stream.
    trap ' ' INT
    docker compose logs -f --tail 60
    trap - INT
    say ""
}

# --- menu ------------------------------------------------------------------

main_menu() {
    while true; do
        banner
        show_status
        say ""
        say "${BOLD}What would you like to do?${NC}"
        say "  1) Start the application        (builds images if missing)"
        say "  2) Restart with a rebuild       (reuses cache where valid)"
        say "  3) Full clean rebuild           (--no-cache, several minutes)"
        say "  4) Stop the application"
        say "  5) View logs"
        say "  6) Refresh this status"
        say "  q) Quit"
        say ""
        printf 'Choice [1]: '
        read -r choice
        choice="${choice:-1}"

        case "$choice" in
            1) start_stack no ;;
            2) start_stack yes ;;
            3) start_stack full ;;
            4) stop_stack ;;
            5) tail_logs ; continue ;;
            6) continue ;;
            q|Q) say ""; say "Leaving the stack as it is. Bye."; exit 0 ;;
            *) warn "Unrecognised choice: $choice" ;;
        esac

        say ""
        printf '%sPress Return to go back to the menu...%s' "$DIM" "$NC"
        read -r _
    done
}

main_menu
