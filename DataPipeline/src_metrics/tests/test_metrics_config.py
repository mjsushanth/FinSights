import yaml

from config import load_metrics_config


def test_load_metrics_config_resolves_real_paths():
    config = load_metrics_config()
    assert config.bucket == "sentence-data-ingestion-mjs"
    assert config.company_dimension_path.exists()
    assert config.gaap_registry_path.exists()
    assert config.domain_rules_path.exists()


def test_kpi_facts_key_matches_ml_config_yaml():
    """metrics_config.yaml's output.kpi_facts must agree with
    ModelPipeline/finrag_ml_tg1/.aws_config/ml_config.yaml's s3.kpi_facts -
    the two configs are independently owned by design (matching how
    src_aws_etl/etl_config.yaml and ml_config.yaml are also independently
    owned), but must not silently drift apart on this one shared value."""
    config = load_metrics_config()

    ml_config_path = (
        config.company_dimension_path.parent.parent.parent.parent  # .../dimensions -> data_cache -> DataPipeline -> repo root
        / "ModelPipeline" / "finrag_ml_tg1" / ".aws_config" / "ml_config.yaml"
    )
    with open(ml_config_path) as f:
        ml_config = yaml.safe_load(f)

    ml_kpi = ml_config["data_ml"]["kpi_facts"]
    expected_key = f"{ml_kpi['path']}/{ml_kpi['filename']}"

    assert config.kpi_facts_key == expected_key, (
        f"metrics_config.yaml's kpi_facts key ({config.kpi_facts_key}) has drifted "
        f"from ml_config.yaml's ({expected_key})"
    )
