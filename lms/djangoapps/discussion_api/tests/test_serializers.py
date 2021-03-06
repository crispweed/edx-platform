"""
Tests for Discussion API serializers
"""
import ddt
import httpretty

from discussion_api.serializers import ThreadSerializer, get_context
from discussion_api.tests.utils import CommentsServiceMockMixin
from django_comment_common.models import (
    FORUM_ROLE_ADMINISTRATOR,
    FORUM_ROLE_COMMUNITY_TA,
    FORUM_ROLE_MODERATOR,
    FORUM_ROLE_STUDENT,
    Role,
)
from student.tests.factories import UserFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory
from openedx.core.djangoapps.course_groups.tests.helpers import CohortFactory


@ddt.ddt
class ThreadSerializerTest(CommentsServiceMockMixin, ModuleStoreTestCase):
    """Tests for ThreadSerializer."""
    def setUp(self):
        super(ThreadSerializerTest, self).setUp()
        httpretty.reset()
        httpretty.enable()
        self.addCleanup(httpretty.disable)
        self.maxDiff = None  # pylint: disable=invalid-name
        self.user = UserFactory.create()
        self.register_get_user_response(self.user)
        self.course = CourseFactory.create()
        self.author = UserFactory.create()

    def create_role(self, role_name, users, course=None):
        """Create a Role in self.course with the given name and users"""
        course = course or self.course
        role = Role.objects.create(name=role_name, course_id=course.id)
        role.users = users

    def make_cs_thread(self, thread_data=None):
        """
        Create a dictionary containing all needed thread fields as returned by
        the comments service with dummy data overridden by thread_data
        """
        ret = {
            "id": "dummy",
            "course_id": unicode(self.course.id),
            "commentable_id": "dummy",
            "group_id": None,
            "user_id": str(self.author.id),
            "username": self.author.username,
            "anonymous": False,
            "anonymous_to_peers": False,
            "created_at": "1970-01-01T00:00:00Z",
            "updated_at": "1970-01-01T00:00:00Z",
            "thread_type": "discussion",
            "title": "dummy",
            "body": "dummy",
            "pinned": False,
            "closed": False,
            "abuse_flaggers": [],
            "votes": {"up_count": 0},
            "comments_count": 0,
            "unread_comments_count": 0,
            "children": [],
            "resp_total": 0,
        }
        if thread_data:
            ret.update(thread_data)
        return ret

    def serialize(self, thread):
        """
        Create a serializer with an appropriate context and use it to serialize
        the given thread, returning the result.
        """
        return ThreadSerializer(thread, context=get_context(self.course, self.user)).data

    def test_basic(self):
        thread = {
            "id": "test_thread",
            "course_id": unicode(self.course.id),
            "commentable_id": "test_topic",
            "group_id": None,
            "user_id": str(self.author.id),
            "username": self.author.username,
            "anonymous": False,
            "anonymous_to_peers": False,
            "created_at": "2015-04-28T00:00:00Z",
            "updated_at": "2015-04-28T11:11:11Z",
            "thread_type": "discussion",
            "title": "Test Title",
            "body": "Test body",
            "pinned": True,
            "closed": False,
            "abuse_flaggers": [],
            "votes": {"up_count": 4},
            "comments_count": 5,
            "unread_comments_count": 3,
        }
        expected = {
            "id": "test_thread",
            "course_id": unicode(self.course.id),
            "topic_id": "test_topic",
            "group_id": None,
            "group_name": None,
            "author": self.author.username,
            "author_label": None,
            "created_at": "2015-04-28T00:00:00Z",
            "updated_at": "2015-04-28T11:11:11Z",
            "type": "discussion",
            "title": "Test Title",
            "raw_body": "Test body",
            "pinned": True,
            "closed": False,
            "following": False,
            "abuse_flagged": False,
            "voted": False,
            "vote_count": 4,
            "comment_count": 5,
            "unread_comment_count": 3,
        }
        self.assertEqual(self.serialize(thread), expected)

    def test_group(self):
        cohort = CohortFactory.create(course_id=self.course.id)
        serialized = self.serialize(self.make_cs_thread({"group_id": cohort.id}))
        self.assertEqual(serialized["group_id"], cohort.id)
        self.assertEqual(serialized["group_name"], cohort.name)

    @ddt.data(
        (FORUM_ROLE_ADMINISTRATOR, True, False, True),
        (FORUM_ROLE_ADMINISTRATOR, False, True, False),
        (FORUM_ROLE_MODERATOR, True, False, True),
        (FORUM_ROLE_MODERATOR, False, True, False),
        (FORUM_ROLE_COMMUNITY_TA, True, False, True),
        (FORUM_ROLE_COMMUNITY_TA, False, True, False),
        (FORUM_ROLE_STUDENT, True, False, True),
        (FORUM_ROLE_STUDENT, False, True, True),
    )
    @ddt.unpack
    def test_anonymity(self, role_name, anonymous, anonymous_to_peers, expected_serialized_anonymous):
        """
        Test that content is properly made anonymous.

        Content should be anonymous iff the anonymous field is true or the
        anonymous_to_peers field is true and the requester does not have a
        privileged role.

        role_name is the name of the requester's role.
        anonymous is the value of the anonymous field in the content.
        anonymous_to_peers is the value of the anonymous_to_peers field in the
          content.
        expected_serialized_anonymous is whether the content should actually be
          anonymous in the API output when requested by a user with the given
          role.
        """
        self.create_role(role_name, [self.user])
        serialized = self.serialize(
            self.make_cs_thread({"anonymous": anonymous, "anonymous_to_peers": anonymous_to_peers})
        )
        actual_serialized_anonymous = serialized["author"] is None
        self.assertEqual(actual_serialized_anonymous, expected_serialized_anonymous)

    @ddt.data(
        (FORUM_ROLE_ADMINISTRATOR, False, "staff"),
        (FORUM_ROLE_ADMINISTRATOR, True, None),
        (FORUM_ROLE_MODERATOR, False, "staff"),
        (FORUM_ROLE_MODERATOR, True, None),
        (FORUM_ROLE_COMMUNITY_TA, False, "community_ta"),
        (FORUM_ROLE_COMMUNITY_TA, True, None),
        (FORUM_ROLE_STUDENT, False, None),
        (FORUM_ROLE_STUDENT, True, None),
    )
    @ddt.unpack
    def test_author_labels(self, role_name, anonymous, expected_label):
        """
        Test correctness of the author_label field.

        The label should be "staff", "staff", or "community_ta" for the
        Administrator, Moderator, and Community TA roles, respectively, but
        the label should not be present if the thread is anonymous.

        role_name is the name of the author's role.
        anonymous is the value of the anonymous field in the content.
        expected_label is the expected value of the author_label field in the
          API output.
        """
        self.create_role(role_name, [self.author])
        serialized = self.serialize(self.make_cs_thread({"anonymous": anonymous}))
        self.assertEqual(serialized["author_label"], expected_label)

    def test_following(self):
        thread_id = "test_thread"
        self.register_get_user_response(self.user, subscribed_thread_ids=[thread_id])
        serialized = self.serialize(self.make_cs_thread({"id": thread_id}))
        self.assertEqual(serialized["following"], True)

    def test_abuse_flagged(self):
        serialized = self.serialize(self.make_cs_thread({"abuse_flaggers": [str(self.user.id)]}))
        self.assertEqual(serialized["abuse_flagged"], True)

    def test_voted(self):
        thread_id = "test_thread"
        self.register_get_user_response(self.user, upvoted_ids=[thread_id])
        serialized = self.serialize(self.make_cs_thread({"id": thread_id}))
        self.assertEqual(serialized["voted"], True)
