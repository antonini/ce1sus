# -*- coding: utf-8 -*-

"""
(Description)

Created on Feb 2, 2015
"""
import copy
import dateutil
import json
from os.path import dirname, abspath
import re
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.dynamic import AppenderQuery
from sqlalchemy.orm.session import make_transient
import time
from types import ListType
from uuid import uuid4

from ce1sus.controllers.admin.attributedefinitions import AttributeDefinitionController
from ce1sus.controllers.admin.conditions import ConditionController
from ce1sus.controllers.admin.group import GroupController
from ce1sus.controllers.admin.objectdefinitions import ObjectDefinitionController
from ce1sus.controllers.admin.references import ReferencesController
from ce1sus.controllers.admin.user import UserController
from ce1sus.controllers.base import ControllerException, ControllerIntegrityException
from ce1sus.controllers.events.event import EventController
from ce1sus.controllers.events.indicatorcontroller import IndicatorController
from ce1sus.db.classes.attribute import Attribute
import ce1sus.db.classes.attribute
from ce1sus.db.classes.common import Properties
import ce1sus.db.classes.definitions
from ce1sus.db.classes.event import Event, EventGroupPermission
import ce1sus.db.classes.event
from ce1sus.db.classes.group import Group
from ce1sus.db.classes.indicator import Indicator
import ce1sus.db.classes.indicator
import ce1sus.db.classes.mailtemplate
from ce1sus.db.classes.object import Object, RelatedObject
import ce1sus.db.classes.object
from ce1sus.db.classes.observables import Observable, ObservableComposition, RelatedObservable
import ce1sus.db.classes.observables
import ce1sus.db.classes.relation
from ce1sus.db.classes.report import Report, Reference
from ce1sus.db.classes.types import AttributeType
import ce1sus.db.classes.types
from ce1sus.db.classes.user import User
import ce1sus.db.classes.user
import ce1sus.db.classes.values
from ce1sus.db.common.session import SessionManager, Base
from ce1sus.depricated.helpers.bitdecoder import BitRight, BitValue
from ce1sus.handlers.attributes.generichandler import GenericHandler
from ce1sus.helpers.common import strings
from ce1sus.helpers.common.config import Configuration
from ce1sus.helpers.common.debug import Log
from ce1sus.helpers.common.objects import get_fields, get_class


__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013-2014, GOVCERT Luxembourg'
__license__ = 'GPL v3+'


def set_db_code(obj, old_code):
  bit_value = BitValue(old_code)
  obj.properties.is_proposal = bit_value.is_proposal
  obj.properties.is_shareable = bit_value.is_shareable
  obj.properties.is_rest_instert = bit_value.is_rest_instert
  obj.properties.is_validated = True
  obj.properties.is_web_insert = bit_value.is_web_insert


def convert_date(string_date):
  return strings.stringToDateTime(string_date)


def clone_attr(attribute, obj):
  attr = Attribute()
  attr.identifier = uuid4()
  attr.modified_on = attribute.modified_on
  attr.created_at = attribute.created_at
  attr.creator = attribute.creator
  attr.creator_id = attr.creator.identifier
  attr.modifier = attribute.modifier
  attr.modifier_id = attr.modifier.identifier
  attr.originating_group = attribute.originating_group
  attr.originating_group_id = attr.originating_group.identifier
  attr.creator_group = attribute.creator.group
  attr.creator_group_id = attribute.creator.group_id
  attr.definition = attribute.definition
  attr.definition_id = attr.definition.identifier
  attr.dbcode = attribute.dbcode
  attr.is_ioc = attribute.is_ioc

  attr.object = obj
  attr.object_id = attr.object.identifier

  attr.value = attribute.value
  return attr


def clone_object(obj, observable, parent=None):
  new_obj = Object()
  # typical foo
  new_obj.identifier = uuid4()
  new_obj.modified_on = obj.modified_on
  new_obj.created_at = obj.created_at
  new_obj.creator = obj.creator
  new_obj.creator_id = new_obj.creator.identifier
  new_obj.modifier = obj.modifier
  new_obj.modifier_id = new_obj.modifier.identifier
  new_obj.originating_group = obj.originating_group
  new_obj.originating_group_id = new_obj.originating_group.identifier
  new_obj.creator_group = obj.creator.group
  new_obj.creator_group_id = obj.creator.group_id
  new_obj.definition = obj.definition
  new_obj.definition_id = new_obj.definition.identifier
  new_obj.dbcode = obj.dbcode

  new_obj.observable = observable
  new_obj.observable_id = new_obj.observable.identifier
  new_obj.parent = parent
  if new_obj.parent:
    new_obj.parent_id = new_obj.parent.identifer

  for item in obj.related_objects:
    res = clone_object(item, observable, new_obj)
    if res:
      new_obj.related_objects.append(res)

  for attribute in obj.attributes:
    if attribute.is_ioc:
      att = clone_attr(attribute, new_obj)
      if att:
        new_obj.attributes.append(att)
  if new_obj.attributes.count() > 0:
    return new_obj
  else:
    return None


def clone_composed_observable(composed_observable):
  new_composed_observable = ObservableComposition()
  new_composed_observable.identifier = uuid4()
  new_composed_observable.dbcode = composed_observable.dbcode

  new_composed_observable.operator = composed_observable.operator
  new_composed_observable.parent = composed_observable.parent
  new_composed_observable.parent_id = composed_observable.parent_id

  for obs in composed_observable.observables:
    obs_i = clone_observable(obs)
    if obs_i:
      new_composed_observable.observables.append(obs_i)

  if new_composed_observable.observables.count() > 0:
    return new_composed_observable
  else:
    return None


def create_related_obj(parent, child):
  related_obj = RelatedObject()
  related_obj.identifier = uuid4()
  related_obj.parent = parent
  related_obj.parent_id = related_obj.parent.identifier
  related_obj.object = child
  related_obj.child_id = related_obj.object.identifier
  return related_obj


def create_related_observable(parent, child):
  related_observable = RelatedObservable()
  related_observable.parent = parent
  related_observable.parent_id = related_observable.parent.identifier
  related_observable.observable = child
  related_observable.child_id = related_observable.observable.identifier
  related_observable.creator_group = child.creator_group
  related_observable.creator_group_id = related_observable.creator_group.identifier
  related_observable.creator = child.creator
  related_observable.creator_id = related_observable.creator.identifier
  related_observable.modifier = child.modifier
  related_observable.modifier_id = related_observable.modifier.identifier
  related_observable.originating_group = related_observable.creator_group
  related_observable.originating_group_id = related_observable.creator_group.identifier
  return related_observable


def clone_rel_observable(rel_observable, parent_obs):
  new_rel_observable = RelatedObservable()
  new_rel_observable.identifier = uuid4()
  new_rel_observable.observable = clone_observable(rel_observable.observable)
  if new_rel_observable.observable:
    new_rel_observable.child_id = new_rel_observable.observable.identifier
  else:
    return None
  new_rel_observable.confidence = rel_observable.confidence

  new_rel_observable.parent = parent_obs
  new_rel_observable.parent_id = parent_obs.identifier
  new_rel_observable.relation = rel_observable.relation
  return new_rel_observable


def clone_observable(observable):
  new_observable = Observable()
  new_observable.identifier = uuid4()
  new_observable.title = observable.title
  new_observable.dbcode = observable.dbcode
  # do not set event as this will then be directly liked to the event!

  new_observable.parent = observable.parent
  new_observable.parent_id = observable.parent_id

  new_observable.description = observable.description

  # typical foo
  new_observable.modified_on = observable.modified_on
  new_observable.created_at = observable.created_at
  new_observable.creator = observable.creator
  new_observable.creator_id = new_observable.creator.identifier
  new_observable.modifier = observable.modifier
  new_observable.modifier_id = new_observable.modifier.identifier
  new_observable.originating_group = observable.originating_group
  new_observable.originating_group_id = new_observable.originating_group.identifier
  new_observable.creator_group = observable.creator_group
  new_observable.creator_group_id = new_observable.creator_group.identifier

  if observable.object:
    obj = clone_object(observable.object, new_observable, None)
    if obj:
      new_observable.object = obj

  if observable.observable_composition:
    composed = clone_composed_observable(observable.observable_composition)
    if composed:
      new_observable.observable_composition = composed

  if observable.related_observables:
    for rel_obj in observable.related_observables:
      rel = clone_rel_observable(rel_obj, new_observable)
      if rel:
        new_observable.related_observables.append(rel)
  if new_observable.object or new_observable.observable_composition:
    # make a relation between the both
    rel_obs = create_related_observable(observable, new_observable)
    observable.related_observables.append(rel_obs)

    return new_observable
  else:
    return None


class Migrator(object):

  def __init__(self):
    basePath = dirname(abspath(__file__))

    ce1susConfigFile = basePath + '/config/ce1sus.conf'
    config = Configuration(ce1susConfigFile)
    self.logger = Log(config).get_logger('Main')
    connector = SessionManager(config).connector
    directconnection = connector.get_direct_session()
    self.session = directconnection
    self.notmapped = open('dumps/notmapped.txt', 'w')

    self.event_controller = EventController(config, directconnection)

    def_con = AttributeDefinitionController(config, directconnection)
    self.attr_defs = def_con.get_all_attribute_definitions()
    def_con = ObjectDefinitionController(config, directconnection)
    self.obj_defs = def_con.get_all_object_definitions()
    def_con = ConditionController(config, directconnection)
    self.conditions = def_con.get_all_conditions()
    def_con = ReferencesController(config, directconnection)
    self.ressources = def_con.get_all()
    def_con = IndicatorController(config, directconnection)
    self.types = def_con.get_all()

    self.user_controller = UserController(config, directconnection)
    self.group_controller = GroupController(config, directconnection)
    self.users = dict()
    self.groups = dict()
    self.seen_attributes = dict()
    self.seen_attribtues_uuids = list()

  def get_users(self):
    if not self.users:
      raise Exception('Users not mapped')
    return self.users

  def get_groups(self):
    if not self.groups:
      raise Exception('Groups not mapped')
    return self.groups

  def close(self):
    self.notmapped.close()
    self.event_controller.event_broker.do_commit(True)
    self.session.close()

  def start_events(self):
    debug = False
    data_file = open('dumps/events.txt', 'r')
    lines = data_file.readlines()
    for line in lines:
      json_dict = json.loads(line)
      print u'Migrating Event # {0} - {1}'.format(json_dict['identifier'], json_dict['uuid'])
      if json_dict['uuid'] == '84ca657d-eee2-4202-99be-f78256eb876a' or not debug:
        event = self.map_event(json_dict)
        self.event_controller.event_broker.insert(event, True)
        event = None
        if debug:
          break

    data_file.close()

  def map_event_group(self, line, owner):
    group = self.get_groups()[line['identifier']]

    grouppermission = EventGroupPermission()
    grouppermission.group = group
    grouppermission.group_id = group.identifier
    grouppermission.dbcode = group.default_dbcode
    if owner.group.identifier == group.identifier:
      grouppermission.permissions.set_all()
    # Set the informations to the owner of the event
    grouppermission.creator_group = owner.group
    grouppermission.creator_group_id = grouppermission.creator_group.identifier
    grouppermission.creator = owner
    grouppermission.creator_id = grouppermission.creator.identifier
    grouppermission.modifier = owner
    grouppermission.modifier_id = grouppermission.modifier.identifier
    grouppermission.originating_group = grouppermission.creator_group
    grouppermission.originating_group_id = grouppermission.creator_group.identifier
    return grouppermission

  def make_report(self, line, owner, event):
    report = Report()
    report.creator_group = self.get_groups()[line['creator_group_id']]
    report.creator_group_id = report.creator_group.identifier
    report.creator = self.get_users()[line['creator_id']]
    report.creator_id = report.creator.identifier
    set_db_code(report, line['dbcode'])

    report.created_at = convert_date(line['created'])
    report.modified_on = convert_date(line['modified'])
    modifier_id = line['modifier_id']
    if modifier_id:
      report.modifier = self.get_users()[modifier_id]
    else:
      report.modifier = report.creator
    report.modifier_id = report.modifier.identifier
    report.originating_group = report.creator_group
    report.originating_group_id = report.creator_group.identifier
    report.event_id = event.identifier
    return report

  def map_report(self, line, owner, event):
    mutexes = list()
    # check if references are not mutexes
    for attribute in line['attributes']:
      if attribute['definition']['name'] == 'mutex':
        mutexes.append(attribute)

    for item in mutexes:
      line['attributes'].remove(item)
    # There were mutexes in the references these are mapped correctly now
    if mutexes:
      observable = self.map_observable_composition(mutexes, line, owner, event, None)
      indicator = self.map_indicator(observable, line, None, event)
      event.observables.append(observable)
      if indicator:
        event.indicators.append(indicator)

    if line['attributes']:
      # map the remaining to the report
      report = self.make_report(line, owner, event)
      for attribute in line['attributes']:
        if attribute['definition']['name'] == 'comment' or attribute['definition']['name'] == 'description' or attribute['definition']['name'] == 'analysis_free_text' or attribute['definition']['name'] == 'reference_free_text':
          if not report.description:
            report.description = ''
          report.description = report.description + '\n' + attribute['value']
        else:
          reference = self.make_reference(attribute, report)
          if reference:
            report.references.append(reference)
      return report
    else:
      return None

  def start_groups(self):
    data_file = open('dumps/groups.txt', 'r')
    lines = data_file.readlines()
    groups = dict()
    for line in lines:
      group_dict = json.loads(line)
      group = Group()
      id_ = group_dict['identifier']
      group.identifier = group_dict['uuid']
      group.email = group_dict['email']
      group.gpg_key = group_dict['gpg_key']
      group.tlp_lvl = group_dict['tlp_lvl']
      group.name = group_dict['name']
      group.send_usermails = group_dict['usermails']

      if group_dict['can_download'] == 1:
        group.permissions.can_download = True
      else:
        group.permissions.can_download = False

      # Setting not available in previous version
      group.permissions.propagate_tlp = False

      group.description = group_dict['description']
      # if group exists add just the id
      try:
        self.group_controller.insert_group(group, commit=False)
      except ControllerIntegrityException:
        group = self.group_controller.get_group_by_id(group.identifier)

      groups[id_] = group

    self.groups = groups
    data_file.close()

  def start_users(self):
    data_file = open('dumps/users.txt', 'r')
    lines = data_file.readlines()
    users = dict()
    for line in lines:
      user_dict = json.loads(line)
      user = User()
      id_ = user_dict['identifier']

      user.username = user_dict['username']
      user.activation_str = user_dict['activation_str']

      dbcode = user_dict['dbcode']
      bitright = BitRight(dbcode)

      user.permissions.manage_group = bitright.set_group
      # The same as in the old one
      user.permissions.validate = bitright.privileged
      user.permissions.privileged = bitright.privileged

      user.activated = convert_date(user_dict['activated'])
      disabled = user_dict['disabled']
      if disabled == 1:
        user.permissions.disabled = True
      else:
        user.permissions.disabled = False

      user.activation_sent = user_dict['activation_sent']
      user.gpg_key = user_dict['gpg_key']
      user.password = user_dict['password']
      group_id = user_dict['group_id']
      user.group = self.get_groups()[group_id]
      user.group_id = user.group.identifier

      user.name = user_dict['name']
      user.sirname = user_dict['sirname']

      user.last_login = convert_date(user_dict['last_login'])

      user.api_key = user_dict['api_key']
      user.email = user_dict['email']

      try:
        self.user_controller.insert_user(user, commit=False)
      except ControllerIntegrityException:
        user = self.user_controller.get_user_by_username(user.username)

      users[id_] = user
    self.users = users
    data_file.close()

  def make_object(self, line, observable):
    obj = Object()
    obj.observable_id = observable.identifier
    obj.observable = observable
    obj.identifier = line['uuid']
    obj.creator_group = self.get_groups()[line['creator_group_id']]
    obj.creator_group_id = obj.creator_group.identifier
    obj.creator = self.get_users()[line['creator_id']]
    obj.creator_id = obj.creator.identifier
    obj.created_at = convert_date(line['created'])
    obj.modified_on = convert_date(line['modified'])
    modifier_id = line['modifier_id']
    set_db_code(obj, line['dbcode'])

    if modifier_id:
      modifier = self.get_users()[modifier_id]
    else:
      modifier = obj.creator
    obj.modifier = modifier
    obj.modifier_id = obj.modifier.identifier
    obj.originating_group = obj.creator_group
    obj.originating_group_id = obj.creator_group.identifier
    return obj

  def make_observable(self, line, event):
    result_observable = Observable()
    result_observable.identifier = line['uuid']
    # The creator of the result_observable is the creator of the object
    result_observable.creator_group = self.get_groups()[line['creator_group_id']]
    result_observable.creator_group_id = result_observable.creator_group.identifier
    result_observable.creator = self.get_users()[line['creator_id']]
    result_observable.creator_id = result_observable.creator.identifier
    result_observable.created_at = convert_date(line['created'])
    result_observable.modified_on = convert_date(line['modified'])
    modifier_id = line['modifier_id']
    if modifier_id:
      modifier = self.get_users()[modifier_id]
    else:
      modifier = result_observable.creator
    result_observable.modifier = modifier
    result_observable.modifier_id = result_observable.modifier.identifier
    result_observable.originating_group = result_observable.creator_group
    result_observable.originating_group_id = result_observable.creator_group.identifier
    result_observable.parent_id = event.identifier
    result_observable.parent = event
    result_observable.event_id = event.identifier
    result_observable.event = event
    result_observable.created_at = convert_date(line['created'])
    result_observable.modified_on = convert_date(line['modified'])
    # db code is the same as for the object
    set_db_code(result_observable, line['dbcode'])

    return result_observable

  def map_reference_definition(self, line):
    name = line['name']
    if name == 'raw_document_file':
      name = 'raw_file'
    if name == 'reference_url':
      name = 'link'
    if name == 'url':
      name = 'link'
    if name == 'mutex':
      return None
    chksum = line['chksum']
    found_def = None
    for definition in self.ressources:
      if name == definition.name:
        found_def = definition
        break
    if found_def:
      return found_def
    else:
      raise Exception(u'Reference Definition {0} with chksum {1} not found in new setup'.format(name, chksum))

  def make_reference(self, attribute, report):
    reference = Reference()
    reference.identifier = attribute['uuid']
    reference.creator_group = self.get_groups()[attribute['creator_group_id']]
    reference.creator_group_id = reference.creator_group.identifier
    reference.creator = self.get_users()[attribute['creator_id']]
    reference.creator_id = reference.creator.identifier
    set_db_code(reference, attribute['dbcode'])

    modifier_id = attribute.get('modifier_id')
    reference.created_at = convert_date(attribute['created'])
    reference.modified_on = convert_date(attribute['modified'])
    if modifier_id:
      reference.modifier = self.get_users()[modifier_id]
    else:
      reference.modifier = reference.creator
    reference.modifier_id = reference.modifier.identifier
    reference.originating_group = reference.creator_group
    reference.originating_group_id = reference.creator_group.identifier

    # TODO definition of report attribute
    definition = self.map_reference_definition(attribute['definition'])
    if definition:
      reference.definition = definition
      reference.value = attribute['value']
      parent_id = attribute['attr_parent_id']
      if parent_id:
        parent = self.seen_attributes.get(parent_id, None)
        # TODO: To check this again!
        if parent:
          parent.children.append(reference)
      return reference
    else:
      self.notmapped.write('Reference Could not be mapped as definition is missing for the new report {0}\n'.format(report.identifier))
      self.notmapped.write('{0}\n'.format(json.dumps(attribute)))
    return None

  def map_condition(self, name):
    for condition in self.conditions:
      if condition.value == name:
        return condition

  def map_attr_def(self, line):
    name = line['name']
    if name == 'email_receive_datetime':
      return None
    elif name == 'email_send_datetime':
      return None
    elif name == 'reference_url':
      name = 'url'
    elif name == 'ipv4_addr_c&c':
      name = 'ipv4_addr'
    elif name == 'ip_protocol':
      name = 'Protocol'
    elif name == 'ip_port':
      name = 'Port'
    elif name == 'description':
      name = 'comment'
    elif name == 'analysis_free_text':
      name = 'comment'
    elif 'named_pipe' in name:
      name = 'Pipe_Name'
    elif name == 'domain':
      name = 'DomainName_Value'
    elif name == 'http_method':
      name = 'HTTP_Method'
    chksum = line['chksum']
    for definition in self.attr_defs:
      if name == definition.name:
        return definition
    raise Exception(u'Attribtue Definition {0} with chksum {1} not found in new setup'.format(name, chksum))

  def map_attribute(self, line, obj, owner):
    if obj.definition.name == 'email':
      if line['definition']['name'] == 'raw_file' or line['definition']['name'] == 'file_name' or line['definition']['name'] == 'email_server':
        return None
    if obj.definition.name == 'Code':
      if line['definition']['name'] == 'hash_sha1':
        return None

    attribute = Attribute()
    id_ = line['uuid']
    if id_ in self.seen_attribtues_uuids:
      id_ = uuid4()

    self.seen_attribtues_uuids.append(id_)
    attribute.identifier = id_
    set_db_code(attribute, line['dbcode'])

    self.seen_attributes[line['identifier']] = attribute

    attribute.creator_group = self.get_groups()[line['creator_group_id']]
    attribute.creator_group_id = attribute.creator_group.identifier
    attribute.creator = self.get_users()[line['creator_id']]
    attribute.creator_id = attribute.creator.identifier
    attribute.created_at = convert_date(line['created'])
    attribute.modified_on = convert_date(line['modified'])

    modifier_id = line.get('modifier_id')
    if modifier_id:
      modifier = self.get_users()[modifier_id]
    else:
      modifier = obj.creator
    attribute.is_ioc = line['ioc'] == 1 or line['ioc'] == '1'
    attribute.modifier = modifier
    attribute.modifier_id = obj.modifier.identifier
    attribute.originating_group = attribute.creator_group
    attribute.originating_group_id = attribute.creator_group.identifier
    parent_id = line['attr_parent_id']
    if parent_id:
      parent = self.seen_attributes.get(parent_id, None)
      # TODO: To check this again!
      if parent:
        parent.children.append(attribute)

    try:
      if 'pattern' in line['definition']['name']:
        line['definition']['name'] = line['definition']['name'].replace('_pattern', '')
        attribute.condition = self.map_condition('FitsPattern')
      else:
        attribute.condition = self.map_condition('Equals')
      definition = self.map_attr_def(line['definition'])
    except Exception as error:
      raise error
    if definition:
      attribute.definition = definition
    else:
      self.notmapped.write('Attribute Could not be mapped as definition is missing for the new object {0}\n'.format(obj.identifier))
      self.notmapped.write('{0}\n'.format(json.dumps(line)))
      return None

    attribute.object = obj
    attribute.object_id = attribute.object.identifier

    attribute.value = line['value']
    if not attribute.value:
      raise Exception('Cannot set Valuen as value was empty')
    if 'c&c' in line['definition']:
      # attach a depricated c&c attribute
      line['uuid'] = '{0}'.format(uuid4())
      line['definition']['name'] = 'is_c&c'
      line['definition']['chksum'] = 0
      line['value'] = 1
      atribute = self.map_attribute(line, obj, owner)
      obj.attributes.append(atribute)

    self.logger.debug('Created attribute {0}'.format(attribute))
    return attribute

  def map_obj_def(self, line):
    name = line['name']
    if 'file' in name:
      name = 'file'
    elif name == 'victim_targeting':
      return None
    elif name == 'user_account':
      name = 'UserAccount'
    chksum = line['chksum']
    found_def = None
    for definition in self.obj_defs:
      if name == definition.name:
        found_def = definition
        break
    if found_def:
      return found_def
    else:
      raise Exception(u'Object Definition {0} with chksum {1} not found in new setup'.format(name, chksum))

  def make_attr_obs(self, line, obj_def, attr_def, owner, event):
    observable = self.make_observable(line, event)
    observable.identifier = uuid4()
    # important to delink them from the event
    observable.event_id = None
    observable.event = None

    obj = self.make_object(line, observable)
    obj.identifier = uuid4()

    line['definition']['name'] = attr_def
    if attr_def == 'ip_port':
      obj.definition = self.map_obj_def({'name': 'SocketAddress', 'chksum': None})
    elif attr_def == 'ip_protocol':
      obj.definition = self.map_obj_def({'name': 'NetworkSocket', 'chksum': None})
    elif attr_def == 'ids_rules':
      value = line['value']
      if 'snort:' in value:
        line['value'] = value.replace('snort:', '')
        obj.definition = self.map_obj_def({'name': 'IDSRule', 'chksum': None})
        line['definition']['name'] = 'snort_rule'
        line['definition']['chksum'] = None
      else:
        raise Exception('Uknown ids system {0}'.format(value))

    elif attr_def == 'yara_rule':
      obj.definition = self.map_obj_def({'name': 'IDSRule', 'chksum': None})

    else:
      obj.definition = self.map_obj_def({'name': obj_def, 'chksum': None})

    if not obj.definition:
      self.notmapped.write('{0} could not be mapped\n'.format(obj_def))
      self.notmapped.write('{0}\n'.format(json.dumps(line)))
      return None

    attribute = self.map_attribute(line, obj, owner)
    if attribute:
      obj.attributes.append(attribute)
    else:
      raise Exception('Attribute could not be mapped')

    # make additional attributes
    if attr_def == 'hostname':
      line['definition']['name'] = 'Naming_System'
      line['definition']['chksum'] = None
      line['uuid'] = u'{0}'.format(uuid4())
      line['value'] = 'DNS'
      attribute = self.map_attribute(line, obj, owner)
      if attribute:
        obj.attributes.append(attribute)
      else:
        raise Exception('No attributes were mapped')
    elif 'url' in attr_def:
      line['definition']['name'] = 'URIType'
      line['definition']['chksum'] = None
      line['uuid'] = u'{0}'.format(uuid4())
      line['value'] = 'URL'
      attribute = self.map_attribute(line, obj, owner)
      if attribute:
        obj.attributes.append(attribute)
      else:
        raise Exception('No attributes were mapped')
    if obj.attributes.count() > 0:
      observable.object = obj

      return observable
    else:
      raise Exception('No attributes were mapped')

  def map_observable_composition(self, array_items, line, owner, event, title=None):
    result_observable = self.make_observable(line, event)
    result_observable.identifier = uuid4()
    if title:
      result_observable.title = 'Indicators for "{0}"'.format(title)
    composed_attribute = ObservableComposition()
    composed_attribute.identifier = uuid4()
    set_db_code(composed_attribute, line['dbcode'])

    composed_attribute.parent_id = result_observable.identifier
    composed_attribute.parent = result_observable

    report = None
    for attribute in array_items:
      name = attribute['definition']['name']
      if 'domain' in name:
        obs = self.make_attr_obs(attribute, 'DomainName', 'domain', owner, event)
        composed_attribute.observables.append(obs)
      elif 'hostname'in name:
        obs = self.make_attr_obs(attribute, 'Hostname', 'Hostname_Value', owner, event)
        composed_attribute.observables.append(obs)
      elif 'ip' in name:
        obs = self.make_attr_obs(attribute, 'Address', name, owner, event)
        composed_attribute.observables.append(obs)
      elif 'file' in name:
        obs = self.make_attr_obs(attribute, 'file', name, owner, event)
        composed_attribute.observables.append(obs)
      elif 'email' in name:
        obs = self.make_attr_obs(attribute, 'email', name, owner, event)
        composed_attribute.observables.append(obs)
      elif 'comment' in name:
        self.notmapped.write('IOC Record comment could not be created the new event {0} and composed attribute {1}\n'.format(event.identifier, composed_attribute.identifier))
        self.notmapped.write('{0}\n'.format(json.dumps(attribute)))
      elif 'hash' in name:
        obs = self.make_attr_obs(attribute, 'file', name, owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'encryption_key':
        self.notmapped.write('{0} could not be mapped for ioc_redords on new composed observable {1}\n'.format(name, composed_attribute.identifier))
        self.notmapped.write('{0}\n'.format(json.dumps(attribute)))
      elif name == 'ids_rules':
        obs = self.make_attr_obs(attribute, 'IDSRule', name, owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'analysis_free_text':
        if not report:
          report = self.make_report(attribute, owner, event)
          report.description = ''
        report.description = report.description + '\n' + attribute['value']
        event.reports.append(report)
      elif name == 'yara_rule':
        obs = self.make_attr_obs(attribute, 'IDSRule', name, owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'reference_free_text':
        if not report:
          report = self.make_report(attribute, owner, event)
          report.description = ''
        report.description = report.description + '\n' + attribute['value']
        event.reports.append(report)
      elif 'http' in name:
        obs = self.make_attr_obs(attribute, 'HTTPSession', name, owner, event)
        composed_attribute.observables.append(obs)
      elif 'traffic_content' in name:
        obs = self.make_attr_obs(attribute, 'forensic_records', 'traffic_content', owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'memory_pattern':
        obs = self.make_attr_obs(attribute, 'Memory', name, owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'mutex':
        obs = self.make_attr_obs(attribute, 'Mutex', 'Mutex_name', owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'win_registry_key':
        value = attribute['value']
        value = value.replace('/', '\\')
        pos = value.find("\\")
        key = value[pos + 1:]
        hive = value[0:pos]
        if hive == 'HKLM' or 'HKEY_LOCAL_MACHINE' in hive:
          hive = 'HKEY_LOCAL_MACHINE'
        elif hive == 'HKCU' or 'HKEY_CURRENT_USER' in hive or hive == 'HCKU':
          hive = 'HKEY_CURRENT_USER'
        elif hive == 'HKEY_CURRENTUSER':
          hive = 'HKEY_CURRENT_USER'
        elif hive == 'HKCR':
          hive = 'HKEY_CLASSES_ROOT'
        else:
          if hive[0:1] == 'H' and hive != 'HKCU_Classes':
            raise Exception('"{0}" not defined'.format(hive))
          else:
            hive = None
        observable = self.make_observable(attribute, event)
        obj = self.make_object(attribute, observable)
        observable.object = obj
        definition = self.map_obj_def({'name': 'WindowsRegistryKey', 'chksum': None})
        obj.definition = definition
        if hive:
          attribute['definition']['name'] = 'WindowsRegistryKey_Hive'
          attribute['value'] = hive
          new_attribute = self.map_attribute(attribute, obj, owner)
          obj.attributes.append(new_attribute)

        attribute['definition']['name'] = 'WindowsRegistryKey_Key'
        attribute['value'] = key
        new_attribute = self.map_attribute(attribute, obj, owner)
        obj.attributes.append(new_attribute)

        composed_attribute.observables.append(observable)
      elif name == 'vulnerability_cve':
        obs = self.make_attr_obs(attribute, 'file', name, owner, event)
        composed_attribute.observables.append(obs)
      elif 'targeted' in name:
        self.notmapped.write('{0} could not be mapped for ioc_redords on new composed observable {1}\n'.format(name, composed_attribute.identifier))
        self.notmapped.write('{0}\n'.format(json.dumps(attribute)))
      elif 'observable_location' in name:
        self.notmapped.write('{0} could not be mapped for ioc_redords on new composed observable {1}\n'.format(name, composed_attribute.identifier))
        self.notmapped.write('{0}\n'.format(json.dumps(attribute)))
      elif 'password' in name:
        self.notmapped.write('{0} could not be mapped for ioc_redords on new composed observable {1}\n'.format(name, composed_attribute.identifier))
        self.notmapped.write('{0}\n'.format(json.dumps(attribute)))
      elif 'traffic_content' in name:
        obs = self.make_attr_obs(attribute, 'forensic_records', 'traffic_content', owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'url':
        obs = self.make_attr_obs(attribute, 'URI', name, owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'url_path':
        # make pattern out of it
        attribute['value'] = u'*{0}'.format(attribute['value'])
        attribute['uuid'] = u'{0}'.format(uuid4())
        attribute['definition']['name'] = 'url_pattern'
        attribute['definition']['chksum'] = None
        obs = self.make_attr_obs(attribute, 'URI', attribute['definition']['name'], owner, event)
        composed_attribute.observables.append(obs)
      elif name == 'url_pattern':
        obs = self.make_attr_obs(attribute, 'URI', name, owner, event)
        composed_attribute.observables.append(obs)
      else:
        raise Exception('Mapping for {0} is not defined'.format(name))

    if composed_attribute.observables.count() == 1:
      composed_attribute.observables[0].event = event
      composed_attribute.observables[0].event_id = event.identifier
      return composed_attribute.observables[0]

    elif composed_attribute.observables.count() > 1:
      result_observable.observable_composition = composed_attribute
      return result_observable
    else:
      return None

  def get_indicator_type(self, indicator_type):
    for type_ in self.types:
      if type_.name == indicator_type:
        return type_
    raise Exception('Type "{0}" is not defined'.format(indicator_type))

  def map_indicator(self, observable, line, indicator_type, event):
    indicator = Indicator()
    indicator.identifier = uuid4()
    indicator.creator_group = observable.creator_group
    indicator.creator_group_id = indicator.creator_group.identifier
    indicator.creator = observable.creator
    indicator.creator_id = indicator.creator.identifier
    indicator.modifier = observable.creator
    indicator.modifier_id = indicator.modifier.identifier
    indicator.originating_group = indicator.creator_group
    indicator.originating_group_id = indicator.creator_group.identifier

    indicator.event = event
    indicator.event_id = event.identifier

    if indicator_type:
      indicator.type_ .append(self.get_indicator_type(indicator_type))

    new_observable = clone_observable(observable)
    if new_observable:
      indicator.observables.append(new_observable)
    else:
      return None
    indicator.created_at = observable.created_at
    indicator.modified_on = observable.modified_on
    return indicator

  def map_ioc_records(self, line, owner, parent_observable, event):
    attributes = line['attributes']
    # sort attributes first
    mal_email = list()
    ips = list()
    file_hashes = list()
    domains = list()
    urls = list()
    artifacts = list()
    c2s = list()
    others = list()
    for attribute in attributes:
      name = attribute['definition']['name']
      if 'raw' in name:
        artifacts.append(attribute)
      elif 'c&c' in name:
        c2s.append(attribute)
      elif 'ipv' in name:
        ips.append(attribute)
      elif 'hash' in name:
        file_hashes.append(attribute)
      elif 'email' in name:
        mal_email.append(attribute)
      elif 'domain' in name or 'hostname' in name:
        domains.append(attribute)
      elif 'url' in name:
        urls.append(attribute)
      else:
        others.append(attribute)

    result_observables = list()

    if mal_email:
      observable = self.map_observable_composition(mal_email, line, owner, event, 'Malicious E-mail')
      if observable:

        indicator = self.map_indicator(observable, line, 'Malicious E-mail', event)
        result_observables.append(observable)
        del mal_email[:]
        if indicator:
          event.indicators.append(indicator)

    if artifacts:
      observable = self.map_observable_composition(artifacts, line, owner, event, 'Malware Artifacts')
      if observable:
        indicator = self.map_indicator(observable, line, 'Malware Artifacts', event)
        del artifacts[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if ips:
      observable = self.map_observable_composition(ips, line, owner, event, 'IP Watchlist')
      if observable:
        indicator = self.map_indicator(observable, line, 'IP Watchlist', event)
        del ips[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if file_hashes:
      observable = self.map_observable_composition(file_hashes, line, owner, event, 'File Hash Watchlist')
      if observable:
        indicator = self.map_indicator(observable, line, 'File Hash Watchlist', event)
        del file_hashes[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if domains:
      observable = self.map_observable_composition(domains, line, owner, event, 'Domain Watchlist')
      if observable:
        indicator = self.map_indicator(observable, line, 'Domain Watchlist', event)
        del domains[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if c2s:
      observable = self.map_observable_composition(c2s, line, owner, event, 'C2')
      if observable:
        indicator = self.map_indicator(observable, line, 'C2', event)
        del c2s[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if urls:
      observable = self.map_observable_composition(urls, line, owner, event, 'URL Watchlist')
      if observable:
        indicator = self.map_indicator(observable, line, 'URL Watchlist', event)
        del urls[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if others:
      observable = self.map_observable_composition(others, line, owner, event, 'Others')
      if observable:
        indicator = self.map_indicator(observable, line, None, event)
        del others[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    return result_observables

  def map_malicious_website(self, line, owner, event):
    observable = self.make_observable(line, event)
    observable.title = 'Malicious website'
    observable.identifier = line['uuid']

    composed_attribute = ObservableComposition()
    composed_attribute.identifier = uuid4()
    set_db_code(composed_attribute, line['dbcode'])

    composed_attribute.parent_id = observable.identifier
    composed_attribute.parent = observable

    attributes = line['attributes']
    for attribtue in attributes:
      name = attribtue['definition']['name']
      if name == 'description':
        if not observable.description:
          observable.description = ''
        observable.description = observable.description + ' ' + attribtue['value']
      elif name == 'url' or name == 'reference_url':
        attribute = self.make_attr_obs(attribtue, 'URI', name, owner, event)
        composed_attribute.observables.append(attribute)
      elif name == 'url_path':
        # make pattern out of it
        attribute['value'] = u'*{0}'.format(attribute['value'])
        attribute['uuid'] = u'{0}'.format(uuid4())
        attribute['definition']['name'] = 'url_pattern'
        attribute['definition']['chksum'] = None
        attribute = self.make_attr_obs(attribtue, 'URI', name, owner, event)
        composed_attribute.observables.append(attribute)
      elif name == 'hostname':
        attribute = self.make_attr_obs(attribtue, 'Hostname', 'Hostname_Value', owner, event)
        composed_attribute.observables.append(attribute)
      elif name == 'ipv4_addr':
        attribute = self.make_attr_obs(attribtue, 'Address', name, owner, event)
        composed_attribute.observables.append(attribute)
      else:
        raise Exception(name)

  def map_cybox(self, line, owner, observable, event):

    obj = self.make_object(line, observable)
    if line['definition']['name'] == 'network_traffic':
      # Most these are pcaps hence building a file with a raw atrifact.
      # the definition of this object is file
      definition = self.map_obj_def({'name': 'file', 'chksum': None})
      obj.definition = definition
      # set attributes for filename etc
      attribute_line = None
      for element in line['attributes']:
        if element['definition']['name'] == 'file_name':
          attribute_line = element
          break

      # remove the assigned attributes from the object
      line['attributes'].remove(attribute_line)

      attribtue = self.map_attribute(attribute_line, obj, owner)
      obj.attributes.append(attribtue)

      # then attach the raw artifact
      raw_artifact = self.make_object(line, observable)
      raw_artifact.identifier = uuid4()
      raw_artifact.definition = self.map_obj_def({'name': 'Artifact', 'chksum': None})
      # set attributes for type and data
      attribute_line = None
      for element in line['attributes']:
        if element['definition']['name'] == 'raw_pcap_file':
          attribute_line = element
          break
      line['attributes'].remove(attribute_line)
      attribute_line['definition']['name'] = 'raw_artifact'
      attribtue = self.map_attribute(attribute_line, raw_artifact, owner)
      raw_artifact.attributes.append(attribtue)
      # set the type
      attribute_line['uuid'] = u'{0}'.format(uuid4())
      attribute_line['definition']['name'] = 'artifact_type'
      attribute_line['value'] = 'Network Traffic'
      attribtue = self.map_attribute(attribute_line, raw_artifact, owner)
      raw_artifact.attributes.append(attribtue)

      # attach the object
      obj.related_objects.append(create_related_obj(obj, raw_artifact))

      pass
    elif 'file' in line['definition']['name']:

      definition = self.map_obj_def({'name': 'file', 'chksum': None})
      obj.definition = definition

      attribute_line = None
      for element in line['attributes']:
        if element['definition']['name'] == 'raw_file' or element['definition']['name'] == 'raw_document_file':
          if attribute_line:
            # there are 2 attributes with raw file -> impossible to determine hat is what
            self.notmapped.write('{0} could not be mapped for file on new object {1} as it contains 2 files\n'.format(line['definition']['name'], obj.identifier))
            self.notmapped.write('{0}\n'.format(json.dumps(line)))
            return None
          else:
            attribute_line = element

      if attribute_line:
        line['attributes'].remove(attribute_line)
        # do the artifact
        # then attach the raw artifact
        raw_artifact = self.make_object(line, observable)
        raw_artifact.identifier = uuid4()
        raw_artifact.definition = self.map_obj_def({'name': 'Artifact', 'chksum': None})

        attribute_line['definition']['name'] = 'raw_artifact'
        attribtue = self.map_attribute(attribute_line, raw_artifact, owner)
        raw_artifact.attributes.append(attribtue)
        # set the type
        attribute_line['definition']['name'] = 'artifact_type'
        attribute_line['value'] = 'File'
        attribute_line['uuid'] = uuid4()
        attribtue = self.map_attribute(attribute_line, raw_artifact, owner)
        raw_artifact.attributes.append(attribtue)

        # append to the object
        obj.related_objects.append(create_related_obj(obj, raw_artifact))
    elif line['definition']['name'] == 'source_code':

      definition = self.map_obj_def({'name': 'Code', 'chksum': None})
      obj.definition = definition

      attribute_hash = None
      attribute_file = None
      attribute_file_name = None
      for element in line['attributes']:
        if element['definition']['name'] == 'raw_file' or element['definition']['name'] == 'raw_document_file':
          attribute_file = element
        elif element['definition']['name'] == 'file_name':
          attribute_file_name = element
        elif element['definition']['name'] == 'hash_sha1':
          attribute_hash = element

      file_obj = self.make_object(line, observable)
      file_obj.identifier = uuid4()
      file_obj.definition = self.map_obj_def({'name': 'file', 'chksum': None})
      if attribute_hash:
        line['attributes'].remove(attribute_hash)
        attribtue = self.map_attribute(attribute_hash, file_obj, owner)
        file_obj.attributes.append(attribtue)
      if attribute_file_name:
        line['attributes'].remove(attribute_file_name)
        attribtue = self.map_attribute(attribute_file_name, file_obj, owner)
        file_obj.attributes.append(attribtue)
      # append to the object
      obj.related_objects.append(create_related_obj(obj, file_obj))

      if attribute_file:
        line['attributes'].remove(attribute_file)
        # do the artifact
        # then attach the raw artifact
        raw_artifact = self.make_object(line, observable)
        raw_artifact.identifier = uuid4()
        raw_artifact.definition = self.map_obj_def({'name': 'Artifact', 'chksum': None})

        attribute_file['definition']['name'] = 'raw_artifact'
        attribtue = self.map_attribute(attribute_file, raw_artifact, owner)
        raw_artifact.attributes.append(attribtue)
        # set the type
        attribute_file['definition']['name'] = 'artifact_type'
        attribute_file['value'] = 'File'
        attribute_file['uuid'] = uuid4()
        attribtue = self.map_attribute(attribute_file, raw_artifact, owner)
        raw_artifact.attributes.append(attribtue)

        # append to the object
        file_obj.related_objects.append(create_related_obj(file_obj, raw_artifact))
    else:
      definition = self.map_obj_def(line['definition'])
      if definition:
        obj.definition = definition
      else:
        self.notmapped.write('Object Could not be mapped as definition is missing for the new observable {0}\n'.format(observable.identifier))
        self.notmapped.write('{0}\n'.format(json.dumps(line)))
        return None
        # set attributes
    for attribute in line['attributes']:
      attribute = self.map_attribute(attribute, obj, owner)
      if attribute:
        obj.attributes.append(attribute)

    if line.get('children'):
      for child in line['children']:
        mapped = None
        if child['definition']['name'] == 'ioc_records':
            # TODO map ioc records
            mapped = self.map_ioc_records(child, owner, observable, event)
            for obs in mapped:
              # attach this one as related observable to the parent observable
              observable.related_observables.append(create_related_observable(observable, obs))

            # -> composed observable
        elif 'reference' in child['definition']['name']:
          report = self.map_report(child, event.creator, event)
          if report:
            event.reports.append(report)
        else:
          mapped = self.map_cybox(child, owner, observable, event)
          if mapped:
            if mapped.identifier == obj.identifier:
              mapped.identifier = uuid4()
            related_object = create_related_obj(obj, mapped)
            obj.related_objects.append(related_object)
          pass
    self.logger.debug('Created object {0}'.format(obj))
    return obj

  def map_ce1sus_object(self, parent, line, owner, event):
    definition = line['definition']
    if ['name'] == 'user_account':
      result_observable = self.make_observable(line, event)
      result_observable.identifier = uuid4()

      composed_attribute = ObservableComposition()
      composed_attribute.uuid = line['uuid']
      set_db_code(composed_attribute, line['dbcode'])

      composed_attribute.parent_id = result_observable.identifier
      composed_attribute.parent = result_observable

      attributes = line['attributes']
      # create for each a single entry
      for attribute in attributes:
        observable = self.make_observable(attribute, event)
        observable.identifier = uuid4()

        obj = self.make_object(line, observable)
        definition = self.map_obj_def({'name': 'UserAccount', 'chksum': None})
        attribtue = self.map_attribute(attribute, obj, owner)
        obj.attributes.append(attribtue)
        observable.object = obj
        composed_attribute.observables.append(observable)
      result_observable.observable_composition = composed_attribute
      return result_observable
    elif definition['name'] == 'ioc_records':

      result = self.map_ioc_records(line, owner, None, event)
      if result:
        return result

      # -> composed observable
    elif definition['name'] == 'malicious_website':
      result = self.map_malicious_website(line, owner, event)
      if result:
        return result
      # -> composed observable
    else:

      observable = self.make_observable(line, event)
      observable.identifier = uuid4()

      obj = self.map_cybox(line, owner, observable, event)
      if obj:
        observable.object = obj

        return observable

    self.notmapped.write('Observable could not be created the new event {0}\n'.format(event.identifier))
    self.notmapped.write('{0}\n'.format(json.dumps(line)))
    return None

  def map_event(self, line):
    event = Event()
    event.identifier = line['uuid']
    event.status_id = line['status_id']
    event.description = line['description']
    event.analysis_id = line['analysis_status_id']

    event.creator_group = self.get_groups()[line['creator_group_id']]
    event.creator_group_id = event.creator_group.identifier
    event.creator = self.get_users()[line['creator_id']]
    event.creator_id = event.creator.identifier
    set_db_code(event, line['dbcode'])

    event.properties.is_shareable = line['published'] == 1 or line['published'] == '1'
    event.risk_id = line['risk_id']
    event.title = line['title']
    event.modifier = self.get_users()[line['modifier_id']]
    event.modifier_id = event.modifier.identifier
    event.tlp_level_id = line['tlp_level_id']

    event.originating_group = event.creator_group
    event.originating_group_id = event.creator_group.identifier

    for group in line['maingroups']:
      event.groups.append(self.map_event_group(group, event.creator))

    for group in line['subgroups']:
      event.groups.append(self.map_event_group(group, event.creator))

    for obj in line['objects']:
      definition = obj['definition']
      if 'reference' in definition['name']:
        # TODO map report
        report = self.map_report(obj, event.creator, event)
        if report:
          event.reports.append(report)
      else:
        observable = self.map_ce1sus_object(None, obj, event.creator, event)
        if observable:
          if isinstance(observable, ListType):
            for obs in observable:
              event.observables.append(obs)
          else:
            event.observables.append(observable)

    event.last_publish_date = convert_date(line['last_publish_date'])

    convert_date(line['first_seen'])
    convert_date(line['last_seen'])

    event.created_at = convert_date(line['created'])
    event.modified_on = convert_date(line['modified'])
    self.logger.debug('Created event {0}'.format(event))
    return event


if __name__ == '__main__':
  migros = Migrator()

  migros.start_groups()
  migros.start_users()

  migros.start_events()

  migros.close()
