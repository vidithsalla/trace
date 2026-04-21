from pathlib import Path


CORE_SERVICES = {"web", "api", "worker", "postgres", "redis", "minio", "minio-init"}
MODEL_SERVICES = {"api", "vllm"}
OCR_SERVICES = {"api", "worker", "ocr"}


def parse_services(compose_path: Path) -> set[str]:
    lines = compose_path.read_text().splitlines()
    services: set[str] = set()
    in_services = False
    for line in lines:
        if line.strip() == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if line and not line.startswith(" "):
            break
        if line.startswith("  ") and line.strip().endswith(":") and not line.startswith("    "):
            services.add(line.strip()[:-1])
    return services


def main() -> None:
    core_path = Path("infra/compose/compose.yaml")
    model_path = Path("infra/compose/compose.model.yaml")
    ocr_path = Path("infra/compose/compose.ocr.yaml")

    core_services = parse_services(core_path)
    model_services = parse_services(model_path)
    ocr_services = parse_services(ocr_path)

    missing_core = CORE_SERVICES - core_services
    if missing_core:
        raise SystemExit(f"Missing core compose services: {sorted(missing_core)}")
    forbidden_core = {"vllm", "ocr"} & core_services
    if forbidden_core:
        raise SystemExit(f"Core compose should stay lightweight; found: {sorted(forbidden_core)}")

    missing_model = MODEL_SERVICES - model_services
    if missing_model:
        raise SystemExit(f"Missing model add-on services: {sorted(missing_model)}")

    missing_ocr = OCR_SERVICES - ocr_services
    if missing_ocr:
        raise SystemExit(f"Missing OCR add-on services: {sorted(missing_ocr)}")

    print("Phase 0 compose structure looks valid for the lightweight core stack.")


if __name__ == "__main__":
    main()
