from pathlib import Path

from app.services.evals import EvalSuiteRunner, StaticTruthPackRunner, regression_truth_paths


def test_regression_truth_packs_all_pass_static_checks() -> None:
    reports = [StaticTruthPackRunner(path).run() for path in regression_truth_paths()]

    assert {report["suite"] for report in reports} == {
        "employment_dispute",
        "internal_investigation",
        "invoice_payment_dispute",
    }
    assert all(report["passed"] for report in reports)
    for report in reports:
        check_names = {check["name"] for check in report["checks"]}
        assert {
            "truth_pack_schema",
            "entity_mentions",
            "golden_questions",
            "known_contradictions",
            "chronology_coverage",
            "memo_section_coverage",
            "ambiguity_handling",
            "branding",
        } <= check_names


def test_eval_suite_runner_can_run_regression_suite_without_acme_db() -> None:
    report = EvalSuiteRunner(db=None).run_all(include_acme=False)  # type: ignore[arg-type]

    assert report["suite"] == "all"
    assert report["passed"] is True
    assert report["summary"] == {"total": 3, "passed": 3, "failed": 0}


def test_eval_suite_runner_can_select_single_regression_corpus() -> None:
    report = EvalSuiteRunner(db=None).run_regression("invoice_payment_dispute")  # type: ignore[arg-type]

    assert report["suite"] == "invoice_payment_dispute"
    assert report["passed"] is True
    assert report["matter"] == "Ridgeway Components v. Solace Retail"


def test_truth_pack_paths_are_repo_relative() -> None:
    paths = regression_truth_paths()

    assert all(isinstance(path, Path) for path in paths)
    assert all(path.exists() for path in paths)
