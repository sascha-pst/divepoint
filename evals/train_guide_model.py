"""Train an offline guide intent classifier on original example questions."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

# The final question in each group is held out. These examples contain no provider data.
QUESTIONS = {
    "length": (
        "How big can this fish get?", "What is its maximum length?",
        "Does it grow very long?", "Tell me the size of this fish.",
        "How large can this fish grow?",
    ),
    "depth": (
        "How deep does this fish swim?", "What is its minimum depth?",
        "Does it occur in shallow water?", "What is its depth range?",
        "What is its maximum depth?",
    ),
    "habitat": (
        "What kind of habitat does it prefer?", "Does this fish live near the bottom?",
        "What type of reef does it live on?", "Describe its usual habitat.",
        "What habitat is typical for this fish?",
    ),
    "records": (
        "Has this fish been recorded here?", "Are there any sightings in this area?",
        "Show me the occurrence records.", "When was the last observation here?",
        "Has it been observed in this area?",
    ),
    "names": (
        "What is this fish called?", "Tell me its scientific name.",
        "Does it have a common name?", "What name do scientists use for this fish?",
        "What is its scientific name?",
    ),
    "no_data": (
        "What does this fish eat?", "Is it safe to dive here?",
        "Recommend a local hotel.", "Can I get food delivered?",
        "Can you recommend a hotel nearby?",
    ),
}


def tokenize(question):
    return re.findall(r"[a-z]+", question.casefold())


def train(groups):
    counts = {topic: Counter(word for question in rows for word in tokenize(question))
              for topic, rows in groups.items()}
    vocabulary = sorted(set().union(*(counts[topic] for topic in counts)))
    question_count = sum(map(len, groups.values()))
    return {
        "unknown_token": "<unknown>",
        "topics": {
            topic: {
                "log_prior": math.log(len(groups[topic]) / question_count),
                "log_likelihoods": {
                    word: math.log((counts[topic][word] + 1) / (counts[topic].total() + len(vocabulary) + 1))
                    for word in [*vocabulary, "<unknown>"]
                },
            }
            for topic in groups
        },
    }


def predict(model, question):
    words = tokenize(question)
    unknown = model["unknown_token"]

    def score(topic):
        row = model["topics"][topic]
        likelihoods = row["log_likelihoods"]
        return row["log_prior"] + sum(
            likelihoods.get(word, likelihoods[unknown]) for word in words
        )

    return max(model["topics"], key=score)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Where to write model weights")
    args = parser.parse_args()

    model = train({topic: rows[:-1] for topic, rows in QUESTIONS.items()})
    correct = 0
    for topic, rows in QUESTIONS.items():
        question = rows[-1]
        predicted = predict(model, question)
        correct += predicted == topic
        print(f"{predicted} (expected {topic}) — {question}")
    print(f"Held-out intent accuracy: {correct}/{len(QUESTIONS)}")
    args.output.write_text(json.dumps(model, indent=2) + "\n")
    print(f"Model weights written to {args.output}")


if __name__ == "__main__":
    main()
