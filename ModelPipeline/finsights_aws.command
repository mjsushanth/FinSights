#!/bin/bash
# =============================================================================
# FinSights - AWS ECS Fargate deploy launcher
#
# Double-click this file to deploy, inspect, or tear down the cloud deployment.
#
# Sibling of finsights.command, which runs the same two images locally. The
# split is deliberate: local needs only Docker, whereas this needs Docker AND
# AWS credentials AND a Python interpreter with boto3, so folding both into one
# script would make the local path fail for reasons that have nothing to do
# with running locally.
#
# All real logic lives in the deploy_aws Python package. This file only finds an
# interpreter and presents the verbs, so that anything it can do is equally
# available as `python -m deploy_aws.cli <verb>` for scripting and CI.
# =============================================================================

set -uo pipefail

# Double-clicking a .command sets the working directory to $HOME, not here.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV="finsights_revival"
AWS_PROFILE_NAME="${AWS_PROFILE:-mjsushanth_mlops}"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; NC=$'\033[0m'

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s  OK  %s %s\n' "$GREEN" "$NC" "$*"; }
warn() { printf '%s WARN %s %s\n' "$YELLOW" "$NC" "$*"; }
bad()  { printf '%s FAIL %s %s\n' "$RED" "$NC" "$*"; }
step() { printf '\n%s>>> %s%s\n' "$CYAN" "$*" "$NC"; }

banner() {
    [ -t 1 ] && clear
    printf '%s' "$CYAN"
    say '==============================================================='
    say '  FinSights - SEC 10-K Financial RAG'
    say '  AWS ECS Fargate deployment'
    printf '%s' "$NC"
    say '==============================================================='
}

# --- interpreter discovery -------------------------------------------------

# boto3 is the only hard requirement. Checked by importing it rather than by
# looking for a directory, because an env can exist without the package.
find_python() {
    local candidates=(
        "/opt/homebrew/Caskroom/miniconda/base/envs/$CONDA_ENV/bin/python"
        "$HOME/miniconda3/envs/$CONDA_ENV/bin/python"
        "$(command -v python3 || true)"
    )
    for candidate in "${candidates[@]}"; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        if "$candidate" -c 'import boto3' >/dev/null 2>&1; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

# --- status ----------------------------------------------------------------

show_status() {
    step "Environment"

    if ! PY="$(find_python)"; then
        bad "no Python with boto3 found (looked for conda env '$CONDA_ENV')"
        say "${DIM}    Install into that env:  conda run -n $CONDA_ENV uv pip install boto3${NC}"
        return 1
    fi
    ok "python: $PY"

    if docker info >/dev/null 2>&1; then
        ok "docker daemon running"
    else
        warn "docker daemon not running - needed only for 'up' with a build"
    fi

    if [ -f "$HOME/.aws/credentials" ] && grep -q "\[$AWS_PROFILE_NAME\]" "$HOME/.aws/credentials" 2>/dev/null; then
        ok "aws profile: $AWS_PROFILE_NAME"
    else
        bad "aws profile '$AWS_PROFILE_NAME' not found in ~/.aws/credentials"
        return 1
    fi
    return 0
}

# --- verb dispatch ---------------------------------------------------------

# Every verb is the same one-line delegation. AWS_PROFILE is exported rather
# than passed as a flag so the Python side keeps a single credential source.
run_cli() {
    export AWS_PROFILE="$AWS_PROFILE_NAME"
    ( cd "$SCRIPT_DIR" && "$PY" -m deploy_aws.cli "$@" )
    local rc=$?
    if [ $rc -ne 0 ]; then
        bad "command failed (exit $rc)"
    fi
    return $rc
}

pause() {
    say ""
    read -r -p "Press Return to continue... " _ || true
}

menu() {
    say ""
    printf '%s' "$BOLD"
    say '  1  Preflight     - check everything, change nothing'
    say '  2  Up            - build, push, deploy, wait for healthy'
    say '  3  Up (no build) - redeploy the images already in ECR'
    say '  4  Status        - what is running, where, what it costs'
    say '  5  Smoke test    - verify reachability from the internet'
    say '  6  Logs          - recent backend output'
    say '  7  Logs          - recent frontend output'
    say '  8  Down          - scale to zero tasks (stops compute spend)'
    say '  9  Destroy       - remove every resource, including images'
    say '  r  Render task definition JSON'
    say '  s  Refresh status'
    say '  q  Quit'
    printf '%s' "$NC"
    say ""
}

main() {
    banner
    if ! show_status; then
        say ""
        bad "environment is not ready - fix the items above and re-run"
        pause
        exit 1
    fi

    while true; do
        menu
        read -r -p "Choose: " choice || exit 0
        case "$choice" in
            1) step "Preflight";           run_cli preflight ;;
            2) step "Up (with build)";     run_cli up ;;
            3) step "Up (no build)";       run_cli up --no-build ;;
            4) step "Status";              run_cli status ;;
            5) step "Smoke test";          run_cli smoke ;;
            6) step "Backend logs";        run_cli logs --container backend ;;
            7) step "Frontend logs";       run_cli logs --container frontend ;;
            8) step "Down";                run_cli down ;;
            9)
                step "Destroy"
                warn "This deletes the service, cluster, roles, security group,"
                warn "log group and BOTH ECR repositories."
                say "${DIM}Nothing outside the deployment is touched: the S3 data bucket,${NC}"
                say "${DIM}the S3 Vectors index and Bedrock are not affected.${NC}"
                say ""
                read -r -p "Type DESTROY to confirm: " confirm || confirm=""
                if [ "$confirm" = "DESTROY" ]; then
                    run_cli destroy --yes
                else
                    warn "cancelled - nothing was deleted"
                fi
                ;;
            r) step "Render task definition"; run_cli render-taskdef ;;
            s) banner; show_status; continue ;;
            q|Q) say ""; say "Leaving the deployment as it is."; exit 0 ;;
            *) warn "unrecognised choice: $choice"; continue ;;
        esac
        pause
        banner
        show_status
    done
}

main "$@"
