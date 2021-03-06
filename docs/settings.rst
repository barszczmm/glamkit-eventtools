.. _ref-settings:

Settings
========

.. _ref-settings-first-day-of-week:

FIRST_DAY_OF_WEEK
-----------------

This setting determines which day of the week your calendar begins on if your locale doesn't already set it. Default is 0, which is Sunday.

.. _ref-settings-OCCURRENCE_CANCEL_REDIRECT:

OCCURRENCE_CANCEL_REDIRECT
--------------------------

This setting controls the behaviour of :func:`Views.get_next_url`. If set, all calendar modifications will redirect here (unless there is a `next` set in the request.)

.. _ref-settings-show-cancelled-occurrences:

SHOW_CANCELLED_OCCURRENCES
--------------------------

This setting controls the behaviour of :func:`Period.classify_occurence`. If True, then occurrences that have been cancelled will be displayed with a CSS class of cancelled, otherwise they won't appear at all.

Defaults to False

.. _ref-settings-check-permission-func:

CHECK_PERMISSION_FUNC
---------------------

This setting controls the callable used to determine if a user has permission to edit an event or occurrence. The callable must take the object and the user and return a boolean. 

example::

    check_edit_permission(ob, user):
        return user.is_authenticated()

If ob is None, then the function is checking for permission to add new occurrences.

.. _ref-settings-get-events-func:

GET_EVENTS_FUNC
---------------

This setting controls the callable that gets all events for calendar display. The callable must take the request and the calendar and return a `QuerySet` of events. Modifying this setting allows you to pull events from multiple calendars or to filter events based on permissions

example::

    get_events(request, calendar):
        return calendar.event_set.all()

