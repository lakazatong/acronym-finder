from typing import TypeAlias

Score: TypeAlias = tuple[int, int, int]

VOWELS = set("aeiouy")

OK_VOWEL_PAIRS = {
    "ai",
    "au",
    "ay",
    "ea",
    "ee",
    "ei",
    "ey",
    "ia",
    "ie",
    "io",
    "oa",
    "oi",
    "oo",
    "ou",
    "oy",
    "ua",
    "ue",
    "ui",
}

OK_STARTS = {
    "bl",
    "br",
    "cl",
    "cr",
    "dr",
    "fl",
    "fr",
    "gl",
    "gr",
    "pl",
    "pr",
    "sc",
    "sk",
    "sl",
    "sm",
    "sn",
    "sp",
    "st",
    "sw",
    "tr",
    "tw",
    "ch",
    "sh",
    "th",
    "wh",
    "ph",
}

OK_CLUSTERS = {  # consonant pairs allowed in the middle / at the end
    "bl",
    "br",
    "ck",
    "cl",
    "cr",
    "ct",
    "dr",
    "ft",
    "gl",
    "gr",
    "ld",
    "lf",
    "lk",
    "lm",
    "lp",
    "ls",
    "lt",
    "mp",
    "nc",
    "nd",
    "ng",
    "nk",
    "ns",
    "nt",
    "nx",
    "pl",
    "pr",
    "pt",
    "rb",
    "rd",
    "rk",
    "rl",
    "rm",
    "rn",
    "rp",
    "rs",
    "rt",
    "sc",
    "sk",
    "sl",
    "sm",
    "sp",
    "st",
    "tr",
    "xt",
    "ll",
    "ss",
    "tt",
    "nn",
    "mm",
    "pp",
    "ff",
    "dd",
    "gg",
    "zz",
    "ch",
    "sh",
    "th",
    "ph",
}


def syllables(w: str) -> int:
    n = 0
    i = 0

    while i < len(w):
        if w[i] in VOWELS:
            n += 1

            while i < len(w) and w[i] in VOWELS:
                i += 1
        else:
            i += 1

    if (
        len(w) >= 3
        and w[-1] == "e"
        and w[-2] not in VOWELS
        and w[-3] in VOWELS
        and n > 1
    ):
        n -= 1

    return max(n, 1)


def local_ok(w: str) -> bool:
    """Rules that can only get worse as letters are appended, so they are
    safe to use for pruning a partial acronym.
    """

    # No triple vowels.
    vowel_run = 0

    # No triple identical letters.
    for i, c in enumerate(w):
        if c in "aeiou":
            vowel_run += 1

            if vowel_run >= 3:
                return False
        else:
            vowel_run = 0

        if i >= 2 and w[i - 2] == c and w[i - 1] == c:
            return False

    # Check vowel pairs/runs.
    i = 0

    while i < len(w):
        if w[i] not in VOWELS:
            i += 1
            continue

        start = i

        while i < len(w) and w[i] in VOWELS:
            i += 1

        run = w[start:i]

        if len(run) >= 2 and run not in OK_VOWEL_PAIRS:
            return False

    # Check consonant runs.
    i = 0

    while i < len(w):
        if w[i] in VOWELS:
            i += 1
            continue

        start = i

        while i < len(w) and w[i] not in VOWELS:
            i += 1

        run = w[start:i]

        if len(run) == 1:
            continue

        if start == 0:
            if run in OK_STARTS:
                continue
            return False

        if run in OK_CLUSTERS:
            continue

        return False

    return True


def pronounceable(w: str) -> bool:
    if not local_ok(w):
        return False

    if not any(c in VOWELS for c in w):
        return False

    if "q" in w and "qu" not in w:
        return False

    # A final "e" must be silent-e (V-C-e), follow a vowel (-ie, -ee, -ue),
    # or be -le.
    if w.endswith("e") and len(w) > 2:
        if (
            w[-3] in VOWELS
            and w[-2] not in VOWELS
            or w[-2] in "aeiou"
            and w[-3] in VOWELS
            or w[-2:] == "le"
            and w[-3] not in VOWELS
        ):
            pass
        else:
            return False

    # x only at the end or between vowels.
    for i, c in enumerate(w[:-1]):
        if c == "x" and (i == 0 or w[i - 1] not in VOWELS or w[i + 1] not in VOWELS):
            return False

    return True


def syllable_lower_bound(prefix: str) -> int:
    """A syllable count no completion of `prefix` can go below (used for
    pruning).

    Vowel groups never disappear when letters are appended; the only thing
    that can lower the count is a silent final e.
    """

    g = 0
    i = 0

    while i < len(prefix):
        if prefix[i] in VOWELS:
            g += 1

            while i < len(prefix) and prefix[i] in VOWELS:
                i += 1
        else:
            i += 1

    if prefix.endswith("e"):
        g -= 1

    return max(g, 1)


def word_options(word, cap):
    opts = []
    n = len(word)
    idx = [0] * cap

    for k in range(1, cap + 1):
        for i in range(k):
            idx[i] = i

        while True:
            letters = "".join(word[i] for i in idx[:k])
            cost = sum(idx[:k])

            existing = None

            for i, (old_letters, old_cost, _) in enumerate(opts):
                if old_letters == letters:
                    existing = i
                    break

            if existing is None:
                selected = [False] * n

                for i in idx[:k]:
                    selected[i] = True

                opts.append((letters, cost, selected))

            elif cost < opts[existing][1]:
                selected = [False] * n

                for i in idx[:k]:
                    selected[i] = True

                opts[existing] = (letters, cost, selected)

            # Advance to the next combination.
            i = k - 1

            while i >= 0 and idx[i] == n - k + i:
                i -= 1

            if i < 0:
                break

            idx[i] += 1

            for j in range(i + 1, k):
                idx[j] = idx[j - 1] + 1

    return opts


def parse_words(tokens):
    words = []
    caps = []
    explicit_caps = []

    for tok in tokens:
        raw = tok
        n = None

        if ":" in tok:
            pos = tok.rfind(":")
            raw = tok[:pos]
            value = tok[pos + 1 :]

            try:
                n = int(value)
            except ValueError:
                raise ValueError(f"can't parse '{tok}' (use word or word:N)")

        if "(" in raw or ")" in raw:
            raise ValueError(f"can't parse '{tok}' (use word or word:N)")

        word = "".join(ch for ch in raw.lower() if ch.isalpha())

        if not word:
            raise ValueError(f"'{raw}' has no letters")

        if n is not None and n < 1:
            raise ValueError(f"{tok}: max letters must be >= 1")

        if n is not None and n > len(word):
            raise ValueError(
                f"{tok}: '{word}' has only {len(word)} letters, can't take {n}"
            )

        words.append(word)
        caps.append(n)
        explicit_caps.append(n is not None)

    return words, caps, explicit_caps


# Generator state.
#
# These are deliberately module-level rather than wrapped in a class.  The
# module itself is the stateful generator, which keeps the control flow close
# to what this would look like with static variables in C.
_words = []
_caps = []
_options = []
_max_remaining = []
_min_len = 0
_max_len = 0
_n = 0
_current_selections = []
_stack = []
_initialized = False
_exhausted = False


def generator_words():
    if not _initialized:
        raise RuntimeError("generator_init() must be called first")

    return _words


def generator_init(words, *, min_len=None, max_len=None):
    global _words
    global _caps
    global _options
    global _max_remaining
    global _min_len
    global _max_len
    global _n
    global _current_selections
    global _stack
    global _initialized
    global _exhausted

    _words, caps, explicit_caps = parse_words(words)

    _n = len(_words)

    _min_len = min_len if min_len is not None else _n

    if _min_len < _n:
        raise ValueError(
            f"min_len must be at least {_n} because every word contributes at least one letter"
        )

    if max_len is not None and max_len < _min_len:
        raise ValueError(f"max_len ({max_len}) must be at least min_len ({_min_len})")

    upper_bound = min_len - _n + 1 if min_len is not None else None

    lower_bound = max_len - _n + 1 if max_len is not None else 1

    _caps = []

    for word, cap, explicit in zip(_words, caps, explicit_caps):
        word_upper = len(word)

        if upper_bound is not None:
            word_upper = min(word_upper, upper_bound)

        if lower_bound > word_upper:
            raise ValueError(
                f"{word}: no valid maximum; bounds are {lower_bound}..{word_upper}"
            )

        if explicit:
            if cap < lower_bound or cap > word_upper:
                raise ValueError(
                    f"{word}:{cap}: max letters must be between "
                    f"{lower_bound} and {word_upper}"
                )
            _caps.append(cap)
        else:
            _caps.append(word_upper)

    natural_max_len = sum(_caps)

    if max_len is None:
        _max_len = natural_max_len
    else:
        _max_len = max_len

        if natural_max_len < _max_len:
            raise ValueError(
                f"max_len {max_len} is unreachable; "
                f"the provided word maxima allow at most {natural_max_len}"
            )

    _options = []

    for w, c in zip(_words, _caps):
        opts = sorted(
            word_options(w, c),
            key=lambda item: (len(item[0]), item[1]),
        )
        _options.append(opts)

    _max_remaining = [sum(_caps[i:]) for i in range(_n + 1)]
    _current_selections = [None] * _n
    _stack = [[0, 0, "", 0]]

    _initialized = True
    _exhausted = False


def generator_next(count=1):
    """Return up to ``count`` newly discovered valid acronym candidates.

    The generator resumes from its previous position; it never starts the
    search over.  Each valid selection path is emitted at most once.

    A result has the shape:

        (syllables, extra_letters, cost, acronym, selections)

    and returned in generator traversal order and are *not* sorted or
    limited by a caller-defined score.  An empty list means the entire search
    space has been exhausted.
    """

    global _exhausted

    if not _initialized:
        raise RuntimeError("generator_init() must be called first")

    if count < 1:
        raise ValueError("count must be at least 1")

    if _exhausted:
        return []

    rows = []

    while _stack and len(rows) < count:
        frame = _stack[-1]
        i, option_index, acr, cost = frame

        if i == _n:
            # This frame represents a complete selection, so consume it and
            # emit the candidate if it satisfies the final-only rules.
            _stack.pop()

            if len(acr) < _min_len or not pronounceable(acr):
                continue

            rows.append(
                (
                    syllables(acr),
                    len(acr) - _n,
                    cost,
                    acr,
                    tuple(_current_selections),
                )
            )
            continue

        if option_index >= len(_options[i]):
            # All choices at this depth have been visited.  Backtrack.
            _stack.pop()
            continue

        # Consume this option in the current frame so the next call resumes at
        # the following sibling rather than repeating this branch.
        frame[1] += 1

        letters, c, selected = _options[i][option_index]
        nxt = acr + letters

        still_needed = _n - i - 1

        if len(nxt) + still_needed > _max_len:
            continue

        if len(nxt) + _max_remaining[i + 1] < _min_len:
            continue

        if not local_ok(nxt):
            continue

        _current_selections[i] = selected

        # Descend one level.  No ranking/pruning based on score happens here:
        # the caller is free to decide what "best" means.
        _stack.append([i + 1, 0, nxt, cost + c])

    if not _stack:
        _exhausted = True

    return rows
