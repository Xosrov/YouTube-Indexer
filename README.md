# YouTube-Indexer
## Index creators  

**Features**  
* Index video details like title, duration and view count
* Detect changes in any of the above
* Detect removal/unlisting of videos
* Saves changelog of changes as well as all videos in json or sqlite(default) format
* Requires no API key
* Privacy-friendly; transmits as little as possible
* Light and fast

**Usage**
* Run the main collector.py file (pass creators names as arguments)
    * python3 collector.py -c "youtuber 1" "youtuber 2" "youtuber 3" "and so on"
* Re-run the script every now and then to detect changes. the changelog and database file(s) are updated after each execution  
* Run collector.py -h for more command info 
- - - -  
**NOTE**
Use the -cts flag to convert existing database formats to SQLite format.

If you encounter any bugs let me know