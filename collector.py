#collect a list of all youtube videos for a channel, allowing you to detect when a video gets unlisted/removed
import requests
import json
from os import path
from datetime import datetime
from time import sleep
import argparse
import sqlite3
from http import HTTPStatus
import traceback

#validate file names
from pathvalidate import sanitize_filename
_SupportedDatabases = {"sqlite", "json"}
_ScriptPath = path.dirname(path.abspath(__file__))
_SqliteSchemaFileLocation = path.join(_ScriptPath, "schema.sql")

#TODOS:
#not accounting for possible captcha appearings or request limiting that might be enforced on IP
#video upload dates not stored. tried my best to keep them organized by dates but some changes bring older videos to top
#better exception handling needed. changes might be lost for long sessions if something wrong happens(added basic error logging for now)
#improve readability


class Collector:
    def __init__(self, databaseType: str, databaseLocation: str, userAgent: str, minVerbosityPriority: int):
        assert databaseType in _SupportedDatabases, f"Supported database types are {_SupportedDatabases}"
        assert path.exists(databaseLocation), "Database location doesn't exist"
        self._JsonDatabaseBaseFilesPath = path.join(
            databaseLocation, "VE_")  # json video data
        self._ChangelogBaseFilesPath = path.join(
            databaseLocation, "RE_")  # changelog data
        self._SQLDatabaseBaseFilePath = path.join(
            databaseLocation, "all_data")  # sqlite video data
        self.databaseType = databaseType
        self.minVerbosityPriority = minVerbosityPriority
        self.session = requests.Session()
        #base header
        self.userAgent = userAgent
        self.session.headers.update({
            "user-agent": userAgent
        })
        self.consent()

    def consent(self):  # run once at start of bot
        self.print(1, 'Consenting to YouTube...')
        firstVisit = self.session.get("https://youtube.com")
        # Check if consent needed
        consent_cookie = self.session.cookies.get("CONSENT", "")
        if "PENDING" in consent_cookie:
            try:
                # consent to youtube
                # get consent link (first link in page since choice doesn't matter much)
                consent_link = firstVisit.text.split('savePreferenceUrl":"')[1].split('"')[0]
                # convert unicode to plaintext
                consent_link = consent_link.encode().decode("unicode-escape")
                resp = self.session.post(consent_link)
                if resp.status_code != HTTPStatus.NO_CONTENT:
                    self.print(1,
                            "Could not consent to YouTube!")
                    self.log_to_file("Error occured in Position -1, Consent link is {} with status {}\n\nHere is the response: {}\n\n".format(
                        consent_link, resp.status_code, resp.text))
                    quit()
            except Exception as e:
                self.print(1, e)
                self.print(1,
                           "YouTube might have changed site format. if re-running the script didn't work, contact me to update the code (position 0)\nCheck logs for more info")
                detailed_error = traceback.format_exc()
                self.log_to_file("Error occured in Position 0, here is detailed traceback:\n\n{}\n\nHere are initial page details after first visit: {}\n\n".format(
                    detailed_error, self.get_request_log(firstVisit)))
                quit()
        else:
            self.print(1, "It seems consent is not required")

    def print(self, verbosityPriority: int, object):
        if verbosityPriority <= self.minVerbosityPriority:
            print(object)

    def log_to_file(self, data: str):
        logname = datetime.now().strftime("error_log_%H_%M_%d_%m_%Y.log")
        with open(path.join(_ScriptPath, logname), 'w') as f:
            f.write(data)

    def get_request_log(self, request: requests.Response):
        logData = "Final page text(url '{}', status {}): \n\n{}\n\nFinal page headers:\n\n{}\n\n".format(
            request.url, request.status_code, request.text, json.dumps(request.headers.__dict__))
        logData += "Page history:"
        for i, hist in enumerate(request.history):
            logData += "\n\n---Item {}\n\n".format(str(i+1))
            logData += "Url '{}', status {} with source:\n\n{}\n\nHeaders:\n\n{}".format(
                hist.url, hist.status_code, hist.text, json.dumps(hist.headers.__dict__))
        return logData

    def convertJSONtoSQLite(self, name: str):
        result = self.searchForChannelName(name)
        if not result:
            self.print(1, f"No channel by such name, ignoring for {name}")
            return None
        channelName, channelID = result
        data = None
        if path.exists(self._SQLDatabaseBaseFilePath + ".sqlite"):
            self.print(
                1, f"Database file at {str(self._SQLDatabaseBaseFilePath) + '.sqlite'} already exists. appending that data too to prevent losses..")
            self.databaseType = "sqlite"
            data = self.readBasicDataFromDB(channelName, channelID)
        #set dtype as json first
        self.databaseType = "json"
        #previous sql data exists. append new data to prevent loss
        if data:
            jsonData = self.readBasicDataFromDB(channelName, channelID)
            #append json data to sqlite data
            for jEach in jsonData:
                append = True
                for sEach in data:
                    #unique element already exists in sql data
                    if jEach["Link"] == sEach["Link"]:
                        append = False
                        break
                if append:
                    self.print(
                        1, f"Appending video '{jEach['Title']}' to new data, as it wasn't there before")
                    data.append(jEach)
        else:
            data = self.readBasicDataFromDB(channelName, channelID)
        if not data:
            self.print(
                2, f"No valid database for channel, ignoring for {channelName}")
            return None
        self.print(2, f"Converting to SQL for {channelName}")
        #set dtype as sql for saving
        self.databaseType = "sqlite"
        self.writeBasicDataToDB(channelName, channelID, data)

    def runSqlSchema(self, SqlCursor: sqlite3.Cursor):
        """
            Make sure database exists
        """
        self.print(
            3, "Making sure SQLite is correct format, running schema.sql commands")
        with open(_SqliteSchemaFileLocation, 'r') as f:
            commands = f.read()
            SqlCursor.executescript(commands)

    def readBasicDataFromDB(self, channelName: str, channelID: str):
        sanitizedChannelName = str(sanitize_filename(channelName))
        if self.databaseType == "json":
            self.print(3, f"Try to read Json for {channelName}")
            try:
                with open(f"{self._JsonDatabaseBaseFilesPath + sanitizedChannelName}.json", 'r') as f:
                    videoData = json.loads(f.read())
                    return videoData
            except FileNotFoundError:
                self.print(3, f"Json file not found for {channelName}")
                return None
            except json.decoder.JSONDecodeError:
                self.print(3, f"Error decoding Json for {channelName}")
                return None
        elif self.databaseType == "sqlite":
            self.print(3, "Connecting to SQL database")
            conn = sqlite3.connect(self._SQLDatabaseBaseFilePath + ".sqlite")
            cursor = conn.cursor()
            self.runSqlSchema(cursor)
            cursor.execute(
                "SELECT video_title, video_link, video_views, video_duration, video_availability FROM basic_video_data WHERE channel_id = ?", (channelID, ))
            data = cursor.fetchall()
            if not data:
                self.print(3, "SQLite database currently empty")
                return None
            videoData = []
            dataKeys = ["Title", "Link", "Views", "Duration", "Availability"]
            for dataValues in data:
                videoData.append(dict(zip(dataKeys, dataValues)))
            self.print(3, f"Read data from SQLite database")
            conn.close()
            return videoData

    def writeBasicDataToDB(self, channelName: str, channelID: str, data: dict):
        sanitizedChannelName = str(sanitize_filename(channelName))
        if self.databaseType == "json":
            self.print(3, f"Dumping to Json for {channelName}")
            with open(f"{self._JsonDatabaseBaseFilesPath + sanitizedChannelName}.json", 'w') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        elif self.databaseType == "sqlite":
            self.print(3, "Connecting to SQLite database")
            conn = sqlite3.connect(self._SQLDatabaseBaseFilePath + ".sqlite")
            cursor = conn.cursor()
            self.runSqlSchema(cursor)
            #delete previous data
            cursor.execute(
                "DELETE FROM channel WHERE channel_id = ?", (channelID, ))
            #write channel data
            cursor.execute(
                "INSERT INTO channel (channel_id, channel_name) VALUES (?, ?)", (channelID, channelName, ))
            #write video data
            self.print(3, f"Writing to SQLite for {channelName}")
            for video in data:
                try:
                    videoLink, videoTitle, videoViews, videoDuration, videoAvailability = video.get("Link"), video.get(
                        "Title"), video.get("Views"), video.get("Duration"), video.get("Availability", 1)
                    cursor.execute("INSERT INTO basic_video_data (video_title, video_link, video_views, video_duration, video_availability, channel_id) VALUES (?, ?, ?, ?, ?, ?)",
                                   (videoTitle, videoLink, videoViews, videoDuration, videoAvailability, channelID, ))
                except sqlite3.IntegrityError as integrityError:
                    if str(integrityError) == "UNIQUE constraint failed: basic_video_data.video_link":
                        self.print(
                            1, f"Video with link {videoLink} already in database, removing old data as links should be unique")
                        #remove old stuff
                        cursor.execute(
                            "DELETE FROM basic_video_data WHERE video_link = ?", (videoLink, ))
                        #insert current stuff
                        cursor.execute("INSERT INTO basic_video_data (video_title, video_link, video_views, video_duration, video_availability, channel_id) VALUES (?, ?, ?, ?, ?, ?)",
                                       (videoTitle, videoLink, videoViews, videoDuration, videoAvailability, channelID, ))
                        continue
                    raise integrityError
            conn.commit()
            conn.close()

    def searchForChannelName(self, name: str):
        self.print(3, f"Searching YouTube for {name}")
        searchedPage = self.session.get(
            f"https://www.youtube.com/results?search_query={name}")
        try:
            initialDataJson = json.loads(searchedPage.text.split(
                'ytInitialData = ')[1].split(';</script>')[0])
            results = initialDataJson[
                "contents"][
                "twoColumnSearchResultsRenderer"][
                "primaryContents"][
                "sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"]
            self.print(4, f"Search results:\n{json.dumps(results)}")
            channelDetails = None
            #look for channel ID in results
            #forced to use loop for check because output has no specific order
            for result in results:
                if "channelRenderer" in result:
                    channelDetails = result["channelRenderer"]
                    break
            if not channelDetails:
                return None
            self.print(4, f"Top result details:\n{json.dumps(channelDetails)}")
            channelID = channelDetails["channelId"]
            channelName = channelDetails["title"]["simpleText"]
            self.print(
                3, f"Found channel with name '{channelName}', ID '{channelID}'")
            return channelName, channelID
        except Exception as e:
            self.print(1, e)
            self.print(1,
                       "YouTube might have changed site format. if re-running the script didn't work, contact me to update the code (position 1)\nCheck logs for more info")
            detailed_error = traceback.format_exc()
            self.log_to_file("Error occured in Position 1, here is detailed traceback:\n\n{}\n\nHere is page data for initial channel name search:\n\n{}".format(
                detailed_error, self.get_request_log(searchedPage)))
            quit()
    #results is a list

    def recursiveVideosExtraction(self, videoList: list, postData: dict, postParametes: dict, videoData: dict, current: int = 1):
        self.print(2, f"Getting video list {current}")
        try:
            #these two sometimes dont exist
            views = "NaN"
            length = "NaN"
            #assume no more videos exist at first
            continuationToken = None
            for video in videoList:
                if "continuationItemRenderer" in video:
                    continuationToken = video["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
                    self.print(
                        3, f"More videos exist, continuation token is {continuationToken}")
                    continue
                videoID = video["richItemRenderer"]["content"]["videoRenderer"]["videoId"]
                title = video["richItemRenderer"]["content"]["videoRenderer"]["title"]["runs"][0]["text"]
                try:
                    views = video["richItemRenderer"]["content"]["videoRenderer"]["viewCountText"]["simpleText"]
                except:
                    self.print(3, f"No views in data for {title}, setting NaN")
                    pass
                try:
                    length = video["richItemRenderer"]["content"]["videoRenderer"]["thumbnailOverlays"][0]["thumbnailOverlayTimeStatusRenderer"]["text"]["simpleText"]
                except:
                    self.print(
                        3, f"No video length in data for {title}, setting NaN")
                    pass
                videoData.append(
                    {"Title": title, "Link": f"https://www.youtube.com/watch?v={videoID}", "Views": views, "Duration": length, "Availability": True})
        except Exception as e:
            self.print(1, e)
            self.print(1,
                       "YouTube might have changed site format. if re-running the script didn't work, contact me to update the code (position 3.1)\nCheck logs for more info")
            detailed_error = traceback.format_exc()
            self.log_to_file("Error occured in Position 3.1, here is detailed traceback:\n\n{}\n\nVideo list:\n\n{}\n\nVideo data:\n\n{}".format(
                detailed_error, json.dumps(videoList), json.dumps(videoData)))
            quit()
        # if no more exists exit function
        if not continuationToken:
            self.print(2, "No more videos exist")
            return
        # ask for more videos
        postData["continuation"] = continuationToken
        self.print(3, "Getting next page")
        videoListPage = self.session.post(
            "https://www.youtube.com/youtubei/v1/browse", headers={}, params=postParametes, data=json.dumps(postData))
        try:
            nextJsonData = json.loads(videoListPage.text)
            nextVideoList = nextJsonData["onResponseReceivedActions"][0][
                "appendContinuationItemsAction"]["continuationItems"]
        except Exception as e:
            self.print(1, e)
            self.print(1,
                       "YouTube might have changed site format. if re-running the script didn't work, contact me to update the code (position 3.2)\nCheck logs for more info")
            detailed_error = traceback.format_exc()
            self.log_to_file("Error occured in Position 3.2, here is detailed traceback:\n\n{}\n\nHere is video list page log:\n\n{}".format(
                detailed_error, self.get_request_log(videoListPage)))
            quit()
        self.recursiveVideosExtraction(
            nextVideoList, postData, postParametes, videoData, current+1)

    #get all video data in formatted form, saves to file at script location
    def getVideos(self, channelID: str):
        initialVideoPage = self.session.get(
            f"https://www.youtube.com/channel/{channelID}/videos")
        try:
            initialRequestDataJson = json.loads(
                '{' + initialVideoPage.text.split("ytcfg.set({")[1].split("); window.ytcfg.obfuscatedData")[0])
            self.print(
                4, f"Initial request json data: \n{json.dumps(initialRequestDataJson)}")
        except Exception as e:
            self.print(1, e)
            self.print(1,
                       "YouTube might have changed site format. if re-running the script didn't work, contact me to update the code (position 2.1)\nCheck logs for more info")
            detailed_error = traceback.format_exc()
            self.log_to_file("Error occured in Position 2.1, here is detailed traceback:\n\n{}\n\nHere is the initial get videos page log:\n\n{}".format(
                detailed_error, self.get_request_log(initialVideoPage)))
            quit()
        # Get post data and parameters
        try:
            APIkey = initialRequestDataJson["INNERTUBE_API_KEY"]
            clientData = initialRequestDataJson["INNERTUBE_CONTEXT"]["client"]
            hl = clientData["hl"]
            gl = clientData["gl"]
            visitorData = clientData["visitorData"]
            clientName = clientData["clientName"]
            clientVer = clientData["clientVersion"]
            self.print(
                3, f"Post Parameters:\n\tAPI key: {APIkey}\nPost Data:\n\thl: {hl}\n\tgl: {gl}\n\tVisitor data: {visitorData}\n\tClient name: {clientName}\n\tClient ver: {clientVer}")
        except Exception as e:
            self.print(1, e)
            self.print(1,
                       "YouTube might have changed site format. if re-running the script didn't work, contact me to update the code (position 2.2)\nCheck logs for more info")
            detailed_error = traceback.format_exc()
            self.log_to_file("Error occured in Position 2.2, here is detailed traceback:\n\n{}\n\nHere is the initial get videos page log:\n\n{}".format(
                detailed_error, self.get_request_log(initialVideoPage)))
            quit()
        self.print(2, "Gotten tokens")

        # final video data list
        finalVideoData = []
        # get first page of videos
        try:
            initialVideoDataJson = json.loads(initialVideoPage.text.split(
                'ytInitialData = ')[1].split(';</script>')[0])
            initialVideoList = initialVideoDataJson["contents"][
                "twoColumnBrowseResultsRenderer"]["tabs"][1][
                "tabRenderer"]["content"]["richGridRenderer"]["contents"]
            self.print(
                4, f"Initial video list:\n{json.dumps(initialVideoList)}")
        except Exception as e:
            self.print(1, e)
            self.print(1,
                       "YouTube might have changed site format. if re-running the script didn't work, contact me to update the code (position 2.3)\nCheck logs for more info")
            detailed_error = traceback.format_exc()
            self.log_to_file("Error occured in Position 2.3, here is detailed traceback:\n\n{}\n\nHere is the initial get videos page log:\n\n{}".format(
                detailed_error, self.get_request_log(initialVideoPage)))
            quit()

        # subsequent base post data
        postData = {
            "context": {
                "client": {
                    "hl": hl,
                    "gl": gl,
                    "visitorData": visitorData,
                    "clientName": clientName,
                    "clientVersion": clientVer,
                }
            }
        }
        # subsequent base parameters
        postParameters = {
            "key": APIkey
        }
        self.recursiveVideosExtraction(
            initialVideoList, postData, postParameters, finalVideoData)
        return finalVideoData

    # overrides changes if there are any, use when no initial file exists
    def getAndSaveVideos(self, channelName: str, channelID: str):
        videoData = self.getVideos(channelID)
        self.writeBasicDataToDB(channelName, channelID, videoData)
        self.print(1, "Done!")

    def detectAndSaveChanges(self, channelName: str, AppendNewData: bool = True):
        self.print(1, f"Checking {channelName}")
        searchResults = self.searchForChannelName(channelName)
        if not searchResults:
            self.print(1, "No channel by such name!")
            return False
        channelName, channelID = searchResults
        self.print(1, f"Found '{channelName}'")
        olddata = self.readBasicDataFromDB(channelName, channelID)
        if olddata is None:
            self.print(1, "No previous data detected, indexing from scratch")
            self.getAndSaveVideos(channelName, channelID)
            return True
        self.print(1, "getting new data... be patient")
        newdata = self.getVideos(channelID)
        change = False
        sanitizedChannelName = str(sanitize_filename(channelName))
        with open(f"{self._ChangelogBaseFilesPath + sanitizedChannelName}.chagelog", 'a') as f:
            self.print(3, "Writing changelogs")
            f.write(
                f"Script run at {datetime.now()}\n===================================================\n")
            for newSubdata in newdata:
                exists = False
                for oldSubdata in olddata:
                    if (newSubdata["Link"] == oldSubdata["Link"]):
                        #check views:
                        if oldSubdata["Views"] != newSubdata["Views"]:
                            change = True
                            self.print(2,
                                       f"Views for video '{oldSubdata['Title']}' changed!")
                            f.write(
                                f"Views have changed :\n    Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Old view count: {oldSubdata['Views']} \n    New view count: {newSubdata['Views']}\n")
                        #check if Duration has changed
                        if (oldSubdata["Duration"] != newSubdata["Duration"]):
                            change = True
                            self.print(2,
                                       f"Duration for video '{oldSubdata['Title']}' has changed!")
                            f.write(
                                f"Duration for video changed:\n    Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Old Duration: {oldSubdata['Duration']} \n    New Duration: {newSubdata['Duration']}\n")
                        #check if Title has changed
                        if (oldSubdata["Title"] != newSubdata["Title"]):
                            change = True
                            self.print(2,
                                       f"Title for video '{oldSubdata['Title']}' has changed!")
                            f.write(
                                f"Title for video changed:\n    Old Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    New Title: {newSubdata['Title']} \n")
                        exists = True
                if not exists:
                    change = True
                    self.print(1, f"Newly added: '{newSubdata['Title']}'")
                    f.write(
                        f"Newly Added:\n    Title: {newSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Views: {newSubdata['Views']} \n    Duration: {newSubdata['Duration']}\n")
            for oldSubdata in olddata:
                exists = False
                for newSubdata in newdata:
                    if (newSubdata["Link"] == oldSubdata["Link"]):
                        exists = True
                        break
                oldSubdata["Availability"] = True
                if not exists:
                    change = True
                    oldSubdata["Availability"] = False
                    self.print(2,
                               f"Video '{oldSubdata['Title']}' Has been removed or unlisted! Still keeping in data though")
                    f.write(
                        f"Removed or Unlisted:\n    Title: {oldSubdata['Title']}\n    Link: {oldSubdata['Link']}\n    Views: {oldSubdata['Views']} \n    Duration: {oldSubdata['Duration']}\n")

            if not change:
                self.print(1, "No changes detected.")
                f.write("No changes detected\n")
        if change:
            #update olddata, then save to file
            if AppendNewData:
                self.print(1, "Appending changes..")
                index = 0
                for newSubdata in newdata:
                    add = True
                    for oldSubdata in olddata:
                        if oldSubdata["Link"] == newSubdata["Link"]:
                            oldSubdata["Title"] = newSubdata["Title"]
                            oldSubdata["Views"] = newSubdata["Views"]
                            oldSubdata["Duration"] = newSubdata["Duration"]
                            add = False
                            break
                    if add:
                        if index > len(olddata):
                            index = len(olddata)
                        # preserve by-date order
                        olddata.insert(index, newSubdata)
                    index += 1
                self.writeBasicDataToDB(channelName, channelID, olddata)
        self.print(1, "Done!")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    inputGroup = parser.add_mutually_exclusive_group(required=True)
    inputGroup.add_argument(
        "-c", "--creators", help="Creator names to index (use quatation marks for multi-worded names)", nargs='*')
    inputGroup.add_argument(
        "-i", "--input-file", help="Input channel names from file (newline-separated names required)")
    parser.add_argument(
        "-cts", "--convert-json-to-sqlite", help="Converts Json databases to SQLite format. Saves in the same location as json files", action='store_true')
    parser.add_argument(
        '-f', "--format", help=f"Database storage format. defaults to SQLite", choices=_SupportedDatabases, default="sqlite")
    parser.add_argument(
        '-l', "--location", help="Database location relative to script's path", default=_ScriptPath)
    parser.add_argument(
        '-ua', "--user-agent", help="User-Agent to use when connecting to YouTube", default="Mozilla/5.0 (Windows NT 6.1; rv:60.0) Gecko/20100101 Firefox/60.0")
    parser.add_argument(
        '-v', "--verbosity", help="Set verbosity from 0-4. (0 for silent, default is 1)", type=int, default=1)
    args = parser.parse_args()

    creators = []
    if args.creators:
        creators = args.creators
    elif args.input_file:
        assert path.exists(
            args.input_file), "Input file location doesn't exist"
        with open(args.input_file, 'r') as f:
            for line in f:
                creators.append(line.strip())

    sample = Collector(args.format, args.location,
                       args.user_agent, args.verbosity)
    sleep(2)
    if args.convert_json_to_sqlite:
        for creator in creators:
            sample.convertJSONtoSQLite(creator)
    else:
        for creator in creators:
            sample.detectAndSaveChanges(creator)
