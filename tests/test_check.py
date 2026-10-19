import pytest
import yaml

from local_video_knowledge.check import REQUIRED, tier, validate_notes


def note(vault, body="", kind="insight", count=60, **overrides):
    fields = {key: "Example" for key in REQUIRED}
    fields.update(type=kind, tags=["learning"], related=[], parent=None, duration=1200, status="active",
                  source_path="/recordings/talk.mp4", recorded_date="2024-05-17",
                  created="2026-10-01", modified="2026-10-01")
    fields.update(overrides)
    text = "---\n" + yaml.safe_dump(fields) + "---\n" + body + "\n"
    text += "\n".join(f"Specific point {i}." for i in range(count))
    path = vault / "Note.md"
    path.write_text(text)
    return path


def test_alias_heading_and_relative_links(tmp_path):
    folder = tmp_path / "cluster"
    folder.mkdir()
    (folder / "Sibling.md").write_text("# Heading\n")
    path = note(tmp_path, "[[Sibling|alias]] [[Sibling#Heading]] [[cluster/Sibling.md#Heading|label]] [[#Local]]")
    assert validate_notes([path], tmp_path)["ok"]


def test_broken_link(tmp_path):
    result = validate_notes([note(tmp_path, "[[Missing#Heading|alias]]")], tmp_path)
    assert not result["ok"]
    assert "Broken link" in result["files"][0]["errors"][0]


@pytest.mark.parametrize("codepoint", [0x2013, 0x2014])
def test_dashes_and_config_optout(tmp_path, codepoint):
    path = note(tmp_path, "A" + chr(codepoint) + "B")
    assert not validate_notes([path], tmp_path)["ok"]
    assert validate_notes([path], tmp_path, no_dashes=False)["ok"]


@pytest.mark.parametrize("duration,expected", [(59, "short"), (299.9, "short"), (300, "medium"),
                                               (899, "medium"), (900, "long"), (None, "long"), (True, "long")])
def test_tiers(duration, expected):
    assert tier(duration) == expected


@pytest.mark.parametrize("duration,kind,enough", [(60, "insight", 25), (60, "moc", 30), (600, "insight", 40),
                                                  (600, "moc", 80), (3600, "insight", 50), (3600, "moc", 150)])
def test_floors_scale_with_duration(tmp_path, duration, kind, enough):
    lines = lambda count: validate_notes([note(tmp_path, kind=kind, count=count, duration=duration)], tmp_path)
    # Every non-blank line counts, frontmatter included; measure the fixed part first.
    base = lines(0)["files"][0]["lines"]
    assert lines(enough - base)["ok"]
    result = lines(enough - base - 1)
    assert not result["ok"]
    assert any("non-blank lines for this duration" in error for error in result["files"][0]["errors"])


@pytest.mark.parametrize("kind,count", [("insight", 2), ("moc", 60)])
def test_short_notes_ignore_blank_lines(tmp_path, kind, count):
    path = note(tmp_path, "\n" * 200, kind=kind, count=count)
    result = validate_notes([path], tmp_path)
    assert not result["ok"]
    assert any("non-blank lines" in error for error in result["files"][0]["errors"])


def test_vault_status_and_nullable_source_fields(tmp_path):
    assert validate_notes([note(tmp_path, status="draft", recorded_date=None, duration=None, count=80)], tmp_path)["ok"]
    assert validate_notes([note(tmp_path, status="seedling")], tmp_path)["ok"]
    result = validate_notes([note(tmp_path, status=" ")], tmp_path)
    assert any("status must be" in error for error in result["files"][0]["errors"])


def test_decomposed_file_names_resolve(tmp_path):
    import unicodedata
    folder = tmp_path / unicodedata.normalize("NFD", "Café")
    folder.mkdir()
    (folder / unicodedata.normalize("NFD", "Crème.md")).write_text("x")
    path = note(tmp_path, "[[Crème]] [[Café/Crème]]")
    assert validate_notes([path], tmp_path)["ok"], validate_notes([path], tmp_path)


def test_dashes_in_paths_and_link_targets_are_exempt(tmp_path):
    name = "Talk " + chr(0x2013) + " 2024"
    (tmp_path / f"{name}.md").write_text("x")
    path = note(tmp_path, f"[[{name}|the talk]] `/recordings/{name}.mp4`", source_path=f"/recordings/{name}.mp4")
    assert validate_notes([path], tmp_path)["ok"]
    assert not validate_notes([note(tmp_path, f"[[{name}|bad {chr(0x2014)} label]]")], tmp_path)["ok"]


def test_decomposed_relative_link(tmp_path):
    import unicodedata
    sub = tmp_path / "Topics" / "sub"
    sub.mkdir(parents=True)
    (sub / unicodedata.normalize("NFD", "Café.md")).write_text("x")
    path = note(tmp_path, "[[sub/Café]]")
    moved = tmp_path / "Topics" / "Note.md"
    path.rename(moved)
    assert validate_notes([moved], tmp_path)["ok"], validate_notes([moved], tmp_path)


@pytest.mark.parametrize("field,value", [("recorded_date", "2024-13-01"), ("duration", -1), ("source_path", ""),
                                         ("related", ["not a link"]), ("tags", [])])
def test_schema_errors(tmp_path, field, value):
    assert not validate_notes([note(tmp_path, **{field: value})], tmp_path)["ok"]


def test_required_keys_and_duplicate_yaml(tmp_path):
    path = tmp_path / "Bad.md"
    path.write_text("---\ntype: insight\ntype: moc\n---\n")
    errors = validate_notes([path], tmp_path)["files"][0]["errors"]
    assert any("Duplicate" in error for error in errors)
    assert any("Missing frontmatter keys" in error for error in errors)


def test_link_cannot_escape_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "Outside.md").write_text("private")
    path = note(vault, "[[../Outside]]")
    assert not validate_notes([path], vault)["ok"]


def test_code_links_ignored_but_frontmatter_links_checked(tmp_path):
    path = note(tmp_path, "`[[InlineExample]]`\n~~~md\n[[FencedExample]]\n~~~\n")
    assert validate_notes([path], tmp_path)["ok"]
    content = path.read_text().replace("parent: null", "parent: '[[MissingParent]]'")
    path.write_text(content)
    assert any("MissingParent" in error for error in validate_notes([path], tmp_path)["files"][0]["errors"])
