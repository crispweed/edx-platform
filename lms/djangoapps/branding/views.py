"""Views for the branding app. """
import logging

from path import path
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse, Http404
from django.utils import translation
from staticfiles.finders import find as staticfiles_find
from staticfiles.storage import staticfiles_storage
from django.shortcuts import redirect
from django_future.csrf import ensure_csrf_cookie
from sendfile import sendfile

from edxmako.shortcuts import render_to_response
import student.views
from student.models import CourseEnrollment
import courseware.views
from microsite_configuration import microsite
from edxmako.shortcuts import marketing_link
from util.cache import cache_if_anonymous
from util.json_request import JsonResponse
from branding.models import BrandingApiConfig
import branding.api as branding_api


log = logging.getLogger(__name__)


def get_course_enrollments(user):
    """
    Returns the course enrollments for the passed in user within the context of a microsite, that
    is filtered by course_org_filter
    """
    enrollments = CourseEnrollment.enrollments_for_user(user)
    microsite_org = microsite.get_value('course_org_filter')
    if microsite_org:
        site_enrollments = [
            enrollment for enrollment in enrollments if enrollment.course_id.org == microsite_org
        ]
    else:
        site_enrollments = [
            enrollment for enrollment in enrollments
        ]
    return site_enrollments


@ensure_csrf_cookie
@cache_if_anonymous()
def index(request):
    '''
    Redirects to main page -- info page if user authenticated, or marketing if not
    '''

    if settings.COURSEWARE_ENABLED and request.user.is_authenticated():
        # For microsites, only redirect to dashboard if user has
        # courses in his/her dashboard. Otherwise UX is a bit cryptic.
        # In this case, we want to have the user stay on a course catalog
        # page to make it easier to browse for courses (and register)
        if microsite.get_value(
            'ALWAYS_REDIRECT_HOMEPAGE_TO_DASHBOARD_FOR_AUTHENTICATED_USER',
            settings.FEATURES.get('ALWAYS_REDIRECT_HOMEPAGE_TO_DASHBOARD_FOR_AUTHENTICATED_USER', True)
        ):
            return redirect(reverse('dashboard'))

    if settings.FEATURES.get('AUTH_USE_CERTIFICATES'):
        from external_auth.views import ssl_login
        # Set next URL to dashboard if it isn't set to avoid
        # caching a redirect to / that causes a redirect loop on logout
        if not request.GET.get('next'):
            req_new = request.GET.copy()
            req_new['next'] = reverse('dashboard')
            request.GET = req_new
        return ssl_login(request)

    enable_mktg_site = microsite.get_value(
        'ENABLE_MKTG_SITE',
        settings.FEATURES.get('ENABLE_MKTG_SITE', False)
    )

    if enable_mktg_site:
        return redirect(settings.MKTG_URLS.get('ROOT'))

    domain = request.META.get('HTTP_HOST')

    # keep specialized logic for Edge until we can migrate over Edge to fully use
    # microsite definitions
    if domain and 'edge.edx.org' in domain:
        return redirect(reverse("signin_user"))

    #  we do not expect this case to be reached in cases where
    #  marketing and edge are enabled
    return student.views.index(request, user=request.user)


@ensure_csrf_cookie
@cache_if_anonymous()
def courses(request):
    """
    Render the "find courses" page. If the marketing site is enabled, redirect
    to that. Otherwise, if subdomain branding is on, this is the university
    profile page. Otherwise, it's the edX courseware.views.courses page
    """
    enable_mktg_site = microsite.get_value(
        'ENABLE_MKTG_SITE',
        settings.FEATURES.get('ENABLE_MKTG_SITE', False)
    )

    if enable_mktg_site:
        return redirect(marketing_link('COURSES'), permanent=True)

    if not settings.FEATURES.get('COURSES_ARE_BROWSABLE'):
        raise Http404

    #  we do not expect this case to be reached in cases where
    #  marketing is enabled or the courses are not browsable
    return courseware.views.courses(request)


def _render_footer_html():
    """Render the footer as HTML. """
    return (
        render_to_response("footer-edx-v3.html")
        if settings.FEATURES.get("IS_EDX_DOMAIN", False)
        else render_to_response("footer.html")
    )


def _footer_css_name():
    """Return the name of the footer CSS static file.

    This takes into account:
    1) Whether asset pipelining is being used (handles both prod and local dev)
    2) Text direction (right-to-left support)

    Returns: unicode

    """
    bidi = 'rtl' if translation.get_language_bidi() else 'ltr'
    version = 'edx' if settings.FEATURES.get('IS_EDX_DOMAIN') else 'openedx'
    css_name = settings.FOOTER_CSS[version][bidi]

    # In production, the asset pipeline copies compiled sass
    # to a css folder.  Unfortunately, this doesn't happen
    # in devstack, so we load the version of the CSS that
    # hasn't yet gone through the asset pipeline.
    return (
        u"sass/{name}" if settings.DEBUG
        else u"css/{name}"
    ).format(name=css_name)


def _send_footer_static(request, name):
    """Send static files for the footer.

    Send static files required for rendering the footer
    client-side (JavaScript and CSS).

    Ordinarily, clients would load static resources like
    this from /static/ URLs.  In production, these URLs always
    include cache-busting hashes.  Since these URLs are meant
    to be included directly in the DOM, we want a URL
    that is always available (e.g. /api/v1/branding/footer.css).

    On the other hand, we *don't* want to serve these
    files directy through Django, because nginx is much
    faster at this.

    For this reason, we use `django-sendfile` as a compromise.
    In production, this will use the "X-Accel-Redirect" header
    to trigger an internal redirect to the static file.
    That way, Django can resolve the path, but nginx still
    serves the file.

    If the file can't be found, this will return a 404.

    Arguments:
        request (HttpRequest)
        name (unicode): The name of the static file to load
            (relative to `settings.STATIC_ROOT`)

    Returns:
        HttpResponse
    """
    # In production, we will load assets from the STATIC_ROOT
    # directory.  In local development, we don't run collectstatic,
    # so we need to find the files in their original locations.
    path = (
        staticfiles_find(name) if settings.DEBUG
        else staticfiles_storage.path(name)
    )
    if path is None:
        raise Http404

    return sendfile(request, path)


def footer(request, extension="json"):
    """Retrieve the branded footer.

    This end-point provides information about the site footer,
    allowing for consistent display of the footer across other sites
    (for example, on the marketing site and blog).

    It can be used in one of two ways:
    1) The client renders the footer from a JSON description.
    2) The client includes JavaScript and CSS from this end-point,
        and the JavaScript renders the footer within the DOM.

    In case (2), we assume that the following dependencies
    are included on the page:
    a) JQuery (same version as used in edx-platform)
    b) font-awesome (same version as used in edx-platform)

    Example: Retrieving the footer as JSON

        GET /api/branding/v1/footer

        {
            "navigation_links": [
                {
                  "url": "http://example.com/about",
                  "name": "about",
                  "title": "About"
                },
                # ...
            ],
            "social_links": [
                {
                    "url": "http://example.com/social",
                    "name": "facebook",
                    "icon-class": "fa-facebook-square",
                    "title": "Facebook"
                },
                # ...
            ],
            "mobile_links": [
                {
                    "url": "http://example.com/android",
                    "name": "google",
                    "image": "http://example.com/google.png",
                    "title": "Google"
                },
                # ...
            ],
            "legal_links": [
                {
                    "url": "http://example.com/terms-of-service.html",
                    "name": "terms_of_service",
                    "title': "Terms of Service"
                },
                # ...
            ],
            "openedx_link": {
                "url": "http://open.edx.org",
                "title": "Powered by Open edX",
                "image": "http://example.com/openedx.png"
            },
            "logo_image": "http://example.com/static/images/default-theme/logo.png",
            "copyright": "EdX, Open edX, and the edX and Open edX logos are \
                registered trademarks or trademarks of edX Inc."
        }


    Example: Including the footer within a page

        <html>
            <head>
                <!-- Include JQuery and FontAwesome here -->
                <title>Footer API Test</title>
            </head>
            <body>
                <h1>Footer API Test</h1>
                <p>This is a test of the footer API.</p>
                <div id="edx-branding-footer"></div>

                <!-- Load this at the bottom of the page so it doesn't block the DOM from loading -->
                <link type="text/css" rel="stylesheet" href="http://example.com/api/v1/branding/footer.css"></link>
                <script type="text/javascript" src="http://example.com/api/v1/branding/footer.js"></script>
            </body>
        </html>


    Example: Retrieving the footer in a particular language

    GET /api/branding/v1/footer?language=ar
    The returned response will use Arabic translation strings

    GET /api/branding/v1/footer.css?language=ar
    The returned CSS will use right-to-left styling.

    """
    # Feature flag enables this end-point
    if not BrandingApiConfig.current().enabled:
        raise Http404

    # Override the language if necessary
    language = request.GET.get('language')
    if language is not None:
        translation.activate(language)

    # Render the footer information based on the extension
    if extension == "json":
        footer_dict = branding_api.get_footer(is_secure=request.is_secure())
        return JsonResponse(footer_dict, 200, content_type="application/json; charset=utf-8")
    elif extension == "html":
        content = _render_footer_html()
        return HttpResponse(content, status=200)
    elif extension == "css":
        return _send_footer_static(request, _footer_css_name())
    elif extension == "js":
        return _send_footer_static(request, path("js") / settings.FOOTER_JS)
    else:
        raise Http404
