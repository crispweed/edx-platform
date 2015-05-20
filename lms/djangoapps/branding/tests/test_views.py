# encoding: utf-8
"""Tests of Branding API views. """
import os
import contextlib
import json
from path import path
from django.test import TestCase
from django.core.urlresolvers import reverse
from django.conf import settings

import mock
import ddt
from config_models.models import cache
from branding.models import BrandingApiConfig


# TODO: remove this settings patch once the V3 footer is enabled permanently
@mock.patch.dict(settings.FEATURES, {'ENABLE_FOOTER_V3': True})
@ddt.ddt
class TestFooter(TestCase):
    """Test API end-point for retrieving the footer. """

    # We don't collect static files for unit tests,
    # so the files we expect to exist won't.
    # Instead, we create the files as part
    # of the test setup.  This has two advantages:
    #
    # 1) It's fast.
    # 2) We can easily verify which file was used.
    #
    # To achieve (2), we write the file path as the
    # content of the file, then assert that the response
    # from the server contains the expected path.
    #
    FAKE_STATIC_FILES = [
        (settings.STATIC_ROOT / name).abspath()
        for name in [
            path("js") / settings.FOOTER_JS_STATIC_NAME,
            path("css") / settings.FOOTER_LTR_CSS_STATIC_NAME,
            path("css") / settings.FOOTER_RTL_CSS_STATIC_NAME,
        ]
    ]

    @classmethod
    def setUpClass(cls):
        """Create the fake static files. """
        # Ensure that the static files directory exists
        for folder_path in ["js", "css/footer"]:
            full_path = (settings.STATIC_ROOT / folder_path).abspath()
            if not os.path.exists(full_path):
                os.makedirs(full_path)

        # Create the fake static files
        # The content of each file is just the path to the file,
        # so we can check this in the response we receive
        # from the server.
        for static_path in cls.FAKE_STATIC_FILES:
            with open(static_path, "w") as static_file:
                static_file.write(static_path)

    @classmethod
    def tearDownClass(cls):
        """Remove the fake static files we created. """
        for static_path in cls.FAKE_STATIC_FILES:
            os.remove(static_path)

    def setUp(self):
        """Clear the configuration cache. """
        super(TestFooter, self).setUp()
        cache.clear()

    @ddt.data("", "css", "js", "html")
    def test_feature_flag(self, extension):
        self._set_feature_flag(False)
        resp = self._get_footer(extension=extension)
        self.assertEqual(resp.status_code, 404)

    @ddt.data(
        # Open source version
        (False, "", "application/json; charset=utf-8", "Open edX"),
        (False, "css", "text/css", settings.FOOTER_LTR_CSS_STATIC_NAME),
        (False, "js", "text/javascript", settings.FOOTER_JS_STATIC_NAME),
        (False, "html", "text/html; charset=utf-8", "Open edX"),

        # EdX.org version
        (True, "", "application/json; charset=utf-8", "edX Inc"),
        (True, "css", "text/css", settings.FOOTER_LTR_CSS_STATIC_NAME),
        (True, "js", "text/javascript", settings.FOOTER_JS_STATIC_NAME),
        (True, "html", "text/html; charset=utf-8", "edX Inc"),
    )
    @ddt.unpack
    def test_footer_content_types(self, is_edx_domain, extension, content_type, content):
        self._set_feature_flag(True)
        with self._set_is_edx_domain(is_edx_domain):
            resp = self._get_footer(extension=extension)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], content_type)

        # Check that the response contains the expected content.
        # For rendered content (HTML / json), we just check for some string
        # that we expect to be in the output.  For static files (CSS / JS)
        # we check for the path that we wrote to the file when creating
        # the test fixtures.
        self.assertIn(content, resp.content)

    # TODO: Remove this test case once the V2 version of the footer is removed
    @mock.patch.dict(settings.FEATURES, {
        'ENABLE_FOOTER_V3': False,
        'IS_EDX_DOMAIN': True
    })
    def test_footer_v2(self):
        self._set_feature_flag(True)
        resp = self._get_footer(extension="html")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("edX Inc", resp.content)

    @mock.patch.dict(settings.FEATURES, {'ENABLE_FOOTER_MOBILE_APP_LINKS': True})
    @ddt.data(True, False)
    def test_footer_json(self, is_edx_domain):
        self._set_feature_flag(True)
        with self._set_is_edx_domain(is_edx_domain):
            resp = self._get_footer()

        self.assertEqual(resp.status_code, 200)
        json_data = json.loads(resp.content)
        self.assertTrue(isinstance(json_data, dict))

        # Logo
        self.assertIn("logo_image", json_data)

        # Links
        self.assertIn("navigation_links", json_data)
        for link in json_data["navigation_links"]:
            self.assertIn("name", link)
            self.assertIn("title", link)
            self.assertIn("url", link)

        # Social links
        self.assertIn("social_links", json_data)
        for link in json_data["social_links"]:
            self.assertIn("name", link)
            self.assertIn("title", link)
            self.assertIn("url", link)
            self.assertIn("icon-class", link)

        # Mobile links
        self.assertIn("mobile_links", json_data)
        for link in json_data["mobile_links"]:
            self.assertIn("name", link)
            self.assertIn("title", link)
            self.assertIn("url", link)
            self.assertIn("image", link)

        # Legal links
        self.assertIn("legal_links", json_data)
        for link in json_data["legal_links"]:
            self.assertIn("name", link)
            self.assertIn("title", link)
            self.assertIn("url", link)

        # OpenEdX
        self.assertIn("openedx_link", json_data)
        self.assertIn("url", json_data["openedx_link"])
        self.assertIn("title", json_data["openedx_link"])
        self.assertIn("image", json_data["openedx_link"])

        # Copyright
        self.assertIn("copyright", json_data)

    @ddt.data(
        ("en", "registered trademarks"),
        ("eo", u"régïstéréd trädémärks"),  # Dummy language string
        ("unknown", "registered trademarks"),  # default to English
    )
    @ddt.unpack
    def test_language_override_translation(self, language, expected_copyright):
        self._set_feature_flag(True)

        # Load the footer with the specified language
        resp = self._get_footer(language=language)
        self.assertEqual(resp.status_code, 200)
        json_data = json.loads(resp.content)

        # Verify that the translation occurred
        self.assertIn(expected_copyright, json_data['copyright'])

    @ddt.data(
        ("en", settings.FOOTER_LTR_CSS_STATIC_NAME),
        ("ar", settings.FOOTER_RTL_CSS_STATIC_NAME),
    )
    @ddt.unpack
    def test_language_rtl(self, language, static_path):
        self._set_feature_flag(True)
        resp = self._get_footer(extension="css", language=language)
        self.assertEqual(resp.status_code, 200)

        # Check that the static path is in the content of the response.
        # (we wrote the path into the files when creating them in
        # the test setup).
        self.assertIn(static_path, resp.content)

    def _set_feature_flag(self, enabled):
        """Enable or disable the feature flag for the branding API end-points. """
        config = BrandingApiConfig(enabled=enabled)
        config.save()

    def _get_footer(self, extension="", language=None):
        """Retrieve the footer. """
        url = reverse("branding_footer")

        if extension:
            url = u"{url}.{ext}".format(url=url, ext=extension)

        if language is not None:
            url = u"{url}?language={lang}".format(url=url, lang=language)

        return self.client.get(url)

    @contextlib.contextmanager
    def _set_is_edx_domain(self, is_edx_domain):
        """Configure whether this an EdX-controlled domain. """
        with mock.patch.dict(settings.FEATURES, {'IS_EDX_DOMAIN': is_edx_domain}):
            yield
