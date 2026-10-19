from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def test_installer_placeholders_present():
    content = SKILL.read_text()
    assert content.startswith("---\nname: local-video-knowledge\n")
    assert "<!-- local-video-knowledge:managed -->" in content
    assert "<!-- local-video-knowledge:wrapper -->" in content


def test_core_rules():
    content = SKILL.read_text()
    assert "The vault's rules win over this skill" in content
    assert "Establish who is speaking" in content
    assert "Never move, rename, edit or delete the user's recordings." in content
    assert "lvk check" in content
    assert "--lease" in content


def test_no_unicode_dashes():
    content = SKILL.read_text()
    assert chr(0x2013) not in content and chr(0x2014) not in content
