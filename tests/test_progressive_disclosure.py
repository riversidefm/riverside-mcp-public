from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS = REPO_ROOT / "skills"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_skill_references as reference_validator  # noqa: E402


ROUTES = {
    ("content-discovery", "cross-skill-handoffs.md"): 14_282,
    ("content-discovery", "hierarchy-navigation.md"): 14_282,
    ("content-discovery", "search.md"): 14_282,
    ("setup", None): 6_875,
    ("social-publishing", "results-and-recovery.md"): 9_855,
    ("social-publishing", "scheduling-and-draft-export.md"): 9_855,
    ("video-editing", "captions-and-brand.md"): 24_112,
    ("video-editing", "cuts-and-audio.md"): 24_112,
    ("video-editing", "edit-lifecycle.md"): 24_112,
    ("video-editing", "transcript-editing.md"): 24_112,
    ("video-editing", "visuals-and-media.md"): 24_112,
}

ROUTING_HEADINGS = {
    "content-discovery": "## Where to read next",
    "social-publishing": "## Mandatory routing",
    "video-editing": "## Where to read next",
}


class ProgressiveDisclosureContextTests(unittest.TestCase):
    """Keep every ordinary routed context smaller than the PR #9 monolith."""

    def context_bytes(self, skill: str, *references: str) -> int:
        total = (SKILLS / skill / "SKILL.md").stat().st_size
        for reference in references:
            total += (SKILLS / skill / "references" / reference).stat().st_size
        return total

    def routing_table_lines(self, skill: str) -> set[int]:
        lines = (SKILLS / skill / "SKILL.md").read_text().splitlines()
        heading = ROUTING_HEADINGS[skill]
        heading_index = lines.index(heading)
        end_index = next(
            (
                index
                for index in range(heading_index + 1, len(lines))
                if lines[index].startswith("## ")
            ),
            len(lines),
        )
        return {
            index + 1
            for index in range(heading_index + 1, end_index)
            if lines[index].startswith("|")
        }

    def test_ordinary_routes_reduce_loaded_instruction_bytes(self) -> None:
        # These are the byte sizes of the corresponding PR #9 SKILL.md files.
        # A route earns the progressive-disclosure trade only when the complete
        # entrypoint + its one matching reference stays below that baseline.
        for (skill, reference), baseline in ROUTES.items():
            with self.subTest(skill=skill, reference=reference):
                references = () if reference is None else (reference,)
                loaded = self.context_bytes(skill, *references)
                self.assertLess(
                    loaded,
                    baseline,
                    f"{skill}/{reference or 'SKILL.md'} loads {loaded} bytes; "
                    f"PR #9 loaded {baseline}",
                )

    def test_compound_social_route_reduces_loaded_instruction_bytes(self) -> None:
        loaded = self.context_bytes(
            "social-publishing",
            "scheduling-and-draft-export.md",
            "results-and-recovery.md",
        )

        self.assertLess(
            loaded,
            9_855,
            f"compound social route loads {loaded} bytes; PR #9 loaded 9855",
        )

    def test_video_editing_compound_route_crossover_stays_where_reviewed(
        self,
    ) -> None:
        """Pin where a compound video-editing route stops being a saving.

        Progressive disclosure trades one large load for a small load plus
        repeated reads, so a request matching enough routing rows eventually
        loads MORE than the 0.6.1 monolith did. That trade is accepted — the
        common requests match one or two rows, and those save 7-11 KB each —
        but the point where it flips must not move without someone looking.

        Two properties are asserted, chosen so the test fails on drift and not
        on improvement:

        * every one- and two-reference route stays under the monolith, which is
          what makes the trade favourable across a realistic request mix;
        * the full five-reference fan-out stays under a recorded ceiling, so a
          growing entrypoint or reference is caught even though exceeding the
          monolith itself is permitted here.

        A failure means re-deriving the trade, not relaxing the numbers.
        """
        entrypoint = (SKILLS / "video-editing" / "SKILL.md").stat().st_size
        references = sorted(
            path.stat().st_size
            for path in (SKILLS / "video-editing" / "references").glob("*.md")
        )
        self.assertEqual(5, len(references), "video editing routes five references")

        def worst_case(count: int) -> int:
            """The most expensive route loading `count` references."""
            largest = references[len(references) - count :] if count else []
            return entrypoint + sum(largest)

        baseline = 24_112  # 0.6.1 skills/video-editing/SKILL.md
        for count in (0, 1, 2):
            with self.subTest(references=count):
                self.assertLess(
                    worst_case(count),
                    baseline,
                    f"worst {count}-reference route loads {worst_case(count)} "
                    f"bytes; the 0.6.1 monolith loaded {baseline}",
                )

        fan_out_ceiling = 33_000
        self.assertLessEqual(
            worst_case(5),
            fan_out_ceiling,
            f"full fan-out loads {worst_case(5)} bytes, over the reviewed "
            f"{fan_out_ceiling}-byte ceiling",
        )

    def test_entrypoint_routing_tables_contain_exactly_the_expected_links(
        self,
    ) -> None:
        for skill, heading in ROUTING_HEADINGS.items():
            with self.subTest(skill=skill):
                skill_md = SKILLS / skill / "SKILL.md"
                routing_table_lines = self.routing_table_lines(skill)
                expected = {
                    f"references/{reference}"
                    for route_skill, reference in ROUTES
                    if route_skill == skill and reference is not None
                }
                routed = {
                    found.destination
                    for found in reference_validator.markdown_destinations(skill_md)
                    if found.line in routing_table_lines
                    and found.destination.startswith("references/")
                }
                self.assertEqual(
                    expected,
                    routed,
                    f"{skill} {heading!r} does not contain its expected routes",
                )

                outside_links = [
                    (found.line, found.destination)
                    for found in reference_validator.markdown_destinations(skill_md)
                    if found.line not in routing_table_lines
                    and found.destination.startswith("references/")
                ]
                self.assertEqual(
                    [],
                    outside_links,
                    f"{skill} routes references outside {heading!r}",
                )

        for reference in sorted(SKILLS.glob("*/references/*.md")):
            with self.subTest(reference=reference.relative_to(REPO_ROOT)):
                local_links = []
                for found in reference_validator.markdown_destinations(reference):
                    if not found.is_link:
                        continue
                    decoded = reference_validator.local_destination(
                        found.destination
                    )
                    if decoded is None:
                        continue
                    local_links.append((found.line, found.destination))
                self.assertEqual(
                    [],
                    local_links,
                    f"{reference.relative_to(REPO_ROOT)} is not terminal",
                )

    def test_skills_do_not_route_to_currently_delisted_editing_tools(self) -> None:
        unavailable = {
            "editing_create_edit_from_segments",
            "editing_reorder_timeline",
        }
        skill_text = "\n".join(
            path.read_text()
            for path in sorted(SKILLS.glob("**/*.md"))
        )

        for tool in unavailable:
            with self.subTest(tool=tool):
                self.assertNotIn(tool, skill_text)

    def test_video_prose_does_not_narrow_the_mandatory_routing_table(self) -> None:
        entrypoint = " ".join(
            (SKILLS / "video-editing" / "SKILL.md").read_text().split()
        )

        self.assertNotIn("Read Edit lifecycle only", entrypoint)

    def test_discovery_does_not_claim_exclusive_ownership_of_returned_ids(self) -> None:
        handoff = " ".join(
            (
                SKILLS
                / "content-discovery"
                / "references"
                / "cross-skill-handoffs.md"
            )
            .read_text()
            .split()
        ).casefold()

        required_nonexclusive_behavior = (
            "editing response can legitimately return a new `editid`",
            "recover the recording `sessionid`s",
            "keep those returned ids",
        )
        for behavior in required_nonexclusive_behavior:
            with self.subTest(behavior=behavior):
                self.assertIn(behavior, handoff)

        exclusive_ownership_claims = (
            r"\bresolved here and nowhere else\b",
            r"\bonly discovery (?:can )?resolve(?:s|d)?\b",
            r"\bdiscovery (?:alone|exclusively) resolve(?:s|d)?\b",
            r"\bdiscovery (?:is )?the only resolver\b",
            # Parenthesised so the two-part pattern cannot be misread as a
            # missing comma between two separate patterns.
            (
                r"\b(?:ids|identifiers).{0,80}\bmust (?:always|only) be resolved "
                r"(?:here|by discovery)\b"
            ),
        )
        for claim in exclusive_ownership_claims:
            with self.subTest(claim=claim):
                self.assertNotRegex(handoff, claim)


if __name__ == "__main__":
    unittest.main()
