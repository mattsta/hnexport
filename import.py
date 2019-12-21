#!/usr/bin/env python3

# Apply retries and backoff to connection handling
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Use async request processing so we can fetch more than 4 requests per second
from requests_futures.sessions import FuturesSession

import multiprocessing
import itertools
import requests
import time
import json
import lzma
import sys
import os

HIGHEST_URL = "https://hacker-news.firebaseio.com/v0/maxitem.json"


def itemURL(id):
    return f"https://hacker-news.firebaseio.com/v0/item/{id}.json"


def userURL(username):
    return f"https://hacker-news.firebaseio.com/v0/user/{username}.json"



class Timer:
    def __init__(self, name=""):
        self.name = name
        self.cancel = False

    def __enter__(self):
        # Note: don't use time.clock() or time.process_time()
        #       because those don't record time during sleep calls
        #       but we need to record sleeps for when we're waiting
        #       for async network replies
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.end = time.perf_counter()
        self.interval = self.end - self.start
        internalStatus = ""
        if self.cancel:
            internalStatus = "[CANCELED] "

        if self.name:
            print(f"[{internalStatus}{self.name}] Duration:", self.interval)
        else:
            print(f"{internalStatus}Duration:", self.interval)


def rangeInclusive(high, low, step=1):
    """ self-documenting wrapper for [A, B] instead of [A, B) """
    return range(high, low + step, step)


def splitListIntoLists(l, n):
    """ group 'l' into multiple lists of length 'n' (final may be shorter) """
    for i in range(0, len(l), n):
        yield l[i:i + n]


# NOTE: if you change this ALL THE BUNDLE FILENAMES WILL CHANGE!
# How many JSON to bundle into one .xz
cacheBundleCount = 100

def setUtimeFromBundle(finalName, gotItAll):
    assert gotItAll, "got is empty?"

    highestTime = None
    highestItem = gotItAll[-1]

    if isinstance(highestItem, dict):
        # If processing already-loaded JSON...
        highest = highestItem
    else:
        # else, decode string from JSON to native dict directly
        highest = json.loads(highestItem)

    if 'time' in highest:
        # Time for items
        highestTime = highest['time']
    elif 'created' in highest:
        # Time for users
        highestTime = highest['created']
    else:
        print(f"Item doesn't have a time? {highest}")
        # Try again with misbehaving item removed...
        return setUtimeFromBundle(finalName, gotItAll[0:-1])

    # Set atime and mtime to last timestamp in bundle
    os.utime(finalName, (highestTime, highestTime))

def setHistoricalMtime(finalName):
    with lzma.open(finalName, "rt") as f:
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

    setUtimeFromBundle(finalName, gotItAll)

def downloadByGroupGroup(type, totalGroup, writeAsCompressedBundle=True):
    # If server doesn't let us connect, back off for a while and try again...
    retry = Retry(connect=7, backoff_factor=0.5)
    safeRetrySession = requests.Session()
    kindRetryAdapter = HTTPAdapter(max_retries=retry)
    safeRetrySession.mount('https://', kindRetryAdapter)

    # Attaach safe retry capability to our async requests worker pool
    session = FuturesSession(max_workers=25, session=safeRetrySession)

    def prepareSession(group):
        if type == "items":
            return [session.get(itemURL(itemId), timeout=5) for itemId in group]

        if type == "users":
            return [session.get(userURL(name), timeout=5) for name in group]


    sessionGroupsWaitingForRead = []

    # request 'groupOfGroupsSegment' count groups before reading async replies
    # (each group is 100, so if we are doing 10 groups of 100, we read
    #  1,000 replies at once. this seems an optimal number and increasing
    #  the async retrieval doesn't appear to improve performance any)
    groupOfGroupsSegment = 10

    def processSessionGroups(sessionGroup):
        if not sessionGroup:
            return

        # note: "list(<dict type>)" just returns all keys of the dict as a list
        #       ...and for modern python versions, dicts store keys in
        #       insert-order, so we know 0 is first and -1 is last inserted.
        groupNameFirst = list(sessionGroup[0])[0]
        groupNameLast = list(sessionGroup[-1])[0]
        with Timer(f"Wrote {len(sessionGroup)} bundle from {groupNameFirst} to {groupNameLast}") as ot:
            for namedSession in sessionGroup:
                bundleName = list(namedSession)[0]
                with Timer(f"Fetched{ ' and compressed' if writeAsCompressedBundle else ''} {bundleName}") as t:
                    for finalName, sessions in namedSession.items():
                        try:
                            # collect each reply
                            # blocks if:
                            #  - content not available yet
                            # throws exception if:
                            #  - timeout
                            #  - connection error
                            #  - read error, etc
                            # Also, don't populate anything NULL returned from API
                            gotItAll = [c for c in [x.result().content for x in sessions] if c != b'null']
                        except BaseException as e:
                            # most likely a timeout error, so retry everything starting
                            # from the beginning (we won't download duplicates)
                            # Note: this is a simple hack for sparse timeouts, but if we
                            # have serious timeouts forever, this will cause memory
                            # problems or eventually recursion limit exceptions
                            print(f"ERROR WHILE FETCHING {bundleName}:", e)
                            ot.cancel = True
                            t.cancel = True
                            return downloadByGroupGroup(totalGroup)

                        # If, for some reason, everything was null and we saved no content, do it all over again
                        if not gotItAll:
                            print("No content for:", finalName)
                            continue

                        if writeAsCompressedBundle:
                            # All items fetched, now concat all json and save as compressed archive
                            # Note: this is not storing a valid JSON list, so to reconstruct
                            #       storage to import as JSON later, do:
                            #       f"[{'},{'.join(content.split('}{'))}]"
                            with lzma.open(finalName, "w", preset=lzma.PRESET_EXTREME) as f:
                                f.write(b''.join(gotItAll))
                        else:
                            for got_ in gotItAll:
                                got = json.loads(got_)
                                finalName = got["id"] + ".json"
                                with open(finalName, "wb") as f:
                                    f.write(got_)

                        setUtimeFromBundle(finalName, gotItAll)

    for group in splitListIntoLists(totalGroup, cacheBundleCount):
        if writeAsCompressedBundle:
            finalName = f"{group[0]}-{group[-1]}.xz"
            if not os.path.exists(finalName):
                # Bundle name did not exist, so fetch contents
                sessionGroupsWaitingForRead.append({finalName: prepareSession(group)})
            else:
                # Bundle name alreay existed, don't fetch again
    #            print("Skipping", finalName)
                # If we need to clean up bad mtime/ctime properties on existing
                # archives, uncomment here to run time updates on existing bundles:
    #            setHistoricalMtime(finalName)
                continue
        else:
            # else, we are NOT bundling and need to process names individually
            for user in group:
                finalName = user + ".json"
                if not os.path.exists(finalName):
                    sessionGroupsWaitingForRead.append({finalName: prepareSession([user])})
                else:
                    continue

        # If we aren't at the async read limit yet, try again!
        if len(sessionGroupsWaitingForRead) < groupOfGroupsSegment:
            continue

        # else, we are at 'groupOfGroupsSegment' count, so read all the async
        # replies now (and block for reads if necessary)
        processSessionGroups(sessionGroupsWaitingForRead)
        # Reset session groups so we can add more on the next loop...
        sessionGroupsWaitingForRead = []

    # Now we are outside the main processing loop, but if we have trailing
    # items in 'sessionGroupsWaitingForRead' UNDER the 'groupOfGroupsSegment'
    # limit, read the remainder of the waiting groups now:
    processSessionGroups(sessionGroupsWaitingForRead)


def fetchByListForTypeInDir(elements, type, dirname):
    # Run this script inside a 'cache' dir so all 200,000+ files don't
    # pollute the current directory.
    os.makedirs(dirname, exist_ok=True)
    os.chdir(dirname)

    if type == "users":
        bundleAndCompress = False
    elif type == "items":
        bundleAndCompress = True

    with Timer(f"Complete Fetch ({type})") as t:
        # Give each worker 20,000 sets of 100 items to fetch
        itemGroupsPerWorker = 20000

        # Split [0, highest] into a list containing
        # 'itemGroupsPerWorker' number of lists to be split among all workers.
        # Note: the final list up to 'highest' may contain FEWER than
        #       'itemGroupsPerWorker' elements, which will cause the final
        #       fetch to probably be less than 'cacheBundleCount' elements.
        #       (i.e. it'll be a bundle from *00-*XX.xz instead of *00-*99.xz)
        fetchGroups = list(splitListIntoLists(elements, itemGroupsPerWorker))

    #    print("Fetch All:", fetchAll)
    #   Inspect (and run) on the last group (for testing):
    #    fetchGroups = [fetchGroups[-1]]
    #    print("Fetch groups:", fetchGroups)

        # Because our worker function has multiple arguments AND we want to split 'fetchGroups'
        # among all workers, we need to generate the cross product of all arguments and
        # all groups so the worker pool can split out data to multiple workers.
        allArguments = itertools.product([type], fetchGroups, [bundleAndCompress])

        # We use maxtasksperchild=1 so python will exit each worker process after it
        # returns so memory gets released right away.
        try:
            with multiprocessing.Pool(processes=parallelismCount, maxtasksperchild=1) as pool:
                pool.starmap(downloadByGroupGroup, allArguments)
        except BaseException as e:
            import traceback
            print("Failed processing:", e)

            # Print any stack trace from child process
            # (yay python its so simple and intuitive)
            print("".join(traceback.format_exception(*sys.exc_info())))
            t.cancel = True

    # return to directory where we started
    os.chdir("..")

if __name__ == "__main__":
    import argparse
    detectedCoreCount = multiprocessing.cpu_count()

    parser = argparse.ArgumentParser(description="HN API Downloader")
    parser.add_argument("-c", "--concurrency", dest="concurrency",
            help=f"Run concurrent downloads (default: {detectedCoreCount})",
            default=detectedCoreCount, type=int)
    itemsOrUsers = parser.add_mutually_exclusive_group(required=True)
    itemsOrUsers.add_argument("-u", "--users", type=str, help="Download profile from API for each user in file")
    itemsOrUsers.add_argument("-i", "--items", action='store_true', help="Download all items from API")

    args = parser.parse_args()

    fetchItems = args.items
    fetchUsers = args.users

    # Number of 'downloadByGroup' to run concurrently
    parallelismCount = args.concurrency
    print("Running with concurrency of", parallelismCount)

    if fetchItems:
        highest = int(requests.get(HIGHEST_URL).text)
        fetchNext = highest

        print("Fetching up to highest current item id:", highest)

        # Generate a python range from [0, highest]
        fetchAll = rangeInclusive(0, highest)

        fetchByListForTypeInDir(fetchAll, "items", "cache")

    if fetchUsers:
        usernames = [u.strip() for u in open(args.users, "rt").readlines()]
        fetchByListForTypeInDir(usernames, "users", "users")




# TODO:
#  - fetch all users
#  - create utility to fetch by ID from bundle
#  - create cache cache infrastructure where fetched IDs unbundle their entire contents into a LFU space-capped directory
