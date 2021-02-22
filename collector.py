#collect a list of all youtube videos for a channel, allowing you to detect when a video gets unlisted/removed
import requests
import json
from os import path
from datetime import datetime
from time import sleep
import argparse
#validate file names
from pathvalidate import sanitize_filename
_filePath = path.dirname(path.abspath(__file__))
_FileNamePrefix = "VE_"  # video data
_ReportFilePrefix = "RE_"  # changelog data
#TODOS:
    #not accounting for possible captcha appearings or request limiting that might be enforced on IP
    #video upload dates not stored. tried my best to keep them organized by dates but some changes bring older videos to top
    #better exception handling needed. changes might be lost for long sessions if something wrong happens
    #improve readability


class Collector:
    def __init__(self, userAgent="Mozilla/5.0 (Windows NT 6.1; rv:60.0) Gecko/20100101 Firefox/60.0"):
        self.session = requests.Session()
        #base header
        self.userAgent = userAgent
        self.session.headers.update({
            "user-agent": userAgent
        })

    def readDataFromFile(self, channelName):
        sanitizedChannelName = sanitize_filename(channelName)
        try:
            with open(path.join(_filePath, f"{_FileNamePrefix + sanitizedChannelName}.json"), 'r') as f:
                jsonData = json.loads(f.read())
                return jsonData
        except FileNotFoundError:
            return None
        except json.decoder.JSONDecodeError:
            return None

    def searchForChannelName(self, name):
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
            # with open("test.json", 'w') as f:
            #     json.dump(results, f, indent=4, ensure_ascii=False)
            #look for channel ID in results
            channelDetails = None
            for result in results:
                if "channelRenderer" in result:
                    channelDetails = result["channelRenderer"]
                    break
            if not channelDetails:
                return None
            channelID = channelDetails["channelId"]
            channelName = channelDetails["title"]["simpleText"]
            return channelName, channelID
        except Exception as e:
            print(e)
            print(
                "YouTube might have changed site format, contact me to update the code (position 1)")
            quit()
    #results is a list

    def recursiveVideosExtraction(self, videoList, postData, postParametes, videoData, current=1):
        print(f"Getting video list {current}")
        try:
            #these two sometimes dont exist
            views = "NaN"
            length = "NaN"
            #assume no more videos exist at first
            continuationToken = None
            for video in videoList:
                if "continuationItemRenderer" in video:
                    continuationToken = video["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
                    continue
                videoID = video["gridVideoRenderer"]["videoId"]
                title = video["gridVideoRenderer"]["title"]["runs"][0]["text"]
                try:
                    views = video["gridVideoRenderer"]["viewCountText"]["simpleText"]
                except:
                    pass
                try:
                    length = video["gridVideoRenderer"]["thumbnailOverlays"][0]["thumbnailOverlayTimeStatusRenderer"]["text"]["simpleText"]
                except:
                    pass
                videoData.append(
                    {"Title": title, "Link": f"https://www.youtube.com/watch?v={videoID}", "Views": views, "Duration": length})
        except Exception as e:
            print(e)
            print(
                "YouTube might have changed site format, contact me to update the code (position 3.1)")
            quit()
        # if no more exists exit function
        if not continuationToken:
            print("No more videos exist")
            return
        # ask for more videos
        postData["continuation"] = continuationToken
        videoListPage = self.session.post(
            "https://www.youtube.com/youtubei/v1/browse", headers={}, params=postParametes, data=json.dumps(postData))
        try:
            nextJsonData = json.loads(videoListPage.text)
            nextVideoList = nextJsonData["onResponseReceivedActions"][0][
                "appendContinuationItemsAction"]["continuationItems"]
        except Exception as e:
            print(e)
            print(
                "YouTube might have changed site format, contact me to update the code (position 3.2)")
            quit()
        self.recursiveVideosExtraction(
            nextVideoList, postData, postParametes, videoData, current+1)

    def saveToFile(self, channelName, data):
        #make sure filename is valid
        sanitizedChannelName = sanitize_filename(channelName)
        with open(path.join(_filePath, f"{_FileNamePrefix + sanitizedChannelName}.json"), 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    #get all video data in formatted form, saves to file at script location

    def getVideos(self, channelID):
        try:
            initialVideoPage = self.session.get(
                f"https://www.youtube.com/channel/{channelID}/videos").text
            # with open("test.html", 'w') as f:
            #     f.write(initialVideoPage)
            initialRequestDataJson = json.loads(
                '{' + initialVideoPage.split("ytcfg.set({")[1].split(");var setMessage")[0])
        except Exception as e:
            print(e)
            print(
                "YouTube might have changed site format, contact me to update the code (position 2.1)")
            quit()
        # with open("test.json", 'w') as f:
        #     json.dump(requestDataJson, f, indent=4, ensure_ascii=False)

        # Get post data and parameters
        try:
            APIkey = initialRequestDataJson["INNERTUBE_API_KEY"]

            clientData = initialRequestDataJson["INNERTUBE_CONTEXT"]["client"]
            hl = clientData["hl"]
            gl = clientData["gl"]
            visitorData = clientData["visitorData"]
            clientName = clientData["clientName"]
            clientVer = clientData["clientVersion"]
        except Exception as e:
            print(e)
            print(
                "YouTube might have changed site format, contact me to update the code (position 2.2)")
            quit()
        print("Gotten tokens")

        # final video data list
        finalVideoData = []

        # get first page of videos
        try:
            initialVideoDataJson = json.loads(initialVideoPage.split(
                'ytInitialData = ')[1].split(';</script>')[0])
            initialVideoList = initialVideoDataJson["contents"][
                "twoColumnBrowseResultsRenderer"]["tabs"][1][
                "tabRenderer"]["content"]["sectionListRenderer"]["contents"][0][
                "itemSectionRenderer"]["contents"][0][
                "gridRenderer"]["items"]
        except Exception as e:
            print(e)
            print(
                "YouTube might have changed site format, contact me to update the code (position 2.3)")
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
    def getAndSaveVideos(self, channelName, channelID):
        videoData = self.getVideos(channelID)
        self.saveToFile(channelName, videoData)
        print("Done!")

    def detectChanges(self, channelName, AppendNewData=True):
        print(f"Checking {channelName}")
        searchResults = self.searchForChannelName(channelName)
        if not searchResults:
            print("No channel by such name!")
            return False
        channelName, channelID = searchResults
        print(f"Found {channelName}!")
        olddata = self.readDataFromFile(channelName)
        if olddata is None:
            print("No previous data detected, indexing from scratch")
            self.getAndSaveVideos(channelName, channelID)
            return True
        print("getting new data... be patient")
        newdata = self.getVideos(channelID)
        change = False
        sanitizedChannelName = sanitize_filename(channelName)
        with open(path.join(_filePath, f"{_ReportFilePrefix + sanitizedChannelName}.chagelog"), 'a') as f:
            f.write(
                f"Script run at {datetime.now()}\n===================================================\n")
            for newSubdata in newdata:
                exists = False
                for oldSubdata in olddata:
                    if (newSubdata["Link"] == oldSubdata["Link"]):
                        #check views:
                        if oldSubdata["Views"] != newSubdata["Views"]:
                            change = True
                            print(
                                f"Views for video '{oldSubdata['Title']}' changed!")
                            f.write(
                                f"Views have changed :\n    Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Old view count: {oldSubdata['Views']} \n    New view count: {newSubdata['Views']}\n")
                        #check if Duration has changed
                        if (oldSubdata["Duration"] != newSubdata["Duration"]):
                            change = True
                            print(
                                f"Duration for video '{oldSubdata['Title']}' has changed!")
                            f.write(
                                f"Duration for video changed:\n    Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Old Duration: {oldSubdata['Duration']} \n    New Duration: {newSubdata['Duration']}\n")
                        #check if Title has changed
                        if (oldSubdata["Title"] != newSubdata["Title"]):
                            change = True
                            print(
                                f"Title for video '{oldSubdata['Title']}' has changed!")
                            f.write(
                                f"Title for video changed:\n    Old Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    New Title: {newSubdata['Title']} \n")
                        exists = True
                if not exists:
                    change = True
                    print(f"Newly added: '{newSubdata['Title']}'")
                    f.write(
                        f"Newly Added:\n    Title: {newSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Views: {newSubdata['Views']} \n    Duration: {newSubdata['Duration']}\n")
            for oldSubdata in olddata:
                exists = False
                for newSubdata in newdata:
                    if (newSubdata["Link"] == oldSubdata["Link"]):
                        exists = True
                        break
                if not exists:
                    change = True
                    print(
                        f"Video '{oldSubdata['Title']}' Has been removed or unlisted! Still keeping in data though")
                    f.write(
                        f"Removed or Unlisted:\n    Title: {oldSubdata['Title']}\n    Link: {oldSubdata['Link']}\n    Views: {oldSubdata['Views']} \n    Duration: {oldSubdata['Duration']}\n")
            if not change:
                print("No changes detected.")
                f.write("No changes detected\n")
        if change:
            #update olddata, then save to file
            if AppendNewData:
                print("Appending changes..")
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
                self.saveToFile(channelName, olddata)
        print("Done!")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--creators", help="Creator names to index (remember to escape spaces in multi-worded names)", required=True, nargs='*')
    args = parser.parse_args()
    sample = Collector()
    print("DONT INTERRUPT THE PROCESS, CHANGES WONT BE SAVED PROPERLY!")
    sleep(2)
    for creator in args.creators:
        sample.detectChanges(creator)
            
