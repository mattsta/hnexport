#!/usr/bin/env python3

import markovify
import glob

import re
import spacy

nlp = spacy.load("en")

class POSifiedText(markovify.Text):
    def word_split(self, sentence):
        return ["::".join((word.orth_, word.pos_)) for word in nlp(sentence)]

    def word_join(self, words):
        sentence = " ".join(word.split("::")[0] for word in words)
        return sentence

what = "comment"
stateSize = 3

combined_model = None
for filename in glob.glob(f"split-flat/{what}/1*"):
    with open(filename) as f:
#        model = POSifiedText(f, retain_original=False, state_size=stateSize)
        model = markovify.Text(f, retain_original=True, state_size=stateSize)

        print("Writing model", filename)
        with open(f"markov-partial-{what}-{filename.split('/')[-1]}-{stateSize}.json", "wt") as w:
            w.write(model.to_json())

        for i in range(10):
            print(model.make_sentence())

        print("==================")

        if combined_model:
            combined_model = markovify.combine(models=[combined_model, model])
        else:
            combined_model = model

        for i in range(10):
            print(combined_model.make_sentence())

        print("===========================================")

text_model = combined_model

print("Writing out combined model...")
with open(f"markov-{what}-{stateSize}.json", "wt") as w:
    w.write(text_model.to_json())

# Print five randomly-generated sentences
for i in range(50):
    print(text_model.make_sentence())

print("Bigger...")

# Print three randomly-generated sentences of no more than 280 characters
for i in range(50):
    print(text_model.make_short_sentence(280))
