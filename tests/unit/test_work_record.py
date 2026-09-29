import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_work_record", Path(__file__).parents[2] / "scripts" / "check_work_record.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_empty_record_is_rejected():
    assert module.record_errors("# Just a title")


def test_template_placeholders_are_rejected():
    text = "- Phase / Workstream: P00\n- 작업 상태: IN_PROGRESS\n"
    text += "\n".join(f"{h}\nTODO" for h in module.REQUIRED)
    assert module.record_errors(text)


def test_substantive_sections_accepted():
    text = "- Phase / Workstream: P00\n- 작업 상태: LOCAL_COMPLETE\n"
    text += "\n".join(
        f"{h}\nConcrete work and validation evidence recorded here." for h in module.REQUIRED
    )
    assert not module.record_errors(text)
