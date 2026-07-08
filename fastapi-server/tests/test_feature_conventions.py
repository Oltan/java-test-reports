"""Feature-lint gate: enforces docs/OTOMASYON_KURALLARI.md §1 on every .feature file.

Rules enforced (see the rulebook for rationale):
  R1  every Scenario carries exactly one DOORS/ABS tag
  R2  DOORS tags live on scenarios, never on the Feature line
  R3  a DOORS number is unique across the whole repo
  R4  @id: values are unique across the whole repo
  R5  every @dep: target refers to an existing @id:
  R6  the @dep: graph is acyclic

The lint itself is a pure function (feature texts in, violation strings out) so
the negative tests below exercise it with inline fixtures without touching the
real feature files.
"""
from pathlib import Path

from services.identifiers import DOORS_PATTERN, extract_doors_id

FEATURES_DIR = Path(__file__).resolve().parents[2] / "test-core" / "src" / "test" / "resources" / "features"


def _parse_features(feature_texts: dict[str, str]):
    """Yield (file, scenario_name, tags) plus per-file feature-level tags."""
    scenarios = []
    feature_tags = {}
    for fname, text in feature_texts.items():
        pending: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("@"):
                pending.extend(t for t in line.split() if t.startswith("@"))
            elif line.startswith("Feature:"):
                feature_tags[fname] = pending
                pending = []
            elif line.startswith(("Scenario:", "Scenario Outline:")):
                name = line.split(":", 1)[1].strip()
                scenarios.append((fname, name, pending))
                pending = []
            # description/step/comment lines: ignored, pending tags survive
            # only until the next Feature/Scenario keyword line
    return scenarios, feature_tags


def lint_features(feature_texts: dict[str, str]) -> list[str]:
    """Check rulebook §1 over the given {filename: content} mapping."""
    violations: list[str] = []
    scenarios, feature_tags = _parse_features(feature_texts)

    # R2: DOORS tag on the Feature line
    for fname, tags in feature_tags.items():
        for tag in tags:
            if DOORS_PATTERN.search(tag):
                violations.append(
                    f"{fname}: feature seviyesinde DOORS tag'i ({tag}) — senaryo seviyesine taşınmalı"
                )

    doors_owner: dict[str, str] = {}
    id_owner: dict[str, str] = {}
    dep_edges: dict[str, list[str]] = {}

    for fname, name, tags in scenarios:
        where = f"{fname}: '{name}'"

        # R1: exactly one DOORS/ABS tag per scenario
        doors_ids = [d for d in (extract_doors_id(t) for t in tags) if d]
        if len(doors_ids) != 1:
            violations.append(f"{where}: tam 1 DOORS/ABS tag'i olmalı ({len(doors_ids)} bulundu)")

        # R3: DOORS number unique repo-wide
        for doors in doors_ids:
            key = doors.upper()
            if key in doors_owner:
                violations.append(f"{where}: {doors} zaten kullanılıyor ({doors_owner[key]})")
            else:
                doors_owner[key] = where

        # R4: @id: unique
        for tag in tags:
            if tag.startswith("@id:"):
                sid = tag[len("@id:"):]
                if sid in id_owner:
                    violations.append(f"{where}: @id:{sid} zaten tanımlı ({id_owner[sid]})")
                else:
                    id_owner[sid] = where
            elif tag.startswith("@dep:"):
                dep_edges.setdefault(where, []).extend(
                    d for d in tag[len("@dep:"):].split(",") if d
                )

    # R5: dep targets exist
    scenario_id_by_where = {}
    for fname, name, tags in scenarios:
        where = f"{fname}: '{name}'"
        for tag in tags:
            if tag.startswith("@id:"):
                scenario_id_by_where[where] = tag[len("@id:"):]
    for where, targets in dep_edges.items():
        for target in targets:
            if target not in id_owner:
                violations.append(f"{where}: @dep:{target} hedefi tanımlı bir @id: değil")

    # R6: dep graph acyclic (edges between @id: nodes only)
    graph = {
        scenario_id_by_where[where]: [t for t in targets if t in id_owner]
        for where, targets in dep_edges.items()
        if where in scenario_id_by_where
    }
    state: dict[str, int] = {}  # 0=visiting, 1=done

    def _visit(node: str, path: list[str]) -> None:
        if state.get(node) == 1:
            return
        if state.get(node) == 0:
            violations.append(f"@dep döngüsü: {' -> '.join(path + [node])}")
            return
        state[node] = 0
        for nxt in graph.get(node, []):
            _visit(nxt, path + [node])
        state[node] = 1

    for node in graph:
        _visit(node, [])

    return violations


def _repo_feature_texts() -> dict[str, str]:
    return {
        f.name: f.read_text(encoding="utf-8")
        for f in sorted(FEATURES_DIR.glob("*.feature"))
    }


# ── Gate: the checked-in feature files must satisfy the rulebook ──

def test_repo_features_satisfy_conventions():
    texts = _repo_feature_texts()
    assert texts, f"feature dosyası bulunamadı: {FEATURES_DIR}"
    assert lint_features(texts) == []


# ── Negative fixtures: prove the lint actually catches violations ──

def test_lint_flags_missing_doors_tag():
    text = "Feature: X\n\n  @smoke\n  Scenario: no doors\n    Given a\n"
    violations = lint_features({"x.feature": text})
    assert any("tam 1 DOORS/ABS" in v for v in violations)


def test_lint_flags_multiple_doors_tags():
    text = "Feature: X\n\n  @DOORS-1 @DOORS-2\n  Scenario: two doors\n    Given a\n"
    violations = lint_features({"x.feature": text})
    assert any("tam 1 DOORS/ABS" in v for v in violations)


def test_lint_flags_duplicate_doors_across_files():
    a = "Feature: A\n\n  @DOORS-7\n  Scenario: one\n    Given a\n"
    b = "Feature: B\n\n  @DOORS-7\n  Scenario: two\n    Given b\n"
    violations = lint_features({"a.feature": a, "b.feature": b})
    assert any("zaten kullanılıyor" in v for v in violations)


def test_lint_flags_feature_level_doors_tag():
    text = "@DOORS-9\nFeature: X\n\n  @DOORS-10\n  Scenario: s\n    Given a\n"
    violations = lint_features({"x.feature": text})
    assert any("feature seviyesinde DOORS" in v for v in violations)


def test_lint_flags_unknown_dep_target():
    text = "Feature: X\n\n  @id:A @dep:Ghost @DOORS-11\n  Scenario: s\n    Given a\n"
    violations = lint_features({"x.feature": text})
    assert any("@dep:Ghost hedefi" in v for v in violations)


def test_lint_flags_duplicate_id():
    text = (
        "Feature: X\n\n"
        "  @id:A @DOORS-12\n  Scenario: s1\n    Given a\n\n"
        "  @id:A @DOORS-13\n  Scenario: s2\n    Given b\n"
    )
    violations = lint_features({"x.feature": text})
    assert any("@id:A zaten tanımlı" in v for v in violations)


def test_lint_flags_dependency_cycle():
    text = (
        "Feature: X\n\n"
        "  @id:A @dep:B @DOORS-14\n  Scenario: s1\n    Given a\n\n"
        "  @id:B @dep:A @DOORS-15\n  Scenario: s2\n    Given b\n"
    )
    violations = lint_features({"x.feature": text})
    assert any("@dep döngüsü" in v for v in violations)


def test_lint_accepts_valid_features():
    text = (
        "@UnitDemo\nFeature: X\n\n"
        "  @id:A @DOORS-16\n  Scenario: s1\n    Given a\n\n"
        "  @id:B @dep:A @DOORS-17\n  Scenario: s2\n    Given b\n"
    )
    assert lint_features({"x.feature": text}) == []
