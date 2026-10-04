from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations

from dataclasses_json import DataClassJsonMixin

VOWELS = set("aeiouy")

OK_VOWEL_PAIRS = {
    "ai", "au", "ay", "ea", "ee", "ei", "ey", "ia", "ie", "io",
    "oa", "oi", "oo", "ou", "oy", "ua", "ue", "ui",
}  # fmt: skip

OK_STARTS = {
    "bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl",
    "pr", "sc", "sk", "sl", "sm", "sn", "sp", "st", "sw", "tr",
    "tw", "ch", "sh", "th", "wh", "ph",
}  # fmt: skip

OK_CLUSTERS = {
    "bl", "br", "ck", "cl", "cr", "ct", "dr", "ft", "gl", "gr",
    "ld", "lf", "lk", "lm", "lp", "ls", "lt", "mp", "nc", "nd",
    "ng", "nk", "ns", "nt", "nx", "pl", "pr", "pt", "rb", "rd",
    "rk", "rl", "rm", "rn", "rp", "rs", "rt", "sc", "sk", "sl",
    "sm", "sp", "st", "tr", "xt", "ll", "ss", "tt", "nn", "mm",
    "pp", "ff", "dd", "gg", "zz", "ch", "sh", "th", "ph",
}  # fmt: skip


@dataclass(frozen=True)
class GenerationRequest(DataClassJsonMixin):
    words: list[str]
    caps: list[int]
    min_len: int
    max_len: int


@dataclass(frozen=True)
class WordOption:
    letters: str
    cost: int
    mask: str


@dataclass
class GeneratorFrame(DataClassJsonMixin):
    index: int
    option_index: int
    acronym: str
    cost: int


type GeneratorStack = list[GeneratorFrame]


def syllables(word: str) -> list[str]:
    result = []
    i = 0

    while i < len(word):
        if word[i] in VOWELS:
            start = i

            while i < len(word) and word[i] in VOWELS:
                i += 1

            result.append(word[start:i])
        else:
            i += 1

    if (
        len(word) >= 3
        and word[-1] == "e"
        and word[-2] not in VOWELS
        and word[-3] in VOWELS
        and len(result) > 1
    ):
        result.pop()

    return result


def local_ok(word: str) -> bool:
    """Check pronunciation rules that cannot improve as letters are appended."""
    vowel_run = 0

    for i, char in enumerate(word):
        if char in "aeiou":
            vowel_run += 1
            if vowel_run >= 3:
                return False
        else:
            vowel_run = 0

        if i >= 2 and word[i - 2] == char and word[i - 1] == char:
            return False

    i = 0

    while i < len(word):
        if word[i] not in VOWELS:
            i += 1
            continue

        start = i

        while i < len(word) and word[i] in VOWELS:
            i += 1

        run = word[start:i]

        if len(run) >= 2 and run not in OK_VOWEL_PAIRS:
            return False

    i = 0

    while i < len(word):
        if word[i] in VOWELS:
            i += 1
            continue

        start = i

        while i < len(word) and word[i] not in VOWELS:
            i += 1

        run = word[start:i]

        if len(run) == 1:
            continue

        if start == 0:
            if run in OK_STARTS:
                continue
            return False

        if run not in OK_CLUSTERS:
            return False

    return True


def pronounceable(word: str) -> bool:
    if not local_ok(word):
        return False

    if not any(char in VOWELS for char in word):
        return False

    if "q" in word and "qu" not in word:
        return False

    # A final "e" must be silent-e (V-C-e), follow a vowel, or be -le.
    if word.endswith("e") and len(word) > 2:
        silent_e = word[-3] in VOWELS and word[-2] not in VOWELS
        follows_vowel = word[-2] in "aeiou" and word[-3] in VOWELS
        ends_in_le = word[-2:] == "le" and word[-3] not in VOWELS

        if not (silent_e or follows_vowel or ends_in_le):
            return False

    # x is allowed only at the end or between vowels.
    for i, char in enumerate(word[:-1]):
        if char == "x" and (
            i == 0 or word[i - 1] not in VOWELS or word[i + 1] not in VOWELS
        ):
            return False

    return True


def syllable_lower_bound(prefix: str) -> int:
    """Return a lower bound on the syllables in any completion of prefix."""
    groups = 0
    i = 0

    while i < len(prefix):
        if prefix[i] in VOWELS:
            groups += 1

            while i < len(prefix) and prefix[i] in VOWELS:
                i += 1
        else:
            i += 1

    if prefix.endswith("e"):
        groups -= 1

    return max(groups, 1)


def word_options(word: str, cap: int) -> list[WordOption]:
    """Build letter masks, preserving distinct masks of the same letters."""
    options = []

    for size in range(1, cap + 1):
        for indices in combinations(range(len(word)), size):
            letters = "".join(word[i] for i in indices)
            cost = sum(indices)
            mask = "".join("1" if i in indices else "0" for i in range(len(word)))

            options.append(
                WordOption(
                    letters=letters,
                    cost=cost,
                    mask=mask,
                )
            )

    return sorted(
        options,
        key=lambda option: (len(option.letters), option.cost),
    )


@dataclass
class Generator:
    """Resumable pronounceable-acronym generator.

    Use create() to validate the request and build the search space.
    get_state() returns an independent checkpoint that can be serialized.
    set_state() restores a checkpoint into a generator with matching settings.
    """

    words: list[str]
    caps: list[int]
    options: list[list[WordOption]]
    max_remaining: list[int]
    min_len: int
    max_len: int
    stack: GeneratorStack
    current_masks: list[str]

    @classmethod
    def create(cls, request: GenerationRequest) -> "Generator":
        options = [
            word_options(word, cap) for word, cap in zip(request.words, request.caps)
        ]

        max_remaining = [sum(request.caps[i:]) for i in range(len(request.words) + 1)]

        return cls(
            words=request.words,
            caps=request.caps,
            options=options,
            max_remaining=max_remaining,
            min_len=request.min_len,
            max_len=request.max_len,
            stack=[GeneratorFrame(0, 0, "", 0)],
            current_masks=[""] * len(request.words),
        )

    def get_stack(self) -> GeneratorStack:
        return deepcopy(self.stack)

    def set_stack(self, stack: GeneratorStack) -> None:
        n = len(self.words)

        if not stack:
            raise ValueError("empty generator stack requires exhausted=true")

        for frame in stack:
            if not 0 <= frame.index <= n:
                raise ValueError("invalid generator stack depth")

            if frame.index < n:
                if not 0 <= frame.option_index <= len(self.options[frame.index]):
                    raise ValueError("invalid generator option index")
            elif frame.option_index != 0:
                raise ValueError("invalid completed generator frame")

        self.stack = deepcopy(stack)

    def next(self) -> tuple[str, list[str]]:
        """Return the next candidate in traversal order."""
        n = len(self.words)

        while self.stack:
            frame = self.stack[-1]

            if frame.index == n:
                self.stack.pop()

                if len(frame.acronym) < self.min_len or not pronounceable(
                    frame.acronym
                ):
                    continue

                return frame.acronym.upper(), self.current_masks.copy()

            if frame.option_index >= len(self.options[frame.index]):
                self.stack.pop()
                continue

            # option_index always points to the next unvisited option.
            option_index = frame.option_index
            frame.option_index += 1

            option = self.options[frame.index][option_index]
            acronym = frame.acronym + option.letters

            still_needed = n - frame.index - 1

            if len(acronym) + still_needed > self.max_len:
                continue

            if len(acronym) + self.max_remaining[frame.index + 1] < self.min_len:
                continue

            if not local_ok(acronym):
                continue

            self.current_masks[frame.index] = option.mask

            self.stack.append(
                GeneratorFrame(
                    index=frame.index + 1,
                    option_index=0,
                    acronym=acronym,
                    cost=frame.cost + option.cost,
                )
            )

        return "", []
