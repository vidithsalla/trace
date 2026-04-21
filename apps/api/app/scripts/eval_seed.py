import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.evals import DEFAULT_TRUTH_PATH, EvalRunner, EvalSuiteRunner, StaticTruthPackRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Trace seeded matter evals.")
    parser.add_argument("--truth", default=str(DEFAULT_TRUTH_PATH), help="Path to seed truth JSON.")
    parser.add_argument(
        "--suite",
        choices=["acme", "regression", "all"],
        default="acme",
        help="Eval scope to run.",
    )
    parser.add_argument(
        "--corpus",
        help="Regression corpus id for --suite regression, e.g. employment_dispute.",
    )
    parser.add_argument("--commit", action="store_true", help="Persist eval-generated artifacts.")
    args = parser.parse_args()

    engine = create_engine(settings.database_url, future=True)
    with Session(engine) as db:
        truth_path = Path(args.truth)
        if args.suite == "all":
            report = EvalSuiteRunner(db, truth_path.parent).run_all(include_acme=True)
        elif args.suite == "regression":
            if args.corpus:
                report = EvalSuiteRunner(db, truth_path.parent).run_regression(args.corpus)
            else:
                report = {
                    "suite": "regression",
                    "reports": EvalSuiteRunner(db, truth_path.parent).run_all(include_acme=False)[
                        "reports"
                    ],
                }
                report["passed"] = all(item["passed"] for item in report["reports"])
        elif truth_path.name == "acme_truth.json":
            report = EvalRunner(db, truth_path).run()
        else:
            report = StaticTruthPackRunner(truth_path).run()
        if args.commit:
            db.commit()
        else:
            db.rollback()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
