## Incorrect legal scope of emotion recognition prohibition
- file: `app/engines/_graph_rag_impl.py:3680`
- bug: The code comment states that Article 5(1)(f) applies to inferring emotions of persons "IN the workplace or an educational institution", but the actual provision applies to use "in the areas of workplace and education institutions", which is broader and includes systems used *by* workplace/education staff on others (e.g., hospital staff using emotion recognition on patients).
- evidence: "Article 5\nProhibited AI practices\n1. The following AI practices shall be prohibited: \n...\n(f) the placing on the market, the putting into service for this specific purpose, or the use of AI systems to infer emotions of a natural person in the areas of workplace and education institutions, except where the use of the AI system is intended to be put in place or into the market for medical or safety reasons;"
- impact: This could lead the system to incorrectly classify certain uses as prohibited when they are actually permitted (e.g., medical use by hospital staff on patients), or vice versa, resulting in inaccurate legal advice.
- fix: Update the comment to accurately reflect the provision's scope by changing "IN the workplace" to "in the areas of workplace" and clarify that the prohibition applies to the context/setting rather than the subject's employment status.
- confidence: 95

## NEEDS MORE EVIDENCE
None
