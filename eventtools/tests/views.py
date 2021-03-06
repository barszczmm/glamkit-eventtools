# -*- coding: utf-8“ -*-
from datetime import date, time, datetime, timedelta
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase

from eventtools.utils import datetimeify
from eventtools_testapp.models import *

from _fixture import bigfixture, reload_films
from _inject_app import TestCaseWithApp as AppTestCase

class TestViews(AppTestCase):
    
    def setUp(self):
        if hasattr(settings, 'OCCURRENCES_PER_PAGE'):
            self._old_OCCURRENCES_PER_PAGE = settings.OCCURRENCES_PER_PAGE
        settings.OCCURRENCES_PER_PAGE = 20
        super(TestViews, self).setUp()
    
    def tearDown(self):
        if hasattr(self, '_old_OCCURRENCES_PER_PAGE'):
            settings.OCCURRENCES_PER_PAGE = self._old_OCCURRENCES_PER_PAGE
        else:
            delattr(settings, 'OCCURRENCES_PER_PAGE')
        super(TestViews, self).tearDown()
    
    def test_purls(self):
        """
        An occurrence has a pURL based on its id.
        You can view a page for an occurrence.
        """
        
        e = self.daily_tour
        o = e.occurrences.all()[0]
        
        #occurrence page
        ourl = reverse('occurrence', args=(o.id,))
        self.assertEqual(o.get_absolute_url(), ourl)
        self.assertTrue(str(o.id) in ourl)
        r1 = self.client.get(ourl)
        self.assertEqual(r1.status_code, 200)
        
        self.assertContains(r1, "Daily Tour") 
        self.assertContains(r1, "1&nbsp;January&nbsp;2010")
        self.assertNotContains(r1, "00:00")
        self.assertNotContains(r1, "12am")
        self.assertNotContains(r1, "midnight")

        e2 = self.weekly_talk
        ourl = reverse('occurrence', args=(e2.occurrences.all()[0].id,))
        r1 = self.client.get(ourl)
        self.assertContains(r1, "Weekly Talk")
        self.assertContains(r1, "1&nbsp;January&nbsp;2010, 10am&ndash;noon")
    
    def test_list_view(self):
        """
        You can view a paginated list of occurrences for an event qs, following a given day, using ?startdate=2010-10-22&page=2.
        Each page shows n=20 occurrences and paginates by that amount.
        The occurrences are in chronological order.
        The times of all-day events do not appear.
        If there are no events in a given day, the day is not shown.
        The occurrences are grouped by day (and thus a day's occurrences may span several pages - this makes computation easier).
        TODO if a day is unfinished, show 'more on page n+1'..
        If there are no events in a given page, a 'no events match' message is shown.
        """
        url = reverse('occurrence_list',)
        r = self.client.get(url,  {'startdate':'2010-01-01'})
        self.assertEqual(r.context['occurrence_pool'].count(), 109)
        self.assertEqual(len(r.context['occurrence_page']), 20)
        self.assertEqual(r.context['occurrence_page'][0].start.date(), date(2010,1,1))
            
        #check results in chrono order
        d = r.context['occurrence_pool'][0].start
        for occ in r.context['occurrence_pool']:
            self.assertTrue(occ.start >= d)
            d = occ.start
        
        #should have some pagination (6 pages)
        self.assertNotContains(r, "Earlier") #it's the first page
        self.assertContains(r, "Later")
        self.assertContains(r, "Showing 1&ndash;20&nbsp;of&nbsp;109")

        self.assertContains(r, "Friday, 1 January 2010", 1) #only print the date once
        self.assertNotContains(r, "Saturday, 2 January 2010") #there are no events
        self.assertContains(r, "Sunday, 3 January 2010", 1) #only print the date once

        self.assertContains(r, "10am&ndash;&#8203;noon")
        self.assertNotContains(r, "12am")# these are all-day
        self.assertNotContains(r, "00:00")# these are all-day
        self.assertNotContains(r, "midnight") # these are all-day
    
        #doesn't matter how far back you go.
        r2 = self.client.get(url,  {'startdate':'2000-01-01'})
        self.assertEqual(list(r.context['occurrence_pool']), list(r2.context['occurrence_pool']))
    
        #links
        o = r.context['occurrence_page'][0]
        ourl = reverse('occurrence', args=(o.id,))
        self.assertContains(r, ourl)
        
        #show a 'not found' message
        r = self.client.get(url, {'startdate':'2020-01-01'})
        self.assertEqual(r.context['occurrence_page'].count(), 0)
        self.assertContains(r, "Sorry, no events were found")
        self.assertNotContains(r, "Earlier")
        self.assertNotContains(r, "Later")
        self.assertNotContains(r, "Showing")
        self.assertEqual(r.status_code, 200) #not 404
        
        
    def test_date_range_view(self):
        """
        You can show all occurrences between two days on one page, by adding ?enddate=2010-10-24. Pagination adds or subtracts the difference in days (+1 - consider a single day) to the range.
        For some ranges, pagination is by a different amount:
        TODO: Precisely a month (paginate by month)
        TODO: Precisely a year (paginate by year)
        """

        url = reverse('occurrence_list',)
        r = self.client.get(url,  {'startdate':'2010-01-01', 'enddate':'2010-01-05'})
        self.assertEqual(r.context['occurrence_pool'].count(), 109)
        self.assertEqual(len(r.context['occurrence_page']), 5)
        self.assertEqual(r.context['occurrence_page'][0].start.date(), date(2010,1,1))
        self.assertEqual(r.context['occurrence_page'].reverse()[0].start.date(), date(2010,1,5))

        self.assertContains(r, "Showing 1&ndash;5&nbsp;January&nbsp;2010")
        self.assertContains(r, '<a href="?startdate=2009-12-27&amp;enddate=2009-12-31">Earlier</a>')
        self.assertContains(r, '<a href="?startdate=2010-01-06&amp;enddate=2010-01-10">Later</a>')

        r = self.client.get(url,  {'startdate':'2010-01-01', 'enddate':'2010-01-31'})
        self.assertContains(r, "Showing January&nbsp;2010")
        # self.assertContains(r, '<a href="?datefrom=2009-12-01&dateto=2009-12-31">December 2009</a>')
        # self.assertContains(r, '<a href="?datefrom=2010-02-01&dateto=2010-02-28">February 2010</a>')

    def test_event_view(self):
        """
        You can view a paginated list of occurrences for an event.
        """
        #event page
        e = self.daily_tour
        eurl = reverse('event', kwargs={'event_slug': e.slug})
        self.assertEqual(e.get_absolute_url(), eurl)
        r3 = self.client.get(eurl, {'page': 2})
        self.assertEqual(r3.status_code, 200)
        
        #should have some pagination (3 pages)
        self.assertEqual(r3.context['occurrence_page'].count(), 20)
        self.assertContains(r3, "Earlier")
        self.assertContains(r3, "Later")
        self.assertContains(r3, "Showing 21&ndash;40&nbsp;of&nbsp;49")

    def test_ical(self):
        """
        You can view an ical for an occurrence.
        The ical is linked from the occurrence page.
        You can view an ical for a collection of occurrences.
        (TODO: do large icals perform well? If not we might have to make it a feed.)
        """
        e = self.daily_tour
        o = e.occurrences.all()[0]
        
        o_url = reverse('occurrence', kwargs={'occurrence_id': o.id })
        o_ical_url = reverse('occurrence_ical', kwargs={'occurrence_id': o.id })
        r = self.client.get(o_ical_url)
        self.assertEqual(r.status_code, 200)
                
        self.assertContains(r, "BEGIN:VCALENDAR", 1)
        self.assertContains(r, "BEGIN:VEVENT", 1)

        self.assertContains(r, "SUMMARY:Daily Tour", 1)
        self.assertContains(r, "DTSTART;VALUE=DATE:20100101", 1)
        self.assertContains(r, "DTEND;VALUE=DATE:20100101", 1)
        self.assertContains(r, "URL:http://testserver%s" % o_url, 1)
        # etc.
    
        #Multiple occurrences
        e_ical_url = reverse('event_ical', kwargs={'event_slug': e.slug })
        r = self.client.get(e_ical_url)
        self.assertEqual(r.status_code, 200)
                
        self.assertContains(r, "BEGIN:VCALENDAR", 1)
        self.assertContains(r, "BEGIN:VEVENT", 49)
        self.assertContains(r, "SUMMARY:Daily Tour", 49)
        self.assertContains(r, "DTSTART;VALUE=DATE:20100101", 1)
        self.assertContains(r, "DTEND;VALUE=DATE:20100101", 1)

    def test_hcal(self):
        """
        The occurrence page uses hCalendar microformat.
        The occurrence listing page uses hCalendar microformat.
        """

    def test_feeds(self):
        """
        You can view an RSS feed for an iterable of occurrences.
        """

        """
        CALENDAR

        A template tag shows a calendar of eventoccurrences in a given month.

        Calendar's html gives classes for 'today', 'date selection', 'has_events', 'no_events', 'prev_month' 'next_month'.

        Calendar optionally shows days.

        Calendar optionally hides leading or trailing empty weeks.

        Calendar can optionally navigate to prev/next months, which set a start_date to the 1st of the next month.



        API (TODO)

        """