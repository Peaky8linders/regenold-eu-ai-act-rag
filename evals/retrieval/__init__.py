"""Retrieval-grain evaluation instruments (R449).

These measure *what retrieval returns*, not what the answer says. The eight
official axes in :mod:`evals.official.rubric` are answer- and reference-level,
so a retrieval win and a generation regression cancel invisibly inside them.
Anything that changes candidate discovery, fusion or passage selection needs
an instrument at this grain before it can be judged at the answer grain.
"""
