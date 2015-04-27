
import datetime
import json

from ..helpers import EventsTestMixin
from .test_video_module import VideoBaseTest

from opaque_keys.edx.keys import UsageKey, CourseKey


class VideoEventsTest(EventsTestMixin, VideoBaseTest):
    """ Test video player event emission """

    def test_video_control_events(self):
        """
        Scenario: Video component is rendered in the LMS in Youtube mode without HTML5 sources
        Given the course has a Video component in "Youtube" mode
        And I play the video
        And I watch 5 seconds of it
        And I pause the video
        Then a "load_video" event is emitted
        And a "play_video" event is emitted
        And a "pause_video" event is emitted
        """
        load_video_promise = self.create_event_of_type_promise('load_video')

        self.navigate_to_video()

        load_video_event = load_video_promise.fulfill()

        self.assert_payload_contains_ids(load_video_event)
        self.assert_event_matches({'event_type': 'load_video'}, load_video_event)

        play_video_promise = self.create_event_of_type_promise('play_video')
        pause_video_promise = self.create_event_of_type_promise('pause_video')

        self.video.click_player_button('play')
        self.video.wait_for_position('0:05')
        self.video.click_player_button('pause')

        play_video_event = play_video_promise.fulfill()
        self.assert_valid_control_event_at_time(play_video_event, 0)

        pause_video_event = pause_video_promise.fulfill()
        self.assert_valid_control_event_at_time(pause_video_event, self.video.seconds)

    def assert_payload_contains_ids(self, video_event):
        """
        Video events should all contain "id" and "code" attributes in their payload.

        This function asserts that those fields are present and have correct values.
        """
        video_descriptors = self.course_fixture.get_nested_xblocks(category='video')
        video_desc = video_descriptors[0]
        video_locator = UsageKey.from_string(video_desc.locator)

        expected_event_pattern = {
            'event': {
                'id': video_locator.html_id(),
                'code': '3_yD_cEKoCk'
            }
        }
        self.assert_event_matches(expected_event_pattern, video_event)

    def assert_valid_control_event_at_time(self, video_event, time_in_seconds):
        """
        Video control events should contain valid ID fields and a valid "currentTime" field.

        This function asserts that those fields are present and have correct values.
        """
        self.assert_payload_contains_ids(video_event)
        current_time = json.loads(video_event['event'])['currentTime']
        self.assertAlmostEqual(current_time, time_in_seconds, delta=0.5)

    def test_strict_event_format(self):
        """
        This test makes a very strong assertion about the fields present in events. The goal of it is to ensure that new
        fields are not added to all events mistakenly. It should be the only existing test that is updated when new top
        level fields are added to all events.
        """

        self.navigate_to_video()

        load_video_event = self.create_event_of_type_promise('load_video').fulfill()

        # Validate the event payload
        self.assert_payload_contains_ids(load_video_event)

        # We cannot predict the value of these fields so we make weaker assertions about them
        dynamic_string_fields = (
            'accept_language',
            'agent',
            'host',
            'ip',
            'event',
            'session'
        )
        for field in dynamic_string_fields:
            self.assert_field_type(load_video_event, field, basestring)
            self.assertIn(field, load_video_event, '{0} not found in the root of the event'.format(field))
            del load_video_event[field]

        # A weak assertion for the timestamp as well
        self.assert_field_type(load_video_event, 'time', datetime.datetime)
        del load_video_event['time']

        # Note that all unpredictable fields have been deleted from the event at this point

        course_key = CourseKey.from_string(self.course_id)
        static_fields_pattern = {
            'context': {
                'course_id': unicode(course_key),
                'org_id': course_key.org,
                'path': '/event',
                'user_id': self.user_info['user_id']
            },
            'event_source': 'browser',
            'event_type': 'load_video',
            'username': self.user_info['username'],
            'page': self.browser.current_url,
            'referer': self.browser.current_url,
            'name': 'load_video',
        }
        self.assert_event_matches(static_fields_pattern, load_video_event, strict=True)

    def assert_field_type(self, event_dict, field, field_type):
        self.assertIn(field, event_dict, '{0} not found in the root of the event'.format(field))
        self.assertTrue(
            isinstance(event_dict[field], field_type),
            'Expected "{key}" to be a "{field_type}", but it has the value "{value}" of type "{t}"'.format(
                key=field,
                value=event_dict[field],
                t=type(event_dict[field]),
                field_type=field_type,
            )
        )