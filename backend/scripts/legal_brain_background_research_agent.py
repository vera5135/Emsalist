#!/usr/bin/env python3
"""
Legal Brain Background Research Agent - CLI
"""

import sys
import os
import json
import argparse

# UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# UTF-8 stderr
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.legal_background_research_agent import LegalBackgroundResearchAgent


def main():
    parser = argparse.ArgumentParser(
        description="Legal Brain Background Research Agent"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run once for all topics"
    )
    parser.add_argument(
        "--query", type=str, default="", help="Run a single query"
    )
    parser.add_argument(
        "--watch", action="store_true", help="Run in watch mode"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Watch mode interval in seconds (min 1800)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max sources per topic/query",
    )
    args = parser.parse_args()

    agent = LegalBackgroundResearchAgent()

    if args.once:
        print("Starting Legal Brain Background Research Agent in ONCE mode...")
        result = agent.run_once(limit_per_topic=args.limit)
        print("\n=== Run Summary ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.query:
        print(f"Starting Legal Brain Background Research Agent in QUERY mode...")
        print(f"Query: {args.query}")
        result = agent.run_query(query=args.query, limit=args.limit)
        print("\n=== Query Summary ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.watch:
        print(f"Starting Legal Brain Background Research Agent in WATCH mode...")
        print(f"Interval: {args.interval}s, Limit per topic: {args.limit}")
        agent.run_watch(interval=args.interval, limit_per_topic=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()