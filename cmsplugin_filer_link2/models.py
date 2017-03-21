# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import NoReverseMatch
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from cms.models import CMSPlugin
from cms.models.fields import PageField

from filer.fields.file import FilerFileField
from filer.utils.compatibility import python_2_unicode_compatible

from djangocms_attributes_field.fields import AttributesField


DEFULT_LINK_STYLES = (
    (" ", "Default"),
)

LINK_STYLES = getattr(settings, "FILER_LINK_STYLES", DEFULT_LINK_STYLES)

EXCLUDED_KEYS = ['class', 'href', 'target', ]


@python_2_unicode_compatible
class FilerLink2Plugin(CMSPlugin):
    name = models.CharField(_('name'), max_length=255)
    url = models.CharField(_('url'), blank=True, null=True, max_length=2000,
                           help_text=_('The url must specify the protocol, e.g. https://DOMAIN'))
    page_link = PageField(
        verbose_name=_('page'),
        blank=True,
        null=True,
        help_text=_('A link to a page has priority over urls.'),
        on_delete=models.SET_NULL,
    )
    persistent_page_link = models.CharField(_('internal url'), blank=True, null=True, max_length=2000)
    mailto = models.EmailField(_('mailto'), blank=True, null=True, max_length=254,
             help_text=_('An email address has priority over both pages and urls'))
    link_style = models.CharField(_('link style'), max_length=255,
                choices=LINK_STYLES, default=LINK_STYLES[0][0])
    new_window = models.BooleanField(_('new window?'), default=False,
                help_text=_('Do you want this link to open a new window?'))
    file = FilerFileField(blank=True, null=True, on_delete=models.SET_NULL)
    link_attributes = AttributesField(excluded_keys=EXCLUDED_KEYS, blank=True,
                                      help_text=_('Optional. Adds HTML attributes to the rendered link.'))
    cmsplugin_ptr = models.OneToOneField(
        to=CMSPlugin,
        related_name='%(app_label)s_%(class)s',
        parent_link=True,
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super(FilerLink2Plugin, self).save(*args, **kwargs)
        # delete link health state
        LinkHealthState.objects.filter(link=self).delete()

    def get_link(self):
        if self.file:
            link = self.file.url
        elif self.mailto:
            link = 'mailto:{}'.format(_(self.mailto))
        elif self.url:
            link = _(self.url)
        elif self.page_link:
            try:
                link = self.page_link.get_absolute_url()
            except NoReverseMatch:
                # if this internal link doesn't work anymore, we mark it not reachable
                self.set_linkstate(LinkHealthState.NOT_REACHABLE)
                # return old internal link and send user to 404
                link = self.persistent_page_link
            else:
                # check if the target page has been moved or renamed and update accordingly
                if link != self.persistent_page_link:
                    self.persistent_page_link = link
                    self.save()
        elif self.persistent_page_link:
            # happens when this link instance pointed to a removed page
            self.set_linkstate(LinkHealthState.NOT_REACHABLE)
            link = self.persistent_page_link
        else:
            link = ''
        return link or ''

    def set_linkstate(self, state):
        if state is None:
            LinkHealthState.objects.filter(link=self).delete()
        else:
            LinkHealthState.objects.update_or_create(link=self, defaults={'state': state})

    def get_linkstate(self):
        try:
            return self.linkhealth.state
        except ObjectDoesNotExist:
            return None

@python_2_unicode_compatible
class LinkHealthState(models.Model):

    NOT_REACHABLE = '4xx'
    REDIRECT = '3xx'
    SERVER_ERROR = '5xx'
    BAD_CONFIGURED = 'bad'

    LINK_STATES = (
        (REDIRECT, _('Redirected')),
        (NOT_REACHABLE, _('Not reachable')),
        (SERVER_ERROR, _('Server error')),
        (BAD_CONFIGURED, _('Bad configured')),
    )

    link = models.OneToOneField(FilerLink2Plugin, unique=True, related_name='linkhealth')
    state = models.CharField(max_length=3, choices=LINK_STATES)
    detected = models.DateTimeField(auto_now=True)

    def __str__(self):
        return u'LinkHealthState for: {}'.format(self.link.name)
