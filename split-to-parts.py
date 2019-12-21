#!/usr/bin/env python3

import multiprocessing
import itertools
import html
import lzma
import json
import os

import datetime

# Currently 3 months...
monthlySplitDuration = datetime.timedelta(weeks=52 / 4).total_seconds()


def dirForType(type):
    return f"split/{type}"


# for objectType in ["job", "story", "comment", "poll", "pollopt"]:
#    os.makedirs(dirForType(objectType), exist_ok=True)


def writeEntryGlobal(type, bucket, username, content):
    dir = dirForType(type)
    for dir in [dirForType(type), dirForType(f"user/{username}")]:
        os.makedirs(dir, exist_ok=True)
        with open(dir + "/global", "at") as g:
            g.write(content)
            # Insert explicit record sep so we can re-join records later
            g.write("\x1e")

        with open(dir + f"/{bucket}", "at") as g:
            g.write(content)
            g.write("\x1e")


def findMe(a):
    return int(a.split("-")[0])


for finalName in sorted(os.listdir("cache"), key=findMe):
    print("Processing", finalName)
    with lzma.open("cache/" + finalName, "rt") as f:
        try:
            # Our JSON is stored as just concatenated objects, so we
            # need to re-form them into a list to load them back as
            # a syntax appropriate JSON array
            listDelim = '"},{"'.join(f.read().split('"}{"'))
            listWrap = f"[{listDelim}]"
            gotItAll = json.loads(listWrap)
        except BaseException as e:
            print(f"Failed to load {finalName}?")
            raise e

    for entry in gotItAll:
        # Take each entry and write the text into three places:
        #   - append to type-specific global word bucket
        #   - append to global word bucket for user (if comment)
        #   - append to date specific type bucket for 6 month range
        #   - append to date specific word bucket for user (if comment)
        try:
            # We can't process deleted entries...
            if "deleted" in entry:
                continue

            itemTime = entry["time"]

            bucketByDuration = int(itemTime // monthlySplitDuration)

            if "text" in entry:
                content = entry["text"]
            else:
                content = entry["title"]

            content = html.unescape(content)
            writeEntryGlobal(entry["type"], bucketByDuration, entry["by"], content)
        except BaseException as e:
            print("Error?", e)
            print("Content:", entry)
