HN Exporter
===========

This repo lets you download all of HN if you wanted to for some reason.

HN publishes all site contents to Google Firebase in real-time, but the API is very slow without clever workarounds (4 items per second with basic requests and there's over 20 million items).

Scripts in this repo help you download all of HN concurrently and pipelined for maximum download throughput (a 15x to 20x speedup over single requests).

Features
--------
- auto-bundle and compress downloaded items
    - Using compression and default bundling options (items stored in batches of 100 then compressed), the current hn dataset size is 3.8 GB (up to item number 21,849,570))
    - all downloaded bundles are given a filesystem time of the last item in the bundle (`ls -latrh cache/`)
- high concurrency options for downloading against the slow API
    - API is hosted at Google so we don't care about rate limits impacting the service
- ability to download individual user data when given a list of usernames
    - hn api doesn't allow enumeration of all users, so you must download all items, then iterate all items to extract each user, then create a list of users to iterate to get their user profile details (TODO: keep a running list of users as items are downloaded)
    - individual user json files are given a filesystem time of their account creation timestamp (`ls -latrh users/`)
- live progress displayed as downloads happen
- auto-resume downloads from most recent archived entry
- example HMM creation scripts
    - `split-to-parts.py` takes everything from the `cache` directory and extracts all contents with record delimiters (warning: uses 30+ GB fully extracted)
    - `markov.py` takes the output of `split-to-parts.py` to generate new text samples given then HN corpus.
    - `markov2.py` does the same but tries to be more clever about parts of speech.


Usage
-----

Run a script. If you get module errors, install the module. Run the script again. Repeat.

To download all HN items (posts, comments, polls, jobs):
```bash
$ ./import.py -i
```

Items will be downloaded into `cache/` and each bundle will be filesystem timestamped with a date taken from inside each bundle itself.

If your download is too slow, try adjusting the `-c CONCURRENCY` argument.


To download all user profiles:
```bash
$ ./import.py -u FILE_CONTAINING_ALL_USERNAMES
```

You can use `slow_bulk_usernames.sh` to extract all usernames from all downloaded items (edit where necessary, ymmv, etc) to generate the file of usernames to retrieve.

The download user json detail files will be filesystem timestamped with the user creation timestamp (turns out I'm the 84th registered HN account out of about 650,000 registered users who have posted to the site! (fun fact: the users who signed up before Feb 19, 2007 are all special YC insiders and many are billionaires now)).



Limitations
-----------
HN allows modification of many items (user profiles, recent edits to posts) but has no historical change API. The only way to get changed items is to redownload items. So, if you want to get all _current_ user profiles, you have to download all user profiles every time you want them to be up-to-date. Also, once you download an item bundle, the live contents can change (or be entirely deleted) after you download it, so for a complete long-term site sync, you should always delete your last two days of bundles then re-download them after all edit capability timers have expired.

Also, because the HN API can't enumerate users, we can only discover users who have posted or commented on the site. If a user registers and never posts or comments, we have no way of discovering them in the API.


Contributions
-------------
Feel free to improve features, fix errors, or implement missing functionality (username saving/appending as new item downloads happen, etc). Contributions welcome.

If you want to provide any datasets or write more in-depth tutorials about using `hnexport`, open an issue with links to your results/writings and we'll add them to this readme.
