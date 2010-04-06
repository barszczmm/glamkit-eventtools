from django.db import models
from django.utils.translation import ugettext, ugettext_lazy as _
from django.template.defaultfilters import date
import datetime

from django.db.models.base import ModelBase

class OccurrenceGeneratorBase(models.Model):
    """
    Defines a set of repetition rules for an event
    """
    first_start_date = models.DateField()
    first_start_time = models.TimeField()
    first_end_date = models.DateField(null = True, blank = True)
    first_end_time = models.TimeField(null = True, blank = True)
    rule = models.ForeignKey('Rule', verbose_name="Repetition rule", null = True, blank = True, help_text="Select '----' for a one-off event.")
    repeat_until = models.DateTimeField(null = True, blank = True, help_text="This date is ignored for one-off events.")

    class Meta:
        ordering = ('first_start_date', 'first_start_time')
        abstract = True
        verbose_name = 'occurrence generator'
        verbose_name_plural = 'occurrence generators'

    def _end_recurring_period(self):
        if self.end_day:
            return datetime.datetime.combine(self.end_day, datetime.time.max)
        else:
            return None	
    end_recurring_period = property(_end_recurring_period)

    # for backwards compatibility    
    def _get_start(self):
        return datetime(self.first_start_date, self.first_start_time)

    def _set_start(self, value):
        self.first_start_date = value.date
        self.first_start_time = value.time
        
    start = property(_get_start, _set_start)
    
    def _get_end_time(self):
        return self.first_end_time
        
    def _set_end_time(self, value):
        self.first_end_time = value
    
    end_time = property(_get_end_time, _set_end_time)    
        
    def _end(self):
        if self.endtime:
            return datetime.datetime.combine(self.start.date(), self.endtime)
        else:
            return self.start
    end = property(_end)

    def __unicode__(self):
        date_format = u'l, %s' % ugettext("DATE_FORMAT")
        return ugettext('%(title)s: %(start)s-%(end)s') % {
            'title': self.event.title,
            'start': date(self.start, date_format),
            'end': date(self.end, date_format),
        }

    def get_occurrences(self, start, end):
#         """
#         >>> rule = Rule(frequency = "MONTHLY", name = "Monthly")
#         >>> rule.save()
#         >>> event = Event(rule=rule, start=datetime.datetime(2008,1,1), end=datetime.datetime(2008,1,2))
#         >>> event.rule
#         <Rule: Monthly>
#         >>> occurrences = event.get_occurrences(datetime.datetime(2008,1,24), datetime.datetime(2008,3,2))
#         >>> ["%s to %s" %(o.start, o.end) for o in occurrences]
#         ['2008-02-01 00:00:00 to 2008-02-02 00:00:00', '2008-03-01 00:00:00 to 2008-03-02 00:00:00']
# 
#         Ensure that if an event has no rule, that it appears only once.
# 
#         >>> event = Event(start=datetime.datetime(2008,1,1,8,0), end=datetime.datetime(2008,1,1,9,0))
#         >>> occurrences = event.get_occurrences(datetime.datetime(2008,1,24), datetime.datetime(2008,3,2))
#         >>> ["%s to %s" %(o.start, o.end) for o in occurrences]
#         []
# 
#         """
        persisted_occurrences = self.occurrence_set.all()
        occ_replacer = OccurrenceReplacer(persisted_occurrences)
        occurrences = self._get_occurrence_list(start, end)
        final_occurrences = []
        for occ in occurrences:
            # replace occurrences with their persisted counterparts
            if occ_replacer.has_occurrence(occ):
                p_occ = occ_replacer.get_occurrence(occ)
                # ...but only if they are within this period
                if p_occ.start < end and p_occ.end >= start:
                    final_occurrences.append(p_occ)
            else:
              final_occurrences.append(occ)
        # then add persisted occurrences which originated outside of this period but now
        # fall within it
        final_occurrences += occ_replacer.get_additional_occurrences(start, end)
        return final_occurrences
        
    def occurrence_model(self):
        model_name = self.__class__.__name__[0:-len("Generator")].lower()
        return = models.get_model(self._meta.app_label, model_name)

    def get_rrule_object(self):
        if self.rule is not None:
            if self.rule.complex_rule:
                try:
                    return rrule.rrulestr(str(self.rule.complex_rule),dtstart=self.start)
                except:
                    pass
            params = self.rule.get_params()
            frequency = 'rrule.%s' % self.rule.frequency
            simple_rule = rrule.rrule(eval(frequency), dtstart=self.start, **params)
            set = rrule.rruleset()
            set.rrule(simple_rule)
            goodfriday = rrule.rrule(rrule.YEARLY, dtstart=self.start, byeaster=-2)
            christmas = rrule.rrule(rrule.YEARLY, dtstart=self.start, bymonth=12, bymonthday=25)
            set.exrule(goodfriday)
            set.exrule(christmas)
            return set

    def _create_occurrence(self, start, end=None):
        if end is None:
            end = start + (self.end - self.start)
        occ = Occurrence(generator__event=self,start=start,end=end, original_start=start, original_end=end)
        return occ
    
    def get_one_occurrence(self):
        try:
            occ = self.occurrence_model().objects.filter(generator__event=self)[0]
        except IndexError:
            now = datetime.datetime.now()
            occ = self.occurrence_model()(generator=self, varied_start_date=now.date, varied_start_time=now.time, varied_end_date=now.date, varied_end_time=now.time, unvaried_start_date=now.date, unvaried_start_time=now.time, unvaried_end_date=now.date, unvaried_end_time=now.time)
        return occ

    def get_occurrence(self, date):
        rule = self.get_rrule_object()
        if rule:
            next_occurrence = rule.after(date, inc=True)
        else:
            next_occurrence = self.start
        if next_occurrence == date:
            try:
                return Occurrence.objects.get(event = self, original_start = date)
            except Occurrence.DoesNotExist:
                return self._create_occurrence(next_occurrence)


    def _get_occurrence_list(self, start, end):
        """
        returns a list of occurrences for this event from start to end.
        """
        difference = (self.end - self.start)
        if self.rule is not None:
            occurrences = []
            if self.end_recurring_period and self.end_recurring_period < end:
                end = self.end_recurring_period
            rule = self.get_rrule_object()
            o_starts = rule.between(start-difference, end, inc=True)
            for o_start in o_starts:
                o_end = o_start + difference
                occurrences.append(self._create_occurrence(o_start, o_end))
            return occurrences
        else:
            # check if event is in the period
            if self.start < end and self.end >= start:
                return [self._create_occurrence(self.start)]
            else:
                return []

    def _occurrences_after_generator(self, after=None):
        """
        returns a generator that produces unpersisted occurrences after the
        datetime ``after``.
        """

        if after is None:
            after = datetime.datetime.now()
        rule = self.get_rrule_object()
        if rule is None:
            if self.end > after:
                yield self._create_occurrence(self.start, self.end)
            raise StopIteration
        date_iter = iter(rule)
        difference = self.end - self.start
        while True:
            o_start = date_iter.next()
            if o_start > self.end_recurring_period:
                raise StopIteration
            o_end = o_start + difference
            if o_end > after:
                yield self._create_occurrence(o_start, o_end)


    def occurrences_after(self, after=None):
        """
        returns a generator that produces occurrences after the datetime
        ``after``.	Includes all of the persisted Occurrences.
        """
        occ_replacer = OccurrenceReplacer(self.occurrence_set.all())
        generator = self._occurrences_after_generator(after)
        while True:
            next = generator.next()
            yield occ_replacer.get_occurrence(next)


class OccurrenceBase(models.Model):

    # explicit fields
    varied_start_date = models.DateField(blank=True, null=True, db_index=True)
    varied_start_time = models.TimeField(blank=True, null=True, db_index=True)
    varied_end_date = models.DateField(blank=True, null=True, db_index=True)
    varied_end_time = models.TimeField(blank=True, null=True, db_index=True)
    unvaried_start_date = models.DateField(db_index=True)
    unvaried_start_time = models.TimeField(db_index=True)
    unvaried_end_date = models.DateField(db_index=True)
    unvaried_end_time = models.TimeField(db_index=True)
    cancelled = models.BooleanField(_("cancelled"), default=False)

    class Meta:
        verbose_name = _("occurrence")
        verbose_name_plural = _("occurrences")
        abstract = True
        unique_together = ('unvaried_start_date', 'unvaried_start_time', 'unvaried_end_date', 'unvaried_end_time')

# 
#     def moved(self):
#         return self.original_start != self.start or self.original_end != self.end
#     moved = property(moved)
# 
#     def move(self, new_start, new_end):
#         self.start = new_start
#         self.end = new_end
#         self.save()
# 
#     def cancel(self):
#         self.cancelled = True
#         self.save()
# 
#     def uncancel(self):
#         self.cancelled = False
#         self.save()


    def __unicode__(self):
        return ugettext("%(event)s: %(day)s") % {
            'event': self.generator.event.title,
            'day': self.start.strftime('%a, %d %b %Y'),
        }

    def __cmp__(self, other):
        rank = cmp(self.start, other.start)
        if rank == 0:
            return cmp(self.end, other.end)
        return rank

    def __eq__(self, other):
        return self.event == other.event and self.original_start == other.original_start and self.original_end == other.original_end


class EventModelBase(ModelBase):
    def __init__(cls, name, bases, attrs):
        # Dynamically build two related classes to handle occurrences
        if name != 'EventBase': # This should only fire if this is a subclass (maybe we should make devs apply this metaclass to their subclass instead?)
            
            # Build names for the new classes
            occ_name = "%s%s" % (name, "Occurrence")
            gen_name = "%s%s" % (occ_name, "Generator")
        
            # Create the generator class
            globals()[gen_name] = type(gen_name,
                (OccurrenceGeneratorBase,),
                dict(__module__ = cls.__module__,),
            )
            generator_class = globals()[gen_name]
            
            # add a foreign key back to the event class
            generator_class.add_to_class('event', models.ForeignKey(cls, related_name = 'generators'))

            # Create the occurrence class
            globals()[occ_name] = type(occ_name,
                (OccurrenceBase,),
                dict(__module__ = cls.__module__,),
            )
            occurrence_class = globals()[occ_name]

            # add a foreign key back to the generator class
            occurrence_class.add_to_class('generator', models.ForeignKey(generator_class, related_name = 'occurrences'))

        super(EventModelBase, cls).__init__(cls, name, bases, attrs)
        
class EventVariationBase(models.Model):
    def __init__(self, *args, **kwargs):
        if not hasattr(self, 'unvaried_event'):
            raise NotImplementedError ('%s must declare a field called "unvaried_event" which is a ForeignKey to the corresponding event' % __class__)
        super(EventVariationBase, self).__init__(*args, **kwargs)

class EventBase(models.Model):
    """
    Event information minus the scheduling details
    
    Event scheduling is handled by one or more OccurrenceGenerators
    """
    __metaclass__ = EventModelBase

    title = models.CharField(_("Title"), max_length = 255)
    short_title = models.CharField(_("Short title"), max_length = 255, blank=True)
    schedule_description = models.CharField(_("Plain English description of schedule"), max_length=255, blank=True)

    class Meta:
        abstract = True # might be better if it wasn't abstract? (ForeignKeys from OccGen etc.)

    def primary_generator(self):
        return self.generators.order_by('start')[0]
        
    def get_one_occurrence(self):
        self.generators.all()[0].get_one_occurrence()
    
    def get_first_occurrence(self): # should return an actual occurrence
        return self.primary_generator().start		
        
    def get_last_day(self):
        lastdays = []
        for generator in self.generators.all():
            if not generator.end_recurring_period:
                return False
            lastdays.append(generator.end_recurring_period)
        lastdays.sort()
        return lastdays[-1]

    def has_multiple_occurrences(self):
        if self.generators.count() > 1 or (self.generators.count() > 0 and self.generators.all()[0].rule != None):
            return '<a href="%s/occurrences/">edit / add occurrences</a>' % self.id
        else:
            return ""
    has_multiple_occurrences.allow_tags = True
    
    def get_absolute_url(self):
        return "/event/%s/" % self.id
    
    def next_occurrences(self):
        from events.periods import Period
        first = False
        last = False
        for gen in self.generators.all():
            if not first or gen.start < first:
                first = gen.start
            if gen.rule and not gen.end_day:
                last = False # at least one rule is infinite
                break
            if not gen.end_day:
                genend = gen.start
            else:
                genend = gen.end_recurring_period
            if not last or genend > last:
                last = genend
        if last:
            period = Period(self.generators.all(), first, last)
        else:
            period = Period(self.generators.all(), datetime.datetime.now(), datetime.datetime.now() + datetime.timedelta(days=28))		
        return period.get_occurrences()

freqs = (
    ("YEARLY", _("Yearly")),
    ("MONTHLY", _("Monthly")),
    ("WEEKLY", _("Weekly")),
    ("DAILY", _("Daily")),
    ("HOURLY", _("Hourly")),
)

class Rule(models.Model):
    """
    This defines a rule by which an event will recur.  This is defined by the
    rrule in the dateutil documentation.

    * name - the human friendly name of this kind of recursion.
    * description - a short description describing this type of recursion.
    * frequency - the base recurrence period
    * param - extra params required to define this type of recursion. The params
      should follow this format:

        param = [rruleparam:value;]*
        rruleparam = see list below
        value = int[,int]*

      The options are: (documentation for these can be found at
      http://labix.org/python-dateutil#head-470fa22b2db72000d7abe698a5783a46b0731b57)
        ** count
        ** bysetpos
        ** bymonth
        ** bymonthday
        ** byyearday
        ** byweekno
        ** byweekday
        ** byhour
        ** byminute
        ** bysecond
        ** byeaster
    """
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    common = models.BooleanField()
    frequency = models.CharField(_("frequency"), choices=freqs, max_length=10, blank=True)
    params = models.TextField(_("inclusion parameters"), blank=True)
    complex_rule = models.TextField(_("complex rules (over-rides all other settings)"), blank=True)

    class Meta:
        verbose_name = _('rule')
        verbose_name_plural = _('rules')
        ordering = ('-common', 'name')

    def get_params(self):
        """
        >>> rule = Rule(params = "count:1;bysecond:1;byminute:1,2,4,5")
        >>> rule.get_params()
        {'count': 1, 'byminute': [1, 2, 4, 5], 'bysecond': 1}
        """
    	params = self.params
        if params is None:
            return {}
        params = params.split(';')
        param_dict = []
        for param in params:
            param = param.split(':')
            if len(param) == 2:
                param = (str(param[0]), [int(p) for p in param[1].split(',')])
                if len(param[1]) == 1:
                    param = (param[0], param[1][0])
                param_dict.append(param)
        return dict(param_dict)
        
    def __unicode__(self):
        """Human readable string for Rule"""
        return self.name
