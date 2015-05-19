"""
Script for collecting a list of videos that are not set to download.

On default mongo, it collects all videos. On split mongo, collects videos on published courses.

"""
from bson.objectid import ObjectId
from pymongo import MongoClient
from pymongo.read_preferences import ReadPreference


client = MongoClient()
db = client['edxapp']

# This is how you connect to a replica with username/password:
# uri = 'mongodb://user_name:my%20url%20encoded%20password@example.com:27017/stuff'
# client = MongoClient(uri)
# db = client['db-instance']

filename_split_mongo = "split_mongo.tsv"
filename_default_mongo = "draft_mongo.tsv"


def clean_file(filename):
    """
    Remove given file and start a new csv
    """
    with open(filename, 'w') as f:
        f.write("org\tcourse_name\tvideo_id\tvideo_display_name\tvideo_download_allowed\thtml5_sources\n")


def get_set_metadata_field(field, mongo_doc):
    """
    Will return "None" if the given metadata field is not set. Otherwise, return the field's value.
    """
    if field in mongo_doc:
        return mongo_doc[field]
    else:
        return "None"


def write_to_file(output_file, org, course_name, video_id, video_display_name, video_download_allowed, html5_sources):
        output_file.write("{org}\t{course_name}\t{video_id}\t{video_display_name}\t{video_download_allowed}\t{html5_sources}\n".format(
            org=org,
            course_name=course_name,
            video_id=video_id,
            video_display_name=video_display_name,
            video_download_allowed=video_download_allowed,
            html5_sources=html5_sources
        )
        )


def get_draft_mongo_data(video_download_allowed=False, html5_sources_missing_only=None):
    """
    Against the 'draft' (aka 'old') mongo store, produce a list of videos that are flagged with download as
    False, or, when specified, all videos where html5 sources are missing
    """
    # Old modulestore
    # Will produce a tsv with org, course name, and video GUID
    with open(filename_default_mongo, 'a') as output_file:
        for i in db['modulestore'].find(
                {"metadata.download_video" : video_download_allowed, "_id.revision": None},
                {"_id.course": 1, "metadata.display_name": 1, "metadata.html5_sources": 1}
        ):
            display_name = get_set_metadata_field(u'display_name', i[u'metadata'])
            html5_sources = get_set_metadata_field(u'html5_sources', i[u'metadata'])
            if html5_sources_missing_only and html5_sources:
                # If we only want to know about videos with missing html5 sources, then don't write anything if
                # there are html5 sources
                pass
            else:
                write_to_file(
                    output_file=output_file,
                    org=(i[u'_id'][u'org']).encode("utf-8"),
                    course_name=(i[u'_id'][u'course']).encode("utf-8"),
                    video_id=(i[u'_id']['name']).encode("utf-8"),
                    video_display_name=display_name.encode("utf-8"),
                    video_download_allowed=video_download_allowed,
                    html5_sources=html5_sources
                )


def get_split_mongo_data(video_download_allowed=False, html5_sources_missing_only=None):
    """
    Against the 'split' (aka 'new') mongo store, produce a list of videos that are flagged with download as
    False, or, when specified, all videos where html5 sources are missing

    """
    published_courses = []
    for i in db['modulestore.active_versions'].find(
            {"versions.published-branch": {"$exists": True}},
            {"_id": 0, "versions.published-branch": 1,
             "course": 1,
             "org": 1}
    ):
        published_courses.append(i)

    for published_course in published_courses:
        # Get all the block sets for a given course as dicts
        for i in db['modulestore.structures'].find(
                {
                    "blocks.fields.download_video": video_download_allowed,
                    "_id": published_course[u'versions'][u'published-branch']
                }
        ):
            # Given one block set, now get all the blocks (could contain multiple video xblocks)
            for b in i[u'blocks']:
                # Given one xblock, only do something with it if it is a video xblock
                # Since the above query returns ALL xblocks, regardless of whether or not they allow downloads for
                # videos, we filter again for download_video == False
                # if b[u'block_type'] == u'video' and b[u'fields'][u'download_video'] == video_download_allowed:
                if b[u'block_type'] == u'video':
                    video_download_flag = get_set_metadata_field(u'download_video', b[u'fields'])
                    # The download flag is only stored if someone explicitly sets advanced settings on a video.
                    # When that doesn't happen, it is effectively set to false; just doesn't exist that way (or, at all)
                    # in mongo.
                    if video_download_flag == "None":
                        video_download_effective = False
                    else:
                        video_download_effective = video_download_flag
                    if video_download_effective == video_download_allowed:
                        html5_sources = get_set_metadata_field(u'html5_sources', b[u'fields'])
                        if html5_sources_missing_only and html5_sources:
                            # If we only want to know about videos with missing html5 sources, then don't write anything if
                            # there are html5 sources
                            pass
                        else:
                            display_name = get_set_metadata_field(u'display_name', b[u'fields'])
                            with open(filename_split_mongo, 'a') as output_file:
                                write_to_file(
                                    output_file=output_file,
                                        org=(published_course[u'org']).encode("utf-8"),
                                        course_name=(published_course[u'course']).encode("utf-8"),
                                        video_id=(b[u'block_id']).encode("utf-8"),
                                        video_display_name=display_name.encode("utf-8"),
                                        video_download_allowed=video_download_flag,
                                        html5_sources=html5_sources
                                    )

# MAIN

# remove any old output files
clean_file(filename_split_mongo)
clean_file(filename_default_mongo)

# Find videos where download is not allowed
get_draft_mongo_data(video_download_allowed=False)
get_split_mongo_data(video_download_allowed=False)

# Find videos where download is allowed, but there is nothing to download
get_draft_mongo_data(video_download_allowed=True, html5_sources_missing_only=True)
get_split_mongo_data(video_download_allowed=True, html5_sources_missing_only=True)
