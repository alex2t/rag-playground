# Implementation issues

Log of the problems met while building the project, what caused them and what was learned. Details and evidence for each are in `fix.md`; decisions are in `decision.md`.

## 1. Development machine
| Problem | Cause | Resolution |
|---|---|---|
| `uv add` failed: `invalid peer certificate: UnknownIssuer` | Norton intercepts TLS; its root certificate is not in uv's bundle | `uv ... --system-certs` |
| Python died with `OPENSSL_Uplink: no OPENSSL_Applink` | Norton sets `SSLKEYLOGFILE` to a named pipe that OpenSSL cannot open | Run Python with `env -u SSLKEYLOGFILE`; the user's environment is left unchanged |
| Live tests failed: `CERTIFICATE_VERIFY_FAILED` | httpx trusts `certifi`, which lacks the Norton root | `SSL_CERT_FILE=<Norton pem>` per command |
| `uv add httpx2` blocked by the permission classifier | Tool policy | The user ran it; rule: give the user the command rather than change their environment |

## 2. Creating the data (the hardest part)

### World model, version 1 (`Harrowgate Cloud Partners`)
- An employee was on a project before being hired. Only references and duplicates were checked. **Fix:** timeline checks.
- Antigravity found 9 cross-entity contradictions: a "second" pilot that was actually the first, a milestone with no matching client, ticket volumes 4x over a service's cap, a missing Revenue Cloud service, false superlatives, practices launched after their leads were hired, and firm-wide totals (100 projects) far above the data (43).
- **Root cause:** the generator wrote free-text claims about other entities, and nothing compared them with the structured data. One broad LLM audit caught only about half of them.
- **Fix:** stricter generator rules, facts computed in code (headcounts, client start years, date order), a claim-word lint (first, only, most, total...), and a 3-pass audit (timelines, numbers, cross-references). The world was regenerated.

### World model, version 2 (`Brightharbor Cloud Partners`)
- A leftover "..." from the generator rewriting a sentence; a relative claim ("nearly three years after...") that was wrong; a certification bonus policy with no tier for 3 employees' certifications.
- **Fix:** an ellipsis check, a rule that every held certification has a tier, and hand edits.

### Documents, first attempt
- 5 sample documents contained 65 invented claims (padding to reach length targets).
- **Fix:** facts-only writing, no length targets, small documents grouped (directories per office).
- Then the documents were too short for the chunk-size sweep. **Fix:** the world was enriched (bios, service scope, project objectives and metrics, runbook steps and known issues): T33.

### Enriched world (`Larkspur Cloud Partners`)
- Generation was cut off: the model used 26k of 32k tokens reasoning. **Fix:** a larger output limit.
- The claim-word lint flagged ordinary Salesforce terms ("record type"). **Fix:** narrower pattern, plus a reviewed allowlist.
- The audit found 13 cross-reference issues (a 120/120 pass requirement no project met, policy vs runbook order, an ambiguous runbook reference). Fixed by hand; re-audit 0.
- Antigravity's review: a checker false positive on years, facts stated 3 times in directories, two bios claiming work the data did not show, "entries/rows" vs "records". Fixed; other items checked and recorded as not defects.

### Tests, version 1 (250 tests)
Antigravity's review confirmed 5 of 6 findings:
- 4 two-document questions answerable from one document (the question gave away a fact).
- Pair selection bug: all 19 client comparisons involved the same 2 clients; client-service pairs used only each client's first project.
- The same facts tested many times, across dev and held-out (runbook owners asked 22 times).
- Repeated templates: 35 of 37 temporal questions were single-date lookups.
- Keywords were document labels, not answer values (21 tests had no keyword in the answer).

**Fix:** a full regeneration with stricter rules: no facts in questions; two-document answers must combine a value from each document; a verifier check that fewer documents do not suffice; keywords that are answer values; balanced pairs; 2 questions per category per document; selection rules for variety and duplicate facts.

### Tests, version 2
- The first two-document prompt produced two unrelated facts joined with "and". Fixed in the prompt after a sample run.
- Supply was short for `temporal` and `multi_doc` under the 40% variety cap. Two new pair relations and targeted top-ups were added.
- The first duplicate-fact rule ("shares any answer value") allowed only 223 of 250 tests, because dates are shared by three categories. It also treated different questions as duplicates. Replaced, by user decision, with the whole-answer rule: a test is a duplicate only if another test fully covers it. All 250 tests, all rules kept.

### Tests, version 2: Antigravity's re-review (fixed 2026-10-27, option B)
- 2 `multi_doc` tests compute years from a bare year ("Client since: 2015") and a full date, so the answer depends on the counting convention.
- Some facts are still tested twice, including across dev and held-out (for example, a project's duration in both `multi_doc` and `temporal`): the whole-answer rule misses pairs where each test has a value the other lacks.
- 21 of 38 `multi_doc` questions follow one template ("how long had X been at the firm when...").
- The verifier wrongly rejected 2 valid questions (it invented a fact). This is harmless to the data, but a reminder that the verifier is fallible.
- Keywords do not contain computed answers: by design, since keywords measure retrieval only, but this was not explained in the public document.
- **Fix (B, user choice):** a year/date code check (13 verified candidates rejected), a stricter same-fact rule, and categories picked scarcest first. $0, no API calls.
- **The simulated 246 was wrong:** it assumed the 40% cap stayed at 15 (computed from the old quota of 38). With the cap at 40% of the new quota, `multi_doc` filled only 34 of 36. Keeping 15 would mean 41.7%, so it was put to the user, who chose to keep the rule strict: `multi_doc` 30, 240 tests (192 dev / 48 held-out). The held-out size is now a fifth of the tests.
- **Remaining limitations:** 16 dev/held-out pairs share one of two values; 12 of 30 `multi_doc` follow the tenure template; 2 duration tests list one of two dates in keywords.

### Tests, version 2: Antigravity's final check (2026-10-27)
- Verdict "fit to commit", with 3 minor notes, all confirmed: one fact tested twice because a keyword had extra words ("85.0% pass rate" vs "85.0%"); one months-and-days answer that depends on the counting convention (23 or 24 days); the year/date check matched only at the start of the question.
- Fixed at the root by user decision (the rule says gold answers must be unambiguous). 19 tests replaced, still 240; a short follow-up check covers only the replaced tests.

## 3. Cost and API limits
- **OpenRouter 402**: "would exceed your available credits given your current in-flight requests". OpenRouter reserves the worst-case cost of each running request (full KB input + 64k output tokens, about $0.72 for the verifier), so 5 in parallel needed about $3.60 of headroom.
- **OpenRouter 403**: the API key had its own total limit ($20), separate from the account balance. Adding credit did not help; raising the key limit did.
- **About $2.28 lost**: the verify and top-up stages saved results only at the end, so batches finished before a failure were paid for and discarded. Both now save each call as it returns.
- **Total dataset spend on the key: about $26.9** (world models and audits about $4.3, documents about $1.4, tests v1 about $4.9, tests v2 about $14, lost about $2.3).

## 4. Mistakes in how the work was done
- **Cost estimates were too low** several times ($6-8, then $10, against $11 for tests v2). The verifier sends the whole KB with every call, and the pool doubled.
- **Wrong advice on credits**: the key's $20 limit was visible in an earlier check, but the user was asked to add credit instead of raising the limit.
- **A wrong feasibility claim**: the 45% cap was presented as reaching 38 `multi_doc` tests without simulating the full selection. It reached only 225 tests in total, and the user approved an option that did not work. Lesson: simulate every option end to end before presenting it.
- **The 40% cap was set without checking it was feasible** for every category.
- **A shell editing bug repeated** 5 times: inline Python edit scripts turned `\n` into real newlines (and once `\b` into a backspace) and broke files. Lesson: use the editor for any edit that contains escapes.
- **Line endings changed by edit scripts**: Python `write_text` on Windows wrote CRLF into LF files, and `sed -i` did the reverse. Caught in the diff and restored. Lesson: edit with the editor, or write bytes in the file's own line ending.
- **Unclear questions to the user**: options used ids and terms (T30, `multi_doc`, 40% cap) without explaining them. Now a rule in `CLAUDE.md`: present every fact needed to decide.

## 5. What worked
- The world model first: every fact was checkable, and every contradiction was fixable at the source.
- Code checks before LLM checks: cheap, exact and repeatable. The LLM audit then found what code could not.
- An independent reviewer (Antigravity) at each checkpoint found real defects every round.
- Each test rule is now enforced by a test on the committed data, so it cannot silently regress.

## 6. Step 4: the computer froze twice (2026-10-27)
**Where we were.** Step 3 (chunk sets) was committed. Step 4 builds the two retrieval stacks from the same chunk set: Stack A is OpenAI's hosted vector store, and Stack B is our own: the open `nomic-embed-text-v1.5` embedding model, run locally on the CPU with fastembed, plus Qdrant. Stack A had just been probed on the real knowledge base (51 chunks, 12 questions, about half a cent).

**What happened.** Claude then ran the same kind of probe on Stack B: embed the 51 chunks with nomic. Nothing came back for 27 minutes, and the whole PC froze. In a new session, Claude wrote the Stack B tests and ran them. The PC froze again at the same point.

**The first guess was wrong.** Docker was not running, so it looked as if Qdrant was struggling locally. The session logs showed otherwise: the tests use Qdrant's in-memory mode (no server, no Docker), which holds a few hundred vectors. Both freezes started at the same call: embedding the whole chunk set.

**Root cause, proven by measurement.** The embedding library processes 256 texts per batch by default, so all 51 chunks went through the model at once. Each chunk is long (up to about 1,100 tokens), and a transformer's memory grows with the square of the input length. Measured on small batches: 1.1 GB for the model plus about 265 MB per chunk. The full batch needed 14-15 GB on an 8 GB laptop, so Windows swapped to disk until it stopped responding.

**Fix.** Batches of 4 chunks: peak memory 2 GB, the whole set embedded in 77 seconds, and the vectors identical to one-at-a-time embedding. One line of code; all 122 tests pass.

**Lessons.**
- A library's default (batch size) was tuned for short sentences, not for 1,000-token chunks. Defaults are assumptions; check them against your data.
- Prove the cause before fixing: the obvious suspect (Qdrant without Docker) was innocent.
- Measure on a tiny input first, then extrapolate, before running anything heavy on a small machine.
- Production note: on the VPS the same batch setting bounds the indexing job's memory, which matters next to Qdrant and the app on one server.

## 7. Step 4: what does "OpenAI vector search" actually do? (2026-10-27)
**Where we were.** Step 4, part 1 was committed: both stacks can index the same 51 baseline chunks. Antigravity reviewed it and found 8 issues. The most important one was about fairness: when Stack A searched with no ranking options, OpenAI used its own defaults, and we had never written down what those are.

**What we found, by testing live (about one cent).**
- OpenAI's search by default is not plain vector search. It fuses a semantic list and a keyword list (the scores are exactly the reciprocal-rank-fusion formula, 2/61), then applies an undocumented ranking model on top.
- That built-in ranker is strong: with it on, the right document was first for all 12 test questions. It also overrides any hybrid weights you set.
- Switched to "semantic only, ranker off", OpenAI found the right document for only 7 of 12 questions, while our self-hosted nomic model found all 12. That gap is suspicious, not a conclusion: we do not yet know what that mode really computes.

**Why it matters.** If Stack A ran with OpenAI's defaults, it would have a hidden ranker and keyword search that Stack B does not have, and a "hosted beats self-hosted" result would be partly an artifact of the defaults. An evaluation expert would ask exactly this.

**Decision (user).** Nothing is set by default. The dashboard user picks Stack A, Stack B or both, and chooses every setting, including OpenAI's ranker, the hybrid weights and the score threshold. Every run records them, and results with OpenAI's ranker on are labelled.

**Lessons.**
- A vendor's default is a design choice made for you. Find it, measure it and make it explicit before comparing systems.
- An undocumented parameter (`ranker: "none"`, hybrid weights) can be proven by its effect: the scores matched a known formula exactly.
- A surprising result is a question, not a finding: the weak "semantic only" score is recorded as open until a direct embedding check explains it.

**Follow-up: the suspicious score explained (half a cent).** We embedded the same chunks and questions directly with OpenAI's own embedding models and ranked them by plain cosine similarity: 12 of 12, first place every time. So OpenAI's embeddings are fine; the vector store's "semantic only, ranker off" mode is simply not plain vector search, and OpenAI does not document what it does. Lesson: when a hosted service gives a strange number, rebuild the simple version yourself and compare.

**Follow-up: a test that proved nothing.** Antigravity also flagged our hybrid-search test: it checked that hybrid search finds a made-up error code, but never checked that plain vector search fails. Measured: plain vector search found it first too, so the test proved nothing about keyword matching. The new test uses near-miss codes (QX7Y-4417 next to QX7Z-4471) in sentences that sound more relevant: vector search ranks the exact code last, hybrid lifts it to second. Lesson: a test of "B helps" must first show that "without B" fails.

## 8. Step 5: the judge that peeked at the answer key (2026-10-27)
**Where we were.** Step 5 builds the scoring. The LLM judge grades every answer from 1 to 5 on accuracy, completeness, relevance and faithfulness. Faithfulness exists to catch the "lucky guess": an answer that happens to be right although the documents the system retrieved never said it.

**What happened.** Antigravity suspected the judge could be swayed by the reference answer, so we added a live test for exactly that: the right price, given with a retrieved page that never mentions the price. The judge gave faithfulness 5, and its own explanation admitted the context did not contain the price, "but the answer aligns fully with the reference answer". An explicit instruction not to do this had been added just before; the small judge model ignored it.

**Fix.** The judge now grades faithfulness in a separate request that never contains the reference answer: it cannot be swayed by what it never sees. This is how established RAG evaluation tools measure faithfulness. Bonus: the documents are now sent only to that request, so the cost stays about the same.

**A second failure that was the test's fault.** Another test expected faithfulness of 2 or less for "right price plus an invented discount". The judge gave 3, which is exactly what our own scale says for "main claim supported, an extra claim invented". The test was changed to "below 4" (the pass mark), openly and by the user's decision, not quietly to make it pass.

**Lessons.**
- An instruction is not a guarantee. If a model must not use some information, do not give it that information.
- Write the test for the failure you fear: this one was found only because a test was designed to catch it.
- When a test fails, first ask whether the code or the test is wrong, and say which.

## 9. Step 6: an "immutable" prompt that could still be overwritten (2026-10-28)
**Where we were.** Step 6 starts the answer pipeline. Every run must record which system prompt it used, so saved prompt versions are meant to be permanent: the database itself refuses to change or delete them.

**What happened.** Antigravity found a back door: SQLite's `REPLACE` command deletes the old row and inserts a new one without running the "no delete" rule. One line of SQL silently rewrote a saved version. Reproduced: it did. It also showed that a blank name or a blank prompt could be saved forever.

**The reviewer's fix was not the root fix.** Antigravity proposed a connection setting (`recursive_triggers`). That setting only lasts for one connection, so anyone opening the database file another way would still get through. Instead, a rule stored inside the database file refuses any insert that lands on an existing version, whoever opens it. A new test then caught a second gap: SQLite's `trim()` removes only spaces, so a prompt made of newlines still counted as "not blank".

**Lessons.**
- "Immutable" is a claim to test against every way of writing, not only the ones our code uses.
- Check a reviewer's fix as carefully as its finding: put the protection where it cannot be bypassed.

## 10. Step 6: a run that could answer the wrong questions (2026-10-28)
**Where we were.** Step 6 joins the parts into one pipeline: retrieve, rerank, answer, judge, store. A run is created first, with its settings, then its questions are answered one by one.

**What happened.** The reviewer (Gemini 3.8) noticed that the run was told *how many* questions to expect, but the list itself was handed over separately. Reproduced: give it fewer questions and it said "done" at half way. Worse, and not in the review: give it ten *other* questions and it said "done" at 100%, with results for questions it never declared. The reviewer's fix (check the count) would have let that through. Runs are compared question by question, so one wrong run would quietly spoil every comparison it is part of.

**Fix.** The run now stores the exact list of questions when it is created, and answers only that list; the database refuses a result for any other question. There is no longer a way to hand it the wrong list.

**Also.** The same reviewer called the tests "robust". Claude broke the code on purpose in eight ways: two breaks went unnoticed. A run could be labelled "temperature controlled" even when the judge or reranker ignores temperature. Fixing the test exposed one more trap: the reranker and the cheapest answer model are the same model, so the first new test could not tell them apart.

**Lessons.**
- Do not trust a count where you can store the list itself.
- "The tests pass" is not "the tests work": break the code on purpose and see whether they notice.
- Check a reviewer's verdict as carefully as its findings.

## 11. Step 6: running a finished run again broke it (2026-10-29)
**Where we were.** Re-checking the fix from section 10 with the reviewer (Gemini 3.8). It confirmed the fix, and tried its own deliberate breaks.

**What happened.** Two of its breaks went unnoticed by the tests. The serious one: starting a run that had already finished made it try again, crash on its own earlier results, and relabel a complete, valid run as "failed". A good run would then drop out of every comparison. Also, a run could be labelled "done" with questions still missing, and finishing a run that does not exist did nothing instead of raising an error.

**The reviewer's fix was too narrow.** It suggested a check at the start of the run function. That protects one caller. Instead, the database now holds the rules: a finished run is final (no new results, no status change), and "done" is only accepted when every question has a result.

**One existing test was wrong.** It marked a run "done" with none of its ten answers stored, so it had been written around the bug. It was corrected, and this was reported rather than done quietly.

**Lessons.**
- Rules about a record's life cycle (running, done, failed) belong where every path must pass: the database.
- A test can encode a bug. When the code is fixed and a test breaks, ask which one was wrong.

## 12. Step 6: "final" only on the paths we had thought of (2026-10-29)
**Where we were.** The reviewer (Gemini 3.8) re-checked the fix from section 11.

**What happened.** The fix held for our own code. But the reviewer showed that plain SQL, typed in any database tool, could still edit a finished run's settings and its stored answers and scores. Claude reproduced that, and found more: a run could be deleted, created already "done" with no answers, or have its settings changed while running. A run is the evidence behind every score in the report; if it can be edited silently, nobody can be sure a result is the one the system produced.

**Fix.** The database now keeps runs and results exactly as written. A run starts as "running", its settings never change, it finishes once, and nothing is deleted or replaced. The reviewer's suggestion covered only finished runs; the fix covers every way of writing.

**A trap found while testing the fix.** The rule "the run id cannot change" did not fire when the id was changed through SQLite's hidden alias for it (`rowid`), so finishing a run could also renumber it. Each rule was then removed on purpose, one at a time, to prove a test notices.

**Lessons.**
- Section 9's lesson again: "final" must hold for every way of writing, not just the one that caused the last bug.
- Database rules have their own blind spots; test them by attacking them, not by reading them.

## 13. Step 6: the first real run, and a setting that quietly broke one stack (2026-10-29)
**Where we were.** The first paid run: 10 questions on each stack with the baseline settings, to check the cost estimate.

**What happened.** The run worked, but two things were wrong. The estimate was 64% too high. And the OpenAI stack refused 8 of 10 questions, while the self-hosted stack answered almost all of them.

**Why the OpenAI stack failed.** To make both stacks "look the same", its "hybrid off" switch had been mapped to an OpenAI search mode that an earlier probe had already flagged as strange. In the real run it found the right document for 2 of 9 questions. The decision was to stop forcing the two stacks into one shape: each stack runs independently, with its own settings, and the OpenAI baseline now uses OpenAI's own default search.

**Why the estimate was high.** Splitting it into parts showed the counted part (what the models read) was right within a few percent. The guessed part, how long the answers and grades would be, was five times too long. The guesses were replaced by the measured lengths, and the check is repeated on ten *different* questions, so the estimate is not checked on the data it was fitted to.

**Also decided.** The system prompt became a ladder step (S6), so the configuration shown in the live demo includes the best prompt, not only the default one.

**Lessons.**
- A warning in your notes is not the same as a fix: the strange OpenAI mode was known, and still chosen later for consistency.
- Do not force two different products into one menu; compare each at its own best and say how it was set.
- When a number is off, split it into the part you measured and the part you guessed.

## 14. Step 6: a reviewer that was confidently wrong (2026-10-29)
**Where we were.** Building the background job runner and the API that starts a run, each checked by the reviewer (Gemini 3.8).

**What happened.** The reviewer approved the job runner with zero findings. But its report said the database runs in a mode that lets readers and writers work at the same time (it does not; Claude checked), and it named five tests as proof that do not exist in the code. Its verdict happened to be right, but part of the reasoning behind it was invented.

**What was done.** Every claim was checked against the code before anything was accepted. The real question it skipped (can the dashboard's progress check be blocked while a result is written?) was answered by Claude: briefly, yes, and a one-line setting would remove it; that is now an open question for the user.

**Lessons.**
- A clean verdict is not evidence; the claims under it are. Check the facts a review rests on, not only its conclusion.
- Names a reviewer cites (tests, settings, files) are the cheapest thing to verify, and the first thing to check.

## 15. Steps 6-7: tests that passed for the wrong reason (2026-10-30)
**Where we were.** Finishing Step 6 (database locking, best-run selection) and building Step 7 (LLM enrichment).

**What happened.** Several new tests looked fine and proved nothing. The test for the database lock passed even without the fix, because it held a weaker lock than a real save does. In the best-run tests, the "never compete" checks passed only because a mislabelled test question had emptied the list of runs, so every run was being excluded. Later, three breaks looked caught, but one test was already failing on its own because a chunk in the test data was one character short.

**First guess.** A green test means the behaviour works. It did not.

**What was done.** Each test was first seen failing, and each rule was then broken on purpose to confirm a test notices. The breaks also found gaps: a sample that was not random at all, and an 80% target that could have used the wrong figure. Writing tests only after the code gave no such first failure, so those relied entirely on the deliberate breaks.

**The half-written line.** Enrichment saves each chunk as soon as it is paid for, to make a stopped build safe. Nobody had tried a stop in the middle of a save: it left half a line, and every later build crashed until someone edited the file by hand. Saves now replace the whole file in one step, so half a line cannot appear. The reviewer's suggestion, skipping a damaged line, would have hidden real damage.

**Lessons.**
- Before trusting a test, watch it fail for the right reason.
- A deliberate break only counts if the suite passes without it.
- Test the stop in the middle of an action, not only between actions.
- Fix what causes bad data, rather than teaching the code to step around it.

## 16. Step 8: a fair-looking sample that would have missed the point (2026-10-30)
**What we were doing:** before trusting the LLM judge, the user grades 30 of its answers. The rule, chosen before any full run, was 3 answers for each score from 1 to 5, so the many good answers would not drown out the weak ones.

**What went wrong:** the first two full runs showed the judge uses only 1, 3 and 5, and about 82% of answers get a 5. The rule filled the empty scores from their neighbours, which pushed the sample towards weak answers: only 7 of the 30 would have been 5s. The check would have said little about the score nearly every answer receives. Nothing failed, and every test passed, because the rule did exactly what it said.

**How it was caught:** by reading the real score counts before the sample was drawn, because the sample locks the first time grading opens.

**The fix (user decision):** split the 15 answers per stack equally over the scores the judge really used, giving 5, 5 and 5 on both stacks. No grade existed yet, so the change cannot favour the result, and the report will say that it happened.

**Lesson:** a rule designed before seeing the data is a guess about the data. Look at the real distribution before locking anything that depends on it. A judge that never uses two of its five scores is also a finding in its own right.

**A second catch (2026-10-31):** the review of the new rule was asked which questions fell in both samples, and its report printed one, with the judge's scores. Grading is blind, and that question would have been the only one shown twice, so the grader would have known the judge's verdict on two answers. The request itself caused the leak. The seed was changed before any grade, without looking at the new picks, and later checks print only counts. The same review pointed out that one overall figure can hide a judge that is right on one side only, so the report now also shows agreement separately for the judge's passes and fails.

**Lesson:** when work depends on someone not seeing something, the checks need the same care as the work: a reviewer's report is also something the grader reads.

**The result (2026-10-31):** the user graded all 30 answers blind and agreed with the judge on 24, exactly the 80% target. It passes with no margin: the true figure could be anywhere from 63% to 90%. Reading the 6 disagreements taught more than the number. The judge can give a half answer full marks for accuracy, while its completeness score notices, and it scored the same kind of slip differently on different answers. So accuracy is not read alone on multi-part questions.
