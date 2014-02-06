# -*- coding: utf-8 -*-

"""
(Description)

Created on Feb 6, 2014
"""

__author__ = 'Weber Jean-Paul'
__email__ = 'jean-paul.weber@govcert.etat.lu'
__copyright__ = 'Copyright 2013, GOVCERT Luxembourg'
__license__ = 'GPL v3+'

from ce1sus.common.ce1susutils import get_class
from dagr.helpers.debug import Log
from ce1sus.api.restclasses import RestClass, RestEvent, RestObject, RestAttribute, RestObjectDefinition, RestAttributeDefinition
from datetime import datetime
from ce1sus.common.ce1susutils import get_class
from types import DictionaryType, ListType
from dagr.helpers.strings import stringToDateTime, InputException
import ast


class DictConversionException(Exception):
  """Base exception for this class"""
  pass


class DictConverter(object):

  def __init__(self, config):
    self.__config = config
    self.logger = Log(config)

  def _get_logger(self):
    """Returns the class logger"""
    return self.logger.get_logger(self.__class__.__name__)

  def __map_dict_to_object(self, dictionary):
    """ maps dictionary to rest objects"""
    self._get_logger().debug('Start mapping dictionary to object')
    start_time = datetime.now()
    if dictionary:
      classname, contents = self.__get_object_data(dictionary)
      result = self.__populate_classname_by_dict(classname, contents)
    else:
      result = None
    self._get_logger().debug('End mapping dictionary to object. Time elapsed {1}'.format(datetime.now() - start_time))
    return result

  def __get_object_data(self, dictionary):
    """ Returns the classname and the corresponding data"""
    self._get_logger().debug('Decapsulating dictionary to classname and data')
    if len(dictionary) == 1:
      for key, value in dictionary.iteritems():
        self._get_logger().debug('Found class name {0}'.format(key))
        return key, value
    else:
      raise ConversionException('Dictionary is malformed expected one entry got more.')

  def __populate_classname_by_dict(self, classname, dictionary):
    """ Maps the data to the class"""
    self._get_logger().debug('Mapping dictionary to class {0}'.format(classname))
    instance = get_class('ce1sus.api.restclasses', classname)
    if not isinstance(instance, RestClass):
      raise ConversionException(('{0} does not implement RestClass').format(classname))
    self.__populate_instance_by_dict(instance, dictionary)
    return instance

  def __set_dict_value(self, instance, key, value):
    """ Maps sub object"""
    self._get_logger().debug('Mapping sub object for attribute {0}'.format(key))
    subkey, subvalue = self.__get_object_data(value)
    subinstance = self.__populate_classname_by_dict(subkey, subvalue)
    setattr(instance, key, subinstance)

  def __set_list_value(self, instance, key, value):
    """ Maps the list attribute"""
    self._get_logger().debug('Mapping list for attribute {0}'.format(key))
    result = list()
    for item in value:
      subkey, subvalue = self.__get_object_data(item)
      subinstance = self.__populate_classname_by_dict(subkey, subvalue)
      result.append(subinstance)
    setattr(instance, key, result)

  def __populate_atomic_value(self, instance, key, value):
    """ Maps atomic attribute"""
    self._get_logger().debug('Mapping value "{1}" for attribute {0}'.format(key, value))
    if value == '':
      value = None
    else:
      string_value = u'{0}'.format(value)
      # TODO: user json
      if string_value.isdigit():
        value = eval(string_value)
      else:
        try:
          # is it a date?
          value = stringToDateTime(string_value)
        except InputException:
          pass
    setattr(instance, key, value)

  def __populate_instance_by_dict(self, instance, dictionary):
    """populates the instance with the dictinary values"""
    self._get_logger().debug('Populating instance by dictionary')
    for key, value in dictionary.iteritems():
      if isinstance(value, DictionaryType):
        self.__set_dict_value(instance, key, value)
      elif isinstance(value, ListType):
        self.__set_list_value(instance, key, value)
      else:
        self.__populate_atomic_value(instance, key, value)

  def convert_to_rest_obj(self, dictionary):
    """Maps a dictionary to an instance"""
    self._get_logger().debug('Mapping dictionary')
    instance = self.__map_dict_to_object(dictionary)
    return instance

  def convert_to_dict(self, rest_object):
    """converts an rest_object to a dictionary"""
    self._get_logger().debug('Converting {0} to dictionary'.format(rest_object.get_classname()))
    return rest_object.to_dict()