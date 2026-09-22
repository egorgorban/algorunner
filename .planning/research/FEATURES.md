# Feature Research

**Domain:** AI-assisted algorithm/editorial generation (LeetCode-style problem solving assistants)
**Researched:** 2026-09-22
**Confidence:** MEDIUM

No direct competitor exists for AlgoRunner's exact shape (multi-agent pipeline that generates a bilingual-input/Russian-output editorial with dual-language verified code). The comparable set splits into two categories that must be reasoned about separately:

- **Human-curated editorial products** (LeetCode official editorials, NeetCode, AlgoExpert, HackerRank) — set the bar for *output structure and pedagogical quality*, but their code is written/reviewed by humans once and published statically; they do not re-verify code per user request.
- **AI code-generation/judge research systems** (CodeContests+, AutoCode, CodeHacker, and the "AI-assisted coding interview" product wave) — set the bar for *trustworthiness of LLM-generated solutions*, i.e. whether generated code should be tested before being presented as correct.

AlgoRunner sits at the intersection: it must match the first category's *presentation* bar and the second category's *verification* bar simultaneously. Findings below are grounded in web research (confidence noted per claim) plus well-established, long-standing product conventions (LeetCode/AlgoExpert page structure) that are stable enough to treat as high-certainty facts even though the sourcing tier is web search (MEDIUM).

## Findings by Research Question

### Q1 — Table-stakes editorial structure and quality bar

LeetCode's own editorial format (and the GitHub solution-repo ecosystem that mirrors it) uses a fixed skeleton per problem: problem restatement → one or more numbered **Approach** blocks, each containing **Intuition**, **Algorithm** (step-by-step), **Code**, and a **Complexity Analysis** subsection with explicit `Time: O(...)` / `Space: O(...)` *and a one-line justification of why* (not just the notation). [confidence: MEDIUM, websearch]

This matches AlgoRunner's confirmed pipeline output shape almost exactly (explanation + code + complexity per approach). The one gap: table-stakes complexity analysis is *justified*, not just stated — the Editorial Writer prompt needs to require a short "why" clause per complexity claim, not merely the Big-O string, or the output will read as thinner than the category norm.

### Q2 — Table-stakes vs differentiator for presenting multiple approaches

**Table stakes:** sequential ordering from brute-force to optimized, explicit approach labels ("Approach 1: Brute Force", "Approach 2: Optimized"), each approach fully self-contained (own explanation, code, complexity) so a reader can stop at any approach and still understand it. This is how LeetCode's official editorials and AlgoExpert both do it. [confidence: MEDIUM, websearch]

**Differentiator:** NeetCode's format doesn't just list approaches side by side — it *bridges* them: state the naive solution, explicitly name the bottleneck (e.g. "this re-scans the array for every element, causing O(n²)"), then show the specific insight that removes that bottleneck before presenting the optimized approach. Reviewers cite this narrative bridge — not the code itself — as the reason NeetCode is perceived as higher quality than terser official editorials. [confidence: MEDIUM, websearch] Codeforces editorials, by contrast, generally present only the one intended solution and treat brute-force/alternative approaches as secondary or comment-thread material — the "always show the naive approach in full" convention is a LeetCode/NeetCode-ecosystem norm, not a universal competitive-programming one. [confidence: LOW, websearch — thinner sourcing than the other two]

**Implication for AlgoRunner:** the Solution Strategist already produces brute-force + optimized (+ alternative) approaches — the missing piece is a Editorial Writer instruction to add a one-sentence bridge ("Approach 1 is correct but too slow because X; Approach 2 fixes this by Y") between consecutive approaches. This is a prompt-level change, not a new pipeline component — cheap to include in v1 as a differentiator.

### Q3 — Table-stakes for ambiguous/underspecified problem statements

Across current AI-assisted coding-interview products and guidance (Google/Meta AI-assisted interview formats, AI interview copilots), clarifying-question behavior is treated as a core *evaluated* skill: an AI assistant reads the problem, asks clarifying questions when requirements are ambiguous, and produces a plan before writing code. The explicit best-practice framing is "never silently assume — ask, or state assumptions and confirm edge cases/format before implementing," because a silently wrong assumption invalidates the whole attempt. [confidence: MEDIUM, websearch]

Two distinct table-stakes patterns exist in the wild, and they are **not interchangeable**:
1. **Interactive clarifying question** — synchronous back-and-forth (works in a live chat/interview UI where the tool can pause and wait for a reply).
2. **Stated assumptions** — the tool proceeds but explicitly documents what it assumed (works in any UX, including fire-and-forget/async).

**Architectural flag for AlgoRunner:** the confirmed pipeline says the Problem Analyzer "asks a clarifying question if underspecified," but AlgoRunner's delivery surface is an async task queue (submit → poll/WebSocket-stream → result), not a live chat. Pattern 1 requires a genuine mid-task pause-and-resume UX (new task state: `awaiting_clarification`, a way to submit an answer against a running task, and a resume path through the checkpointed LangGraph state) that is not yet in the confirmed requirements. Pattern 2 (stated assumptions, surfaced in the final editorial or in task status) fits the existing architecture with no new components. **This is a scoping decision the requirements-definition step needs to make explicitly**, not an oversight in this research — recommend defaulting to stated-assumptions-in-output for v1, with true interactive clarification flagged as a natural v1.x extension once the pause/resume plumbing exists anyway (it's a superset of the correction-loop resume capability already required).

### Q4 — Table-stakes for verifying a generated solution actually works

This is the one area where the two competitor categories give opposite signals, and the human-curated-editorial comparison is the wrong reference class. Static editorial sites (LeetCode, NeetCode, AlgoExpert) do not execute-and-verify code per request — their code is human-written and reviewed once, then published. If AlgoRunner were compared only to those, test generation + execution could look like a "nice differentiator."

But AlgoRunner is not human-curated — it is LLM-generated per request, and the correct reference class is AI code-generation/judge research systems. There, recent work (CodeContests+, AutoCode, CodeHacker, 2025-2026) converges on a **Generator → Validator → Checker** pattern as necessary infrastructure, not optional polish: generate diverse test cases (random, edge/corner, adversarial/stress), validate that they satisfy problem constraints, and check that the candidate solution's output is actually correct — because without this, LLM-generated "solutions" are frequently wrong or subtly buggy despite looking plausible. [confidence: MEDIUM, websearch] AutoCode reports ~98.7% judgment consistency only *because* of this closed-loop verification, underscoring that skipping it materially degrades trustworthiness.

**Conclusion: table-stakes, not nice-to-have**, given AlgoRunner's Core Value statement ("Correctness... matters more than explanation quality or speed"). This validates the already-confirmed pipeline (Test Generator + Python/Go Executor tools + Reviewer + bounded correction loop) as non-negotiable baseline architecture — it should not be considered a cuttable scope item under schedule pressure.

### Q5 — Baseline features present in comparable products but NOT in AlgoRunner's confirmed requirements

LeetCode's problem-page convention (and AlgoExpert's mirror of it) includes several elements that read as "expected" for a "LeetCode-style" output but are absent from AlgoRunner's current confirmed requirements list: **Difficulty Level**, **Topic/Technique Tags** (e.g. "Two Pointers", "Dynamic Programming", "Graph — BFS"), **Similar Problems** links, and (on some problems) a **Follow-up** prompt (e.g. "Can you solve it in O(1) extra space?"). [confidence: MEDIUM, websearch] AlgoExpert additionally structures every problem by difficulty (Easy/Medium/Hard/Very Hard) and category, and layers a 2-part video + in-browser execution/checking environment on top. [confidence: MEDIUM, websearch]

Of these, **difficulty rating**, **topic/technique tags**, and **explicit edge-case callouts** are cheap to add (see Table Stakes table below — they're near-free byproducts of information the pipeline already produces) and their absence would make output feel noticeably thinner than the genre norm. **Similar problems** and **video/visual explanations** require capabilities AlgoRunner does not have (a curated problem corpus; image/video generation) and should be treated as explicitly out of scope, not silently dropped — call this out to the user as a deliberate exclusion.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete relative to "LeetCode-style editorial" framing.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-approach structure: Intuition → Algorithm → Code → Complexity | LeetCode/AlgoExpert/NeetCode all use this skeleton; readers scan for it | LOW | Already implied by confirmed pipeline; ensure Editorial Writer prompt enforces the four-part structure per approach, not free-form prose |
| Complexity claims justified with a one-line "why," not just Big-O notation | Bare `O(n log n)` without justification reads as incomplete vs. genre norm | LOW | Prompt-level requirement on Editorial Writer / Reviewer's complexity check |
| Sequential approach ordering (brute-force → optimized → alternative) | Universal convention across LeetCode, NeetCode, AlgoExpert | LOW | Already implied by Solution Strategist's "brute-force + optimized" framing |
| Test-driven correctness verification before presenting a solution as final | Table stakes specifically for *LLM-generated* code (per CodeContests+/AutoCode/CodeHacker research); AlgoRunner's Core Value statement makes this the top priority | HIGH | Already the confirmed pipeline (Test Generator + Python/Go executors + Reviewer + correction loop) — do not cut this under schedule pressure |
| Explicit handling of ambiguity before solving (ask OR state assumptions) | Treated as an evaluated core skill in current AI-coding-interview tooling; silent wrong assumptions invalidate the whole output | MEDIUM | Confirmed pipeline has clarifying-question stage but the async delivery surface makes true interactive Q&A non-trivial — see Q3 flag; minimum viable version is "stated assumptions surfaced in output" |
| Difficulty rating (Easy/Medium/Hard) | Universal on LeetCode/AlgoExpert; used for expectation-setting before reading | LOW | Not in confirmed requirements — cheap: Problem Analyzer or Solution Strategist can emit this as a one-field classification |
| Topic/technique tags (e.g. "Two Pointers", "Sliding Window", "DP") | Universal on LeetCode/AlgoExpert; also aids the explanation itself ("this is a classic two-pointer problem") | LOW | Not in confirmed requirements — near-free: the algorithm/pattern name is already implicit in the Solution Strategist's approach description, just needs to be surfaced as structured metadata |
| Edge-case callouts surfaced in the article itself | Reviewer already evaluates edge cases internally; readers of an editorial expect to see "what about empty input / duplicates / single element" addressed explicitly, not just silently handled | LOW-MEDIUM | Requires threading Reviewer's edge-case findings through to the Editorial Writer's input, not just pass/fail |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable — and cheap relative to AlgoRunner's existing architecture.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Narrative bridge between approaches ("Approach 1 is correct but too slow because X; Approach 2 fixes this by Y") | This is specifically what separates NeetCode's perceived quality from terser official editorials — motivates *why* the optimization exists rather than presenting approaches as isolated silos | LOW | Prompt-level addition to Editorial Writer; no new pipeline component — high value/cost ratio, recommend including in v1 |
| Dual verified language output (Python + Go), both actually compiled/executed | No mainstream editorial product verifies multi-language code per request; AlgoExpert *offers* multiple languages but doesn't dynamically generate+verify them per query | Already committed | This is AlgoRunner's structural edge over static editorial sites — worth stating explicitly in product framing, not just an implementation detail |
| Russian-language output for an English-or-Russian-input problem | No mainstream English-first product (LeetCode, NeetCode, AlgoExpert, HackerRank) targets this localization niche for editorial-quality output | Already committed | Directly addresses an underserved audience segment; worth foregrounding in any positioning material |
| Follow-up variation prompt per problem (e.g. "what if input doesn't fit in memory?") | LeetCode surfaces this on some problems; signals depth beyond the immediate answer | LOW-MEDIUM | Can piggyback on the Solution Strategist's existing reasoning about the optimized approach's limits — v1.x candidate, not blocking v1 |
| Structured review-history transparency (why a correction loop iteration failed and what changed) | Neither LeetCode nor NeetCode show "attempt history" — this would be a novel trust-building UX surface unique to a multi-agent verification pipeline | MEDIUM | Data already exists in ReviewResult/correction loop; surfacing it in the web UI (not necessarily the Russian editorial itself) is a UI-layer decision, not a new agent |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems given AlgoRunner's confirmed constraints and current milestone scope.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| User-facing interactive code playground (edit-and-rerun generated code in-browser) | AlgoExpert offers this; feels like a natural extension of "we already execute code" | Requires exposing the Python/Go executor tools to arbitrary user-edited input over the web — directly collides with the explicitly deferred sandboxing/resource-limits work; unsafe to expose today's plain-subprocess executors to end users | Ship static, copy-able code blocks in v1; revisit an interactive playground only after sandboxing/resource limits (already tracked as a future milestone) land |
| Full multi-language support (AlgoExpert-style, 9 languages) | Mirrors the "richest" competitor and seems like an easy win once code generation exists | Multiplies Code Generator, Test Generator, and Executor-tool surface area per approach; conflicts with the fixed, product-owner-confirmed Python+Go scope | Stay at Python + Go for this milestone; treat additional languages as a distinct future milestone requiring its own executor tools |
| Live interactive clarifying-question chat (true synchronous back-and-forth) | Matches the highest-quality pattern seen in AI-interview-assistant products | Requires new task-state machinery (pause/await-input/resume) not in the confirmed requirements or architecture; risks scope creep into the async task-queue design | v1: Problem Analyzer states its assumptions in the output/status when input is ambiguous instead of blocking; true interactive clarification is a natural v1.x extension once correction-loop resume plumbing exists |
| "Similar problems" recommendations | Standard LeetCode/AlgoExpert feature, feels like it "completes" the editorial page | Requires a curated, tagged corpus of other problems to recommend against — AlgoRunner has no problem database or corpus; building one is a different product surface entirely | Tag the *current* problem's own topics/technique (cheap, already recommended as table stakes) but do not attempt cross-problem recommendations without a corpus |
| Empirical complexity verification (actually benchmarking generated code to confirm the claimed Big-O) | Feels like a natural companion to "verify the code actually works" | Explicitly out of scope per PROJECT.md — the product owner has already decided complexity is reviewed analytically only, not empirically | Keep Reviewer's complexity check analytical (LLM reasoning over the code), as already decided |
| Video or animated visual explanations | NeetCode's most-cited strength; visually explains algorithm state changes | Requires a video/diagram generation capability entirely absent from the current text-pipeline architecture — large scope addition, no confirmed requirement supports it | Rely on precise natural-language explanation + code; consider ASCII/inline diagrams as a much lower-cost partial substitute in a later milestone if ever pursued |

## Feature Dependencies

```
Difficulty rating ──derives from──> Problem Analyzer / Solution Strategist output
Topic/technique tags ──derives from──> Solution Strategist's approach naming (algorithm/pattern already identified)
Edge-case callouts in article ──requires──> Reviewer's edge-case findings threaded to Editorial Writer input
Narrative bridge between approaches ──requires──> Editorial Writer receiving all approaches together (already true) + prompt update
Follow-up variation prompt ──enhances──> Solution Strategist's optimized-approach reasoning

Interactive clarifying-question chat ──requires──> Task pause/await-input/resume state machinery
Interactive clarifying-question chat ──shares infrastructure with──> Correction-loop checkpoint/resume (LangGraph state already checkpointed)

Interactive code playground ──conflicts with──> deferred sandboxing/resource-limits scope
Full multi-language support ──conflicts with──> fixed Python+Go constraint
Similar-problems recommendations ──requires──> a problem corpus/database (does not exist)
```

### Dependency Notes

- **Difficulty rating and Topic tags derive from existing agent outputs:** neither requires a new agent — they're a small schema addition to Problem Analyzer or Solution Strategist's structured output (Pydantic model gains 1-2 fields), then surfaced by the Editorial Writer.
- **Edge-case callouts require plumbing, not a new agent:** the Reviewer already evaluates edge cases as part of its structured `ReviewResult`; the gap is ensuring that information reaches the Editorial Writer's input rather than being discarded once a solution passes review.
- **Interactive clarifying-question chat shares infrastructure with the correction loop:** both need "pause a running LangGraph execution, accept new input, resume from checkpoint." If the correction loop's checkpointing is built well in v1, true interactive clarification becomes a much smaller v1.x lift rather than a from-scratch feature — worth designing the checkpoint/resume mechanism generically now even if clarification stays non-interactive in v1.
- **Interactive code playground conflicts with deferred sandboxing:** do not schedule this until the sandboxing/resource-limits milestone is committed to, since exposing today's plain-subprocess Python/Go executors to arbitrary user input is a security regression, not a feature.

## MVP Definition

### Launch With (v1)

Minimum viable product — matches or cheaply extends the already-confirmed requirements list.

- [ ] Per-approach structure (Intuition/Algorithm/Code/Complexity) with justified complexity claims — already implied, just needs prompt-level enforcement
- [ ] Sequential brute-force → optimized approach ordering with a narrative bridge sentence between approaches — cheap differentiator, no new component
- [ ] Test generation + dual-language execution + Reviewer + bounded correction loop — already confirmed, validated here as non-negotiable table stakes (not a cut candidate)
- [ ] Stated-assumptions handling for ambiguous input (Problem Analyzer documents what it assumed when it doesn't have an interactive channel to ask) — minimum viable version of the clarifying-question requirement given the async architecture
- [ ] Difficulty rating field — cheap, high expectation-match
- [ ] Topic/technique tags field — cheap, high expectation-match
- [ ] Edge-case callouts surfaced in the final article — cheap given Reviewer already computes this

### Add After Validation (v1.x)

- [ ] True interactive clarifying-question flow (task pause/await-input/resume) — build once the correction loop's checkpoint/resume path proves out the underlying mechanism
- [ ] Follow-up variation prompt per problem — nice depth signal, not blocking
- [ ] Review-history transparency in the web UI (why a correction iteration failed) — UI-layer surfacing of data that already exists

### Future Consideration (v2+)

- [ ] Similar/related problems recommendations — blocked on a problem corpus that doesn't exist yet and isn't in scope
- [ ] Interactive code playground — blocked on the already-deferred sandboxing/resource-limits milestone
- [ ] Additional language support beyond Python/Go — a distinct future milestone with its own executor-tool work
- [ ] Video/animated visual explanations — large scope addition with no current architectural support

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|----------------------|----------|
| Justified complexity claims (prompt-level) | HIGH | LOW | P1 |
| Narrative bridge between approaches | HIGH | LOW | P1 |
| Test-gen + execution + review verification loop | HIGH | HIGH (already committed) | P1 |
| Stated-assumptions handling for ambiguity | HIGH | LOW-MEDIUM | P1 |
| Difficulty rating | MEDIUM | LOW | P1 |
| Topic/technique tags | MEDIUM | LOW | P1 |
| Edge-case callouts in article | MEDIUM | LOW-MEDIUM | P1 |
| Follow-up variation prompt | MEDIUM | LOW-MEDIUM | P2 |
| Review-history transparency (UI) | MEDIUM | MEDIUM | P2 |
| True interactive clarifying-question flow | MEDIUM | HIGH | P2 |
| Similar-problems recommendations | LOW-MEDIUM | HIGH (needs corpus) | P3 |
| Interactive code playground | MEDIUM | HIGH (blocked on sandboxing) | P3 |
| Additional language support | LOW | HIGH | P3 |
| Video/animated explanations | MEDIUM | VERY HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | LeetCode Editorial | NeetCode | AlgoExpert | AlgoRunner's Approach |
|---------|--------------------|----------|------------|------------------------|
| Multi-approach presentation | Approach 1/2/3, mostly siloed | Brute force → optimal with explicit narrative bridge | Single approach per video (occasionally two) | Adopt NeetCode's bridge pattern on top of the already-planned brute-force + optimized structure |
| Complexity analysis | Stated with brief justification | Explained conversationally as part of the walkthrough | Stated in video + written | Justified Big-O per approach, enforced at the Editorial Writer prompt level |
| Difficulty/tags | Yes (difficulty + topic tags) | Inherits LeetCode's tags via problem numbering | Yes (4-tier difficulty + 15 categories) | Add lightweight difficulty + tag fields (cheap, high expectation match) |
| Code verification before publishing | Human-reviewed once, not re-verified per view | Human-reviewed once | Human-reviewed once, plus a user-facing execution/check environment | LLM-generated per request, verified via generated tests + dual-language execution + Reviewer + correction loop — the one place AlgoRunner exceeds the human-curated category by necessity |
| Ambiguity handling | N/A — problems are pre-specified by the platform | N/A | N/A | Problem Analyzer surfaces a clarifying question or states assumptions — no direct precedent in this comparison set since none of these products take free-text problem input |
| Output language | English | English | English | Russian-only output regardless of input language — a differentiator with no precedent in this comparison set |

## Sources

- LeetCode editorial structure — websearch, MEDIUM confidence (cross-checked against multiple GitHub solution-repo mirrors and an actual editorial page: `leetcode.com/problems/next-permutation/editorial/`)
- NeetCode teaching style (brute-force → optimal narrative bridge) — websearch, MEDIUM confidence (corroborated across a review site and community discussion)
- AlgoExpert feature set (difficulty tiers, categories, 2-part video, 9 languages, execution environment) — websearch, MEDIUM confidence (corroborated across `algoexpert.io/product` and multiple independent review sites)
- Codeforces editorial conventions (single intended solution, brute-force less consistently presented) — websearch, LOW confidence (thinner sourcing, no single authoritative statement of editorial-writing convention)
- LeetCode problem-page metadata (difficulty, topic tags, similar problems, follow-up questions) — websearch, MEDIUM confidence
- AI-assisted coding interview clarifying-question norms (Google/Meta-style AI-assisted interviews, AI interview copilots) — websearch, MEDIUM confidence
- Competitive-programming/AI code-generation verification research: CodeContests+, AutoCode, CodeHacker (arXiv, 2025-2026) — websearch, MEDIUM confidence; used as the reference class for judging AlgoRunner's test-gen + execution + review loop as table stakes rather than a differentiator
- `.planning/PROJECT.md` — confirmed pipeline, constraints, and out-of-scope list (primary source for what is already committed vs. what this research adds)

---
*Feature research for: AI-assisted algorithm/editorial generation (AlgoRunner)*
*Researched: 2026-09-22*
