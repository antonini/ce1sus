# -*- coding: utf-8 -*-

"""
module handing the event pages

Created: Aug 28, 2013
"""
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from ce1sus.brokers.event.commentbroker import CommentBroker
from ce1sus.brokers.event.eventclasses import Event
from ce1sus.brokers.relationbroker import RelationBroker
from ce1sus.brokers.staticbroker import TLPLevel, Risk, Analysis, Status
from ce1sus.common.mailhandler import MailHandlerException
from ce1sus.controllers.base import Ce1susBaseController
from ce1sus.helpers.bitdecoder import BitValue
from dagr.db.broker import ValidationException, BrokerException, NothingFoundException, \
  IntegrityException
from dagr.helpers.converters import ObjectConverter, ConversionException
from dagr.helpers.datumzait import DatumZait
from dagr.helpers.strings import cleanPostValue
import uuid as uuidgen


__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013, GOVCERT Luxembourg'
__license__ = 'GPL v3+'




def get_all_attribtues_from_event(event):
  attributes = list()
  for obj in event.objects:
    __get_all_attributes_from_obj(attributes, obj)
  return attributes


def __get_all_attributes_from_obj(attributes, obj):
  attributes += obj.attributes
  for child in obj.children:
    __get_all_attributes_from_obj(attributes, child)


class EventController(Ce1susBaseController):
  """event controller handling all actions in the event section"""

  def __init__(self, config):
    Ce1susBaseController.__init__(self, config)
    self.send_mails = config.get('ce1sus', 'sendmail', False)
    self.comment_broker = self.broker_factory(CommentBroker)
    self.relation_broker = self.broker_factory(RelationBroker)

  def change_owner(self, event_id, group_id, user):
    try:
      group = self.group_broker.get_by_id(group_id)
      event = self.event_broker.get_by_id(event_id)
      user = self.user_broker.getUserByUserName(user.username)
      event.creator_group = group
      self.event_broker.update_event(user, event, commit=True)
    except BrokerException as error:
      self._raise_exception(error)

  def get_related_events(self, event, user, cache):
    """
    Returns the relations which the user can see


    :param user:
    :type user: User
    :param event:
    :type event: Event
    :param cache:
    :type cache: Dictionary

    :returns: List of Relation
    """
    result = list()
    try:
      # get for each object
      # prepare list
      #
      relations = self.relation_broker.get_relations_by_event(event, True)
      for relation in relations:
        rel_event = relation.rel_event
        if rel_event.identifier != event.identifier:
          if self._is_event_viewable_for_user(rel_event, user, cache):
            result.append(rel_event)
    except NothingFoundException as error:
      self._raise_nothing_found_exception(error)
    except BrokerException as error:
      self._get_logger().error(error)
    return result

  def __popultate_event(self, **kwargs):
    """
    Populates an event
    """
    try:
      action = kwargs.get('action', None)
      identifier = kwargs.get('identifier', None)
      status = kwargs.get('status', None)
      tlp_index = kwargs.get('tlp_index', None)
      description = kwargs.get('description', None)
      name = kwargs.get('name', None)
      published = kwargs.get('published', None)
      if not published:
        published = None
      first_seen = kwargs.get('first_seen', None)
      last_seen = kwargs.get('last_seen', None)
      risk = kwargs.get('risk', None)
      analysis = kwargs.get('analysis', None)
      uuid = kwargs.get('uuid', None)
      user = kwargs.get('user', None)
      # fill in the values
      if hasattr(user, 'session'):
        user = self._get_user(user.username)
      event = Event()
      if action == 'insert':
          if uuid is None:
            event.uuid = unicode(uuidgen.uuid4())
          else:
            event.uuid = uuid
          # TODO: Check if creator_group_id was not passed
          event.creator_group_id = user.default_group.identifier
          event.maingroups = list()
          event.maingroups.append(user.default_group)
          event.bit_value = BitValue('0', event)
          event.bit_value.is_shareable = True
          event.created = DatumZait.utcnow()
          event.creator_id = user.identifier
          event.creator = user
          event.creator_group = user.default_group
      else:
        # dont want to change the original in case the user cancel!
        event = self.event_broker.get_by_id(identifier)
        # right checks only if there is a change!!!!

      if not action == 'remove':
        event.title = cleanPostValue(name)
        event.description = cleanPostValue(description)
        if not event.description:
          event.description = 'no description'
        # TODO: make checks if they are not an integer!
        ObjectConverter.set_integer(event, 'tlp_level_id', tlp_index)
        ObjectConverter.set_integer(event, 'status_id', status)
        ObjectConverter.set_integer(event, 'published', published)
        # if published
        if event.published == 1:
          event.last_publish_date = DatumZait.utcnow()
        event.modified = DatumZait.utcnow()
        event.modifier = user
        event.modifier_id = event.modifier.identifier

        if first_seen:
          try:
            ObjectConverter.set_date(event, 'first_seen', first_seen)
          except ConversionException:
            event.first_seen = first_seen
        else:
          event.first_seen = DatumZait.utcnow()
        if last_seen:
          try:
            ObjectConverter.set_date(event, 'last_seen', last_seen)
          except ConversionException:
            event.last_seen = last_seen
        else:
          event.last_seen = event.first_seen
        ObjectConverter.set_integer(event, 'analysis_status_id', analysis)
        ObjectConverter.set_integer(event, 'risk_id', risk)

      return event
    except ConversionException as error:
      self._raise_exception(error)

  def populate_web_event(self, user, **kwargs):
    """
    populates an event object with the given arguments

    :param user:
    :type user: String

    :returns: Event
    """
    kwargs['user'] = user
    event = self.__popultate_event(**kwargs)
    is_validation = kwargs.get('validation', None)
    if not is_validation:
      event.bit_value.is_web_insert = True
      event.bit_value.is_validated = True
      event.bit_value.is_shareable = True
    return event

  def populate_rest_event(self, user, group, dictionary, action):
    """
    populates an event object with the given rest_event

    :param user:
    :type user: String

    :returns: Event
    """
    tlp_index = TLPLevel.get_by_name(dictionary.get('tlp', None))
    risk_index = Risk.get_by_name(dictionary.get('risk', None))
    analysis_index = Analysis.get_by_name(dictionary.get('analysis', None))
    status_index = Status.get_by_name(dictionary.get('status', None))
    uuid = dictionary.get('uuid', None)
    if not uuid:
      uuid = None
    if action == 'insert':
      identifier = None
      first_seen = dictionary.get('first_seen', None)
      if not first_seen:
        first_seen = datetime.now()
      last_seen = dictionary.get('last_seen', None)
      if not last_seen:
        last_seen = first_seen
    else:
      event = self.event_broker.get_by_uuid(uuid)
      identifier = event.identifier
      first_seen = event.first_seen
      last_seen = event.last_seen

    params = {'user': user,
              'identifier': identifier,
              'action': action,
              'status': status_index,
              'tlp_index': tlp_index,
              'description': dictionary.get('description', 'No description'),
              'name': dictionary.get('title', 'No Title'),
              'published': dictionary.get('published', '0'),
              'first_seen': first_seen,
              'last_seen': last_seen,
              'risk': risk_index,
              'analysis': analysis_index,
              'uuid': uuid,
              }

    # pylint:disable=W0142
    event = self.__popultate_event(**params)

    if group:
      event.creator_group = group

    event.bit_value.is_rest_instert = True

    share = dictionary.get('share', None)
    if share == '1' or share == 1:
      event.bit_value.is_shareable = True
    else:
      event.bit_value.is_shareable = False

    event.bit_value.is_validated = False

    return event

  def insert_event(self, user, event, mkrelations=True):
    """
    inserts an event

    If it is invalid the event is returned

    :param event:
    :type event: Event

    :returns: Event, Boolean
    """
    self._get_logger().debug('User {0} inserts a new event'.format(user.username))
    try:
      self.event_broker.insert(event, False)
      # generate relations if needed!
      attributes = get_all_attribtues_from_event(event)
      if (mkrelations == 'True' or mkrelations is True) and attributes:
        self.relation_broker.generate_bulk_attributes_relations(event, attributes, False)
      self.event_broker.do_commit(True)
      return event, True
    except ValidationException:
      return event, False
    except IntegrityException:
      self._get_logger().info(u'User {0} tried to insert an event with uuid "{1}" but the uuid already exists'.format(user.username, event.uuid))
      self._raise_duplicate_found_exception(u'An event with uuid "{0}" already exists'.format(event.uuid))
    except BrokerException as error:
      self._raise_exception(error)

  def remove_event(self, user, event):
    """
    removes an event

    :param event:
    :type event: Event
    """
    self._get_logger().debug('User {0} removes event {1}'.format(user.username, event.identifier))
    try:
      self.event_broker.remove_by_id(event.identifier)
    except BrokerException as error:
      self._raise_exception(error)

  def update_event(self, user, event):
    """
    updates an event

    If it is invalid the event is returned

    :param event:
    :type event: Event
    """
    self._get_logger().debug('User {0} updates event {1}'.format(user.username, event.identifier))
    try:
      user = self._get_user(user.username)
      self.event_broker.update_event(user, event, True)
      if self.send_mails:
        old_event = self.event_broker.get_by_id(event.identifier)
        changed = event.published != old_event.published
        if changed and event.bit_value.is_validated_and_shared:
          self.mail_handler.send_event_mail(event)
      return event, True
    except ValidationException:
      return event, False
    except (BrokerException, MailHandlerException) as error:
      self._raise_exception(error)

  def get_full_event_relations(self, event, user, cache):
    """
    Returns the complete event relations with attributes and all
    """
    try:
      result = list()
      relations = self.relation_broker.get_relations_by_event(event, False)
      seen_events = list()
      for relation in relations:
          rel_event = relation.rel_event
          # check if is viewable for user
          if relation.rel_event_id in seen_events:
            result.append(relation)
          else:
            if self._is_event_viewable_for_user(rel_event, user, cache):
              result.append(relation)
              seen_events.append(relation.rel_event_id)
      return result
    except NothingFoundException as error:
      self._raise_nothing_found_exception(error)
    except BrokerException as error:
      self._raise_exception(error)

  def get_cb_tlp_lvls(self):
    """
    Returns the values for the combobox displaying tlp lvls
    """
    try:
      return TLPLevel.get_definitions()
    except BrokerException as error:
      self._raise_exception(error)

  def get_by_uuid(self, uuid):
    """
    Returns the event by its uuid
    """
    try:
      return self.event_broker.get_by_uuid(uuid)
    except NothingFoundException as error:
      self._raise_nothing_found_exception(error)
    except BrokerException as error:
      self._raise_exception(error)

  def __pub_unpub_event(self, event, user, publish):
    try:
      if self.is_event_owner(event, user):
        event.published = publish
      user_db = self.user_broker.getUserByUserName(user.username)
      self.event_broker.update_event(user_db, event, commit=True)
    except BrokerException as error:
      self._raise_exception(error)

  def unpublish_event(self, event, user):
    self.__pub_unpub_event(event, user, 0)

  def publish_event(self, event, user):
    self.__pub_unpub_event(event, user, 1)
