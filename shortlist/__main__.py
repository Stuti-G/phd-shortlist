from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .pipeline import run_pipeline
from .feedback import build_priors, save_priors



def main(argv=None) -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        print("Failed to load .env file")

    parser = argparse.ArgumentParser(prog="shortlist")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="build a shortlist for a student profile")
    run.add_argument("--student", required=True, help="path to student profile JSON")
    run.add_argument("--out", required=True, help="path to write shortlist JSON")

    fb = sub.add_parser("feedback", help="ingest outcomes CSV -> ranking priors")
    fb.add_argument("--outcomes", required=True, help="path to outcomes CSV")
    fb.add_argument("--out", required=True, help="path to write priors JSON")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        profile = json.loads(Path(args.student).read_text(encoding="utf-8"))
        t0 = time.time()
        shortlist = run_pipeline(profile)
        elapsed = time.time() - t0

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(shortlist.model_dump_json(indent=2), encoding="utf-8")

        m = shortlist.meta
        print(
            f"[done] {len(shortlist.supervisors)} supervisors "
            f"({m.total_candidates_retrieved} retrieved) "
            f"via {m.llm_provider} in {elapsed:.1f}s -> {out}",
            file=sys.stderr,
        )

    elif args.cmd == "feedback":
        priors = build_priors(args.outcomes)
        save_priors(priors, args.out)
        print(
            f"[done] priors from {args.outcomes}: "
            f"{len(priors.by_supervisor)} supervisors, "
            f"{len(priors.flagged_for_review)} flagged for filter review -> {args.out}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
