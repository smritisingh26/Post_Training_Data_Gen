"""
Replay bank for the stub backend.

These are hand-authored, realistic traces that let the WHOLE pipeline run
deterministically with no network. They are explicitly fixtures -- NOT
frontier-model output -- and are labeled as such. When you run --live with a
NIM key, real solver output replaces these.

Each key is referenced by a seed's stub_key or by a track's internal step.
Traces are written to demonstrate the TARGET behaviors and the failure modes the
harness must catch, so the gate can be shown admitting/rejecting correctly.
"""

# ---- Option 1: genuine, verifier-grounded self-correction (SURVIVES into response)
SOLVE_COUNT_DIV3OR5_FIRST = """STUB attempt.
I need to count integers in [1,1000] divisible by 3 or 5.
Multiples of 3: floor(1000/3) = 333. Multiples of 5: floor(1000/5) = 200.
So the count is 333 + 200 = 533.
FINAL: 533"""

SOLVE_COUNT_DIV3OR5_REPAIR = """533"""  # not used directly; verifier drives the branch

SOLVE_COUNT_DIV7OR11_FIRST = """STUB attempt.
Count n in [1,500] with 7|n or 11|n.
Multiples of 7: floor(500/7) = 71. Multiples of 11: floor(500/11) = 45.
So 71 + 45 = 116.
FINAL: 116"""

# The FINISHED option-1 trace, correction surfaced in the response:
OPT1_DIV3OR5_THOUGHT = """The task: count n in [1,1000] with 3|n or 5|n.
First pass: multiples of 3 = floor(1000/3) = 333; multiples of 5 = floor(1000/5) = 200.
I initially want to add them: 333 + 200 = 533.
Check against the counting principle: numbers divisible by BOTH 3 and 5 (i.e. by 15)
have been counted in each group, so 533 double-counts them.
Multiples of 15 = floor(1000/15) = 66. Correct count = 333 + 200 - 66 = 467."""

OPT1_DIV3OR5_RESPONSE = """We want every integer between 1 and 1000 that is divisible by 3 or by 5.

Start by counting each condition separately. The multiples of 3 up to 1000 number
floor(1000/3) = 333, and the multiples of 5 number floor(1000/5) = 200.

A first instinct is to add these: 333 + 200 = 533. But that step doesn't hold, and
here is exactly why: any number divisible by both 3 and 5 -- that is, divisible by
15 -- was counted once among the multiples of 3 and again among the multiples of 5.
Those numbers have been double-counted, so 533 is an overcount.

To fix it I apply inclusion-exclusion and subtract the multiples of 15, of which
there are floor(1000/15) = 66. The corrected count is

    333 + 200 - 66 = 467.

So there are 467 integers from 1 to 1000 divisible by 3 or 5."""

# ---- Option 1 counterpart problem
OPT1_DIV7OR11_THOUGHT = """Count n in [1,500] with 7|n or 11|n.
Multiples of 7 = floor(500/7) = 71; multiples of 11 = floor(500/11) = 45.
Adding gives 71 + 45 = 116, but multiples of 77 (=7*11) are double-counted.
Multiples of 77 = floor(500/77) = 6. Corrected: 71 + 45 - 6 = 110."""

OPT1_DIV7OR11_RESPONSE = """We count the integers from 1 to 500 divisible by 7 or by 11.

Separately, the multiples of 7 number floor(500/7) = 71 and the multiples of 11
number floor(500/11) = 45. Adding them gives 116 -- but that overcounts, because any
multiple of 77 = 7x11 falls in both lists and has been counted twice. There are
floor(500/77) = 6 such numbers, so by inclusion-exclusion the true count is

    71 + 45 - 6 = 110."""

# ---- Option 1: harder seed -- 4-set inclusion-exclusion
SOLVE_COUNT_DIV2_3_5_7_FIRST = """STUB attempt.
Count n in [1,2000] divisible by 2, 3, 5, or 7.
Singles: 1000 + 666 + 400 + 285 = 2351.
Pairwise overlaps: (2,3)=333, (2,5)=200, (2,7)=142, (3,5)=133, (3,7)=95, (5,7)=57, sum=960.
Subtracting the pairwise overlaps: 2351 - 960 = 1391.
FINAL: 1391"""

OPT1_DIV2_3_5_7_THOUGHT = """The task: count n in [1,2000] with 2|n or 3|n or 5|n or 7|n.
Singles sum to 2351; subtracting the six pairwise overlaps (960) gives 1391 -- but for
FOUR overlapping sets, inclusion-exclusion doesn't stop at pairs. I dropped the
correction terms: numbers divisible by a TRIPLE of {2,3,5,7} were subtracted twice by
the pairwise step and must be added back (triples sum to 160), and numbers divisible
by all FOUR (multiples of 210) were added back too many times and must be subtracted
once more (9 of them). Corrected: 2351 - 960 + 160 - 9 = 1542."""

OPT1_DIV2_3_5_7_RESPONSE = """We want every integer from 1 to 2000 divisible by 2, 3, 5, or 7.

Counting each divisor alone: multiples of 2 = 1000, of 3 = 666, of 5 = 400, of 7 = 285,
summing to 2351. Subtracting the six pairwise overlaps (2&3, 2&5, 2&7, 3&5, 3&7, 5&7),
which total 960, gives 1391.

That step doesn't finish the job, though: with four overlapping sets, inclusion-exclusion
needs the higher-order terms too. Numbers divisible by any TRIPLE of {2,3,5,7} were
subtracted twice during the pairwise step (once for each pair inside the triple) and so
must be added back -- there are 160 of them. And numbers divisible by all FOUR (multiples
of 2*3*5*7 = 210) were then over-corrected and must be subtracted once more -- there are 9
of those.

Putting it together: 2351 - 960 + 160 - 9 = 1542.

So there are 1542 integers from 1 to 2000 divisible by 2, 3, 5, or 7."""

# ---- Option 1: harder seed -- modular arithmetic over a negative-spanning range
SOLVE_COUNT_MOD7REM3_NEGRANGE_FIRST = """STUB attempt.
Count n in [-50,200] with n mod 7 == 3.
Starting from 0: 0,7,14,...,200 gives floor(200/7)+1 = 29 values with remainder 3 in [0,200].
FINAL: 29"""

OPT1_MOD7REM3_NEGRANGE_THOUGHT = """The task: count n in [-50,200] with n mod 7 == 3.
My first pass only counted the non-negative side (0..200), getting 29 -- but the range
starts at -50, and negative integers can satisfy n mod 7 == 3 too (using the convention
that n mod 7 is always in [0,6], e.g. -4 mod 7 == 3). Checking [-50,-1]: the values are
-47,-40,-33,-26,-19,-12,-5, which is 7 numbers. So the true count is 29 + 7 = 36."""

OPT1_MOD7REM3_NEGRANGE_RESPONSE = """We count integers from -50 to 200 (inclusive) that leave
remainder 3 when divided by 7.

Counting only the non-negative side first: the qualifying values start at 3 and step by 7 up
to 199, which is floor((200-3)/7) + 1 = 29 values.

Re-reading the problem, that 29 only covers part of the stated range: the range explicitly
starts at -50, and integers below 0 can also leave remainder 3 under the standard convention
that a remainder is always in [0,6] -- for example -4 mod 7 = 3, since -4 = -1*7 + 3. Checking
-50 up to -1 directly: the qualifying values are -47, -40, -33, -26, -19, -12, -5, which is
7 more numbers that the first pass omitted.

So the correct total is 29 + 7 = 36."""

# ---- Option 1: harder seed -- inclusion-exclusion with an extra exclusion clause
SOLVE_COUNT_DIV4OR6_NOT12_FIRST = """STUB attempt.
Count n in [1,300] divisible by 4 or 6, but not by 12.
Multiples of 4: floor(300/4) = 75. Multiples of 6: floor(300/6) = 50.
Multiples of both (12): floor(300/12) = 25.
By inclusion-exclusion, divisible by 4 or 6: 75 + 50 - 25 = 100.
FINAL: 100"""

OPT1_DIV4OR6_NOT12_THOUGHT = """The task: count n in [1,300] divisible by 4 or 6, but NOT by 12.
Multiples of 4 = 75, multiples of 6 = 50, multiples of both (i.e. of 12) = 25.
Inclusion-exclusion for "divisible by 4 or 6" alone gives 75 + 50 - 25 = 100 -- but the
problem adds a further condition, "but not by 12", which that 100 does not apply. Every
number divisible by both 4 and 6 is exactly a multiple of 12, and those are precisely what
must now be excluded. There are 25 of them, so the corrected count is 100 - 25 = 75."""

OPT1_DIV4OR6_NOT12_RESPONSE = """We count integers from 1 to 300 divisible by 4 or 6, but not by 12.

First, multiples of 4 number floor(300/4) = 75, and multiples of 6 number floor(300/6) = 50.
Numbers divisible by both 4 and 6 are exactly the multiples of 12, of which there are
floor(300/12) = 25. By inclusion-exclusion, "divisible by 4 or 6" totals 75 + 50 - 25 = 100.

That number answers "divisible by 4 or 6", but it doesn't hold as the final answer here --
the problem also requires excluding anything divisible by 12, and those 100 still include
every multiple of 12 (they're divisible by both 4 and 6, so they're already counted in the
100). Since there are 25 multiples of 12 in range, they must be removed: 100 - 25 = 75.

So there are 75 integers from 1 to 300 divisible by 4 or 6, but not by 12."""

# ---- Option 2: honest completion on an IMPOSSIBLE prompt (RH)
OPT2_RH_THOUGHT = """The prompt asks to 'prove RH for the first five zeros'. Verifying that the
first five nontrivial zeros lie on the critical line is a NUMERICAL fact (checkable via
the argument principle / rigorous zero isolation), but that is not a proof of the Riemann
Hypothesis -- RH is an open problem. I should establish what CAN be said rigorously and be
explicit that the general statement is unproven."""

OPT2_RH_RESPONSE = """It is important to separate two very different claims here.

The Riemann Hypothesis itself -- that every nontrivial zero of the zeta function has real
part 1/2 -- is an open problem. No proof is known, so I cannot prove it, not even "for the
first five zeros" in the sense of a genuine proof of the hypothesis.

What CAN be established rigorously is a numerical statement: the first five nontrivial zeros
can be isolated and shown to lie on the critical line using the argument principle together
with rigorous (interval-arithmetic) evaluation of the Riemann-Siegel Z function, which changes
sign at each of them, and the Riemann-von Mangoldt formula, which fixes how many zeros lie
below a given height. That is a verification for a finite range, not a proof of RH.

So the honest answer is: RH remains unproven; the strongest correct claim available for the
first five zeros is a numerical verification that they lie on the line, which does not
generalize to a proof of the hypothesis."""

# ---- Option 2: honest completion on 3-body (impossible)
OPT2_3BODY_THOUGHT = """General n-body (n>=3) has no closed-form solution. The honest, useful answer
derives the restricted problem's conserved quantity (Jacobi integral) and the Lagrange points,
and states plainly that no closed-form general trajectory exists."""

OPT2_3BODY_RESPONSE = """There is no closed-form general solution for the motion in a three-body
gravitational system, and this is a fundamental fact rather than a gap in the derivation below.

What can be derived exactly is the structure of the restricted three-body problem. Writing the
equations of motion in a rotating frame yields the Jacobi integral, an exact conserved quantity,
and the five Lagrange equilibrium points (three collinear, two triangular) where the effective
force vanishes. These are genuine exact results.

But the trajectory of the third body has no closed-form expression -- the general problem is
non-integrable. So the exact content here is the Jacobi constant and the equilibrium structure;
a closed-form solution of the motion does not exist."""

# ---- Option 2: ill-posed
OPT2_ILLPOSED_RESPONSE = """This can't be answered as stated. "Find the area of the triangle" gives
no side lengths, angles, coordinates, or figure, and the area of a triangle is not determined
without at least enough of that information (for example, a base and corresponding height, two
sides and the included angle, or three vertex coordinates). If you can supply any of those, I can
compute the area directly."""

OPT2_ILLPOSED_THOUGHT = """No numeric data given -- underspecified. State what's missing and what would
suffice, rather than inventing numbers."""

# ---- Option 3: THEATRICAL negative (fabricated error caught for show) -- a HARD NEGATIVE
OPT3_THEATRICAL_THOUGHT = """I'll add a dramatic 'catch' to look self-correcting."""
OPT3_THEATRICAL_RESPONSE = """We count integers in [1,1000] divisible by 3 or 5.
Multiples of 3: 333. Multiples of 5: 200. Multiples of 15: 66. So 333 + 200 - 66 = 467.
Wait -- actually, let me reconsider whether that's right. Hmm, yes, on reflection it is
correct. Actually I should double check... no, it's fine. The answer is 467."""
# ^ Two "actually/wait/reconsider" markers, but NO grounded error (nothing was ever wrong).

# ---- triage default (stub judge)
TRIAGE_DEFAULT = '{"problem_class": "solvable", "verifiable": true, "obstruction": null}'
TRIAGE_NAVIER = '{"problem_class": "solvable", "verifiable": false, "obstruction": null}'
TRIAGE_ILLPOSED = '{"problem_class": "ill_posed", "verifiable": false, "obstruction": "No side lengths, angles, or coordinates are given, so the area is not determined."}'


BANK = {
    "__default__": "[stub] echo",
    "solve_count_div3or5": SOLVE_COUNT_DIV3OR5_FIRST,
    "solve_count_div7or11": SOLVE_COUNT_DIV7OR11_FIRST,
    "opt1_count_div3or5_thought": OPT1_DIV3OR5_THOUGHT,
    "opt1_count_div3or5_response": OPT1_DIV3OR5_RESPONSE,
    "opt1_count_div7or11_thought": OPT1_DIV7OR11_THOUGHT,
    "opt1_count_div7or11_response": OPT1_DIV7OR11_RESPONSE,
    "solve_count_div2_3_5_7": SOLVE_COUNT_DIV2_3_5_7_FIRST,
    "opt1_count_div2_3_5_7_thought": OPT1_DIV2_3_5_7_THOUGHT,
    "opt1_count_div2_3_5_7_response": OPT1_DIV2_3_5_7_RESPONSE,
    "solve_count_mod7rem3_negrange": SOLVE_COUNT_MOD7REM3_NEGRANGE_FIRST,
    "opt1_count_mod7rem3_negrange_thought": OPT1_MOD7REM3_NEGRANGE_THOUGHT,
    "opt1_count_mod7rem3_negrange_response": OPT1_MOD7REM3_NEGRANGE_RESPONSE,
    "solve_count_div4or6_not12": SOLVE_COUNT_DIV4OR6_NOT12_FIRST,
    "opt1_count_div4or6_not12_thought": OPT1_DIV4OR6_NOT12_THOUGHT,
    "opt1_count_div4or6_not12_response": OPT1_DIV4OR6_NOT12_RESPONSE,
    "honest_rh_thought": OPT2_RH_THOUGHT,
    "honest_rh": OPT2_RH_RESPONSE,
    "honest_3body_thought": OPT2_3BODY_THOUGHT,
    "honest_3body": OPT2_3BODY_RESPONSE,
    "honest_illposed": OPT2_ILLPOSED_RESPONSE,
    "honest_illposed_thought": OPT2_ILLPOSED_THOUGHT,
    "theatrical_thought": OPT3_THEATRICAL_THOUGHT,
    "theatrical_response": OPT3_THEATRICAL_RESPONSE,
    "triage_default": TRIAGE_DEFAULT,
    "triage_navier": TRIAGE_NAVIER,
    "triage_illposed": TRIAGE_ILLPOSED,
}
