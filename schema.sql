--Schematic for Sqlite database
--Foreign key constraint enforcement;
PRAGMA FOREIGN_KEYS = on;
--Assuming channel id's are constant and unique;
CREATE TABLE IF NOT EXISTS channel ( channel_id TEXT UNIQUE NOT NULL, channel_name TEXT NOT NULL );
CREATE TABLE IF NOT EXISTS basic_video_data (video_title TEXT NOT NULL,  video_link TEXT UNIQUE NOT NULL, video_views TEXT, video_duration TEXT, video_availability INTEGER NOT NULL, channel_id TEXT NOT NULL, FOREIGN KEY (channel_id) REFERENCES channel (channel_id) ON UPDATE CASCADE ON DELETE CASCADE );