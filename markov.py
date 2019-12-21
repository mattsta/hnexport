#!/usr/bin/env python3

import markovify

what = "comment"
stateSize = 3

# Get raw text as string.
with open(f"split-flat/{what}/global") as f:
#    text = f.read().replace('\x1e', '\n')
    text = f.read()

# Build the model.
# if too big: retain_original=False
#text_model = markovify.NewlineText(text, state_size=stateSize)
text_model = markovify.Text(text, state_size=stateSize)

with open(f"markov-{what}-{stateSize}.json", "wt") as w:
    w.write(text_model.to_json())

# Print five randomly-generated sentences
for i in range(50):
    print(text_model.make_sentence())

print("Bigger...")

# Print three randomly-generated sentences of no more than 280 characters
for i in range(50):
    print(text_model.make_short_sentence(280))
