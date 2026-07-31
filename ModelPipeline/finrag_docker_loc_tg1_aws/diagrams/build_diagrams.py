"""Generate the FinSights deployment teaching diagrams as SVG.

A tiny declarative SVG builder plus four diagram definitions. Exists as a
script rather than hand-written SVG so that box geometry, text wrapping, and
the colour language stay consistent across all four, and so a later edit is a
data change rather than coordinate surgery.

Usage:  python build.py <outdir>
"""
import sys
from pathlib import Path
from typing import List, Tuple

# --- design language -------------------------------------------------------
BG = "#fcfcfa"
INK = "#1e293b"
DIM = "#64748b"
FAINT = "#94a3b8"
BLUE = "#2563eb"      # our code / control plane
TEAL = "#0d9488"      # AWS managed services
VIOLET = "#7c3aed"    # data plane
AMBER = "#b45309"     # decision / trade-off
ROSE = "#be123c"      # failure / danger
GREEN = "#15803d"     # verified / good
SLATE = "#475569"

SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# average glyph width as a fraction of font-size, for wrapping
W_SANS, W_MONO = 0.512, 0.60


def esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def wrap(text: str, size: float, width: float, mono: bool = False) -> List[str]:
    per = size * (W_MONO if mono else W_SANS)
    limit = max(8, int(width / per))
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) <= limit:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class Svg:
    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.parts: List[str] = []

    def raw(self, s: str) -> None:
        self.parts.append(s)

    def rect(self, x, y, w, h, fill="#fff", stroke=None, sw=2, r=12, dash=None, op=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.raw(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
                 f'fill="{fill}" fill-opacity="{op}"{s}{d}/>')

    def text(self, x, y, t, size=14, fill=INK, weight="400", mono=False,
             anchor="start", op=1.0):
        fam = MONO if mono else SANS
        self.raw(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" '
                 f'font-weight="{weight}" fill="{fill}" fill-opacity="{op}" '
                 f'text-anchor="{anchor}">{esc(t)}</text>')

    def flow(self, x, y, lines: List[Tuple[str, str]], width: float, lh=17.5) -> float:
        """Render (style, text) pairs, wrapping to width. Returns final y."""
        for style, txt in lines:
            if style == "gap":
                y += 7
                continue
            if style == "lead":
                for ln in wrap(txt, 13.5, width):
                    self.text(x, y, ln, 13.5, SLATE, "600")
                    y += lh
                y += 3
            elif style == "bullet":
                for i, ln in enumerate(wrap(txt, 12.8, width - 12)):
                    if i == 0:
                        self.text(x + 1, y, "•", 12.8, FAINT)
                    self.text(x + 12, y, ln, 12.8, INK)
                    y += 16.5
            elif style == "code":
                for ln in wrap(txt, 11.8, width, mono=True):
                    self.text(x, y, ln, 11.8, BLUE, "500", mono=True)
                    y += 15.5
            elif style == "note":
                for i, ln in enumerate(wrap(txt, 12.3, width - 14)):
                    if i == 0:
                        self.text(x + 1, y, "▸", 12.3, AMBER, "700")
                    self.text(x + 14, y, ln, 12.3, AMBER)
                    y += 16
            elif style == "bad":
                for i, ln in enumerate(wrap(txt, 12.3, width - 14)):
                    if i == 0:
                        self.text(x + 1, y, "✕", 12.3, ROSE, "700")
                    self.text(x + 14, y, ln, 12.3, ROSE)
                    y += 16
            elif style == "good":
                for i, ln in enumerate(wrap(txt, 12.3, width - 14)):
                    if i == 0:
                        self.text(x + 1, y, "✓", 12.3, GREEN, "700")
                    self.text(x + 14, y, ln, 12.3, GREEN)
                    y += 16
        return y

    def card(self, x, y, w, h, num, title, accent, lines, subtitle=None):
        self.rect(x, y, w, h, "#ffffff", accent, 2, 13)
        self.rect(x, y, w, 34, accent, None, 0, 13)
        self.rect(x, y + 20, w, 14, accent, None, 0, 0)
        if num:
            self.rect(x + 10, y + 8, 22, 18, "#ffffff", None, 0, 5, op=0.28)
            self.text(x + 21, y + 22, num, 12.5, "#ffffff", "700", anchor="middle")
            tx = x + 40
        else:
            tx = x + 13
        self.text(tx, y + 22, title, 13.5, "#ffffff", "700")
        yy = y + 52
        if subtitle:
            for ln in wrap(subtitle, 12.2, w - 26):
                self.text(x + 13, yy, ln, 12.2, DIM, "500")
                yy += 15.5
            yy += 4
        self.flow(x + 13, yy, lines, w - 26)

    def arrow(self, x1, y1, x2, y2, color=FAINT, sw=2.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                 f'stroke-width="{sw}"{d} marker-end="url(#ah)"/>')

    def label(self, x, y, t, color=DIM, size=11.5, mono=False, anchor="middle"):
        self.text(x, y, t, size, color, "600", mono=mono, anchor=anchor)

    def banner(self, x, y, w, title, body, accent):
        h = 30 + 17 * len(wrap(body, 13, w - 30))
        self.rect(x, y, w, h, "#ffffff", accent, 2, 12)
        self.rect(x, y, 6, h, accent, None, 0, 3)
        self.text(x + 18, y + 22, title, 13.5, accent, "700")
        yy = y + 41
        for ln in wrap(body, 13, w - 34):
            self.text(x + 18, yy, ln, 13, INK)
            yy += 17
        return h

    def render(self, title, subtitle) -> str:
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
                f'height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
                f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" '
                f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M0,0 L10,5 L0,10 z" fill="{FAINT}"/></marker></defs>'
                f'<rect width="{self.w}" height="{self.h}" fill="{BG}"/>')
        t = (f'<text x="40" y="46" font-family="{SANS}" font-size="25" '
             f'font-weight="700" fill="{INK}">{esc(title)}</text>'
             f'<text x="40" y="70" font-family="{SANS}" font-size="13.5" '
             f'fill="{DIM}">{esc(subtitle)}</text>'
             f'<line x1="40" y1="84" x2="{self.w-40}" y2="84" stroke="#e2e8f0" '
             f'stroke-width="1.5"/>')
        foot = (f'<text x="40" y="{self.h-16}" font-family="{SANS}" font-size="11" '
                f'fill="{FAINT}">FinSights on AWS ECS Fargate  |  verified '
                f'2026-07-31, account 908877262866  |  source: '
                f'ModelPipeline/deploy_aws/</text>')
        return head + t + "".join(self.parts) + foot + "</svg>"


def legend(s: Svg, y: int, items) -> None:
    """Right-aligned legend. Width is computed from a deliberately generous
    per-glyph estimate, because underestimating it makes swatches collide with
    the preceding label - which is exactly what happened on the first render.
    """
    widths = [26 + int(len(name) * 7.4) for _, name in items]
    x = s.w - 40 - sum(widths)
    for (color, name), adv in zip(items, widths):
        s.rect(x, y - 9, 11, 11, color, None, 0, 3)
        s.text(x + 17, y, name, 11.5, DIM, "600")
        x += adv


OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
OUT.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# D1 - the control plane, end to end
# ===========================================================================
def d1() -> None:
    s = Svg(1480, 1136)
    legend(s, 68, [(BLUE, "our code"), (TEAL, "AWS managed"), (AMBER, "trade-off"),
                   (ROSE, "what broke"), (GREEN, "verified")])
    CW, CH, GX, GY, X0, Y0 = 452, 258, 22, 22, 40, 104

    def pos(c, r):
        return X0 + c * (CW + GX), Y0 + r * (CH + GY)

    x, y = pos(0, 0)
    s.card(x, y, CW, CH, "1", "config.py  —  DeployConfig", BLUE,
           [("lead", "One frozen dataclass. Every name, size, port and model id."),
            ("bullet", "Immutable: two callers cannot disagree about a name."),
            ("bullet", "Validates the Fargate cpu/memory pair up front, because the API error names neither the bad value nor the valid ones."),
            ("bullet", "Holds NO account id. Never committed."),
            ("note", "Dec 2025 had two YAMLs that disagreed: one made finsights-cluster, the other deployed to finsights-cluster-new. Teardown deleted the wrong one.")],
           subtitle="The single source of truth")

    x, y = pos(1, 0)
    s.card(x, y, CW, CH, "2", "aws_session.py  —  AwsSession", BLUE,
           [("lead", "One boto3 Session; cached clients; identity on demand."),
            ("code", "self._clients[service] = session.client(...)"),
            ("bullet", "account_id comes from STS at run time, so every ARN is built for whoever is running the command."),
            ("bullet", "Two credential worlds must both work: a laptop profile, and CI env vars where no profile exists at all."),
            ("note", "Naming a profile unconditionally breaks CI: boto3 raises ProfileNotFound before it ever reads the environment.")],
           subtitle="Lazily built, shared everywhere")

    x, y = pos(2, 0)
    s.card(x, y, CW, CH, "3", "policies.py  —  IamPolicies", BLUE,
           [("lead", "Two documents: who may assume, and what they may do."),
            ("bullet", "5 statements. No wildcard action. No Delete, anywhere."),
            ("bullet", "A us.* model id is an inference profile, not a model. It needs the profile ARN AND the foundation-model ARN in every region it can route to."),
            ("bad", "Grant only us-east-1 and it works most of the time, then throws AccessDenied when Bedrock routes elsewhere."),
            ("good", "Region list read from GetInferenceProfile, not guessed.")],
           subtitle="Least privilege, written as data")

    x, y = pos(0, 1)
    s.card(x, y, CW, CH, "4", "provisioner.py  —  Provisioner", TEAL,
           [("lead", "Six resources, created in dependency order, idempotently."),
            ("bullet", "ECR x2, log group, 2 IAM roles, security group, cluster."),
            ("bullet", "THE RULE: guard only what is not idempotent."),
            ("code", "CreateRole      -> guarded (EntityAlreadyExists)"),
            ("code", "AttachRolePolicy-> unconditional, every run"),
            ("bad", "The old guard tested 1 thing but did 2. Role created, policy attach failed -> every later run printed 'exists' and never repaired it.")],
           subtitle="Converge, do not create")

    x, y = pos(1, 1)
    s.card(x, y, CW, CH, "5", "images.py  —  ImagePublisher", BLUE,
           [("lead", "Drives docker from Python: login, build, push."),
            ("code", "docker build --platform linux/arm64 -f ... ."),
            ("bullet", "ECR password is a 12-hour token from the API, passed on stdin so it never enters the process table."),
            ("bullet", "ONE set of Dockerfiles, shared with local dev. Everything that differs is injected, not built in."),
            ("note", "If the image differed between local and cloud, the thing you tested would not be the thing you deployed.")],
           subtitle="Subprocess as a typed method")

    x, y = pos(2, 1)
    s.card(x, y, CW, CH, "6", "taskdef.py  —  TaskDefinitionBuilder", BLUE,
           [("lead", "Builds the RegisterTaskDefinition payload from code."),
            ("bullet", "One task, two containers, one network namespace."),
            ("bullet", "Health checks RESTATED here: Fargate ignores the image's HEALTHCHECK entirely."),
            ("bullet", "dependsOn HEALTHY reproduces compose's depends_on."),
            ("bad", "THIS is the file whose absence killed Dec 2025. The definition lived only in a console, so the workflow could only describe-then-patch. Account closed -> nothing could recreate it.")],
           subtitle="The correction to the fatal bug")

    x, y = pos(0, 2)
    s.card(x, y, CW, CH, "7", "service.py  —  ServiceOperator", TEAL,
           [("lead", "Register, create-or-update, scale, inspect, remove."),
            ("bullet", "Polls for steady state instead of using the boto3 waiter, so the REASON for a failure gets logged."),
            ("bullet", "Reads the public IP from the task ENI on demand: with one task and no load balancer, the IP genuinely changes."),
            ("note", "Fargate bills per TASK, not per container. So a 2nd container is ~free and a 2nd task doubles the bill.")],
           subtitle="The lifecycle verbs")

    x, y = pos(1, 2)
    s.card(x, y, CW, CH, "8", "cli.py  —  DeploymentCli", BLUE,
           [("lead", "preflight / up / status / smoke / logs / down / destroy"),
            ("bullet", "preflight INVOKES both Bedrock models rather than listing them; a model can be listed and still not be usable."),
            ("bullet", "down = desired count 0. No stopped-container charge exists on Fargate, because there is no stopped container."),
            ("bullet", "destroy removes even the images, for true zero."),
            ("note", "All logic is runnable on a laptop. Every Dec 2025 bug would have been visible if it had been.")],
           subtitle="Thin: it only wires and dispatches")

    x, y = pos(2, 2)
    s.card(x, y, CW, CH, None, "VERIFIED, not asserted", GREEN,
           [("good", "Query answered on ECS: $0.0140, 12,670 tokens, 9,631 ms."),
            ("good", "Log said 'using IAM role' + 'S3_STREAMING mode'."),
            ("good", "POST /query 200 OK from 127.0.0.1 — the wiring proof."),
            ("good", "Polars object_store resolved the task role. This was the biggest open risk: it does its own credential lookup, separate from botocore."),
            ("good", "destroy -> empty on all 6 checks -> up rebuilt to steady state. That round trip is the real IaC test."),
            ("good", "down reached desired=0 running=0. ECR left: 0.643 GB.")],
           subtitle="Every claim above was observed")

    yb = Y0 + 3 * (CH + GY) + 4
    s.banner(40, yb, 1400,
             "The one idea that ties all nine boxes together",
             "Infrastructure that exists only in a cloud console is not infrastructure you own. Each module above turns a "
             "click into a value in a file, so the repository becomes the source of truth and AWS holds a copy — rather than "
             "AWS holding the truth and the repository holding a patch script. The test of whether you got it right is not "
             "that deploy works; it is that destroy-then-deploy works.",
             SLATE)
    (OUT / "D1-control-plane.svg").write_text(
        s.render("The deploy control plane, end to end",
                 "Nine modules, what each one owns, and the specific December 2025 bug each one exists to prevent"))


# ===========================================================================
# D2 - request path and the namespace boundary
# ===========================================================================
def d2() -> None:
    s = Svg(1480, 1060)
    legend(s, 68, [(BLUE, "our code"), (TEAL, "AWS managed"), (VIOLET, "data plane"),
                   (ROSE, "what broke"), (GREEN, "verified")])

    s.rect(40, 104, 1400, 62, "#ffffff", FAINT, 2, 12, dash="7 5")
    s.text(60, 132, "THE INTERNET", 15, INK, "700")
    s.text(60, 152, "Anyone. Unauthenticated. This is correct — the RAG UI is the product.", 12.5, DIM)
    s.label(1230, 132, "one way in, one port", DIM, 12)
    s.arrow(740, 166, 740, 196, TEAL, 2.6)
    s.label(880, 188, "tcp/8501 only", TEAL, 12.5, mono=True)

    s.rect(40, 196, 1400, 78, "#f0fdfa", TEAL, 2, 12)
    s.text(60, 224, "SECURITY GROUP   finsights-app-sg", 14.5, TEAL, "700")
    s.flow(60, 246, [("bullet", "inbound tcp/8501 from 0.0.0.0/0   —   inbound on 8000: NOTHING")], 800)
    s.text(880, 224, "Dec 2025 allowed 8000 from 0.0.0.0/0:", 12.3, ROSE, "600")
    s.text(880, 244, "the paid /query endpoint, open to the", 12.3, ROSE)
    s.text(880, 261, "internet, unauthenticated and unmetered.", 12.3, ROSE)

    s.arrow(740, 274, 740, 302, TEAL, 2.6)
    s.rect(40, 302, 1400, 60, "#ffffff", TEAL, 2, 12)
    s.text(60, 330, "VPC / PUBLIC SUBNET   —   route table 0.0.0.0/0 → internet gateway (free)", 14, TEAL, "700")
    s.text(60, 350, "Public vs private is a property of the ROUTE TABLE, not the subnet. Private subnets would need a NAT gateway: ~$32.85/mo per AZ.", 12.3, DIM)

    s.arrow(740, 362, 740, 392, VIOLET, 2.6)

    # the task
    s.rect(40, 392, 1400, 300, "#faf5ff", VIOLET, 3, 14)
    s.text(62, 424, "ECS TASK   —   1 vCPU / 3072 MiB / ARM64   —   networkMode awsvpc", 15.5, VIOLET, "700")
    s.text(62, 446, "awsvpc gives the task its own ENI and its own IP. It is also what makes “localhost” mean “this task” rather than “this host”.", 12.4, DIM)

    s.rect(62, 462, 1356, 210, "#ffffff", VIOLET, 2, 12, dash="8 5")
    s.text(80, 488, "ONE NETWORK NAMESPACE, SHARED BY BOTH CONTAINERS", 13.5, VIOLET, "700")
    s.text(80, 507, "A namespace is an enforced perception boundary. Both processes see the SAME loopback interface, so 127.0.0.1 reaches across.", 12.2, DIM)

    s.rect(90, 522, 560, 132, "#f8fafc", BLUE, 2, 10)
    s.text(108, 548, "frontend  —  Streamlit", 13.5, BLUE, "700")
    s.flow(108, 570, [("code", "listens 0.0.0.0:8501"),
                      ("code", "BACKEND_URL=http://localhost:8000"),
                      ("bullet", "146 MiB, flat. A pure HTTP client."),
                      ("bullet", "Session-affine: WebSocket + in-process state.")], 520)

    s.rect(830, 522, 560, 132, "#f8fafc", BLUE, 2, 10)
    s.text(848, 548, "backend  —  FastAPI + RAG", 13.5, BLUE, "700")
    s.flow(848, 570, [("code", "listens 0.0.0.0:8000"),
                      ("bullet", "213 MiB idle → 1,220 MiB peak on a query."),
                      ("bullet", "No ingress rule. No route from outside."),
                      ("bullet", "dependsOn: frontend waits for HEALTHY.")], 520)

    s.arrow(650, 588, 826, 588, GREEN, 3)
    s.label(738, 578, "localhost:8000", GREEN, 12.5, mono=True)
    s.label(738, 606, "$0 / month", GREEN, 12)

    # Caption on its own band, then three straight drops below it. The first
    # render ran the arrows diagonally through the caption text.
    s.text(40, 716, "Task role credentials arrive over the container credential endpoint at 169.254.170.2 - there are no keys in the image and none in the task definition.",
           11.8, DIM, "600")
    for cx in (265, 740, 1215):
        s.arrow(cx, 730, cx, 764, TEAL, 2.4)

    # data plane
    for i, (nm, body, col) in enumerate([
        ("Bedrock", "Haiku 4.5 via us.* inference profile, plus cohere.embed-v4. InvokeModel only.", TEAL),
        ("S3", "Read the corpus. Write ONLY under LOGS/FINRAG/*. No delete.", TEAL),
        ("S3 Vectors", "QueryVectors on one index. No PutVectors, no DeleteVectors.", TEAL),
    ]):
        x = 40 + i * 470
        s.rect(x, 770, 450, 96, "#f0fdfa", col, 2, 11)
        s.text(x + 18, 798, nm, 14, col, "700")
        s.flow(x + 18, 820, [("bullet", body)], 415)

    yb = 890
    h = s.banner(40, yb, 690, "Why this is cheaper AND more capable",
                 "Two services would let you scale them independently — but independent scaling only helps if something "
                 "distributes load across the replicas, and DNS cannot do that: resolvers cache per TTL and carry no load "
                 "information. So option B needs an ALB (~$16.43/mo) to deliver its own benefit. Co-location is free and "
                 "uniquely preserves compose's depends_on ordering.", AMBER)
    s.banner(750, yb, 690, "The line that proves the whole argument",
             "INFO: 127.0.0.1:34932 - \"POST /query HTTP/1.1\" 200 OK.  The request reached the backend from the loopback "
             "address. No load balancer, no service discovery, no DNS, no hosted zone. That source IP is not a detail — it "
             "is the entire cost argument, observed.", GREEN)
    del h
    (OUT / "D2-request-path.svg").write_text(
        s.render("Request path, and the namespace boundary",
                 "How a browser reaches an answer — and why the backend has no door to the internet"))


# ===========================================================================
# D3 - module and class map
# ===========================================================================
def d3() -> None:
    s = Svg(1480, 1268)
    legend(s, 68, [(BLUE, "pure / our code"), (TEAL, "calls AWS"), (AMBER, "design note")])

    s.rect(40, 104, 1400, 54, "#eff6ff", BLUE, 2, 12)
    s.text(60, 137, "DEPENDENCY DIRECTION  —  everything flows one way: config → session → the things that do work → the CLI that wires them", 13.5, BLUE, "700")

    # Lane tops are computed from one origin and one pitch, so the label band,
    # the cards and the connecting arrows cannot drift into each other. The
    # first render hardcoded them and the top label struck through the banner.
    CARD_H, PITCH, LANE0 = 172, 236, 194
    lanes = [
        (LANE0 + 0 * PITCH, "DATA — no behaviour, no I/O", [
            ("config.py", "DeployConfig", "frozen dataclass", BLUE,
             ["from_env()", "image_uri(acct, repo)", "backend_url", "tag_list()"],
             "Constructed once, passed down. Nothing mutates it, so no module can surprise another."),
            ("policies.py", "IamPolicies", "pure functions over config", BLUE,
             ["ecs_tasks_trust_policy()", "task_role_policy(acct)", "_bedrock_resources(acct)"],
             "Takes config + account id, returns dicts. No AWS calls at all — so it is trivially testable."),
        ]),
        (LANE0 + 1 * PITCH, "ACCESS — owns the one connection", [
            ("aws_session.py", "AwsSession", "cached client factory", BLUE,
             ["session (lazy @property)", "client(name) -> cached", "account_id (STS, once)"],
             "THE pattern you noticed: a session captured as an object, handed to every collaborator by constructor."),
            ("taskdef.py", "TaskDefinitionBuilder", "assembles a payload", BLUE,
             ["build(acct, exec, task)", "_backend_container()", "_http_probe(url)"],
             "Pure assembly. Given ids, returns the dict AWS wants. No calls, no state."),
        ]),
        (LANE0 + 2 * PITCH, "WORK — talks to AWS and to docker", [
            ("provisioner.py", "Provisioner", "converges resources", TEAL,
             ["ensure_all()", "ensure_task_role()", "discover_network()", "delete_all()"],
             "Every ensure_* is safe to run twice. Every delete_* tolerates absence, so a half-built stack still tears down."),
            ("images.py", "ImagePublisher", "wraps subprocess", BLUE,
             ["docker_login()", "build_and_push()", "platform @property", "_run(cmd, step)"],
             "The other pattern you noticed: shell commands as typed methods, with the failure tail lifted into an exception."),
        ]),
        (LANE0 + 3 * PITCH, "ORCHESTRATE — the only place ordering lives", [
            ("service.py", "ServiceOperator", "the lifecycle", TEAL,
             ["deploy(resources)", "scale(n)", "wait_for_steady_state()", "status()", "public_ip()"],
             "Create-or-update in one verb: describe first, branch second. Idempotent from the caller's view."),
            ("cli.py", "DeploymentCli", "wires + dispatches", BLUE,
             ["preflight()", "up() down() destroy()", "smoke()", "build_parser()"],
             "Thin on purpose. It owns argument parsing and ordering — no AWS logic lives here."),
        ]),
    ]

    for ytop, lane_name, mods in lanes:
        s.text(40, ytop - 12, lane_name, 12, FAINT, "700")
        for i, (fname, cls, kind, col, methods, why) in enumerate(mods):
            x = 40 + i * 712
            w = 690
            s.rect(x, ytop, w, CARD_H, "#ffffff", col, 2, 12)
            s.rect(x, ytop, w, 30, col, None, 0, 12)
            s.rect(x, ytop + 18, w, 12, col, None, 0, 0)
            s.text(x + 13, ytop + 20, f"{fname}", 12.5, "#ffffff", "700", mono=True)
            s.text(x + w - 13, ytop + 20, kind, 11.5, "#ffffff", "600", anchor="end")
            s.text(x + 13, ytop + 52, f"class {cls}", 14.5, col, "700", mono=True)
            yy = ytop + 74
            for m in methods:
                s.text(x + 22, yy, f". {m}", 11.8, SLATE, "500", mono=True)
                yy += 15.5
            s.flow(x + 13, yy + 8, [("note", why)], w - 30)

    for lane_index in range(len(lanes) - 1):
        y_from = LANE0 + lane_index * PITCH + CARD_H + 6
        y_to = LANE0 + (lane_index + 1) * PITCH - 26
        for cx in (385, 1097):
            s.arrow(cx, y_from, cx, y_to, FAINT)

    yb = LANE0 + (len(lanes) - 1) * PITCH + CARD_H + 34
    s.banner(40, yb, 690, "Dependency injection, in one sentence",
             "Nothing constructs its own collaborators. Provisioner is handed an AwsSession; AwsSession is handed a "
             "DeployConfig. So a test can pass a fake, and no module can reach out and surprise you.", AMBER)
    s.banner(750, yb, 690, "Why the split is 8 files and not 1",
             "Each file has exactly one reason to change: a name changes -> config; a permission changes -> policies; the "
             "container shape changes -> taskdef. That is what 'single responsibility' buys you — predictable blast radius.", AMBER)
    (OUT / "D3-module-map.svg").write_text(
        s.render("Module and class map",
                 "Eight modules, their public class, their key methods — and the direction dependencies are allowed to point"))


# ===========================================================================
# D4 - what happens on `up`
# ===========================================================================
def d4() -> None:
    s = Svg(1480, 1310)
    legend(s, 68, [(BLUE, "runs locally"), (TEAL, "AWS API call"),
                   (VIOLET, "result"), (ROSE, "what broke")])

    for x, w, nm, col in [(40, 400, "YOUR LAPTOP", BLUE),
                          (470, 520, "AWS CONTROL PLANE", TEAL),
                          (1020, 420, "WHAT NOW EXISTS", VIOLET)]:
        s.rect(x, 104, w, 40, "#ffffff", col, 2, 10)
        s.text(x + w // 2, 130, nm, 13.5, col, "700", anchor="middle")

    steps = [
        ("1", "STS GetCallerIdentity", "Resolve the account id. Every ARN below is built from this, not from a constant.", TEAL, "account = 908877262866", None),
        ("2", "CreateRepository x2", "Guarded: RepositoryAlreadyExists is the success path. Lifecycle policy applied unconditionally.", TEAL, "ECR: backend + frontend", "Untagged images expire after 1 day, so rebuilds do not accumulate storage."),
        ("3", "CreateLogGroup", "Then PutRetentionPolicy EVERY run, so changing the constant takes effect with no teardown.", TEAL, "/ecs/finsights, 7 days", "The default is never-expire. That is how CloudWatch bills creep."),
        ("4", "CreateRole (execution)", "GUARDED — CreateRole is the only non-idempotent call here.", TEAL, "finsightsEcsExecutionRole", None),
        ("5", "AttachRolePolicy", "UNCONDITIONAL. This is the self-heal: a role left half-built by a crashed run is repaired on the next run.", TEAL, "AmazonECSTaskExecutionRolePolicy", "The Dec 2025 guard tested the role but did two operations. It never repaired."),
        ("6", "CreateRole + PutRolePolicy", "Inline policy, so it is versioned with the repo and PutRolePolicy is a full replace — no drift, no detach step.", TEAL, "finsightsEcsTaskRole, 5 statements", None),
        ("7", "Describe VPC / subnets / route tables", "Verify each subnet's route table actually reaches an IGW. MapPublicIpOnLaunch is not proof.", TEAL, "3 subnets, 3 AZs, no NAT", None),
        ("8", "CreateSecurityGroup + authorize", "Duplicate rule is the success path. Only 8501. Nothing on 8000.", TEAL, "sg-... : one ingress rule", None),
        ("9", "CreateServiceLinkedRole", "The step nobody writes, because the console does it silently on first visit.", ROSE, "AWSServiceRoleForECS", "THIS FAILED ON RUN 1. A never-touched account has no such role, so CreateCluster returned 'Unable to assume the service linked role'. It is the concrete reason 'works on a fresh account' was false."),
        ("10", "CreateCluster", "Idempotent: returns the existing cluster if there is one.", TEAL, "finsights-cluster", None),
        ("11", "docker build --platform linux/arm64", "Native on Apple Silicon: no QEMU. ARM64 is also 20% cheaper per vCPU-hour and per GB-hour.", BLUE, "two images, 0.643 GB total", None),
        ("12", "GetAuthorizationToken → docker push", "12-hour token on stdin, never in the process table.", BLUE, "images live in ECR", None),
        ("13", "RegisterTaskDefinition", "Built from taskdef.py. No describe-then-patch, so a fresh account behaves like an old one.", TEAL, "finsights-app:1", "The single most important step. Dec 2025 could not do this at all."),
        ("14", "CreateService + poll to steady state", "Poll directly rather than using the waiter, so the reason for a stall gets logged.", TEAL, "running=1, both HEALTHY", None),
    ]

    y = 158
    for num, action, detail, col, result, note in steps:
        lines = wrap(detail, 12.3, 366)
        nlines = wrap(note, 12.3, 386) if note else []
        h = max(58, 30 + 16.5 * len(lines), 30 + 16 * len(nlines))
        s.rect(470, y, 520, h, "#ffffff", col, 2, 10)
        s.rect(470, y, 30, h, col, None, 0, 4)
        s.text(485, y + 20, num, 12.5, "#ffffff", "700", anchor="middle")
        s.text(510, y + 20, action, 12.8, col, "700", mono=True)
        yy = y + 38
        for ln in lines:
            s.text(510, yy, ln, 12.3, INK)
            yy += 16.5
        s.rect(1020, y, 420, h, "#faf5ff" if col != ROSE else "#fff1f2", VIOLET if col != ROSE else ROSE, 2, 10)
        s.text(1036, y + 20, result, 12.3, VIOLET if col != ROSE else ROSE, "700", mono=True)
        if note:
            yy = y + 38
            style = "bad" if col == ROSE else "note"
            s.flow(1036, yy, [(style, note)], 386)
        s.arrow(992, y + h / 2, 1016, y + h / 2, FAINT, 1.8)
        if col == BLUE:
            s.arrow(444, y + h / 2, 466, y + h / 2, BLUE, 2)
        y += h + 12

    s.rect(40, 158, 400, 248, "#eff6ff", BLUE, 2, 12)
    s.text(60, 186, "One command", 14.5, BLUE, "700")
    s.flow(60, 208, [("code", "python -m deploy_aws.cli up"),
                     ("gap", ""),
                     ("lead", "Or double-click finsights_aws.command."),
                     ("bullet", "Steps 1-10 and 13-14 are AWS API calls."),
                     ("bullet", "Steps 11-12 run docker locally."),
                     ("bullet", "Everything is safe to run twice."),
                     ("gap", ""),
                     ("note", "Total wall time from an empty account: about 7 minutes, most of it pushing 0.643 GB of layers.")], 366)

    s.rect(40, 424, 400, 232, "#f0fdf4", GREEN, 2, 12)
    s.text(60, 452, "The real test: reverse it", 14.5, GREEN, "700")
    s.flow(60, 474, [("code", "cli destroy --yes  →  cli up"),
                     ("gap", ""),
                     ("good", "All 6 resource checks came back empty."),
                     ("good", "up rebuilt everything to steady state as rev 2."),
                     ("gap", ""),
                     ("lead", "Pets vs cattle: if you cannot destroy and rebuild it, you do not have infrastructure as code — you have a console with a backup script.")], 366)

    s.rect(40, 674, 400, 172, "#fffbeb", AMBER, 2, 12)
    s.text(60, 702, "Cost, the moment step 14 ends", 14.5, AMBER, "700")
    s.flow(60, 724, [("code", "$0.04306 / hour  (1 vCPU, 3 GB, ARM)"),
                     ("bullet", "24/7: ~$31.43/mo"),
                     ("bullet", "2 h/day: ~$2.68/mo"),
                     ("bullet", "after 'down': $0.064/mo (ECR only)"),
                     ("bullet", "after 'destroy': $0")], 366)
    (OUT / "D4-up-sequence.svg").write_text(
        s.render("What actually happens when you run `up`",
                 "Fourteen steps from an empty account to a serving task — with every idempotency decision, and the one that broke"))


d1(); d2(); d3(); d4()
for f in sorted(OUT.glob("D*.svg")):
    print(f"{f.name}  {f.stat().st_size:,} bytes")
