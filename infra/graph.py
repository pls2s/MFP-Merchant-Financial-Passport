"""Colour-coded architecture diagram of the stack in infra/live: `tofu graph`, each resource coloured by
its AWS service (the course labs' s00.py colours, plus API Gateway), drawn left to right by Graphviz.

    python3 infra/graph.py [tofu dir]   # writes arch.svg and arch.png next to the .tf files

Run through `infra/setup.sh graph`, which installs Graphviz first.
"""

import shutil
import subprocess
import sys
from pathlib import Path

# (prefix of the resource address, service, fill, border, text) — first match wins
SERVICES = [
    ("terraform_data.data_bucket", "Amazon S3", "#DCFCE7", "#16A34A", "#14532D"),
    ("aws_s3_", "Amazon S3", "#DCFCE7", "#16A34A", "#14532D"),
    ("aws_dynamodb_", "Amazon DynamoDB", "#DBEAFE", "#2563EB", "#1E3A8A"),
    ("aws_lambda_", "AWS Lambda", "#FFEDD5", "#EA580C", "#7C2D12"),
    ("terraform_data.web_deploy", "AWS Amplify", "#F3E8FF", "#9333EA", "#581C87"),
    ("aws_amplify_", "AWS Amplify", "#F3E8FF", "#9333EA", "#581C87"),
    ("aws_sns_", "Amazon SNS", "#FCE7F3", "#DB2777", "#831843"),
    ("aws_cloudwatch_", "EventBridge / CloudWatch", "#FEF9C3", "#CA8A04", "#78350F"),
    ("aws_apigatewayv2_", "Amazon API Gateway", "#FEE2E2", "#DC2626", "#7F1D1D"),
]

HEADER = """  rankdir="LR"; pad="0.3"; nodesep="0.45"; ranksep="0.75";
  label="MFP on AWS — OpenTofu dependency graph (infra/live)"; labelloc="t"; fontname="Helvetica-Bold"; fontsize="16";
  node [shape="box", style="rounded,filled", fillcolor="#F8FAFC", color="#94A3B8", fontname="Helvetica", fontsize="11"];
  edge [color="#64748B", penwidth="1.2"];"""


def service(address: str):
    return next((s for s in SERVICES if address.startswith(s[0])), None)


def colorize(raw: str) -> str:
    out, used, header = [], {}, False
    for line in raw.splitlines():
        out.append(line)
        if not header and "digraph" in line and "{" in line:
            out.append(HEADER)
            header = True
            continue
        if "->" in line or "[label" not in line:
            continue
        label = line[line.find("[label"):].split('"')[1]
        s = service(label)
        if s:
            _, name, fill, border, text = s
            used[name] = s
            start, end = line.find("[label"), line.rfind("]")
            out[-1] = (f'{line[:start]}[label="{label}", style="filled,rounded", fillcolor="{fill}", '
                       f'color="{border}", fontcolor="{text}", penwidth="2.2", fontname="Helvetica-Bold"]{line[end + 1:]}')
    # A legend of the services in this graph, in SERVICES order.
    legend = ['  subgraph cluster_legend { label="Service colours"; fontname="Helvetica-Bold"; fontsize="12"; '
              'style="rounded"; color="#CBD5E1";']
    names = [s[1] for s in SERVICES if s[1] in used]
    for i, name in enumerate(dict.fromkeys(names)):
        _, _, fill, border, text = used[name]
        legend.append(f'    legend{i} [label="{name}", style="filled,rounded", fillcolor="{fill}", color="{border}", '
                      f'fontcolor="{text}", penwidth="2.2", fontname="Helvetica-Bold"];')
    legend += [f"    legend{i} -> legend{i + 1} [style=invis];" for i in range(len(dict.fromkeys(names)) - 1)]
    legend.append("  }")
    closing = max(i for i, line in enumerate(out) if line.strip() == "}")
    return "\n".join(out[:closing] + legend + out[closing:])


def main():
    work = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "live").resolve()
    tofu = shutil.which("tofu") or str(Path.home() / ".local/bin/tofu")
    raw = subprocess.check_output([tofu, "graph"], cwd=work, text=True)
    dot_path = work / "arch_colored.dot"
    dot_path.write_text(colorize(raw), encoding="utf-8")
    for fmt in ("svg", "png"):
        subprocess.run(["dot", f"-T{fmt}", "-Gdpi=150" if fmt == "png" else "-Gdpi=72", str(dot_path),
                        "-o", str(work / f"arch.{fmt}")], check=True)
    print(f"Saved {work / 'arch.svg'} and {work / 'arch.png'}")
    print("CloudShell: Actions -> Download file -> paste the path above")


if __name__ == "__main__":
    main()
