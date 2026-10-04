# History focus rendering regression

Verified on Windows on 2026-10-04. This fix changes only History painting; the verified organization/undo implementation is unchanged.

## 1. Root cause

`TimelineDelegate.paint()` draws the timeline dot using a fill brush, draws the operation metadata, and finally draws a focus rectangle when Qt supplies `State_HasFocus`. The dot's brush remained active. `QPainter.drawRect()` uses both the pen and the current brush, so the intended outline also filled the entire card interior over the already-painted text.

For a selected operation in Light mode the retained brush is the forest-green accent `#2F6651`, producing the reported large solid rectangle. The current/focused row can change as selection is restored during model refresh or the user switches entries, explaining the apparent movement of the block. The underlying model and file outcomes remained correct.

## 2. Exact files changed

Modified:

- `filepilot/ui/pages/history.py`: clear the fill brush before the focus outline, plus an explanatory comment.
- `tests/test_ui.py`: six parameterized painter cases and one real workflow regression test.

Added:

- `verification/history_ui.py`: reproducible native before/fixed History audit with disposable files and separate-process restart verification.
- `docs/history-rendering-fix.md`: this report.

Generated evidence is under `verification/output/history-before/`, `history-fixed/`, `history-ui-baseline.json` and `history-preservation.json`.

## 3. Exact fix

Set `painter.setBrush(Qt.BrushStyle.NoBrush)` immediately before the existing focus pen and rectangle. The outline remains visible; all existing metadata, fills, timeline marks and dimensions remain intact. No size policy, fixed height, spacer, layout, stylesheet, palette or selection behavior changed.

## 4. Native reproduction and hierarchy inspection

The unfixed native run performed scan → preview → apply → History → Undo twice with 40 disposable files, then focused the current operation. Both operations were `Undone`, all 40 files were restored, and `No moves to undo` was correctly disabled. The screenshot reproduced the exact solid green region above the older operation.

The timeline is a `QListView` with a model and painted delegate, inside a vertical `QSplitter`, ordinary body widget and stacked page. The list and splitter have ordinary expanding policies; the list minimum height is 0. Both row rectangles were the existing 100 pixels tall, with contiguous spacing. There were five internal view widgets, without per-card widgets or stale layout entries. The sampled interior was the accent `#2f6651` instead of selected tint `#E4ECE4`. This identifies a paint-state defect rather than expanding cards, hidden widgets, stale spacers or an incorrect background container.

Before evidence: `verification/output/history-before/two-undone-focused.png` and `report.json`. Fixed equivalent: `verification/output/history-fixed/two-undone-immediate-light-1280.png`.

## 5. History states tested

The fixed native audit created 18 real operations in temporary fixtures. It verified one completed operation; one undone operation immediately after Undo; a new completed operation above an older undone one; switching to the older entry; two undone operations; switching between undone entries; three repeated model refreshes; navigating away and back; a new undone operation above an older completed one; and long History scrolling to top and bottom. It then started a separate Python/Qt process against the same isolated database and checked History at both ends again.

Every capture explicitly focused the selected entry, the condition missing from earlier rendering checks. Row heights/adjacency, horizontal overflow and selected interior paint were asserted. The original 40-file content/path snapshot matched after two complete organization/undo cycles. Details, states and the disabled Undo button were preserved.

## 6. Sizes and themes

All 13 states were exercised in Light, Dark and System at 1440×900, 1280×800 and 1000×680: **117 native captures** on Qt's `windows` platform. Zero Qt warnings, error notices or failed geometry/paint assertions. Representative focused, mixed-state, long-scrolled and restarted screenshots were visually inspected. Partially visible rows at the viewport edge use the existing vertical scrolling; no heights or scrolling mechanics were changed.

The full matrix used process-local `QT_SCALE_FACTOR=0.8` on the available 125% Windows monitor, giving device pixel ratio 1.0 so the largest requested logical window fits. No system display setting was changed.

Evidence: `verification/output/history-fixed/report.json` and `restart-report.json`.

## 7. Regression tests

`test_history_focus_outline_preserves_card_contents` covers selected and unselected focus in all three themes (six cases). It compares the focused and unfocused rendered interiors pixel-for-pixel, including metadata text, while separately requiring a visible focus outline. All six cases failed against the original implementation and passed after the fix.

`test_history_focused_cards_survive_undo_refresh_and_navigation` performs two real 40-file apply/undo cycles, focuses History, checks the actual viewport paint after completion and repeated refresh, navigates away/back, switches entries, verifies 40 outcomes and correct Undo availability, and checks the widget count did not grow.

Focused result: **7 passed, 18 deselected in 4.22s**.

## 8. Full suite and static verification

Full existing suite with the seven added cases: **124 passed, 1 skipped in 166.81s (0:02:46)**. The unchanged skip is `tests/test_analysis.py:90`, requiring Windows Developer Mode or privileges to create symbolic links. No existing test was removed, weakened or newly skipped.

Compilation passed with `python -m compileall -q filepilot main.py tests verification`. All application, test and verification Python sources passed AST parsing. Source SHA-256 comparisons identify only `filepilot/ui/pages/history.py` and `tests/test_ui.py` as changed existing files in this task.

## 9. Scope preserved

Organization behavior, move/restore logic, empty-directory cleanup, SQLite provenance, duplicate detection, SHA-256, scanning, settings, workers, palette and other page designs are byte-for-byte unchanged from the pre-fix baseline. The production patch adds only one paint-state instruction and its comment. All mutations used temporary fixtures; the normal user database and manually verified working folder were not touched. Git was not initialized; no commit, push or installer was produced.
