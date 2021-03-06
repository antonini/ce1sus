# -*- coding: utf-8 -*-

"""
(Description)

Created on Feb 20, 2015
"""
from StringIO import StringIO
from copy import deepcopy
from datetime import datetime
from dateutil import parser
import json
from os import makedirs, remove
from os.path import isdir, isfile
import re
import time
import urllib2
from uuid import uuid4
from xml.etree.ElementTree import ParseError
from zipfile import ZipFile

from ce1sus.common.system import APP_REL
from ce1sus.controllers.base import BaseController, ControllerIntegrityException
from ce1sus.controllers.common.process import ProcessController
from ce1sus.db.brokers.definitions.attributedefinitionbroker import AttributeDefinitionBroker
from ce1sus.db.brokers.definitions.conditionbroker import ConditionBroker
from ce1sus.db.brokers.definitions.objectdefinitionbroker import ObjectDefinitionBroker
from ce1sus.db.brokers.definitions.referencesbroker import ReferenceDefintionsBroker
from ce1sus.db.brokers.definitions.typebrokers import IndicatorTypeBroker
from ce1sus.db.brokers.event.eventbroker import EventBroker
from ce1sus.db.brokers.mispbroker import ErrorMispBroker
from ce1sus.db.classes.attribute import Attribute
from ce1sus.db.classes.event import Event
from ce1sus.db.classes.group import Group
from ce1sus.db.classes.indicator import Indicator
from ce1sus.db.classes.log import ErrorMispAttribute
from ce1sus.db.classes.object import Object
from ce1sus.db.classes.observables import Observable, ObservableComposition
from ce1sus.db.classes.processitem import ProcessType
from ce1sus.db.classes.report import Reference, Report
from ce1sus.db.common.broker import BrokerException, NothingFoundException, IntegrityException
from ce1sus.mappers.misp.ce1susmisp import Ce1susMISP
import xml.etree.ElementTree as et


__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013-2014, GOVCERT Luxembourg'
__license__ = 'GPL v3+'


def remove_non_ioc(observable):
    # remove observable from event
  observable.event = None
  observable.event_id = None
  if observable.object:
    iocs = list()
    for attribute in observable.object.attributes:
            # give attribute new uuid
      attribute.uuid = uuid4()
      if attribute.is_ioc:
        iocs.append(attribute)
    if iocs:
      observable.object.attributes = iocs
    else:
      return None
  elif observable.observable_composition:
    result = list()
    for obs in observable.observable_composition.observables:
      ret = remove_non_ioc(obs)
      if ret:
        result.append(ret)
    if result:
      observable.observable_composition.observables = result
    else:
      return None

  if observable.related_observables:
    result = list()
    for related_observable in observable.related_observables:
      ret = remove_non_ioc(related_observable)
      if ret:
        result.append(ret)
    if result:
      observable.related_observables = result
    else:
      return None
  return observable


def clone_observable(observable):
  newobj = deepcopy(observable)
  # remove non ioc objects
  newobj = remove_non_ioc(newobj)
  return newobj


class MispConverterException(Exception):
  pass


class MispMappingException(MispConverterException):
  pass


class MispPushException(MispConverterException):
  pass


class MispConverter(BaseController):

  ce1sus_risk_level = ['High', 'Medium', 'Low', 'None', 'Undefined']
  ce1sus_analysis_level = ['None', 'Opened', 'Stalled', 'Completed', 'Unknown']
  ce1sus_status_level = ['Confirmed', 'Draft', 'Deleted', 'Expired']

  header_tags = ['id', 'org', 'date', 'risk', 'info', 'published', 'uuid', 'attribute_count',
                 'analysis', 'timestamp', 'distribution', 'proposal_email_lock', 'orgc',
                 'locked', 'threat_level_id', 'publish_timestamp'
                 ]

  threat_level_id_map = {'1': 'High',
                         '2': 'Medium',
                         '3': 'Low',
                         '4': 'None',
                         }

  analysis_id_map = {'0': 'Opened',
                     '1': 'Opened',
                     '2': 'Completed',
                     }

  distribution_to_tlp_map = {'0': 'red',
                             '1': 'amber',
                             '2': 'amber',
                             '3': 'green'
                             }

  attribute_tags = ['id', 'type', 'category', 'to_ids', 'uuid', 'event_id', 'distribution', 'timestamp', 'value', 'ShadowAttribute', 'uuid', 'comment']

  def get_api_header_parameters(self):
    return {'Accept': 'application/xml',
            'Authorization': self.api_key,
            'User-Agent': 'ce1sus {0}'.format(APP_REL)}

  def __init__(self, config, api_url, api_key, misp_tag='Generic MISP', session=None):
    BaseController.__init__(self, config, session)
    self.api_url = api_url
    self.api_key = api_key
    self.tag = misp_tag
    self.object_definitions_broker = self.broker_factory(ObjectDefinitionBroker)
    self.attribute_definitions_broker = self.broker_factory(AttributeDefinitionBroker)
    self.reference_definitions_broker = self.broker_factory(ReferenceDefintionsBroker)
    self.indicator_types_broker = self.broker_factory(IndicatorTypeBroker)
    self.condition_broker = self.broker_factory(ConditionBroker)
    self.event_broker = self.broker_factory(EventBroker)
    self.error_broker = self.broker_factory(ErrorMispBroker)
    self.ce1sus_misp_converter = Ce1susMISP(config, session)
    self.process_controller = ProcessController(config, session)

    self.dump = False
    self.file_location = None

  def set_tlp(self, item, distribution):
    item.tlp = MispConverter.distribution_to_tlp_map[distribution]

  def set_event_header(self, event, rest_event, title_prefix=''):
    event_header = {}
    for h in MispConverter.header_tags:
      e = event.find(h)
      if e is not None and e.tag not in event_header:
        event_header[e.tag] = e.text

        if h == 'threat_level_id':
          event_header['risk'] = MispConverter.threat_level_id_map[e.text]
        elif h == 'analysis':
          event_header['analysis'] = MispConverter.analysis_id_map[e.text]

    if not event_header.get('description', '') == '':
      # it seems to be common practice to specify TLP level in the event description
      m = re.search(r'tlp[\s:\-_]{0,}(red|amber|green|white)', event_header['description'], re.I)
      if m:
        event_header['tlp'] = m.group(1).lower()
    else:
      try:
        event_header['tlp'] = MispConverter.distribution_to_tlp_map[event_header['distribution']]
      except KeyError:
        event_header['tlp'] = 'amber'

    # Populate the event
    event_id = event_header.get('id', '')
    rest_event.uuid = event_header.get('uuid', None)
    if not rest_event.uuid:
      message = 'Cannot find uuid for event {0} generating one'.format(event_id)
      self.logger.warning(message)
      # raise MispMappingException(message)

    rest_event.description = unicode(event_header.get('info', ''))
    rest_event.title = u'{0}Event {1} - {2}'.format(title_prefix, event_id, rest_event.description)
    date = event_header.get('date', None)
    if date:
      rest_event.first_seen = parser.parse(date)
    else:
      rest_event.first_seen = datetime.utcnow()

    rest_event.last_seen = rest_event.first_seen

    date = event_header.get('timestamp', None)
    if date:
      rest_event.modified_on = datetime.utcfromtimestamp(int(date))
    else:
      rest_event.modified_on = datetime.utcnow()

    date = event_header.get('publish_timestamp', None)
    if date:
      rest_event.last_publish_date = datetime.utcfromtimestamp(int(date))
    else:
      rest_event.last_publish_date = datetime.utcnow()

    rest_event.created_at = rest_event.first_seen

    rest_event.tlp = event_header.get('tlp', 'amber')
    rest_event.risk = event_header.get('risk', 'None')
    # event.uuid = event_header.get('uuid', None)

    if rest_event.risk not in MispConverter.ce1sus_risk_level:
      rest_event.risk = 'None'

    rest_event.analysis = event_header.get('analysis', 'None')

    if rest_event.analysis not in MispConverter.ce1sus_analysis_level:
      rest_event.analysis = 'None'

    rest_event.comments = []

    published = event_header.get('published', '1')
    if published == '1':
      rest_event.properties.is_shareable = True
    else:
      rest_event.properties.is_shareable = False
    rest_event.status = u'Confirmed'
    group_name = event_header.get('orgc', None)
    group = self.get_group_by_name(group_name)
    rest_event.originating_group_id = group.identifier
    group_name = event_header.get('org', None)
    group = self.get_group_by_name(group_name)
    rest_event.creator_group_id = group.identifier
    rest_event.modifier_id = self.user.identifier
    rest_event.creator_id = self.user.identifier

    rest_event.properties.is_shareable = True
    rest_event.properties.is_validated = False
    return event_id

  def get_group_by_name(self, name):
    group = None
    try:
      group = self.group_broker.get_by_name(name)
    except NothingFoundException:
      # create it
      group = Group()
      group.name = name
      self.group_broker.insert(group, False, False)
    except BrokerException as error:
      self.logger.error(error)
      raise MispConverterException(error)
    if group:
      return group
    else:
      raise MispConverterException('Error determining group')

  def log_element(self, obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution):
    error = ErrorMispAttribute()
    error.orig_uuid = uuid
    error.category = category
    if event:
      error.event_id = event.identifier
    if obj:
      error.object = obj
    if observable:
      error.observable = observable
    error.misp_id = id_
    error.type_ = type_
    error.value = value
    if ioc == 1:
      error.is_ioc = True
    else:
      error.is_ioc = False
    error.share = share
    error.message = message

    # TODO Find a way to log these elements in the DB

    self.error_broker.insert(error, False)

  def append_attributes(self, obj, observable, id_, category, type_, value, ioc, share, event, uuid, ts, distribution):
    if '|' in type_:
      # it is a composed attribute
      if type_ in ('filename|md5', 'filename|sha1', 'filename|sha256'):
        splitted = type_.split('|')
        if len(splitted) == 2:
          first_type = splitted[0]
          second_type = splitted[1]
          splitted_values = value.split('|')
          first_value = splitted_values[0]
          second_value = splitted_values[1]
          self.append_attributes(obj, observable, id_, category, first_type, first_value, ioc, share, event, None, ts, distribution)
          self.append_attributes(obj, observable, id_, category, second_type, second_value, ioc, share, event, None, ts, distribution)
        else:
          message = 'Composed attribute {0} splits into more than 2 elements'.format(type_)
          self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
          # raise MispMappingException(message)
          return None
      else:
        message = 'Composed attribute {0} cannot be mapped'.format(type_)
        self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
        # raise MispMappingException(message)
        return None

    elif type_ == 'regkey':
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
      elif hive in ['HKCR', 'HKEY_CLASSES_ROOT']:
        hive = 'HKEY_CLASSES_ROOT'
      else:
        if hive[0:1] == 'H' and hive != 'HKCU_Classes':
          message = '"{0}" not defined'.format(hive)
          self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
          # raise MispMappingException(message)
          return None
        else:
          hive = None

      if hive:
        # TODO link hive
        self.append_attributes(obj, observable, id_, category, 'WindowsRegistryKey_Hive', hive, ioc, share, event, None, ts, distribution)
      self.append_attributes(obj, observable, id_, category, 'WindowsRegistryKey_Key', key, ioc, share, event, None, ts, distribution)

    elif category in ['external analysis', 'artifacts dropped', 'payload delivery'] and type_ == 'malware-sample':
      filename = value

      splitted = value.split('|')
      if len(splitted) == 2:
        first_type = 'file_name'

        first_value = splitted[0]
        filename = first_value
        second_value = splitted[1]
        second_type = self.get_hash_type(obj, observable, id_, category, type_, ioc, share, event, uuid, second_value, distribution)
        # TODO link filename and hash
        self.append_attributes(obj, observable, id_, category, first_type, first_value, ioc, share, event, None, ts, distribution)
        self.append_attributes(obj, observable, id_, category, second_type, second_value, ioc, share, event, None, ts, distribution)
      else:
        message = 'Composed attribute {0} splits into more than 2 elements'.format(type_)
        self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
        # raise MispMappingException(message)

      # Download the attachment if it exists
      data = self.fetch_attachment(id_, uuid, event.uuid, filename)
      if data:

        message = u'Downloaded file "{0}" id:{1}'.format(filename, id_)
        self.logger.info(message)
        # build raw_artifact
        raw_artifact = Object()
        self.set_tlp(raw_artifact, distribution)
        self.set_properties(raw_artifact, share)
        self.set_extended_logging(raw_artifact, event, ts)
        raw_artifact.definition = self.get_object_definition(obj, observable, id_, ioc, share, event, uuid, 'Artifact', None, None, distribution)
        if raw_artifact.definition:
          raw_artifact.definition_id = raw_artifact.definition.identifier
        else:
          message = 'Could not find object definition Artifact'
          self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
          # raise MispMappingException(message)
          return None

        # add raw artifact
        attr = Attribute()
        self.set_tlp(attr, distribution)
        attr.definition = self.get_attibute_definition(id_, ioc, share, event, uuid, '', 'raw_artifact', None, raw_artifact, observable, attr, distribution)
        if attr.definition:
          attr.definition_id = attr.definition.identifier
          attr.value = data
          if attr.validate():
            obj.related_objects.append(raw_artifact)
          else:
            message = 'Value {0} was invalid for {1}'.format(attr.value, attr.definition_id)
            self.logger.error(message)
            self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
            return None

        else:
          message = 'Could not find attribute definition raw_artifact'
          self.logger.error(message)
          self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
          return None
          # raise MispMappingException(message)

      else:
        message = u'Failed to download file "{0}" id:{1}, add manually'.format(filename, id_)
        self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
        self.logger.warning(message)

    else:
      attribute = Attribute()
      self.set_tlp(attribute, distribution)
      attribute.uuid = uuid
      self.set_properties(attribute, share)
      self.set_extended_logging(attribute, event, ts)
      attribute.definition = self.get_attibute_definition(id_, ioc, share, event, uuid, category, type_, value, obj, observable, attribute, distribution)
      if attribute.definition:
        attribute.definition_id = attribute.definition.identifier
        attribute.object = obj
        attribute.object_id = attribute.object.identifier
        attribute.value = value
        if not attribute.validate():
          message = 'Value {0} was invalid for {1}'.format(attribute.value, attribute.definition_id)
          self.logger.error(message)
          self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
          return None
        # foo workaround
        def_name = attribute.definition.name
        attribute.definition = None
        setattr(attribute, 'def_name', def_name)
        if ioc == 1:
          attribute.is_ioc = True
        else:
          attribute.is_ioc = False
        attribute.properties.is_shareable = True

        obj.attributes.append(attribute)

  def get_hash_type(self, obj, observable, id_, category, type_, ioc, share, event, uuid, value, distribution):
    '''Supports md5, sha1, sha-256, sha-384, sha-512'''
    hash_types = {32: 'hash_md5',
                  40: 'hash_sha1',
                  64: 'hash_sha256',
                  96: 'hash_sha384',
                  128: 'hash_sha512',
                  }
    if len(value) in hash_types:
      return hash_types[len(value)]
    else:
      message = 'Cannot map hash {0}'.format(value)
      self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
      return None
      # raise MispMappingException(message)

  def get_object_definition(self, obj, observable, id_, ioc, share, event, uuid, category, type_, value, distribution):
    # compose the correct chksum/name
    chksum = None
    name = None
    if category == 'Artifact':
      name = category
    elif type_ in ['filename|md5', 'filename|sha1', 'filename|sha256', 'md5', 'sha1', 'sha256'] or category in ['antivirus detection']:
      name = 'file'
    elif type_ in ['domain']:
      name = 'DomainName'
    elif type_ in ['email-src', 'email-attachment', 'email-subject', 'email-dst']:
      name = 'email'
    elif category in ['network activity', 'payload delivery']:
      if type_ in ['ip-dst', 'ip-src']:
        name = 'Address'
      elif type_ in ['url']:
        name = 'URI'
      elif type_ in ['hostname']:
        name = 'Hostname'
      elif type_ in ['http-method', 'user-agent']:
        name = 'HTTPSession'
      elif type_ in ['vulnerability', 'malware-sample', 'filename']:
        name = 'file'
      elif type_ == 'pattern-in-traffic':
        name = 'forensic_records'
      elif type_ in ['text', 'as', 'comment']:
        message = u'Category "{0}" Type "{1}" with value "{2}" not mapped map manually'.format(category, type_, value)
        print message
        self.logger.warning(message)
        return None
      elif 'snort' in type_:
        name = 'IDSRule'
    elif category in ['payload type', 'payload installation']:
      name = 'file'
    elif category in ['artifacts dropped']:
      if 'yara' in type_ or 'snort' in type_:
        name = 'IDSRule'
      elif type_ == 'mutex':
        name = 'Mutex'
      elif 'pipe' in type_:
        name = 'Pipe'
      elif type_ in ['text', 'others']:
        message = u'Category "{0}" Type "{1}" with value "{2}" not mapped map manually'.format(category, type_, value)
        print message
        self.logger.warning(message)
        return None
      else:
        name = 'Artifact'
    elif category in ['external analysis']:
      if type_ == 'malware-sample':
        name = 'file'
    elif category in ['persistence mechanism']:
      if type_ == 'regkey':
        name = 'WindowsRegistryKey'
      else:
        message = u'Type "{0}" not defined'.format(type_)
        self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
        # raise MispMappingException()
        return None
    elif category in ['targeting data']:
      message = u'Category "{0}" Type "{1}" with value "{2}" not mapped map manually'.format(category, type_, value)
      self.log_element(obj, observable, id_, category, type_, value, None, share, event, uuid, message, distribution)
      return None
    if name or chksum:
      # search for it
      try:
        definition = self.object_definitions_broker.get_defintion_by_name(name)
        return definition
      except BrokerException as error:
        self.logger.error(error)

        # if here no def was found raise exception
        message = u'No object definition for "{0}"/"{1}" and value "{2}" can be found'.format(category, type_, value)
        self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
        # raise MispMappingException(message)
        return None

  def get_reference_definition(self, ioc, share, event, uuid, category, type_, value, distribution):
    # compose the correct chksum/name
    chksum = None
    name = None
    if category == 'artifacts dropped' and type_ == 'other':
      return None
    elif type_ == 'url':
      name = 'link'
    elif type_ in ['text', 'other']:
      name = 'comment'
    elif type_ == 'attachment':
      name = 'raw_file'
    else:
      name = type_

    if name or chksum:
      # search for it
      try:
        reference_definition = self.reference_definitions_broker.get_definition_by_name(name)
        return reference_definition
      except BrokerException as error:
        self.logger.error(error)
        # if here no def was found raise exception
        message = u'No reference definition for "{0}"/"{1}" and value "{2}" can be found'.format(category, type_, value)
        self.log_element(None, None, None, category, type_, value, ioc, share, event, uuid, message, distribution)
        # raise MispMappingException(message)
        return None

  def get_condition(self, condition):
    try:
      condition = self.condition_broker.get_condition_by_value(condition)
      return condition
    except BrokerException as error:
      self.logger.error(error)
      raise MispMappingException(u'Condition "{0}" is not defined'.format(condition))

  def get_attibute_definition(self, id_, ioc, share, event, uuid, category, type_, value, obj, observable, attribute, distribution):
    # compose the correct chksum/name
    chksum = None
    name = None

    if type_ == 'raw_artifact':
      name = type_

    if 'pattern' in type_:
      condition = self.get_condition('FitsPattern')
    else:
      condition = self.get_condition('Equals')

    attribute.condition_id = condition.identifier
    if category == 'antivirus detection' and type_ == 'text':
      name = 'comment'

    elif type_ == 'pattern-in-file':
      name = 'pattern-in-file'
    elif type_ == 'pattern-in-memory':
      name = 'pattern-in-memory'
    elif type_ in ['md5', 'sha1', 'sha256']:
      name = u'hash_{0}'.format(type_)
    elif type_ in ['filename']:
      name = 'file_name'
    elif type_ == 'filename' and ('\\' in value or '/' in value):
      name = 'file_path'
    elif type_ == 'domain':
      name = 'DomainName_Value'
    elif type_ == 'email-src' or type_ == 'email-dst':
      name = 'email_sender'
    elif type_ == 'email-attachment':
      name = 'email_attachment_file_name'
    elif 'yara' in type_:
      name = 'yara_rule'
    elif 'snort' in type_:
      name = 'snort_rule'
    elif category in ['network activity', 'payload delivery']:
      if type_ in ['ip-dst']:
        name = 'ipv4_addr'
        observable.description = observable.description + ' - ' + 'Destination IP'
      elif type_ in ['ip-src']:
        name = 'ipv4_addr'
        observable.description = observable.description + ' - ' + 'Source IP'
      elif type_ in ['hostname']:
        name = 'Hostname_Value'
      elif type_ in ['url']:
        name = 'url'
        if type_ == 'url' and '://' not in value:
          attribute.condition = self.get_condition('FitsPattern')
      elif type_ == 'http-method':
        name = 'HTTP_Method'
      elif type_ in ['vulnerability']:
        name = 'vulnerability_cve'
      elif type_ in ['user-agent']:
        name = 'User_Agent'
      # Add to the observable the comment destination as in this case only one address will be present in the observable

    # try auto assign
    elif type_ == 'mutex':
      name = 'Mutex_name'
    elif 'pipe' in type_:
      name = 'Pipe_Name'
    elif category == 'artifacts dropped':
      if type_ in ['text']:
        message = u'Category "{0}" Type "{1}" with value "{2}" not mapped map manually'.format(category, type_, value)
        self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
        return None
    elif category == 'payload installation':
      if type_ == 'attachment':
        name = 'file_name'
    if not name:
      name = type_.replace('-', '_').replace(' ', '_')

    definition = self.__find_attr_def(obj, observable, id_, category, type_, value, ioc, share, event, uuid, name, chksum, distribution)

    if definition:
      return definition
    else:
      name = name.title()
      definition = self.__find_attr_def(obj, observable, id_, category, type_, value, ioc, share, event, uuid, name, chksum, distribution)
      if definition:
        return definition
      else:
        message = u'Category "{0}" Type "{1}" with value "{2}" cannot be found'.format(category, type_, value)
        self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
        return None
        # raise MispMappingException(message)

  def __find_attr_def(self, obj, observable, id_, category, type_, value, ioc, share, event, uuid, name, chksum, distribution):
    try:
      definition = self.attribute_definitions_broker.get_defintion_by_name(name)
      return definition
    except BrokerException as error:
      self.logger.error(error)
      # if here no def was found raise exception
      message = u'No attribute definition for "{0}"/"{1}" and value "{2}" can be found "{3}"'.format(category, type_, value, name)
      self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
      return None

  def create_reference(self, uuid, category, type_, value, data, comment, ioc, share, event, ts, distribution):
    reference = Reference()
    self.set_tlp(reference, distribution)
    # TODO map reference
    # reference.identifier = uuid
    reference.uuid = uuid
    definition = self.get_reference_definition(ioc, share, event, uuid, category, type_, value, distribution)
    if definition:
      reference.definition_id = definition.identifier
      reference.value = value

      self.set_extended_logging(reference, event, ts)
      return reference
    else:
      message = u'Category {0} Type {1} with value {2} not mapped map manually'.format(category, type_, value)
      self.log_element(None, None, None, category, type_, value, ioc, share, event, uuid, message, distribution)
      return None

  def create_observable(self, id_, uuid, category, type_, value, data, comment, ioc, share, event, ts, distribution, ignore_uuid=False):
    if (category in ['external analysis', 'internal reference', 'targeting data', 'antivirus detection'] and type_ in ['attachment', 'comment', 'link', 'text', 'url', 'text']) or (category == 'internal reference' and type_ in ['text', 'comment']) or type_ == 'other' or (category == 'attribution' and type_ == 'comment') or category == 'other' or (category == 'antivirus detection' and type_ == 'link'):
      # make a report
      # Create Report it will be just a single one
      reference = self.create_reference(uuid, category, type_, value, data, comment, ioc, share, event, ts, distribution)
      if reference:
        if len(event.reports) == 0:
          report = Report()
          self.set_tlp(report, distribution)
          # report.event = event
          report.event_id = event.identifier

          self.set_extended_logging(report, event, ts)
          if comment:
            if report.description:
              report.description = report.description + ' - ' + comment
            else:
              report.description = comment
          event.reports.append(report)
        event.reports[0].references.append(reference)
    elif category == 'attribution':
      reference = self.create_reference(uuid, category, type_, value, data, comment, ioc, share, event, ts, distribution)
      reference.value = u'Attribution: "{0}"'.format(reference.value)
      if len(event.reports) == 0:
        report = Report()
        self.set_tlp(report, distribution)

        self.set_extended_logging(report, event, ts)
        if comment:
          if report.description:
            report.description = report.description + ' - ' + comment
          else:
            report.description = comment
        event.reports.append(report)
      reference.report = event.reports[0]
      reference.report_id = event.reports[0].identifier
      event.reports[0].references.append(reference)

    else:
      observable = self.make_observable(event, comment, share, distribution, ignore_uuid)
      observable.title = u'MISP: {0}/{1}'.format(category, type_)
      # create object
      obj = Object()
      self.set_tlp(obj, distribution)
      self.set_properties(obj, share)
      self.set_extended_logging(obj, event, ts)
      observable.object = obj
      definition = self.get_object_definition(obj, observable, id_, ioc, share, event, uuid, category, type_, value, distribution)
      if definition:
        obj.definition_id = definition.identifier
        obj.observable = observable
        obj.observable_id = obj.observable.identifier
        # create attribute(s) for object
        self.append_attributes(obj, observable, id_, category, type_, value, ioc, share, event, uuid, ts, distribution)
        if not observable.description:
          observable.description = None
        return observable
      else:
        return None

  def set_properties(self, instance, shared):
    instance.properties.is_proposal = False
    instance.properties.is_rest_instert = True
    instance.properties.is_validated = False
    instance.properties.is_shareable = shared

  def make_observable(self, event, comment, shared, distribution, local_event=None):
    result_observable = Observable()
    self.set_tlp(result_observable, distribution)
    if local_event:
      result_observable.event_id = local_event.identifier
      result_observable.parent_id = local_event.identifier
    else:
      result_observable.event_id = event.identifier
      result_observable.parent_id = event.identifier
    # result_observable.event = event

    # result_observable.parent = event

    if comment is None:
      result_observable.description = ''
    else:
      result_observable.description = comment

    self.set_properties(result_observable, shared)
    # The creator of the result_observable is the creator of the object
    self.set_extended_logging(result_observable, event, datetime.utcnow())

    return result_observable

  def map_observable_composition(self, array, event, title, shared, distribution, local_event=None):
    result_observable = self.make_observable(event, None, True, distribution, local_event)
    if title:
      result_observable.title = 'Indicators for "{0}"'.format(title)
    composed_attribute = ObservableComposition()

    self.set_properties(composed_attribute, shared)
    result_observable.observable_composition = composed_attribute

    for observable in array:
      # remove relation to event as it is in the relation of an composition
      observable.event = None
      observable.event_id = None
      composed_attribute.observables.append(observable)

    return result_observable

  def is_obs_empty(self, observable):
    empty = True
    if observable:
      if observable.object:
        if len(observable.object.attributes) > 0:
          empty = False
      if observable.observable_composition:
        for obs in observable.observable_composition.observables:
          # TODO find a way to determine this
          sub_empty = self.is_obs_empty(obs)
    return empty

  def parse_attributes(self, event, misp_event, local_event=False):

    # make lists
    mal_email = list()
    ips = list()
    file_hashes = list()
    domains = list()
    urls = list()
    artifacts = list()
    c2s = list()
    others = list()
    attrs = misp_event.iter(tag='Attribute')
    for attrib in attrs:
      type_ = ''
      value = ''
      category = ''
      id_ = ''
      data = None
      ioc = 0
      share = 1
      comment = ''
      uuid = None
      distribution = None

      for a in MispConverter.attribute_tags:
        e = attrib.find(a)
        if e is not None:
          if e.tag == 'type':
            type_ = e.text.lower()
          elif e.tag == 'value':
            value = e.text
          elif e.tag == 'to_ids':
            ioc = int(e.text)
          elif e.tag == 'category':
            category = e.text.lower()
          elif e.tag == 'data':
            data = e.text
          elif e.tag == 'id':
            id_ = e.text
          elif e.tag == 'comment':
            comment = e.text
          elif e.tag == 'uuid':
            uuid = e.text
          elif e.tag == 'timestamp':
            ts = e.text
          elif e.tag == 'distribution':
            distribution = e.text
      # ignore empty values:
      if value:
        observable = self.create_observable(id_, uuid, category, type_, value, data, comment, ioc, share, event, ts, distribution, local_event)
        empty = True
        empty = self.is_obs_empty(observable)

        # returns all attributes for all context (i.e. report and normal properties)
        if observable and isinstance(observable, Observable) and not empty:
          obj = observable.object
          attr_def_name = None
          if obj:
            if len(obj.attributes) == 1:
              attr_def_name = obj.attributes[0].def_name
            elif len(obj.attributes) == 2:
              for attr in obj.attributes:
                if 'hash' in attr.def_name:
                  attr_def_name = attr.def_name
                  break
            else:
              attr_def_name = 'SNAFU'
              # raise MispMappingException(message)
          else:
            message = u'Misp Attribute "{0}" defined as "{1}"/"{2}" with value "{3}" resulted in an empty observable'.format(id_, category, type_, value)
            self.log_element(obj, observable, id_, category, type_, value, ioc, share, event, uuid, message, distribution)
            return None
            # raise MispMappingException(message)

          # TODO make sorting via definitions
          if attr_def_name:
            if 'raw' in attr_def_name:
              artifacts.append(observable)
            elif 'c&c' in attr_def_name:
              c2s.append(observable)
            elif 'ipv' in attr_def_name:
              ips.append(observable)
            elif 'hash' in attr_def_name:
              file_hashes.append(observable)
            elif 'email' in attr_def_name:
              mal_email.append(observable)
            elif 'domain' in attr_def_name or 'hostname' in attr_def_name:
              domains.append(observable)
            elif 'url' in attr_def_name:
              urls.append(observable)
            else:
              others.append(observable)
          else:
            others.append(observable)
      else:
        self.logger.warning('Dropped empty attribute')
    result_observables = list()

    if mal_email:
      observable = self.map_observable_composition(mal_email, event, 'Malicious E-mail', share, distribution, local_event)
      if observable:
        indicator = self.map_indicator(observable, 'Malicious E-mail', event)
        result_observables.append(observable)
        del mal_email[:]
        if indicator:
          event.indicators.append(indicator)

    if artifacts:
      observable = self.map_observable_composition(artifacts, event, 'Malware Artifacts', share, distribution, local_event)
      if observable:
        indicator = self.map_indicator(observable, 'Malware Artifacts', event)
        del artifacts[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if ips:
      observable = self.map_observable_composition(ips, event, 'IP Watchlist', share, distribution, local_event)
      if observable:
        indicator = self.map_indicator(observable, 'IP Watchlist', event)
        del ips[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if file_hashes:
      observable = self.map_observable_composition(file_hashes, event, 'File Hash Watchlist', share, distribution, local_event)
      if observable:
        indicator = self.map_indicator(observable, 'File Hash Watchlist', event)
        del file_hashes[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if domains:
      observable = self.map_observable_composition(domains, event, 'Domain Watchlist', share, distribution, local_event)
      if observable:
        indicator = self.map_indicator(observable, 'Domain Watchlist', event)
        del domains[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if c2s:
      observable = self.map_observable_composition(c2s, event, 'C2', share, distribution, local_event)
      if observable:
        indicator = self.map_indicator(observable, 'C2', event)
        del c2s[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if urls:
      observable = self.map_observable_composition(urls, event, 'URL Watchlist', share, distribution, local_event)
      if observable:
        indicator = self.map_indicator(observable, 'URL Watchlist', event)
        del urls[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if others:
      observable = self.map_observable_composition(others, event, 'Others', share, distribution, local_event)
      if observable:
        indicator = self.map_indicator(observable, None, event)
        del others[:]
        result_observables.append(observable)
        if indicator:
          event.indicators.append(indicator)

    if result_observables:
      return result_observables
    else:
      self.logger.warning('Event {0} does not contain attributes. None detected'.format(event.uuid))
      return result_observables

  def __make_single_event_xml(self, xml_event, local_event=None):
    try:
      rest_event = Event()

      event_id = self.set_event_header(xml_event, rest_event)
      if local_event:
        rest_event.identifier = local_event.identifier
      else:
        self.event_broker.insert(rest_event, False)

      observables = self.parse_attributes(rest_event, xml_event, local_event)
      rest_event.observables = observables
      # Append reference

      result = list()

      report = Report()
      report.tlp = 'red'

      self.set_extended_logging(report, rest_event, datetime.utcnow())
      value = u'{0}{1} Event ID {2}'.format('', self.tag, event_id)
      reference = self.create_reference(None, None, 'reference_external_identifier', value, None, None, False, False, rest_event, datetime.utcnow(), '0')
      report.references.append(reference)
      value = u'{0}/events/view/{1}'.format(self.api_url, event_id)
      reference = self.create_reference(None, None, 'link', value, None, None, False, False, rest_event, datetime.utcnow(), '0')
      report.references.append(reference)

      result.append(report)

      # check if there aren't any empty reports

      for event_report in rest_event.reports:
        if event_report.references:
          result.append(event_report)

      rest_event.reports = result
      setattr(rest_event, 'misp_id', event_id)

      return rest_event
    except IntegrityException as error:
      raise ControllerIntegrityException(error)

  def parse_events(self, xml):
    events = xml.iterfind('./Event')
    rest_events = []

    for event in events:
      rest_event = self.__make_single_event_xml(event)

      rest_events.append(rest_event)

    return rest_events

  def set_extended_logging(self, instance, event, ts):

    instance.creator_group_id = event.creator_group_id
    instance.created_at = event.created_at

    try:
      instance.modified_on = datetime.utcfromtimestamp(int(ts))
    except TypeError:
      instance.modified_on = ts
    instance.modifier_id = self.user.identifier
    instance.creator_id = self.user.identifier
    instance.originating_group_id = event.creator_group_id

  def get_xml_event(self, event_id):
    url = '{0}/events/{1}'.format(self.api_url, event_id)

    req = urllib2.Request(url, None, self.get_api_header_parameters())
    xml_string = urllib2.urlopen(req).read()
    return xml_string

  def get_uuid_from_event_xml(self, xml_string):
    try:
      xml = et.fromstring(xml_string)
    except ParseError:
      xml = et.fromstring(xml_string[1:])
      xml = xml[0]
    event_uuid = xml.find('uuid')
    if event_uuid is None:
      event_uuid = xml[0].find('uuid')
      if event_uuid is None:
        raise MispConverterException('Not a MISP XML')
      else:
        return event_uuid.text
    else:
      return event_uuid.text

  def get_event_from_xml(self, xml_string, local_event):
    try:
      xml = et.fromstring(xml_string)
    except ParseError:
      xml = et.fromstring(xml_string[1:])
      xml = xml[0]
    # test if right format
    event_uuid = xml.find('uuid')
    if event_uuid is None:
      event_uuid = xml[0].find('uuid')
      if event_uuid is None:
        raise MispConverterException('Cannot detect xml')
      else:
        xml = xml[0]

    rest_event = self.__make_single_event_xml(xml, local_event)

    # Remove empty reports
    reports = list()
    for report in rest_event.reports:
      if len(report.references) > 0:
        reports.append(report)
    rest_event.reports = reports

    # TODO: Append the group of the misp user with all permissions as he inserted it !?
    return rest_event

  def __get_dump_path(self, base, dirname):
    sub_path = '{0}/{1}/{2}'.format(datetime.now().year,
                                    datetime.now().month,
                                    datetime.now().day)
    if self.file_location:
      path = '{0}/{1}/{2}'.format(base, sub_path, dirname)
      if not isdir(path):
        makedirs(path)
      return path
    else:
      message = 'Dumping of files was activated but no file location was specified'
      self.logger.error(message)
      raise MispConverterException(message)

  def __dump_files(self, dirname, filename, data):
    path = self.__get_dump_path(self.file_location, dirname)
    full_path = '{0}/{1}'.format(path, filename)
    if isfile(full_path):
      remove(full_path)
    f = open(full_path, 'w+')
    f.write(data)
    f.close()

  def get_event(self, event_id):
    print u'Getting event {0} - {1}/events/view/{0}'.format(event_id, self.api_url)
    xml_string = self.get_xml_event(event_id)
    rest_event = self.get_event_from_xml(xml_string)

    if self.dump:
      event_uuid = rest_event.uuid
      self.__dump_files(event_uuid, 'Event-{0}.xml'.format(event_id), xml_string)
    return rest_event

  def map_indicator(self, observable, indicator_type, event):
    indicator = Indicator()

    self.set_extended_logging(indicator, event, datetime.utcnow())

    # indicator.event = event
    indicator.event_id = event.identifier

    if indicator_type:
      indicator.types.append(self.get_indicator_type(indicator_type))

    new_observable = clone_observable(observable)
    if new_observable:
      indicator.observables.append(new_observable)
    else:
      return None

    return indicator

  def __parse_event_list(self, xml_sting):
    try:
      xml = et.fromstring(xml_sting)
    except ParseError:
      xml = et.fromstring(xml_sting[1:])
    event_list = {}

    for event in xml.iter(tag='Event'):
      event_id_element = event.find('id')

      if event_id_element is not None:
        event_id = event_id_element.text
        if event_id not in event_list:
          event_list[event_id] = {}
        else:
          message = 'Event collision, API returned the same event twice, should not happen!'
          self.logger.error(message)
          raise ValueError(message)

        for event_id_element in event:
          event_list[event_id][event_id_element.tag] = event_id_element.text
    return event_list

  def get_index(self, unpublished=False):
    url = '{0}/events/index'.format(self.api_url)
    req = urllib2.Request(url, None, self.get_api_header_parameters())
    xml_sting = urllib2.urlopen(req).read()
    result = dict()
    for event_id, event in self.__parse_event_list(xml_sting).items():
      if event['published'] == '0' and not unpublished:
        continue
      id_ = event_id
      uuid = event['uuid']

      timestamp = datetime.utcfromtimestamp(int(event['timestamp']))
      if id_:
        result[uuid] = (id_, timestamp)

    return result

  def filter_event_push(self, parent, server_details):
    url = '{0}/events/filterEventIdsForPush'.format(self.api_url)
    events = parent.get_all_events(server_details.user)
    result = list()
    for event in events:
      if not parent.is_event_viewable(event, server_details.user):
        continue
      eventdict = dict()
      eventdict['Event'] = dict()
      eventdict['Event']['uuid'] = event.uuid
      eventdict['Event']['id'] = event.identifier
      eventdict['Event']['timestamp'] = int(time.mktime(event.modified_on.timetuple()))
      result.append(eventdict)

    headers = self.get_api_header_parameters()
    headers['Content-Type'] = 'application/json'
    headers['Accept'] = 'application/json'
    headers['Connection'] = 'close'
    content = json.dumps(result)
    headers['Content-Length'] = len(content)

    req = urllib2.Request(url, content, headers)
    xml_sting = urllib2.urlopen(req).read()
    events_to_push = json.loads(xml_sting)
    headers['Content-Type'] = 'application/xml'
    headers['Accept'] = 'application/xml'
    headers['Connection'] = 'close'
    content = json.dumps(result)

    for event_to_push in events_to_push:
      # schedule the events to push

      self.process_controller.create_new_process(ProcessType.PUSH, event_to_push, server_details.user, server_details)

    return 'OK'

  def push_event(self, event_xml):
    url = '{0}/events'.format(self.api_url)
    headers = self.get_api_header_parameters()
    headers['Content-Type'] = 'application/xml'
    headers['Accept'] = 'application/xml'
    headers['Connection'] = 'close'
    headers['Content-Length'] = len(event_xml)
    req = urllib2.Request(url, event_xml, headers)

    try:
      connection = urllib2.urlopen(req)
      if connection.msg == 'OK':
        return True
      else:
        if connection.code == 302:
          # it already exists
          # TODO when the event alredy exists
          # makes something with the url returned in the header
          # ref: https://github.com/MISP/MISP/issues/449
          return True
        else:
          # log error
          response = connection.read()
          raise MispPushException(u'unexpected error occured {0}'.format(response))
    except (urllib2.HTTPError, urllib2.URLError) as error:
      raise MispPushException(error)

  def get_recent_events(self, limit=20, unpublished=False):
    url = '{0}/events/index/sort:date/direction:desc/limit:{1}'.format(self.api_url, limit)

    req = urllib2.Request(url, None, self.get_api_header_parameters())
    xml_sting = urllib2.urlopen(req).read()

    result = list()

    for event_id, event in self.__parse_event_list(xml_sting).items():
      if event['published'] == '0' and not unpublished:
        continue
      event = self.get_event(event_id)
      result.append(event)

    return result

  def fetch_attachment(self, attribute_id, uuid, event_uuid, filename):
    url = '{0}/attributes/download/{1}'.format(self.api_url, attribute_id)
    try:
      result = None
      req = urllib2.Request(url, None, self.get_api_header_parameters())
      resp = urllib2.urlopen(req).read()
      binary = StringIO(resp)
      zip_file = ZipFile(binary)
      zip_file.setpassword('infected'.encode('utf-8'))
      if self.dump:

        path = self.__get_dump_path(self.file_location, event_uuid)
        destination_folder = '{0}/{1}'.format(path, '')
        if not isdir(destination_folder):
          makedirs(destination_folder)
        # save zip file

        f = open('{0}/{1}.zip'.format(destination_folder, filename), 'w+')
        f.write(resp)
        f.close()
        extraction_destination = '{0}/{1}.zip_contents'.format(destination_folder, filename)
        if not isdir(extraction_destination):
          makedirs(extraction_destination)
        # unzip the file
        zip_file.extractall(extraction_destination)

      # do everything in memory
      zipfiles = zip_file.filelist

      for zipfile in zipfiles:
        filename = zipfile.filename
        result = zip_file.read(filename)
        break

      zip_file.close()
      return result
    except urllib2.HTTPError:
      return None

  def get_indicator_type(self, indicator_type):

    try:
      type_ = self.indicator_types_broker.get_type_by_name(indicator_type)
      return type_
    except BrokerException as error:
      self.logger.error(error)
      message = u'Indicator type {0} is not defined'.format(indicator_type)
      self.logger.error(message)
      raise MispMappingException(message)
