"""Pure prompt-budget handling shared by Stage-2 transports."""

def _shrink_user_for_groq(user: str, budget: int = 10000) -> str:
    """Fit ``user`` into ``budget`` chars WITHOUT deleting the grounding.

    R315 + R341. The Stage-2 user message has two layouts:

    **Multi-turn** (contains ``Latest question:``)::

        [Context anchors ...] / Conversation so far: ...   <- compressible
        Latest question: ...                               <- must survive
        EU AI ACT REFERENCES ...                           <- must survive
        VERBATIM PROVISION TEXT ...                        <- must survive
        ANSWER COVERAGE / CRITICAL RULES ...               <- must survive

    **Single-turn** (starts with ``ORIGINAL QUESTION:``)::

        ORIGINAL QUESTION: ...                             <- must survive
        [query profile / context / references ...]         <- compressible middle
        ANSWER COVERAGE / CRITICAL RULES ...               <- must survive

    R341: The previous fallback for single-turn was ``user[:budget]`` which
    chopped the TAIL where ``USER_ANSWER_COVERAGE_CLAUSE`` and
    ``USER_CRITICAL_RULES_CLAUSE`` sit — the highest-impact instructions.
    Now both layouts preserve head (question) + tail (rules), compressing
    only the bulky middle (cross-references, verbatim text, KG context).
    """

    if budget <= 0:
        return ""
    if len(user) <= budget:
        return user

    # --- Locate the critical tail rules (R308 coverage + R340 critical) ---
    # These sit at the very end of user_message.  Find the earliest of the
    # two clause markers so we can protect everything from there onward.
    _TAIL_MARKERS = (
        " ANSWER COVERAGE:",          # USER_ANSWER_COVERAGE_CLAUSE start
        " CRITICAL ANSWER RULES",     # USER_CRITICAL_RULES_CLAUSE start
        " SCOPE STOP RULE",           # R367 USER_SCOPE_STOP_CLAUSE start
        " ANSWER DISCIPLINE (V3",     # R380 USER_V3_DISCIPLINE_CLAUSE start
        " ANSWER CONTRACT (compact):",
        " ANSWER CONTRACT (evidence):",
        " CHALLENGE TURN:",
    )
    tail_start = len(user)  # default: no protected tail found
    for tm in _TAIL_MARKERS:
        pos = user.find(tm)
        if pos >= 0:
            tail_start = min(tail_start, pos)

    protected_tail = user[tail_start:] if tail_start < len(user) else ""

    # --- Multi-turn: split on "Latest question:" ---
    marker = "Latest question:"
    idx = user.find(marker)
    if idx >= 0 and idx < tail_start:
        head = user[:idx]
        # Middle = from marker to tail rules; tail rules are protected separately
        middle = user[idx:tail_start]
        core = middle + protected_tail
        if len(core) <= budget:
            keep = budget - len(core)
            if keep > 0:
                banner = "... [EARLIER CONVERSATION TRUNCATED FOR GROQ CONTEXT LIMIT] ...\n\n"
                if keep < len(banner):
                    # If a full notice and the latest question fit, spend the
                    # shortfall on the following context, never on the rules.
                    available = budget - len(banner) - len(protected_tail)
                    question_end = middle.find("\n")
                    if question_end >= 0 and available >= question_end + 1:
                        return banner + middle[:available] + protected_tail
                    return head[-keep:] + core
                keep -= len(banner)
                trimmed = head[-keep:] if keep else ""
                return (
                    banner
                    + trimmed
                    + core
                )
            return core
        # Even middle + tail overflow: keep question front + tail rules,
        # compress the verbatim text in between.
        mid_budget = budget - len(protected_tail)
        if mid_budget > 0:
            return middle[:mid_budget] + protected_tail
        return protected_tail[:budget]

    # --- Single-turn: starts with "ORIGINAL QUESTION:" ---
    # Locate end of question header (first double-newline after question).
    q_marker = "ORIGINAL QUESTION:"
    q_idx = user.find(q_marker)
    if q_idx >= 0:
        # Find the end of the question block (first blank line)
        q_end = user.find("\n\n", q_idx)
        if q_end < 0:
            q_end = min(len(user), q_idx + 500)
        else:
            q_end += 2  # include the double newline

        question_head = user[:q_end]
        middle_block = user[q_end:tail_start]

        head_tail_len = len(question_head) + len(protected_tail)
        if head_tail_len <= budget:
            mid_budget = budget - head_tail_len
            if mid_budget > 0:
                # Keep question + as much middle as fits + tail rules
                banner = "\n... [MIDDLE CONTEXT TRUNCATED FOR GROQ CONTEXT LIMIT] ...\n"
                if len(middle_block) > mid_budget and mid_budget >= len(banner):
                    return question_head + middle_block[:mid_budget - len(banner)] + banner + protected_tail
                return question_head + middle_block[:mid_budget] + protected_tail
            return question_head + protected_tail
        # Even head + tail overflow — keep tail rules (they're the instructions),
        # trim the question.
        q_budget = budget - len(protected_tail)
        if q_budget > 0:
            return question_head[:q_budget] + protected_tail
        return protected_tail[:budget]

    # --- Unrecognised layout: preserve tail rules, trim front ---
    if protected_tail and len(protected_tail) < budget:
        front_budget = budget - len(protected_tail)
        banner = "\n... [TRUNCATED FOR GROQ CONTEXT LIMIT] ...\n"
        if front_budget >= len(banner):
            return user[:front_budget - len(banner)] + banner + protected_tail
        return user[:front_budget] + protected_tail
    return user[:budget]

