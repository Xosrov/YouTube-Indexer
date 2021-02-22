#collect a list of all youtube videos for a channel, allowing you to detect when a video gets unlisted/removed
import requests
import re
import json
from os import path
from datetime import datetime
from time import sleep
import argparse
_filePath = path.dirname(path.abspath(__file__))
_FileNamePrefix = "VE_" #video data
_ReportFilePrefix = "RE_" #changelog data
#TODOS:
    #not accounting for possible captcha appearings or request limiting that might be enforced on IP
    #video upload dates not stored. tried my best to keep them organized by dates but some changes bring older videos to top
    #better exception handling needed. changes might be lost for long sessions if something wrong happens
    #improve readability

class Collector:
    def __init__(self, userAgent = "Mozilla/5.0 (Windows NT 6.1; rv:60.0) Gecko/20100101 Firefox/60.0"):
        self.session = requests.Session()
        #base header
        self.userAgent = userAgent
        self.session.headers.update({
            "user-agent": userAgent
        })
        #regex is for single use and yt changes regularly anyway, so not using bs4
        
        #used for channel search
        #param(s) are Channel ID and Name:
        self.findChannelIDre = re.compile(r'''ytInitialData.*?channelId":"(.*?)".*?Text":"(.*?)"''')

        #used for initial channel overview. the rest can be obtained in json format
        #param(s) are Video Title, Video ID(url), ViewCount, duration:
        self.initialVideoDataExtractor = re.compile(r'''runs":\[{"text":"([^"]*?)"}\],"access.*?url":"(.*?)".*?CountText.*?Text":"(.*?)".*?simpleText":"(.*?)"''')

        #token parameters for json request
        #param(s) are API token, VisitorData, ClientName and ClientVersion
        self.clientData = re.compile(r'''TUBE_API_KEY":"(.*?)".*?visitorData":"(.*?)".*?clientName":"(.*?)".*?clientVersion":"(.*?)"''')

        #language parameters for json request
        #param(s) are hl and gl
        self.languageParams = re.compile(r'''hl":"(.*?)".*?gl":"(.*?)"''')

        #initial continuation token, rest can be obtained from json
        #param(s) are continuation token
        self.initialContinuationToken = re.compile(r'''{"token":"(.*?)"''')

    def readDataFromFile(self, channelName):
        try:
            with open(path.join(_filePath, f"{_FileNamePrefix + channelName}.json"), 'r') as f:
                jsonData = json.loads(f.read())
                return jsonData
        except FileNotFoundError:
            return None
        except json.decoder.JSONDecodeError:
            return None
    def getChannelIdFromName(self, name):
        searchedPage = self.session.get(f"https://www.youtube.com/results?search_query={name}")
        result = re.search(self.findChannelIDre, searchedPage.content.decode('utf-8'))
        return result.group(2), result.group(1)
    #results is a list
    def recursiveVideosExtraction(self, postData, postParametes, results, current=1):
        #use new json format
        videoListPage = self.session.post("https://www.youtube.com/youtubei/v1/browse", headers={}, params=postParametes, data=json.dumps(postData))
        try:
            jsonData = json.loads(videoListPage.text)
        except Exception as e:
            print(e)
            print("Invalid output for json object, YouTube might have changed page layout.\nask me to update the code")
            quit()
        # print(jsonData)
        # with open("test.json", 'w') as f:
        #     json.dump(jsonData, f, indent=4)
        try:
            print(f"Getting more videos list {current}")
            #loop over useful json items
            for infoChunk in jsonData["onResponseReceivedActions"][0]["appendContinuationItemsAction"]["continuationItems"]:
                #video item
                if "gridVideoRenderer" in infoChunk:
                    fullDict = infoChunk["gridVideoRenderer"]
                    results.append ({
                        "Title": fullDict["title"]["runs"][0]["text"], 
                        "Link": f'https://www.youtube.com/watch?v={fullDict["videoId"]}', 
                        "Views": fullDict["shortViewCountText"]["simpleText"], 
                        "Duration": fullDict["thumbnailOverlays"][0]["thumbnailOverlayTimeStatusRenderer"]["text"]["simpleText"]
                        })
                #page over, get next page
                elif "continuationItemRenderer" in infoChunk:
                    postData["continuation"] = infoChunk["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"]
                    self.recursiveVideosExtraction(postData, postParametes, results, current+1)
                    break
        except Exception as e:
            print(e)
            print("Invalid output for json parsing, YouTube might have changed page layout.\nask me to update the code")
            quit()
    def saveToFile(self, channelName, data):
        with open(path.join(_filePath, f"{_FileNamePrefix + channelName}.json"), 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    #get all video data in formatted form, saves to file at script location
    def getVideos(self, channelName):
        (channelName, channelID) = self.getChannelIdFromName(channelName)
        print(f"Found {channelName}!")
        initialVideoPage = self.session.get(f"https://www.youtube.com/channel/{channelID}/videos").text
        videoData = []
        try:
            for (title, videoID, views, length) in re.findall(self.initialVideoDataExtractor, initialVideoPage):
                title = title.replace("\\", "")
                videoData.append({"Title": title, "Link": f"https://www.youtube.com{videoID}", "Views": views, "Duration": length})
        except Exception as e:
            print(e)
            print("Invalid output for video list, YouTube might have changed page layout.\nask me to update the code")
            quit()
        print("Gotten initial video list")
        try:
            #data and params for subsequent json requests
            hl, gl = re.search(self.languageParams, initialVideoPage).groups()
            tokenParam, visitorData, clientName, clientVer = re.search(self.clientData, initialVideoPage).groups()
            continuation = re.search(self.initialContinuationToken, initialVideoPage).group(1)
        except Exception as e:
            print(e)
            print("Invalid output for tokens, YouTube might have changed page layout.\nask me to update the code")
            quit()
        #NOTE: youtube changed this again... find a more viable solution
        print("Gotten tokens")
        data = {
            "context": {
                "client": {
                    "hl": hl,
                    "gl": gl,
                    "visitorData": visitorData,
                    "clientName": clientName,
                    "clientVersion": clientVer,
                }
            },
            "continuation": continuation
        }
        params = {
            "key": tokenParam
        }
        self.recursiveVideosExtraction(data, params, videoData)
        # with open("test.json", 'w') as f:
        #     json.dump(videoData, f, indent=4)
        return channelName, videoData
    def getAndSaveVideos(self, channelName): #overrides changes if there are any, use when no initial file exists
        (channelName, data) = self.getVideos(channelName)
        self.saveToFile(channelName, data)
        print("Done!")
    #run this before getVideos(), in case you want to detect new additions that is
    def detectChanges(self,channelName, AppendNewData = True): #detects changes
        print(f"Checking {channelName}")
        (channelName, _) = self.getChannelIdFromName(channelName)
        olddata = self.readDataFromFile(channelName)
        if olddata is None:
            return None
        print("getting new data... be patient")
        (_ , newdata) = self.getVideos(channelName)
        change = False
        with open(path.join(_filePath, f"{_ReportFilePrefix + channelName}.chagelog"), 'a') as f:
            f.write(f"Script run at {datetime.now()}\n===================================================\n")
            for newSubdata in newdata:
                exists = False
                for oldSubdata in olddata:
                    if (newSubdata["Link"] == oldSubdata["Link"]):
                        #check views:
                        if oldSubdata["Views"] != newSubdata["Views"]:
                            change = True
                            print(f"Views for video '{oldSubdata['Title']}' changed!")
                            f.write(f"Views have changed :\n    Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Old view count: {oldSubdata['Views']} \n    New view count: {newSubdata['Views']}\n")
                        #check if Duration has changed
                        if (oldSubdata["Duration"] != newSubdata["Duration"]):
                            change = True
                            print(f"Duration for video '{oldSubdata['Title']}' has changed!")
                            f.write(f"Duration for video changed:\n    Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Old Duration: {oldSubdata['Duration']} \n    New Duration: {newSubdata['Duration']}\n")
                        #check if Title has changed
                        if (oldSubdata["Title"] != newSubdata["Title"]):
                            change = True
                            print(f"Title for video '{oldSubdata['Title']}' has changed!")
                            f.write(f"Title for video changed:\n    Old Title: {oldSubdata['Title']}\n    Link: {newSubdata['Link']}\n    New Title: {newSubdata['Title']} \n")
                        exists = True
                if not exists:
                    change = True
                    print(f"Newly added: '{newSubdata['Title']}'")
                    f.write(f"Newly Added:\n    Title: {newSubdata['Title']}\n    Link: {newSubdata['Link']}\n    Views: {newSubdata['Views']} \n    Duration: {newSubdata['Duration']}\n")
            for oldSubdata in olddata:
                exists = False
                for newSubdata in newdata:
                    if (newSubdata["Link"] == oldSubdata["Link"]):
                        exists = True
                        break
                if not exists:
                    change = True
                    print(f"Video '{oldSubdata['Title']}' Has been removed or unlisted! Still keeping in data though")
                    f.write(f"Removed or Unlisted:\n    Title: {oldSubdata['Title']}\n    Link: {oldSubdata['Link']}\n    Views: {oldSubdata['Views']} \n    Duration: {oldSubdata['Duration']}\n")
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
                        olddata.insert(index, newSubdata) #preserve by-date order
                    index += 1
                self.saveToFile(channelName, olddata)
        print("Done!")
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--creators", help="Creator names to index (remember to escape spaces in multi-worded names)", required=True, nargs='*')
    args = parser.parse_args()
    sample = Collector()
    print("DONT INTERRUPT THE PROCESS, CHANGES WONT BE SAVED PROPERLY!")
    sleep(2)
    for creator in args.creators:
        if sample.detectChanges(creator) is None:
            print("No data is stored for this channel, or data has bad format. storing data with the getAndSaveVideos() function")
            sample.getAndSaveVideos(creator)
