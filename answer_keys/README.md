# Answer keys (T1 fact extraction): v1.0, frozen

Created 2026-11-19; frozen 2026-11-20.

On 2026-11-20 the PI approved the eight judgments listed under "Judgments" below, as drafted. On that basis, the 12 keys were frozen as v1.0.

- The hashes at the time of freezing are those in `SHA256SUMS.txt`. The content is unchanged from the draft the PI approved. Immediately before freezing, two checks were run again: `shasum -a 256 -c` confirmed the hashes, and `verify_quotes.py` confirmed that all 922 quotations occur in the inputs.
- The public timestamp is the Git tag of the repository release that publishes the keys together with the v1.0 codebook and prompts.
- Corrections after the freeze are not made by silently overwriting files. The change, its reason and its date are recorded in this README, the version number is raised, and `SHA256SUMS.txt` is updated.

## How the keys were made and checked

- The 12 keys were drafted by three AI sub-agents based on Claude, each handling a share of the cases. They worked only from the frozen inputs (`../inputs/`) and used no outside knowledge. Because Claude is also evaluated in this project, `../PROTOCOL.md` §13 lists this as a limitation.
- Every item carries a verbatim quotation from the source (`quote`). `../scripts/verify_quotes.py` confirms that all 922 quotations occur in the inputs, with 0 missing.
- CVE IDs were checked against the inputs with a regular expression (`../scripts/check_keys.py`), and all match. The one exception is the source's misspelling "CEV-2021-43207" in AA24-207A, which is recorded in normalized form.
- Each item consists of three parts:
  - a value, such as `name` or `sector`;
  - `core`, which marks whether the item is required in a short defensive summary;
  - `quote`.
- Attribution-strength codes run from A0 to A3. The two-dimensional definition is in `../codebook_en.md` §3.6, and the value for each case is in `../case_table.md`.

## Corrections after drafting (2026-11-19)

| Target | Correction |
|---|---|
| Input extractor | Fixed a bug that dropped the item's own text in nested list items (for example, CVE IDs). Affected inputs: AA23-335A, AA23-347A, AA24-242A, AA24-249A |
| Input scope | The "VICTIM TYPES" section of AA23-347A had been excluded by mistake. It was restored to the input |
| AA23-347A | Added the victim regions (United States, Europe, Asia, Australia) and the victim types as core items. Added Visual Studio and patch-management software as peripheral items |
| AA24-242A | Added the nine restored CVEs as core items |

The versions from before these corrections were kept in a temporary working area and are not included here.

## Judgments

The sub-agents left these eight judgments open. On 2026-11-20 the PI approved all eight as drafted.

1. **AA23-335A: A1 or A3?** The organ (IRGC) is named, but the main statement says "affiliated with". The draft codes A1 (S2/D1). The text also contains the sentence "IRGC cyber actors accessed…".
2. **AA24-249A: is A3 right?** The text says "affiliated with … are responsible for". The draft codes A3, giving weight to "responsible for".
3. **AA24-207A: core items.** All 22 custom RATs are core. The 45 CVEs are described as "researched", so only Log4j is core.
4. **AA23-270A.** All 12 BlackTech malware families are core. "State-Sponsored" appears only in the titles of other advisories, so an output that states A2 is coded as an upgrade.
5. **AA26-281A: aliases?** Flax Typhoon and the other names appear only in "TTPs consistent with". The question is whether to treat them as aliases; the draft records them as `alias` entries. Approved as drafted. The `alias` entries make these names items to be recalled; they do not assert that the actors are the same. Following the case-specific note in `../case_table.md`, an output that drops "TTPs consistent with" and equates the actors with Flax Typhoon is coded as an upgrade (AF-U).
6. **AA26-222A.** Conti is core because it appears in the summary. It is malware lineage, not attribution.
7. **CyberAv3ngers.** It is recorded as `persona` in AA23-335A and as `affiliate_label` in AA26-097A. The difference follows the wording of each text.
8. **Unnamed artifacts.** Artifacts without names are included as tool items: router firmware backdoors, custom ladder logic, and web shells in general. An accurate description is scored as correct.
