# −*− coding: UTF−8 −*−
from django.db import models, transaction
from django.db.models.base import ModelBase
from django.utils.translation import ugettext, ugettext_lazy as _
from django.core import exceptions

from dateutil import rrule

from rule import Rule, FREQUENCY_TIME_MAP

from nosj.fields import JSONField

from eventtools.utils import datetimeify
from eventtools.conf import settings
from eventtools.utils.pprint_timespan import (
    pprint_datetime_span, pprint_date_span)

from datetime import date, time, datetime, timedelta

class GeneratorModel(models.Model):
    """
    A GeneratorModel generates Occurrences according to given rules. For example:
        • One occurrence, Tuesday 18th August 2010, 1500-1600
        • Every Tuesday, starting Tuesday 18th August 2012.
        • Every weekday except during Training Week, starting 17th August 2008, finishing 30th October 2008.
        • etc.

    Occurrences which repeat need a repetition Rule (see rules.py for details).

    The event_start/event_end datetime fields describe the first occurrence. The repetition rule is then applied, to
    generate all occurrences that start before the `repeat_until` datetime limit.

    Generators without repeat_until limits potentially repeat infinitely. In this case, we generate occurrences until a
    set timedelta in the future. This timedelta is set in the setting 'DEFAULT_GENERATOR_LIMIT'.    
    """

    #define a field called 'event' in the subclass
    event_start = models.DateTimeField(db_index=True)
    event_end = models.DateTimeField(blank=True, db_index=True)
    rule = models.ForeignKey(Rule, verbose_name=_(u"repetition rule"), null = True, blank = True, help_text=_(u"Select '----' for a one-off event."))
    repeat_until = models.DateTimeField(null = True, blank = True, help_text=_(u"These start dates are ignored for one-off events."))
    exceptions = JSONField(null=True, blank=True, help_text=_(u"These dates are skipped by the generator."), default={})
    
    class Meta:
        abstract = True
        ordering = ('event_start',)

    def __unicode__(self):
        return u"%s, %s" % (self.event, self.robot_description())

    def clean(self):
        if self.event_end is None:
            self.event_end = self.event_start

        if self.event_start > self.event_end:
            raise exceptions.ValidationError('start must be earlier than end')
        if self.repeat_until is not None and \
                self.repeat_until < self.event_end:
            raise exceptions.ValidationError(
                'repeat_until must not be earlier than start')
        if self.repeat_until is not None and self.rule is None:
            raise exceptions.ValidationError(
                'repeat_until has no effect without a repetition rule')
        if self.rule and self.rule.frequency in FREQUENCY_TIME_MAP \
                and self.event_end - self.event_start \
                > FREQUENCY_TIME_MAP[self.rule.frequency]:
            raise exceptions.ValidationError('The event timespan is longer '
                'than the repetition frequency. The "repeat until" date may '
                'have been mistakenly used as the "event end".')
        super(GeneratorModel, self).clean()


    @transaction.commit_on_success()
    def save(self, *args, **kwargs):
        generate = kwargs.pop('generate', True)
        
        if self.event_end is None:
            self.event_end = self.event_start

        self.event_start = datetimeify(self.event_start, clamp="min")
        self.event_end = datetimeify(self.event_end, clamp="max")
        if self.repeat_until is not None:
            self.repeat_until = datetimeify(self.repeat_until, clamp="max")

        if self.event_end.time == time.min:
            self.event_end.time == time.max

        if self.event_start > self.event_end:
            raise AttributeError('Start must be earlier than end.')

        if self.repeat_until is not None and self.repeat_until < self.event_start:
            raise AttributeError('Repeat_until must not be earlier than start.')
        
        if self.repeat_until is not None and self.rule is None:
            raise AttributeError('Repeat_until has no effect without a repetition rule.')
        
        if self.rule and self.rule.frequency in FREQUENCY_TIME_MAP \
                and self.event_end - self.event_start \
                > FREQUENCY_TIME_MAP[self.rule.frequency]:
            raise AttributeError('The event timespan is longer than the '
                'repetition frequency. The "repeat until" date may have been '
                'mistakenly used as the "event end".')
        
        """
        When you change a generator and save it, it updates its existing occurrences according to the following:
        
        * If a repetition rule was changed:
            delete occurrences that don't conform to the new rule.
            
        * If a repeat_until rule was changed:
            delete out-of-bounds occurrences.
            
        * If start date (or datetime) was changed:
            run the old rule, and timeshift all occurrences produced by the old rule.

        * Else if only start time was changed:
            update all the generator's occurrences that have the same start time.
            
        * If end date or (or datetime) was changed:
            run the (new) generator and update the end date of all occurrences produced by the rule
        
        * If only end time was changed:
            update all the generator's occurrences that have the same end time.
        """
        
        if self.pk: #it already exists so could potentially be changed
            saved_self = type(self).objects.get(pk=self.pk)
            start_shift = self.event_start - saved_self.event_start
            end_shift = self.event_end - saved_self.event_end
            duration = self.event_duration

            if start_shift:
                if self.event_start.date() != saved_self.event_start.date(): # we're shifting days (and times)
                    occurrence_set = self.occurrences.filter(start__in=list(saved_self.generate_dates()))
                elif self.event_start.time() != saved_self.event_start.time(): #we're only shifting times
                    occurrence_set = [o for o in self.occurrences.all() if o.start.time() == saved_self.event_start.time()]

                for occ in occurrence_set:
                    occ.start += start_shift
                    occ.end = occ.start + duration
                    if self.repeat_until and occ.start < self.repeat_until:
                        occ.save()
                    else:
                        occ.delete()

            elif end_shift: #only end has changed (both is covered above)            
                if self.event_end.date() != saved_self.event_end.date(): # we're shifting days (and times)
                    occurrence_set = self.occurrences.filter(start__in=list(self.generate_dates()))
                elif self.event_end.time() != saved_self.event_end.time(): #we're only shifting times
                    occurrence_set = [o for o in self.occurrences.all() if o.end.time() == saved_self.event_end.time()]
                
                for occ in occurrence_set:
                    occ.end += end_shift
                    if occ.end < occ.start:
                        # Something has gone wrong, let's do the only sane
                        # thing to do
                        occ.end = occ.start + duration
                    occ.save()
            
            if self.repeat_until and (
                    not saved_self.repeat_until or
                    self.repeat_until < saved_self.repeat_until):
                self.occurrences.filter(start__gt=self.repeat_until).delete()
            
            # If the rule has changed, delete occurrences that don't conform
            # to the new rule
            if self.rule != saved_self.rule:
                for occurrence in self.occurrences.exclude(start__in=list(self.generate_dates())):
                    if not self.is_exception(occurrence.start):
                        occurrence.delete()

        super(GeneratorModel, self).save(*args, **kwargs)
        if generate:
            self.generate() #need to do this after save, so we have ids.
    
    @property
    def all_day(self):
        return self.event_start.time() == time.min and self.event_end.time() == time.max
    
    @property
    def event_duration(self):
        return self.event_end-self.event_start
    
    @classmethod
    def Occurrence(cls):
        return cls.occurrences.related.model

    def create_occurrence(self, start, end=None, honour_exceptions=False):
        """
        Occurrences are only generated if all of the following are true:
            * the start time isn't in the list of exceptions (unless we're 'force'-creating)
            * the occurrence hasn't already been saved by this generator (regardless of the event it is now assigned to)
            * the occurrence doesn't already exist for this event (regardless of the generator it came from)
        """
        if not honour_exceptions or (honour_exceptions and not self.is_exception(start)):
            
            if settings.ALLOW_CLASHING_OCCURRENCES:
                # if this occurrence is already generated by this generator, do nothing
                if self.occurrences.filter(start=start, end=end).count():
                    return
            else:                    
                # if this occurrence exists at all, do nothing (it's a clash and they're not allowed)
                if self.Occurrence().objects.filter(event=self.event, start=start, end=end).count():
                    return
            #good to go
            return self.occurrences.create(event=self.event, start=start, end=end) #generator = self
        # it's an exception, don't generate it.
        return

    def generate_dates(self):
        if self.rule is None:
            yield self.event_start
            raise StopIteration
        
        rule = self.rule.get_rrule(dtstart=self.event_start)
        date_iter = iter(rule)
        drop_dead_date = self.repeat_until or datetime.now() + settings.DEFAULT_GENERATOR_LIMIT
        
        while True:
            d = date_iter.next()
            if d > drop_dead_date:
                break
            yield d

    @transaction.commit_on_success()
    def generate(self):
        """
        generate my occurrences
        """

        if self.rule is None: #the only occurrence in the village, boyo
            self.create_occurrence(start=self.event_start, end=self.event_end, honour_exceptions=True)
            return

        event_duration = self.event_duration
        for o_start in self.generate_dates():
            o_end = o_start + event_duration
            self.create_occurrence(start=o_start, end=o_end, honour_exceptions=True)

    def robot_description(self):
        return u'\n'.join(
            [pprint_datetime_span(start, end) + repeat_description \
            for start, end, repeat_description in self.get_spans()])
    
    def get_spans(self):
        if self.rule:
            if self.occurrences.count() > 3:
                if self.repeat_until:
                    repeat_description = u', repeating %s until %s' % (
                        self.rule,
                        pprint_date_span(self.repeat_until, self.repeat_until)
                    )
                else:
                    repeat_description = u', repeating %s' % self.rule
                return [(self.event_start, self.event_end, repeat_description),]
            else:
                return [(occ.start, occ.end, u'') for occ in self.occurrences.all()]
        else:
            return [(self.event_start, self.event_end, u''),]
        
    
    def is_exception(self, dt):
        if self.exceptions is None:
            return False
        return self.exceptions.has_key(dt.isoformat())
    
    def add_exception(self, dt):
        if self.exceptions is None:
            self.reset_exceptions()
        
        self.exceptions[dt.isoformat()] = True
        self.save(generate=False)       

    def remove_exception(self, dt):
        if self.exceptions is None:
            self.reset_exceptions()
        if self.is_exception(dt):
            del self.exceptions[dt.isoformat()]
            self.save(generate=False)

    def reset_exceptions(self):
        self.exceptions = {}
        self.save(generate=False)

    def reload(self):
        """
        Call with x = x.reload() - it doesn't change itself
        """
        return type(self)._default_manager.get(pk=self.pk)

